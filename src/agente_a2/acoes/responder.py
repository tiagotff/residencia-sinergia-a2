"""a2.responder — perguntas de F1, F2, F3, F4 e F5 no chat (RAG com fonte).

Pipeline:

    TAREFA ─► guardrails de entrada ─┬─ crise/emergência ─► texto aprovado da base (SO-Q048/049), PRECISA_HUMANO
                                     ├─ injeção ───────────► recusa fixa, sem LLM
                                     ├─ dados de terceiros ─► recusa fixa, sem LLM
                                     ▼
                       busca híbrida nas 4 bases + roteamento
                                     ├─ nada relevante ────► escopo (OK) ou "sem documento" → RH (PRECISA_HUMANO)
                                     ▼
                       cache (pergunta + versões dos documentos)
                                     ▼
                       LLM (Especialista da base) ─► guardrails de saída ─► 1 nova tentativa ─► fallback extrativo
                                     ▼
                       relato de EPI? ─► apoio.solicitacao_epi + evento solicitacao_epi.aberta
                                     ▼
                       RESULTADO (saidas com fontes {base, titulo, versao, refs})
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass

from pydantic import BaseModel, Field

from sinergia_contratos import Decisao, Evento, Saida, Tarefa

from ..guardrails import textos
from ..guardrails.entrada import analisar, neutralizar_contexto
from ..guardrails.saida import (RelatoEPI, RespostaLLM, fundamentacao, limpar_formato, validar,
                                validar_complemento)
from ..llm import prompts
from ..rag.catalogo import BASE_RESERVADA_F3, BASES, base_da_intencao
from ..rag.consulta import planejar as planejar_consulta
from ..rag.recuperador import ResultadoBusca, termos_do_lexico
from ..texto import dobrar, tokens
from . import cordialidade
from .comum import (Dependencias, Parcial, agora, fontes_de, para_colaborador, primeiro_nome,
                    sem_referencias_internas, texto_corrido)
from .relato_epi import detectar as detectar_epi
from .relato_epi import nome_com_artigo, tem_sinal_de_problema

log = logging.getLogger(__name__)

ID_CRISE = ["SO-Q048"]
ID_EMERGENCIA = ["SO-Q049"]
IDS_REPOSICAO = ["EPI-Q021", "EPI-Q022"]
# Roteiro da base de EPI para cada situação (seção 3 da base). "pedido" = quer EPI novo sem dizer o motivo.
ID_POR_SITUACAO = {"avariado": "EPI-Q025", "perdido": "EPI-Q026", "nao_recebido": "EPI-Q027",
                   "tamanho_inadequado": "EPI-Q028", "pedido": "EPI-Q021"}
ID_POR_RELATO = ID_POR_SITUACAO  # compatibilidade

class PayloadResponder(BaseModel):
    pergunta: str = Field(min_length=1)
    intencao: str | None = None
    historico_resumo: str | None = None


@dataclass
class _Gerada:
    resposta: RespostaLLM
    usou_llm: bool
    modo: str            # "llm" | "llm_2a_tentativa" | "extrativo"
    motivos_falha: list[str]


def executar(tarefa: Tarefa, dep: Dependencias) -> Parcial:
    tel: dict = {"modo": None, "tentativas": [], "motivos_falha": []}
    parcial = _executar(tarefa, dep, tel)
    parcial.telemetria = tel
    return parcial


def _executar(tarefa: Tarefa, dep: Dependencias, tel: dict) -> Parcial:
    cfg = dep.config
    entrada = PayloadResponder.model_validate(tarefa.payload)
    momento = agora(tarefa, cfg.fuso)
    hoje = momento.date()
    para = para_colaborador(tarefa)
    analise = analisar(entrada.pergunta, cfg.max_chars_pergunta)
    regras = analise.regras()
    # Intenção fora do catálogo (ex.: "string" vindo de teste manual) é ignorada, não vira viés.
    intencao = entrada.intencao if base_da_intencao(entrada.intencao) else None
    tel.update({
        "pergunta_mascarada": analise.texto,
        "sinais": [{"tipo": x.tipo, "regra": x.regra, "peso": x.peso} for x in analise.sinais],
        "mascarados": analise.mascarados,
        "truncado": analise.truncado,
        "intencao": intencao,
    })
    if entrada.intencao and not intencao:
        tel["intencao_invalida"] = entrada.intencao[:40]

    def fixa(texto: str, motivo: str, status: str = "OK", payload: dict | None = None, sensivel=False,
             confianca: float | None = None) -> Parcial:
        return Parcial(
            status=status,
            payload={"base": None, "trechos_usados": 0, **(payload or {})},
            saidas=[Saida(tipo="mensagem", para=para, texto=texto, sensivel=sensivel)],
            decisao=Decisao(motivo=motivo, usou_llm=False, confianca=confianca),
        )

    # 1) Risco à vida e emergência: conteúdo aprovado da base, sem LLM, escala.
    if analise.crise or analise.emergencia:
        tel["modo"] = "guardrail_crise" if analise.crise else "guardrail_emergencia"
        ids = ID_CRISE if analise.crise else ID_EMERGENCIA
        trechos = dep.recuperador.por_ids(ids, hoje)
        if trechos:
            t = trechos[0]
            return Parcial(
                status="PRECISA_HUMANO",
                payload={"base": t.base, "trechos_usados": 1, "ids_trechos": ids,
                         "encaminhar_para": "SESMT" if analise.emergencia else "RH", "sinal": regras},
                saidas=[Saida(tipo="mensagem", para=para, texto=texto_corrido(t.resposta, cfg.max_chars_resposta),
                              fontes=fontes_de(trechos), sensivel=True)],
                decisao=Decisao(motivo=f"guardrail {'crise' if analise.crise else 'emergencia'}: resposta aprovada "
                                       f"{ids[0]} e escalonamento", usou_llm=False, confianca=1.0),
            )
        return fixa(textos.INDISPONIVEL, "guardrail crise/emergencia sem documento vigente", "PRECISA_HUMANO",
                    {"encaminhar_para": "RH", "sinal": regras}, sensivel=True, confianca=1.0)

    # 2) Injeção de prompt e dados de terceiros: recusa sem chamar o LLM.
    if analise.injecao:
        tel["modo"] = "guardrail_injecao"
        log.warning("Possível injeção de prompt bloqueada (%s) em %s", regras, tarefa.id_mensagem)
        return fixa(textos.INJECAO, f"guardrail injecao bloqueada: {regras}", payload={"sinal": regras}, confianca=1.0)
    if analise.terceiros:
        tel["modo"] = "guardrail_terceiros"
        return fixa(textos.TERCEIROS, f"guardrail dados de terceiros: {regras}", payload={"sinal": regras},
                    confianca=1.0)

    historico = neutralizar_contexto(entrada.historico_resumo)
    nome = _primeiro_nome(tarefa, dep)
    primeira = not historico

    # 3) Cordialidade: cumprimento, agradecimento e despedida respondidos sem busca e sem LLM.
    social = cordialidade.classificar(analise.texto)
    if social:
        tel["modo"] = "saudacao"
        if nome:
            tel["nome_exibido"] = nome
        texto_social = {
            "cumprimento": lambda: cordialidade.boas_vindas(nome, momento, primeira),
            "agradecimento": lambda: cordialidade.agradecimento(nome),
            "confirmacao": lambda: cordialidade.confirmacao(nome),
            "despedida": lambda: cordialidade.despedida(nome, momento),
        }[social]()
        return fixa(texto_social, f"cordialidade: {social}", payload={"interacao_social": social})

    # Cumprimento junto com a dúvida, no início da conversa: a resposta começa com a saudação.
    saudar = primeira and cordialidade.tem_cumprimento(analise.texto)

    def cumprimentar(texto: str) -> str:
        if not saudar:
            return texto
        if nome:
            tel["nome_exibido"] = nome
        return f"{cordialidade.prefixo(nome, momento)} {texto}"

    # 4) Relato/pedido de EPI: só na mensagem ATUAL (nunca inferido do histórico).
    deteccao = detectar_epi(analise.texto)
    if deteccao:
        tel["deteccao_epi"] = {"situacao": deteccao.situacao, "epi": deteccao.epi}

    # 5) R do RAG: entendimento da pergunta (reescrita + subconsultas) e busca múltipla com fusão.
    plano = planejar_consulta(analise.texto, historico, dep.llm_planejador)
    tel["plano"] = plano.para_telemetria()
    com_contexto = plano.usou_historico
    if dobrar(plano.autonoma) != dobrar(analise.texto):
        tel["consulta_busca"] = plano.autonoma
    busca = dep.recuperador.buscar_multi(plano.consultas, hoje, intencao, plano.tema)
    if deteccao:
        _priorizar(busca, dep.recuperador.por_ids([ID_POR_SITUACAO[deteccao.situacao]], hoje))
    tel["diag"] = busca.diagnostico
    if busca.vazio:
        # Tema reconhecido pela mensagem ATUAL (o histórico não decide se é assunto do A2).
        lexico_atual = termos_do_lexico(analise.texto)
        relevante = bool(busca.base_intencao or lexico_atual or (plano.usou_llm and plano.tema))
        tel["modo"] = "sem_trecho" if relevante else "fora_escopo"
        if not relevante:
            if nome:
                tel["nome_exibido"] = nome
            return fixa(cumprimentar(cordialidade.fora_do_escopo(nome)), "fora do escopo das bases do A2")
        motivo = "sem trecho vigente que responda"
        if busca.base_intencao == BASE_RESERVADA_F3:
            motivo += " (F3: base de procedimentos e treinamentos ainda não ingerida)"
        base_tema = busca.base_intencao or next(iter(lexico_atual), None) or plano.tema
        quem, texto_enc = textos.sem_documento(base_tema)
        return fixa(cumprimentar(texto_enc), motivo, "PRECISA_HUMANO",
                    {"base": busca.base_intencao, "encaminhar_para": quem, "motivo": "sem_trecho_vigente"})

    # 5) Cache: só para respostas sem efeito colateral, sem histórico e sem personalização sensível.
    perfil = _perfil(tarefa, dep)
    chave = _chave_cache(analise.texto, intencao, perfil, dep, hoje)
    usa_cache = cfg.cache_respostas and not historico and not deteccao
    if usa_cache and chave in dep.cache:
        tel["modo"] = "cache"
        cacheado: Parcial = dep.cache[chave]
        saidas = [s.model_copy(update={"para": para}, deep=True) for s in cacheado.saidas]
        decisao = cacheado.decisao.model_copy(update={"motivo": cacheado.decisao.motivo + "; servida do cache"})
        return Parcial(status=cacheado.status, payload={**cacheado.payload, "cache": True}, saidas=saidas,
                       eventos=[], decisao=decisao)

    # 6) Geração com validação.
    gerada = _gerar(busca, analise.texto, historico, perfil, dep, tel, entendimento=_entendimento(plano))
    r = gerada.resposta
    tel["modo"] = gerada.modo
    tel["motivos_falha"] = gerada.motivos_falha

    # F3 ainda não tem base: sem o LLM para julgar a cobertura, não arriscar resposta de outra base.
    if gerada.modo == "extrativo" and busca.base_intencao == BASE_RESERVADA_F3:
        r = RespostaLLM(resposta=textos.SEM_DOCUMENTO, cobertura="nenhuma")

    # Relato final: regras sobre a mensagem atual; o do LLM só vale se a mensagem confirmar.
    relato: RelatoEPI | None = None
    if deteccao and deteccao.abre_solicitacao:
        relato = RelatoEPI(situacao=deteccao.situacao,
                           epi_mencionado=(r.relato_epi.epi_mencionado if r.relato_epi else None) or deteccao.epi)
    elif r.relato_epi and not deteccao and tem_sinal_de_problema(analise.texto):
        relato = r.relato_epi
    elif r.relato_epi:
        tel["relato_llm_descartado"] = r.relato_epi.model_dump()

    roteiro = None
    situacao_roteiro = relato.situacao if relato else (deteccao.situacao if deteccao else None)
    if situacao_roteiro:
        roteiro = next(iter(dep.recuperador.por_ids([ID_POR_SITUACAO[situacao_roteiro]], hoje)), None)
    # O tema é EPI e a base tem o roteiro: "sem cobertura" do LLM não vale; responde pelo roteiro.
    if roteiro and r.cobertura == "nenhuma":
        r = RespostaLLM(resposta=texto_corrido(roteiro.resposta, 600), ids_usados=[roteiro.id_pergunta],
                        cobertura="parcial")
        tel["roteiro_epi_aplicado"] = roteiro.id_pergunta
    tel["cobertura"] = r.cobertura
    tel["relato_epi"] = relato.model_dump() if relato else None

    if r.cobertura == "nenhuma":
        base_tema = busca.base_intencao if busca.base_intencao == BASE_RESERVADA_F3 else busca.base_principal
        quem, texto_enc = textos.sem_documento(base_tema)
        return fixa(cumprimentar(texto_enc), f"trechos recuperados não cobrem a pergunta ({gerada.modo})", "PRECISA_HUMANO",
                    {"base": base_tema, "bases_consultadas": busca.bases, "encaminhar_para": quem,
                     "motivo": "sem_cobertura"})

    citados = [p.trecho for p in busca.trechos if p.trecho.id_pergunta in r.ids_usados]
    if roteiro and roteiro not in citados:
        citados.insert(0, roteiro)
    base_resposta = citados[0].base if citados else busca.base_principal
    texto = sem_referencias_internas(limpar_formato(r.resposta))
    payload: dict = {
        "base": base_resposta,
        "trechos_usados": len(citados),
        "ids_trechos": [t.id_pergunta for t in citados],
        "bases_consultadas": busca.bases,
        "cobertura": r.cobertura,
    }
    eventos: list[Evento] = []
    status = "OK"

    # 7) F5: relato de EPI -> solicitação (sem duplicar pedido aberto do mesmo EPI).
    if relato and tarefa.contexto.id_colaborador:
        texto = _sem_frases_de_reposicao(texto)
        id_solic, existente = _abrir_solicitacao(tarefa, dep, relato, analise.texto)
        if id_solic is not None and existente:
            texto = f"{texto} {textos.SOLICITACAO_EPI_EXISTENTE.format(id=id_solic)}"
            payload.update({"id_solicitacao_epi": id_solic, "solicitacao_existente": True})
        elif id_solic is not None:
            texto = f"{texto} {textos.SOLICITACAO_EPI_ABERTA.format(id=id_solic)}"
            payload["id_solicitacao_epi"] = id_solic
            eventos.append(Evento(tipo="solicitacao_epi.aberta", dados={"id_solicitacao": id_solic}))
        else:
            texto = f"{texto} {textos.SOLICITACAO_EPI_FALHOU}"
            status = "PRECISA_HUMANO"
            payload["encaminhar_para"] = "TST"
        citados += [t for t in dep.recuperador.por_ids(IDS_REPOSICAO, hoje) if t not in citados]
        payload["ids_trechos"] = [t.id_pergunta for t in citados]
    elif deteccao and deteccao.situacao == "pedido":
        texto = f"{texto} {textos.PEDIDO_SEM_MOTIVO.format(epi=nome_com_artigo(deteccao.epi))}"
        payload["aguardando_motivo_epi"] = True

    # G do RAG, parte 2: dica de conhecimento geral (validada à parte; nunca regra, número ou saúde clínica).
    if cfg.rag_complemento and r.complemento and gerada.usou_llm and not relato and not deteccao and not r.sensivel:
        complemento, recusa = validar_complemento(r.complemento)
        if complemento:
            texto = f"{texto} Dica: {complemento}"
            tel["complemento"] = complemento
            payload["complemento_geral"] = True
        else:
            tel["complemento_descartado"] = {"texto": r.complemento[:300], "motivo": recusa}

    texto = cumprimentar(texto)
    sensivel = r.sensivel
    if sensivel:
        status = "PRECISA_HUMANO"

    confianca = busca.melhor * {"total": 1.0, "parcial": 0.7}.get(r.cobertura, 0.3)
    if gerada.modo == "extrativo":
        confianca *= 0.85
    if gerada.usou_llm and gerada.modo != "extrativo" and citados:
        # Fundamentação: quanto da resposta gerada tem apoio nas fontes citadas.
        nota_fund, sem_apoio = fundamentacao(r.resposta, [t.texto_para_prompt() for t in citados])
        tel["fundamentacao"] = {"score": nota_fund, "sem_apoio": sem_apoio}
        confianca *= 0.7 + 0.3 * nota_fund
    motivo = _motivo(busca, citados, gerada, analise.suspeita_injecao, analise.mascarados)
    if com_contexto:
        motivo += "; busca com o contexto da conversa"
    if plano.usou_llm:
        motivo += f"; pergunta reescrita e {len(plano.consultas)} consulta(s) fundidas"
    if tel.get("fundamentacao"):
        motivo += f"; fundamentação {int(tel['fundamentacao']['score'] * 100)}%"
    if tel.get("roteiro_epi_aplicado"):
        motivo += f"; roteiro de EPI {tel['roteiro_epi_aplicado']} aplicado"

    parcial = Parcial(
        status=status,
        payload=payload,
        saidas=[Saida(tipo="mensagem", para=para, texto=texto, fontes=fontes_de(citados), sensivel=sensivel)],
        eventos=eventos,
        decisao=Decisao(motivo=motivo, usou_llm=gerada.usou_llm, confianca=round(min(confianca, 1.0), 2),
                        modelo=dep.llm.nome if gerada.usou_llm and dep.llm else None),
    )
    if usa_cache and not eventos and not sensivel and r.cobertura == "total" and gerada.modo != "extrativo":
        dep.cache[chave] = parcial
    return parcial


def _entendimento(plano) -> str:
    partes = [plano.autonoma]
    if plano.subconsultas:
        partes.append("Aspectos: " + "; ".join(plano.subconsultas))
    return "\n".join(partes)


_FRASE_REPOSICAO = re.compile(
    r"(pe[cç]a|pedir|solicit\w*)[^.]{0,50}reposi|reposi[cç][aã]o[^.]{0,50}(chat|24)|24\s*horas|"
    r"entreg\w* o novo|tem at[eé] 24|pedido (de reposi[cç][aã]o )?(foi )?abert", re.IGNORECASE)


def _sem_frases_de_reposicao(texto: str) -> str:
    """Tira do texto do LLM o que o sistema vai confirmar (pedido, prazo), evitando repetição."""
    frases = re.split(r"(?<=[.!?])\s+", texto.strip())
    mantidas = [f for f in frases if not _FRASE_REPOSICAO.search(f)]
    return " ".join(mantidas or frases[:1]).strip()


# ----------------------------------------------------------------------------------------------

def _gerar(busca: ResultadoBusca, pergunta: str, historico: str, perfil: str, dep: Dependencias,
           tel: dict | None = None, entendimento: str = "") -> _Gerada:
    tel = tel if tel is not None else {"tentativas": []}
    cfg = dep.config
    ids = {p.trecho.id_pergunta: p.trecho.texto_para_prompt() for p in busca.trechos}
    if dep.llm is None:
        return _extrativo(busca, ["llm_nao_configurado"], pergunta=pergunta)

    system, usuario = prompts.montar(busca, pergunta, historico, perfil, cfg.max_chars_resposta, entendimento)
    tel["prompt"] = {"system": system, "usuario": usuario, "modelo": dep.llm.nome}
    mensagens = [("system", system), ("user", usuario)]
    motivos: list[str] = []
    for tentativa in (1, 2):
        inicio = time.perf_counter()
        try:
            bruto = dep.llm.gerar(mensagens)
        except Exception as e:  # timeout, rate limit, rede
            log.warning("Falha no LLM (%s): %s", dep.llm.nome, e)
            tel["tentativas"].append({"n": tentativa, "erro": f"{type(e).__name__}: {str(e)[:200]}",
                                      "ms": round((time.perf_counter() - inicio) * 1000)})
            return _extrativo(busca, [f"erro_llm: {type(e).__name__}"], pergunta=pergunta)
        resposta, motivos = validar(bruto, ids_recuperados=ids, pergunta=pergunta, max_chars=cfg.max_chars_resposta)
        tel["tentativas"].append({"n": tentativa, "resposta": bruto[:4000], "aprovada": resposta is not None,
                                  "motivos": motivos, "ms": round((time.perf_counter() - inicio) * 1000)})
        if resposta:
            return _Gerada(resposta, True, "llm" if tentativa == 1 else "llm_2a_tentativa", [])
        log.info("Resposta do LLM recusada (%s): %s", tentativa, motivos)
        mensagens = mensagens + [("assistant", bruto[:2000]),
                                 ("user", prompts.CORRECAO.format(motivos="; ".join(motivos)))]
    return _extrativo(busca, motivos, usou_llm=True, pergunta=pergunta)


def _extrativo(busca: ResultadoBusca, motivos: list[str], usou_llm: bool = False,
               pergunta: str = "") -> _Gerada:
    """Sem LLM (ou com o LLM recusado): devolve a resposta aprovada do melhor trecho."""
    t = busca.trechos[0].trecho
    return _Gerada(
        RespostaLLM(resposta=texto_corrido(t.resposta, 600), ids_usados=[t.id_pergunta], cobertura="parcial"),
        usou_llm, "extrativo", motivos,
    )


def _priorizar(busca: ResultadoBusca, trechos) -> None:
    from ..rag.recuperador import TrechoPontuado

    for t in reversed(trechos):
        busca.trechos = [p for p in busca.trechos if p.trecho.id_pergunta != t.id_pergunta]
        nota = busca.trechos[0].pontuacao if busca.trechos else 0.6
        busca.trechos.insert(0, TrechoPontuado(t, nota, 0.0, 0.0))
    if busca.trechos:
        busca.base_principal = busca.trechos[0].trecho.base
        if busca.base_principal not in busca.bases:
            busca.bases.insert(0, busca.base_principal)


def _primeiro_nome(tarefa: Tarefa, dep: Dependencias) -> str | None:
    """Primeiro nome do cadastro (ou do registro inicial), só para a saudação feita pelo código."""
    nome = (tarefa.registro_inicial or {}).get("nome")
    if dep.repositorio and tarefa.contexto.id_colaborador:
        try:
            colab = dep.repositorio.colaborador(tarefa.contexto.id_colaborador)
            nome = (colab.nome if colab else None) or nome
        except Exception:
            pass
    return primeiro_nome(nome)


def _perfil(tarefa: Tarefa, dep: Dependencias) -> str:
    """Contexto mínimo e não sensível: cargo e jornada."""
    partes = []
    ri = tarefa.registro_inicial or {}
    colab = None
    if dep.repositorio and tarefa.contexto.id_colaborador:
        try:
            colab = dep.repositorio.colaborador(tarefa.contexto.id_colaborador)
        except Exception as e:
            log.warning("Cadastro indisponível: %s", e)
    if colab and colab.cargo:
        partes.append(f"cargo: {colab.cargo}")
        try:
            epis = [e.nome for e in dep.repositorio.epis_do_cargo(colab.id_cargo)] if colab.id_cargo else []
        except Exception:
            epis = []
        if epis:
            partes.append(f"EPIs do cargo: {', '.join(epis)}")
    ini = (colab.jornada_inicio if colab else None) or ri.get("jornada_inicio")
    fim = (colab.jornada_fim if colab else None) or ri.get("jornada_fim")
    if ini and fim:
        partes.append(f"jornada: {ini} às {fim}")
    if tarefa.contexto.perfil and tarefa.contexto.perfil != "colaborador":
        partes.append(f"perfil de acesso: {tarefa.contexto.perfil}")
    return neutralizar_contexto("; ".join(partes), 300)


def _chave_cache(pergunta: str, intencao: str | None, perfil: str, dep: Dependencias, hoje) -> str:
    norm = " ".join(sorted(tokens(pergunta)))
    bruto = f"{norm}|{intencao or ''}|{perfil}|{dep.recuperador.store.assinatura(hoje)}"
    return hashlib.sha256(bruto.encode()).hexdigest()


def _abrir_solicitacao(tarefa: Tarefa, dep: Dependencias, relato: RelatoEPI, pergunta: str
                       ) -> tuple[int | None, bool]:
    """(id, já_existia). Reaproveita pedido ABERTO do mesmo EPI em vez de abrir outro."""
    if dep.repositorio is None:
        return None, False
    try:
        id_epi = None
        colab = dep.repositorio.colaborador(tarefa.contexto.id_colaborador)
        mencionado = dobrar(f"{relato.epi_mencionado or ''} {pergunta}")
        if colab and colab.id_cargo:
            # Só associa o EPI do cargo quando não há ambiguidade ("luvas" com térmica e anticorte = sem EPI
            # definido; o TST confirma qual). Nome completo citado ("luva térmica") resolve.
            citados = set(tokens(mencionado))
            candidatos = [e for e in dep.repositorio.epis_do_cargo(colab.id_cargo) if set(tokens(e.nome)) & citados]
            completos = [e for e in candidatos if set(tokens(e.nome)) <= citados]
            escolhido = completos if len(completos) == 1 else candidatos if len(candidatos) == 1 else []
            id_epi = escolhido[0].id_epi if escolhido else None
        existente = dep.repositorio.solicitacao_aberta(tarefa.contexto.id_colaborador, id_epi)
        if existente is not None:
            return existente, True
        return dep.repositorio.abrir_solicitacao_epi(
            id_colaborador=tarefa.contexto.id_colaborador,
            id_epi=id_epi,
            situacao=relato.situacao,
            descricao=pergunta[:500],
            origem_id_mensagem=tarefa.id_mensagem,
        ), False
    except Exception as e:
        log.error("Falha ao abrir solicitação de EPI: %s", e)
        return None, False


def _motivo(busca: ResultadoBusca, citados, gerada: _Gerada, suspeita: bool, mascarados: list[str]) -> str:
    partes = [f"resposta RAG com {len(citados)} trecho(s) vigente(s)"]
    nomes = ", ".join(BASES[b].nome if b in BASES else b for b in busca.bases)
    partes.append(f"bases: {nomes}")
    if busca.base_intencao and busca.base_intencao != busca.base_principal:
        partes.append(f"intenção indicava {busca.base_intencao}, evidência apontou {busca.base_principal}")
    if gerada.modo != "llm":
        partes.append(f"modo {gerada.modo}" + (f" ({'; '.join(gerada.motivos_falha)[:160]})" if gerada.motivos_falha else ""))
    if suspeita:
        partes.append("sinal fraco de injeção (respondido com cautela)")
    if mascarados:
        partes.append(f"dados mascarados antes do LLM: {', '.join(mascarados)}")
    return "; ".join(partes)
