"""Backend local do Console A2 + entrega do front React compilado.

    python -m agente_a2.web        # http://127.0.0.1:8000 (só este computador)

Uso exclusivamente local: sem API pública (nada de /executar, /docs ou /openapi.json), acesso
só por 127.0.0.1, token de sessão em toda chamada e dados gravados no banco local
(``dados/interacoes.db``). Detalhes em ``seguranca.py``.
Desenvolvimento do front: ``cd web && npm run dev`` (http://localhost:5173, com proxy para :8000).
"""

from __future__ import annotations

import json
import logging
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import __version__
from ..agente import AgenteA2, criar_agente_a2
from ..config import RAIZ, ConfigA2
from ..guardrails import entrada as g_entrada
from ..interacoes import CATEGORIAS_FEEDBACK, MOTIVOS_FILA, RegistroInteracoes
from ..llm import prompts
from ..rag.catalogo import BASES
from ..rag.ingestao import ingerir_pasta
from .seguranca import Blindagem, novo_token

log = logging.getLogger(__name__)
DIST = RAIZ / "web" / "dist"
FIXTURES = RAIZ / "fixtures" / "a2"


class Contexto:
    """Monta uma vez: config, registro, agente com LLM e agente extrativo (mesmo índice e registro)."""

    def __init__(self) -> None:
        try:
            from dotenv import load_dotenv

            load_dotenv(RAIZ / ".env")
        except ImportError:
            pass
        self.config = ConfigA2()
        self.fuso = ZoneInfo(self.config.fuso)
        self.registro = RegistroInteracoes(self.config.interacoes_db_url, self.config.sal_pseudonimo,
                                           self.config.retencao_dias) if self.config.registrar_interacoes else None
        repo_kwargs: dict[str, Any] = {}
        self.demo = not self.config.database_url
        if self.demo:
            from ..demo import repositorio_demo

            repo_kwargs["repositorio"] = repositorio_demo(self.config.fuso)
        self.agente_llm: AgenteA2 = criar_agente_a2(self.config, registro=self.registro, **repo_kwargs)
        d = self.agente_llm.dep
        self.agente_extrativo = AgenteA2(store=d.recuperador.store, embedder=d.recuperador.embedder,
                                         repositorio=d.repositorio, config=self.config, registro=self.registro)

    def agente(self, usar_llm: bool) -> AgenteA2:
        return self.agente_llm if (usar_llm and self.agente_llm.dep.llm) else self.agente_extrativo

    def hoje(self):
        return datetime.now(self.fuso).date()


_ctx: Contexto | None = None
_ctx_trava = threading.Lock()


def ctx() -> Contexto:
    """Monta o contexto uma única vez, mesmo com várias requisições simultâneas na abertura da página."""
    global _ctx
    if _ctx is None:
        with _ctx_trava:
            if _ctx is None:
                _ctx = Contexto()
    return _ctx


def _registro() -> RegistroInteracoes:
    r = ctx().registro
    if r is None:
        raise HTTPException(409, "Registro de interações desligado (A2_REGISTRAR_INTERACOES=0)")
    return r


TOKEN_SESSAO = novo_token()

# Sem documentação interativa nem esquema publicado: nada da API fica exposto.
app = FastAPI(title="SinergIA · Console A2", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(Blindagem, token=TOKEN_SESSAO)


@app.get("/api/sessao", include_in_schema=False)
def sessao() -> dict:
    """Entrega o token à página do console (legível só pela mesma origem)."""
    return {"token": TOKEN_SESSAO}


# ------------------------------------------------------------------ status e configuração

@app.get("/api/status", tags=["console"])
def status() -> dict:
    c = ctx()
    rec = c.agente_llm.dep.recuperador
    vig = rec.store.bases_vigentes(c.hoje())
    return {
        "versao_a2": __version__,
        "llm": c.agente_llm.dep.llm.nome if c.agente_llm.dep.llm else None,
        "embeddings": rec.embedder.nome,
        "indice": c.config.store,
        "indice_vazio": not vig,
        "bases": [{"slug": b, "nome": BASES[b].nome if b in BASES else b, "titulo": t, "versao": v}
                  for b, (t, v) in vig.items()],
        "registro": c.registro.descricao if c.registro else None,
        "registro_local": c.registro.local if c.registro else None,
        "retencao_dias": c.config.retencao_dias,
        "cadastro": "demonstração" if c.demo else "banco",
        "limiares": {"cosseno": c.config.limiar_cosseno_efetivo(), "bm25": c.config.limiar_bm25,
                     "pontuacao": c.config.limiar_pontuacao, "margem_relativa": c.config.margem_relativa,
                     "peso_vetorial": c.config.peso_vetorial, "top_k": c.config.top_k},
        "exigir_aprovacao": c.config.exigir_aprovacao,
        "rag_reescrita": bool(c.agente_llm.dep.llm_planejador),
        "rag_complemento": c.config.rag_complemento,
        "cache": c.config.cache_respostas,
    }


@app.post("/api/ingerir", tags=["console"])
def ingerir() -> dict:
    c = ctx()
    rec = c.agente_llm.dep.recuperador
    return ingerir_pasta(c.config.pasta_bases, rec.store, rec.embedder)


@app.get("/api/prompt", tags=["console"])
def prompt_atual() -> dict:
    import hashlib

    regras = []
    for tipo, lista in [("injeção", g_entrada._REGRAS_INJECAO), ("crise", g_entrada._REGRAS_CRISE),
                        ("emergência", g_entrada._REGRAS_EMERGENCIA), ("terceiros", g_entrada._REGRAS_TERCEIROS)]:
        regras += [{"tipo": tipo, "regra": n, "peso": p, "padrao": r.pattern[:220]} for n, p, r in lista]
    return {"versao": hashlib.sha256(prompts.SYSTEM.encode()).hexdigest()[:10], "system": prompts.SYSTEM,
            "usuario": prompts.USUARIO, "correcao": prompts.CORRECAO, "regras_entrada": regras,
            "validacoes_saida": [
                "JSON no esquema (resposta, ids_usados, cobertura, sensivel, relato_epi)",
                "IDs citados precisam estar entre os trechos recuperados",
                "Cobertura total/parcial exige ao menos um ID",
                "Todo número da resposta precisa estar na fonte ou na pergunta",
                "Sem vazamento do prompt (tags, nomes de campos, regras)",
                "Sem orientação médica (remédio, dose, diagnóstico)",
                "Sem tom punitivo que não esteja na base",
                "Tamanho entre 15 e o limite configurado; sem markdown",
                "Complemento de conhecimento geral validado à parte: sem números, leis, direitos, regras ou saúde clínica",
                "Fundamentação medida frase a frase contra as fontes citadas (Painel e Fila de melhoria)"]}


@app.get("/api/colaboradores", tags=["console"])
def colaboradores() -> list[dict]:
    c = ctx()
    repo = c.agente_llm.dep.repositorio
    if not c.demo or repo is None:
        return []
    saida = []
    for col in repo.colaboradores.values():
        epis = [e.nome for e in repo.epis_do_cargo(col.id_cargo)] if col.id_cargo else []
        saida.append({"id": col.id_colaborador, "nome": col.nome, "cargo": col.cargo,
                      "jornada": f"{col.jornada_inicio}–{col.jornada_fim}", "epis": epis,
                      "situacao": repo.situacao(col.id_colaborador, c.hoje()).estado})
    return saida


# ------------------------------------------------------------------ chat

class PedidoChat(BaseModel):
    pergunta: str = Field(min_length=1, max_length=4000)
    intencao: str | None = None
    id_colaborador: int = 42
    historico: list[str] = Field(default_factory=list, max_length=10)
    usar_llm: bool = True
    thread_id: str | None = None


def _raio_x(exe) -> dict:
    tel = dict(exe.telemetria or {})
    prompt = tel.get("prompt") or {}
    return {"telemetria": {k: v for k, v in tel.items() if k != "prompt"},
            "prompt": {"system": prompt.get("system"), "usuario": prompt.get("usuario"), "modelo": prompt.get("modelo")},
            "latencia_ms": exe.latencia_ms}


@app.post("/api/chat", tags=["console"])
def chat(p: PedidoChat) -> dict:
    c = ctx()
    agente = c.agente(p.usar_llm)
    idm = f"t-ui-{uuid.uuid4().hex[:10]}"
    tarefa = {
        "protocolo": "sinergia/1", "id_mensagem": idm, "tipo": "TAREFA", "acao": "a2.responder",
        "origem": "A0", "destino": "A2",
        "correlacao": {"id_caso": None, "thread_id": p.thread_id or f"chat-{p.id_colaborador}-ui", "id_tarefa": idm},
        "contexto": {"id_colaborador": p.id_colaborador, "id_empresa": 1, "perfil": "colaborador", "canal": "chat",
                     "data_hora": datetime.now(c.fuso).isoformat(timespec="seconds")},
        "payload": {"pergunta": p.pergunta, "intencao": p.intencao or None,
                    "historico_resumo": " | ".join(p.historico[-3:]) or None},
    }
    exe = agente.executar_detalhado(tarefa, origem="ui")
    return {"id_interacao": exe.id_interacao, "tarefa": tarefa, "resultado": exe.resultado.model_dump(mode="json"),
            "raio_x": _raio_x(exe)}


# ------------------------------------------------------------------ interações e feedback

@app.get("/api/interacoes", tags=["interações"])
def listar(pagina: int = Query(1, ge=1), tamanho: int = Query(25, ge=1, le=200), busca: str | None = None,
           base: str | None = None, status: str | None = None, modo: str | None = None,
           feedback: str | None = None, acao: str | None = None, dias: int | None = None) -> dict:
    return _registro().listar(pagina=pagina, tamanho=tamanho, busca=busca, base=base, status=status, modo=modo,
                              feedback=feedback, acao=acao, dias=dias)


@app.get("/api/interacoes/{id_interacao}", tags=["interações"])
def detalhe(id_interacao: int) -> dict:
    d = _registro().detalhe(id_interacao)
    if d is None:
        raise HTTPException(404, "Interação não encontrada")
    return d


class PedidoFeedback(BaseModel):
    avaliacao: Literal["positivo", "negativo"]
    categoria: str | None = None
    comentario: str | None = Field(default=None, max_length=2000)
    resposta_sugerida: str | None = Field(default=None, max_length=2000)
    base_correta: str | None = None
    autor: str | None = Field(default=None, max_length=80)
    situacao: Literal["aberto", "resolvido"] = "aberto"


@app.post("/api/interacoes/{id_interacao}/feedback", tags=["interações"])
def feedback(id_interacao: int, p: PedidoFeedback) -> dict:
    try:
        return _registro().registrar_feedback(id_interacao, **p.model_dump())
    except KeyError:
        raise HTTPException(404, "Interação não encontrada")
    except ValueError as e:
        raise HTTPException(422, str(e))


class PedidoSituacao(BaseModel):
    situacao: Literal["aberto", "resolvido"]


@app.patch("/api/feedback/{id_feedback}", tags=["interações"])
def atualizar_feedback(id_feedback: int, p: PedidoSituacao) -> dict:
    try:
        return _registro().atualizar_feedback(id_feedback, p.situacao)
    except KeyError:
        raise HTTPException(404, "Feedback não encontrado")


@app.get("/api/feedback/categorias", tags=["interações"])
def categorias() -> dict:
    return {"categorias": CATEGORIAS_FEEDBACK, "motivos_fila": MOTIVOS_FILA}


@app.get("/api/melhoria", tags=["interações"])
def melhoria(motivo: str | None = None, incluir_resolvidas: bool = False) -> dict:
    return _registro().fila_melhoria(motivo=motivo, incluir_resolvidas=incluir_resolvidas)


@app.get("/api/metricas", tags=["interações"])
def metricas(dias: int = Query(30, ge=1, le=365)) -> dict:
    return _registro().metricas(dias)


@app.get("/api/exportar", tags=["interações"])
def exportar(formato: Literal["csv", "jsonl", "dataset", "xlsx"] = "csv", busca: str | None = None, base: str | None = None,
             status: str | None = None, modo: str | None = None, feedback: str | None = None,
             dias: int | None = None) -> Response:
    r = _registro()
    carimbo = datetime.now(ctx().fuso).strftime("%Y%m%d_%H%M")
    if formato == "xlsx":
        import tempfile

        from ..extracao import coletar, perguntas_do_indice, salvar_xlsx

        c = ctx()
        abas = coletar(r, dias=dias, fuso=c.config.fuso,
                       perguntas_bases=perguntas_do_indice(c.agente_llm.dep.recuperador.store, c.hoje()))
        with tempfile.TemporaryDirectory() as tmp:
            corpo = salvar_xlsx(abas, Path(tmp) / "a.xlsx").read_bytes()
        tipo = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        nome = f"a2_analise_{carimbo}.xlsx"
    elif formato == "dataset":
        corpo, tipo, nome = r.exportar_dataset(), "application/x-ndjson", f"a2_dataset_avaliacao_{carimbo}.jsonl"
    else:
        corpo = r.exportar(formato, busca=busca, base=base, status=status, modo=modo, feedback=feedback, dias=dias)
        tipo = "text/csv; charset=utf-8" if formato == "csv" else "application/x-ndjson"
        nome = f"a2_interacoes_{carimbo}.{formato}"
    return Response(corpo, media_type=tipo, headers={"Content-Disposition": f'attachment; filename="{nome}"'})


# ------------------------------------------------------------------ bases, playground, avaliação

@app.get("/api/bases", tags=["bases"])
def bases() -> list[dict]:
    c = ctx()
    trechos = [t for t in c.agente_llm.dep.recuperador.store.trechos_vigentes(c.hoje()) if t.parte == 1]
    saida = []
    for slug, b in BASES.items():
        ts = [t for t in trechos if t.base == slug]
        if not ts:
            continue
        t0 = ts[0]
        saida.append({"slug": slug, "nome": b.nome, "especialista": b.especialista, "titulo": t0.documento_titulo,
                      "versao": t0.documento_versao, "vigencia": t0.vigencia_inicio.isoformat() if t0.vigencia_inicio
                      else None, "aprovacao": t0.aprovacao, "funcionalidades": list(b.funcionalidades),
                      "perguntas": len(ts), "secoes": sorted({t.secao for t in ts}),
                      "oficial": sum(1 for t in ts if "OFICIAL" in t.tipos_fonte),
                      "interno": sum(1 for t in ts if "INTERNO" in t.tipos_fonte)})
    return saida


@app.get("/api/bases/{slug}/perguntas", tags=["bases"])
def perguntas(slug: str) -> list[dict]:
    c = ctx()
    if slug not in BASES:
        raise HTTPException(404, "Base desconhecida")
    ts = [t for t in c.agente_llm.dep.recuperador.store.trechos_vigentes(c.hoje()) if t.base == slug and t.parte == 1]
    return [{"id": t.id_pergunta, "secao": t.secao, "titulo": t.titulo, "variacoes": t.variacoes,
             "variacoes_extras": getattr(t, "variacoes_extras", []) or [],
             "resposta": t.resposta, "fonte": t.fonte, "tipos_fonte": t.tipos_fonte, "ordem": t.ordem,
             "texto_indexado": t.texto_indexado} for t in sorted(ts, key=lambda x: x.ordem)]


@app.get("/api/fixtures", tags=["playground"])
def fixtures() -> list[dict]:
    saida = []
    for f in sorted(FIXTURES.rglob("*.tarefa.json")):
        nome = str(f.relative_to(FIXTURES)).replace("\\", "/").replace(".tarefa.json", "")
        esperado = f.with_name(f.name.replace(".tarefa.json", ".esperado.json"))
        saida.append({"nome": nome, "tarefa": json.loads(f.read_text(encoding="utf-8")),
                      "esperado": json.loads(esperado.read_text(encoding="utf-8")) if esperado.exists() else None})
    return saida


class PedidoTarefa(BaseModel):
    tarefa: dict
    usar_llm: bool = True
    novo_id: bool = True


@app.post("/api/playground", tags=["playground"])
def playground(p: PedidoTarefa) -> dict:
    tarefa = dict(p.tarefa)
    if p.novo_id and "id_mensagem" in tarefa:
        tarefa["id_mensagem"] = f"{tarefa['id_mensagem']}-{uuid.uuid4().hex[:4]}"
    agente = ctx().agente(p.usar_llm)
    exe = agente.executar_detalhado(tarefa, origem="playground")
    return {"id_interacao": exe.id_interacao, "resultado": exe.resultado.model_dump(mode="json"),
            "raio_x": _raio_x(exe)}


@app.post("/api/avaliacao", tags=["avaliação"])
def avaliacao() -> dict:
    from ..avaliacao import avaliar, calibrar

    c = ctx()
    rec = c.agente_llm.dep.recuperador
    rel = avaliar(rec, c.hoje())
    texto = calibrar(rec, c.hoje())
    sugestao = re.search(r"RAG_LIMIAR_COSSENO=([\d.]+)", texto)
    return {"consultas": rel.consultas, "recall_1": rel.recall_1, "recall_3": rel.recall_3,
            "roteamento": rel.roteamento, "fora_aceitas": rel.fora_aceitas, "fora_total": rel.fora_total,
            "erros": [{"consulta": a, "esperado": b, "obtido": o} for a, b, o in rel.erros[:50]],
            "calibracao": texto, "limiar_sugerido": float(sugestao.group(1)) if sugestao else None,
            "limiar_atual": c.config.limiar_cosseno_efetivo()}


# ------------------------------------------------------------------ front compilado (SPA)

if (DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/{caminho:path}", include_in_schema=False)
def spa(caminho: str):
    if caminho.startswith("api/"):
        raise HTTPException(404)
    arquivo = DIST / caminho
    if caminho and arquivo.is_file():
        return FileResponse(arquivo)
    if (DIST / "index.html").exists():
        return FileResponse(DIST / "index.html")
    return PlainTextResponse("Front não compilado. Rode: cd web && npm install && npm run build.", status_code=200)


def _main() -> None:  # python -m agente_a2.web [porta]
    import sys
    import webbrowser

    import uvicorn

    porta = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print("\n  Carregando bases e modelo de embeddings...")
    ctx()   # carrega antes de abrir o navegador
    print(f"\n  Console A2 em http://127.0.0.1:{porta}  (somente este computador · Ctrl+C para parar)\n")
    try:
        webbrowser.open(f"http://127.0.0.1:{porta}")
    except Exception:
        pass
    # Sempre em 127.0.0.1: o console não fica acessível pela rede.
    uvicorn.run(app, host="127.0.0.1", port=porta, log_level="warning", server_header=False, date_header=False)
