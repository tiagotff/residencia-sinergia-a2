"""Registro de interações do A2 para melhoria contínua (prompt, guardrails, busca).

Banco: qualquer URL do SQLAlchemy em ``INTERACOES_DB_URL``.
  * padrão: SQLite em ``dados/interacoes.db`` (arquivo local, sem instalar nada);
  * PostgreSQL: ``postgresql+psycopg://usuario:senha@localhost:5432/sinergia``.
As tabelas são criadas na primeira execução (``a2_interacao``, ``a2_feedback``, ``a2_prompt``).

Privacidade (LGPD) — o que é gravado:
  * a pergunta **já mascarada** pelos guardrails (CPF, CID, e-mail, telefone);
  * o colaborador como **pseudônimo** (HMAC-SHA256 com ``A2_SAL_PSEUDONIMO``), nunca o ID;
  * a TAREFA sem ``registro_inicial`` (nome, matrícula) e o RESULTADO sem ID do colaborador,
    com o primeiro nome substituído por ``[NOME]``;
  * expurgo automático após ``A2_RETENCAO_DIAS`` (padrão 180).

O que se ganha: cada resposta guarda a versão do prompt, o modo (LLM, 2ª tentativa,
extrativo, guardrail, cache), os trechos e notas da busca, as tentativas do LLM com os
motivos de recusa da validação, latência e confiança. Com o feedback humano, isso vira
fila de melhoria e conjunto de avaliação (``exportar_dataset``).
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, delete,
                        func, or_, select)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

log = logging.getLogger(__name__)

CATEGORIAS_FEEDBACK = {
    "resposta_correta": "Resposta correta",
    "resposta_errada": "Resposta errada ou imprecisa",
    "base_errada": "Consultou a base errada",
    "faltou_informacao": "Faltou informação na base",
    "tom_inadequado": "Tom inadequado",
    "guardrail_indevido": "Guardrail bloqueou sem motivo",
    "guardrail_falhou": "Guardrail deveria ter bloqueado",
    "outro": "Outro",
}

# Por que uma interação entra na fila de melhoria
MOTIVOS_FILA = {
    "feedback_negativo": "Feedback negativo",
    "sem_cobertura": "Bases não cobrem a pergunta",
    "llm_recusado": "LLM recusado pela validação",
    "erro_llm": "Falha na chamada ao LLM",
    "guardrail": "Guardrail acionado",
    "baixa_confianca": "Confiança baixa",
    "baixa_fundamentacao": "Resposta pouco apoiada nas fontes",
}


def _agora() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class PromptVersao(Base):
    __tablename__ = "a2_prompt"
    versao: Mapped[str] = mapped_column(String(16), primary_key=True)
    texto: Mapped[str] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)


class Interacao(Base):
    __tablename__ = "a2_interacao"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora, index=True)
    origem: Mapped[str] = mapped_column(String(20), default="api")          # ui | api | cli | playground
    id_mensagem: Mapped[str] = mapped_column(String(80), index=True)
    thread_id: Mapped[str | None] = mapped_column(String(80))
    acao: Mapped[str] = mapped_column(String(40), index=True)
    colaborador: Mapped[str | None] = mapped_column(String(16), index=True)  # pseudônimo
    intencao: Mapped[str | None] = mapped_column(String(40))
    pergunta: Mapped[str | None] = mapped_column(Text)                       # mascarada
    resposta: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), index=True)
    modo: Mapped[str | None] = mapped_column(String(30), index=True)
    base: Mapped[str | None] = mapped_column(String(40), index=True)
    bases: Mapped[list] = mapped_column(JSON, default=list)
    ids_trechos: Mapped[list] = mapped_column(JSON, default=list)
    cobertura: Mapped[str | None] = mapped_column(String(10))
    usou_llm: Mapped[bool] = mapped_column(Boolean, default=False)
    modelo: Mapped[str | None] = mapped_column(String(80))
    confianca: Mapped[float | None] = mapped_column(Float)
    latencia_ms: Mapped[int | None] = mapped_column(Integer)
    tentativas_llm: Mapped[int] = mapped_column(Integer, default=0)
    sensivel: Mapped[bool] = mapped_column(Boolean, default=False)
    id_solicitacao_epi: Mapped[int | None] = mapped_column(Integer)
    motivo: Mapped[str | None] = mapped_column(Text)
    erro: Mapped[str | None] = mapped_column(String(60))
    versao_prompt: Mapped[str | None] = mapped_column(String(16), index=True)
    versao_a2: Mapped[str | None] = mapped_column(String(16))
    versoes_bases: Mapped[dict] = mapped_column(JSON, default=dict)
    telemetria: Mapped[dict] = mapped_column(JSON, default=dict)   # sinais, diag, tentativas, prompt do usuário
    tarefa: Mapped[dict] = mapped_column(JSON, default=dict)
    resultado: Mapped[dict] = mapped_column(JSON, default=dict)
    feedbacks: Mapped[list["Feedback"]] = relationship(back_populates="interacao", cascade="all, delete-orphan",
                                                        order_by="Feedback.criado_em")


class Feedback(Base):
    __tablename__ = "a2_feedback"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_interacao: Mapped[int] = mapped_column(ForeignKey("a2_interacao.id", ondelete="CASCADE"), index=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)
    avaliacao: Mapped[str] = mapped_column(String(10))                 # positivo | negativo
    categoria: Mapped[str | None] = mapped_column(String(30))
    comentario: Mapped[str | None] = mapped_column(Text)
    resposta_sugerida: Mapped[str | None] = mapped_column(Text)
    base_correta: Mapped[str | None] = mapped_column(String(40))
    autor: Mapped[str | None] = mapped_column(String(80))
    situacao: Mapped[str] = mapped_column(String(15), default="aberto")  # aberto | resolvido
    interacao: Mapped[Interacao] = relationship(back_populates="feedbacks")


# ---------------------------------------------------------------------------------------------

def _mascarar_nome(obj: Any, nomes: list[str]) -> Any:
    if not nomes:
        return obj
    texto = json.dumps(obj, ensure_ascii=False)
    for n in nomes:
        texto = re.sub(rf"\b{re.escape(n)}\b", "[NOME]", texto)
    return json.loads(texto)


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:            # SQLite devolve sem fuso
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat(timespec="seconds")


class RegistroInteracoes:
    def __init__(self, url: str, sal: str = "sinergia-dev", retencao_dias: int = 180):
        self.url = url
        if url.startswith("sqlite:///"):
            from pathlib import Path

            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(url, pool_pre_ping=True,
                                    connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
        Base.metadata.create_all(self.engine)
        self._sessao = sessionmaker(self.engine, expire_on_commit=False)
        self._sal = sal.encode()
        self.retencao_dias = retencao_dias
        self.expurgar()

    @property
    def descricao(self) -> str:
        """Tipo do banco e arquivo/servidor, sem usuário nem senha."""
        if self.url.startswith("sqlite"):
            from pathlib import Path

            return f"SQLite local · {Path(self.url.split(':///', 1)[-1]).name}"
        return re.sub(r"//[^@/]*@", "//", self.url.split("?")[0])

    @property
    def local(self) -> bool:
        """True se o banco está nesta máquina (arquivo SQLite ou servidor em localhost)."""
        if self.url.startswith("sqlite"):
            return True
        servidor = re.sub(r"^[^:]+://([^@/]*@)?", "", self.url).split("/")[0].split(":")[0]
        return servidor in {"localhost", "127.0.0.1", "::1", ""}

    # ----------------------------------------------------------------- gravação
    def pseudonimo(self, id_colaborador: int | None) -> str | None:
        if id_colaborador is None:
            return None
        return hmac.new(self._sal, str(id_colaborador).encode(), hashlib.sha256).hexdigest()[:16]

    def _versao_prompt(self, s: Session, system: str | None) -> str | None:
        if not system:
            return None
        # O system muda só pelo "Especialista" e pelo limite; a versão é o molde.
        from .llm.prompts import SYSTEM

        versao = hashlib.sha256(SYSTEM.encode()).hexdigest()[:10]
        if s.get(PromptVersao, versao) is None:
            s.add(PromptVersao(versao=versao, texto=SYSTEM))
        return versao

    def salvar(self, *, tarefa: dict, resultado: dict, telemetria: dict, latencia_ms: int, origem: str,
               versoes_bases: dict, versao_a2: str) -> int:
        tel = dict(telemetria or {})
        payload_t = tarefa.get("payload") or {}
        ri = tarefa.get("registro_inicial") or {}
        nomes = [n for n in str(ri.get("nome") or "").replace(".", " ").split() if len(n) > 2]
        exibido = tel.pop("nome_exibido", None)
        if exibido and exibido not in nomes:
            nomes.append(exibido)

        tarefa_limpa = {k: v for k, v in tarefa.items() if k != "registro_inicial"}
        tarefa_limpa["payload"] = dict(payload_t)
        if "pergunta" in payload_t:
            tarefa_limpa["payload"]["pergunta"] = tel.get("pergunta_mascarada", payload_t["pergunta"])
        if payload_t.get("historico_resumo"):
            from .guardrails.entrada import neutralizar_contexto

            tarefa_limpa["payload"]["historico_resumo"] = neutralizar_contexto(payload_t["historico_resumo"])
        ctx = dict(tarefa_limpa.get("contexto") or {})
        id_colab = ctx.pop("id_colaborador", None) or ri.get("id_colaborador")
        ctx["colaborador"] = self.pseudonimo(id_colab)
        tarefa_limpa["contexto"] = ctx
        if ri:
            tarefa_limpa["registro_inicial_campos"] = sorted(ri)

        res = json.loads(json.dumps(resultado, default=str))
        for s_ in res.get("saidas", []):
            (s_.get("para") or {}).pop("id_colaborador", None)
        res = _mascarar_nome(res, nomes)

        prompt = tel.pop("prompt", None) or {}
        tel["prompt_usuario"] = prompt.get("usuario")
        saida0 = (res.get("saidas") or [{}])[0]
        decisao = res.get("decisao") or {}
        payload_r = res.get("payload") or {}

        with self._sessao.begin() as s:
            reg = Interacao(
                origem=origem,
                id_mensagem=str(tarefa.get("id_mensagem")),
                thread_id=(tarefa.get("correlacao") or {}).get("thread_id"),
                acao=str(tarefa.get("acao")),
                colaborador=self.pseudonimo(id_colab),
                intencao=payload_t.get("intencao") or tel.get("intencao"),
                pergunta=tel.get("pergunta_mascarada"),
                resposta=saida0.get("texto"),
                status=res.get("status", "ERRO"),
                modo=tel.get("modo") or ("erro" if res.get("erro") else None),
                base=payload_r.get("base"),
                bases=payload_r.get("bases_consultadas") or ([payload_r["base"]] if payload_r.get("base") else []),
                ids_trechos=payload_r.get("ids_trechos") or [],
                cobertura=tel.get("cobertura") or payload_r.get("cobertura"),
                usou_llm=bool(decisao.get("usou_llm")),
                modelo=decisao.get("modelo") or prompt.get("modelo"),
                confianca=decisao.get("confianca"),
                latencia_ms=latencia_ms,
                tentativas_llm=len(tel.get("tentativas") or []),
                sensivel=bool(saida0.get("sensivel")),
                id_solicitacao_epi=payload_r.get("id_solicitacao_epi"),
                motivo=decisao.get("motivo"),
                erro=(res.get("erro") or {}).get("codigo"),
                versao_prompt=self._versao_prompt(s, prompt.get("system")),
                versao_a2=versao_a2,
                versoes_bases=versoes_bases,
                telemetria=tel,
                tarefa=tarefa_limpa,
                resultado=res,
            )
            s.add(reg)
            s.flush()
            return reg.id

    def registrar_feedback(self, id_interacao: int, *, avaliacao: str, categoria: str | None = None,
                           comentario: str | None = None, resposta_sugerida: str | None = None,
                           base_correta: str | None = None, autor: str | None = None,
                           situacao: str = "aberto") -> dict:
        if avaliacao not in {"positivo", "negativo"}:
            raise ValueError("avaliacao deve ser 'positivo' ou 'negativo'")
        if categoria and categoria not in CATEGORIAS_FEEDBACK:
            raise ValueError(f"categoria desconhecida: {categoria}")
        from .guardrails.entrada import neutralizar_contexto

        with self._sessao.begin() as s:
            if s.get(Interacao, id_interacao) is None:
                raise KeyError(id_interacao)
            fb = Feedback(id_interacao=id_interacao, avaliacao=avaliacao, categoria=categoria,
                          comentario=neutralizar_contexto(comentario, 2000) or None,
                          resposta_sugerida=neutralizar_contexto(resposta_sugerida, 2000) or None,
                          base_correta=base_correta, autor=(autor or None),
                          situacao="resolvido" if avaliacao == "positivo" else situacao)
            s.add(fb)
            s.flush()
            return self._fb_dict(fb)

    def atualizar_feedback(self, id_feedback: int, situacao: str) -> dict:
        if situacao not in {"aberto", "resolvido"}:
            raise ValueError("situacao deve ser 'aberto' ou 'resolvido'")
        with self._sessao.begin() as s:
            fb = s.get(Feedback, id_feedback)
            if fb is None:
                raise KeyError(id_feedback)
            fb.situacao = situacao
            return self._fb_dict(fb)

    def expurgar(self) -> int:
        if not self.retencao_dias:
            return 0
        limite = _agora() - timedelta(days=self.retencao_dias)
        with self._sessao.begin() as s:
            n = s.execute(delete(Interacao).where(Interacao.criado_em < limite)).rowcount or 0
        if n:
            log.info("Expurgadas %s interações com mais de %s dias", n, self.retencao_dias)
        return n

    # ----------------------------------------------------------------- leitura
    @staticmethod
    def _fb_dict(f: Feedback) -> dict:
        return {"id": f.id, "id_interacao": f.id_interacao, "criado_em": _iso(f.criado_em), "avaliacao": f.avaliacao,
                "categoria": f.categoria, "comentario": f.comentario, "resposta_sugerida": f.resposta_sugerida,
                "base_correta": f.base_correta, "autor": f.autor, "situacao": f.situacao}

    def _resumo(self, i: Interacao) -> dict:
        ultimo = i.feedbacks[-1] if i.feedbacks else None
        return {
            "id": i.id, "criado_em": _iso(i.criado_em), "origem": i.origem, "acao": i.acao,
            "colaborador": i.colaborador, "intencao": i.intencao, "pergunta": i.pergunta, "resposta": i.resposta,
            "status": i.status, "modo": i.modo, "base": i.base, "bases": i.bases, "ids_trechos": i.ids_trechos,
            "cobertura": i.cobertura, "usou_llm": i.usou_llm, "modelo": i.modelo, "confianca": i.confianca,
            "latencia_ms": i.latencia_ms, "tentativas_llm": i.tentativas_llm, "sensivel": i.sensivel,
            "id_solicitacao_epi": i.id_solicitacao_epi, "versao_prompt": i.versao_prompt, "erro": i.erro,
            "feedback": ultimo.avaliacao if ultimo else None,
            "feedback_situacao": ultimo.situacao if ultimo else None,
            "motivos_fila": self._motivos_fila(i),
        }

    def detalhe(self, id_interacao: int) -> dict | None:
        with self._sessao() as s:
            i = s.get(Interacao, id_interacao)
            if i is None:
                return None
            d = self._resumo(i)
            d.update({"id_mensagem": i.id_mensagem, "thread_id": i.thread_id, "motivo": i.motivo,
                      "versao_a2": i.versao_a2, "versoes_bases": i.versoes_bases, "telemetria": i.telemetria,
                      "tarefa": i.tarefa, "resultado": i.resultado,
                      "feedbacks": [self._fb_dict(f) for f in i.feedbacks]})
            return d

    def _filtros(self, q, *, busca=None, base=None, status=None, modo=None, feedback=None, acao=None, dias=None):
        if busca:
            like = f"%{busca}%"
            q = q.where(or_(Interacao.pergunta.ilike(like), Interacao.resposta.ilike(like),
                            Interacao.motivo.ilike(like)))
        if base:
            q = q.where(Interacao.base == base)
        if status:
            q = q.where(Interacao.status == status)
        if modo:
            q = q.where(Interacao.modo.like(f"{modo}%"))
        if acao:
            q = q.where(Interacao.acao == acao)
        if dias:
            q = q.where(Interacao.criado_em >= _agora() - timedelta(days=int(dias)))
        if feedback == "sem":
            q = q.where(~Interacao.feedbacks.any())
        elif feedback in {"positivo", "negativo"}:
            q = q.where(Interacao.feedbacks.any(Feedback.avaliacao == feedback))
        return q

    def listar(self, *, pagina: int = 1, tamanho: int = 25, **filtros) -> dict:
        with self._sessao() as s:
            base_q = self._filtros(select(Interacao), **filtros)
            total = s.scalar(select(func.count()).select_from(base_q.subquery())) or 0
            itens = s.scalars(base_q.order_by(Interacao.id.desc()).offset((pagina - 1) * tamanho).limit(tamanho)).all()
            return {"total": total, "pagina": pagina, "tamanho": tamanho, "itens": [self._resumo(i) for i in itens]}

    @staticmethod
    def _motivos_fila(i: Interacao) -> list[str]:
        motivos = []
        if any(f.avaliacao == "negativo" and f.situacao == "aberto" for f in i.feedbacks):
            motivos.append("feedback_negativo")
        if i.cobertura == "nenhuma" or i.modo == "sem_trecho":
            motivos.append("sem_cobertura")
        tent = (i.telemetria or {}).get("tentativas") or []
        if any(t.get("aprovada") is False for t in tent):
            motivos.append("llm_recusado")
        if any(t.get("erro") for t in tent):
            motivos.append("erro_llm")
        if (i.modo or "").startswith("guardrail_"):
            motivos.append("guardrail")
        fund = ((i.telemetria or {}).get("fundamentacao") or {}).get("score")
        if fund is not None and fund < 0.6:
            motivos.append("baixa_fundamentacao")
        if i.confianca is not None and i.confianca < 0.4 and i.acao == "a2.responder" \
                and not (i.modo or "").startswith(("guardrail_", "fora_")):
            motivos.append("baixa_confianca")
        return motivos

    def fila_melhoria(self, *, motivo: str | None = None, incluir_resolvidas: bool = False, limite: int = 200) -> dict:
        with self._sessao() as s:
            itens = s.scalars(select(Interacao).order_by(Interacao.id.desc()).limit(2000)).all()
            fila = []
            for i in itens:
                m = self._motivos_fila(i)
                resolvida = bool(i.feedbacks) and all(f.situacao == "resolvido" for f in i.feedbacks)
                if not m or (resolvida and not incluir_resolvidas):
                    continue
                if motivo and motivo not in m:
                    continue
                fila.append(self._resumo(i))
            contagem = Counter(x for i in fila for x in i["motivos_fila"])
            return {"total": len(fila), "por_motivo": {k: contagem.get(k, 0) for k in MOTIVOS_FILA},
                    "itens": fila[:limite]}

    def metricas(self, dias: int = 30) -> dict:
        with self._sessao() as s:
            itens = s.scalars(select(Interacao).where(
                Interacao.criado_em >= _agora() - timedelta(days=dias)).order_by(Interacao.id)).all()
            n = len(itens)
            por_dia: dict[str, Counter] = defaultdict(Counter)
            for i in itens:
                dia = (i.criado_em if i.criado_em.tzinfo else i.criado_em.replace(tzinfo=timezone.utc)) \
                    .astimezone(timezone(timedelta(hours=-3))).date().isoformat()
                por_dia[dia][i.status] += 1
            guardrails = Counter(sx["tipo"] for i in itens for sx in (i.telemetria or {}).get("sinais", [])
                                 if (i.modo or "").startswith("guardrail_"))
            recusas = Counter(m.split(":")[0] for i in itens for t in (i.telemetria or {}).get("tentativas", [])
                              for m in t.get("motivos", []))
            feedbacks = [f for i in itens for f in i.feedbacks]
            categorias = Counter(f.categoria for f in feedbacks if f.categoria)
            responder = [i for i in itens if i.acao == "a2.responder"]
            com_llm = [i for i in responder if i.tentativas_llm]
            lat = sorted(i.latencia_ms for i in itens if i.latencia_ms is not None)
            sem_cob = Counter(i.pergunta for i in itens if i.pergunta and
                              (i.cobertura == "nenhuma" or i.modo in {"sem_trecho"}))
            por_prompt: dict[str, dict] = {}
            for v in {i.versao_prompt for i in com_llm if i.versao_prompt}:
                grupo = [i for i in com_llm if i.versao_prompt == v]
                fb = [f for i in grupo for f in i.feedbacks]
                por_prompt[v] = {
                    "interacoes": len(grupo),
                    "aprovadas_1a": round(sum(1 for i in grupo if i.modo == "llm") / len(grupo), 3),
                    "fallback": round(sum(1 for i in grupo if i.modo == "extrativo") / len(grupo), 3),
                    "feedback_positivo": sum(1 for f in fb if f.avaliacao == "positivo"),
                    "feedback_negativo": sum(1 for f in fb if f.avaliacao == "negativo"),
                }
            return {
                "dias": dias,
                "total": n,
                "status": dict(Counter(i.status for i in itens)),
                "modos": dict(Counter(i.modo or "—" for i in itens)),
                "bases": dict(Counter(i.base for i in itens if i.base)),
                "acoes": dict(Counter(i.acao for i in itens)),
                "por_dia": [{"dia": d, **c} for d, c in sorted(por_dia.items())],
                "guardrails": dict(guardrails),
                "recusas_llm": dict(recusas.most_common(10)),
                "llm": {
                    "chamadas": sum(i.tentativas_llm for i in itens),
                    "aprovadas_1a": sum(1 for i in com_llm if i.modo == "llm"),
                    "aprovadas_2a": sum(1 for i in com_llm if i.modo == "llm_2a_tentativa"),
                    "fallback": sum(1 for i in com_llm if i.modo == "extrativo"),
                    "respostas_com_llm": len(com_llm),
                },
                "latencia_ms": {"media": round(sum(lat) / len(lat)) if lat else None,
                                "p95": lat[int(len(lat) * 0.95) - 1] if lat else None},
                "confianca_media": round(sum(i.confianca for i in responder if i.confianca is not None) /
                                         max(1, sum(1 for i in responder if i.confianca is not None)), 3)
                if responder else None,
                "feedback": {"positivo": sum(1 for f in feedbacks if f.avaliacao == "positivo"),
                             "negativo": sum(1 for f in feedbacks if f.avaliacao == "negativo"),
                             "abertos": sum(1 for f in feedbacks if f.situacao == "aberto" and f.avaliacao == "negativo"),
                             "categorias": dict(categorias)},
                "epi_solicitacoes": sum(1 for i in itens if i.id_solicitacao_epi),
                "rag": {
                    "fundamentacao_media": (lambda v: round(sum(v) / len(v), 3) if v else None)(
                        [f["score"] for i in itens if (f := (i.telemetria or {}).get("fundamentacao"))]),
                    "com_complemento": sum(1 for i in itens if (i.telemetria or {}).get("complemento")),
                    "complementos_descartados": sum(1 for i in itens if (i.telemetria or {}).get("complemento_descartado")),
                    "perguntas_reescritas": sum(1 for i in itens if ((i.telemetria or {}).get("plano") or {}).get("usou_llm")),
                },
                "sem_cobertura_top": [{"pergunta": p, "vezes": c} for p, c in sem_cob.most_common(8)],
                "por_versao_prompt": por_prompt,
            }

    # ----------------------------------------------------------------- exportação
    def exportar(self, formato: str = "csv", **filtros) -> str:
        with self._sessao() as s:
            itens = s.scalars(self._filtros(select(Interacao), **filtros).order_by(Interacao.id)).all()
            linhas = [self._resumo(i) for i in itens]
        if formato == "jsonl":
            return "\n".join(json.dumps(x, ensure_ascii=False) for x in linhas)
        buf = io.StringIO()
        colunas = ["id", "criado_em", "origem", "acao", "intencao", "pergunta", "resposta", "status", "modo", "base",
                   "ids_trechos", "cobertura", "usou_llm", "modelo", "confianca", "latencia_ms", "tentativas_llm",
                   "versao_prompt", "feedback", "motivos_fila"]
        w = csv.DictWriter(buf, fieldnames=colunas, extrasaction="ignore", delimiter=";")
        w.writeheader()
        for x in linhas:
            w.writerow({k: (", ".join(map(str, v)) if isinstance(v, list) else v) for k, v in x.items()})
        return "﻿" + buf.getvalue()     # BOM: abre com acentos no Excel

    def exportar_dataset(self) -> str:
        """JSONL de casos revisados: pergunta, base esperada, resposta de referência e veredito.

        Serve como conjunto de regressão ao mudar prompt, guardrails ou limiares.
        """
        with self._sessao() as s:
            itens = s.scalars(select(Interacao).where(Interacao.feedbacks.any()).order_by(Interacao.id)).all()
            casos = []
            for i in itens:
                f = i.feedbacks[-1]
                casos.append({
                    "id_interacao": i.id, "pergunta": i.pergunta, "intencao": i.intencao,
                    "base_obtida": i.base, "base_esperada": f.base_correta or i.base,
                    "ids_obtidos": i.ids_trechos, "resposta_obtida": i.resposta,
                    "resposta_referencia": f.resposta_sugerida or (i.resposta if f.avaliacao == "positivo" else None),
                    "veredito": f.avaliacao, "categoria": f.categoria, "modo": i.modo,
                    "versao_prompt": i.versao_prompt,
                })
        return "\n".join(json.dumps(c, ensure_ascii=False) for c in casos)
