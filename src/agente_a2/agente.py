"""AgenteA2 — Bem-Estar (núcleo). Interface única: ``executar(tarefa) -> resultado``.

Garante as regras de transporte do sinergia/1 (relatório 7.2):

* toda TAREFA recebida devolve exatamente um RESULTADO (inclusive em erro);
* idempotência por ``id_mensagem`` (a mesma TAREFA devolve o mesmo RESULTADO
  sem gravar de novo; a solicitação de EPI também é única por mensagem);
* ``correlacao`` copiada, ``em_resposta_a`` preenchido, ``estado_proposto``
  sempre nulo (o A2 não move caso).
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from sinergia_contratos import Erro, Resultado, Tarefa

from .acoes import acompanhar_afastamento, orientar_epi, responder
from .acoes.comum import Dependencias, Parcial
from .config import ConfigA2
from .llm.cliente import ClienteGroq, ClienteLLM
from .rag.embeddings import Embedder, criar_embedder
from .rag.recuperador import Recuperador
from .rag.stores import Store, StoreMemoria, StorePGVector
from .repositorio import Repositorio

log = logging.getLogger(__name__)

AcaoFn = Callable[[Tarefa, Dependencias], Parcial]

ACOES: dict[str, AcaoFn] = {
    "a2.responder": responder.executar,
    "a2.orientar_epi": orientar_epi.executar,
    "a2.acompanhar_afastamento": acompanhar_afastamento.executar,
}
# Ações do contrato fora do escopo desta entrega (não dependem do RAG):
# a2.gerar_lembretes (F1/F3/F4, regras de jornada) e a2.recomendar_beneficios (rede neural 1).
PENDENTES = {"a2.gerar_lembretes", "a2.recomendar_beneficios"}

@dataclass
class Execucao:
    """RESULTADO + o que aconteceu por dentro (para a interface e o registro)."""

    resultado: Resultado
    telemetria: dict = field(default_factory=dict)
    latencia_ms: int = 0
    id_interacao: int | None = None
    repetida: bool = False


_NAMESPACE = uuid.UUID("5e1e7a2a-0000-4000-8000-a2a2a2a2a2a2")


class AgenteA2:
    def __init__(
        self,
        db: Any = None,                       # sessão/engine SQLAlchemy (opcional)
        llm: ClienteLLM | None = None,
        rede_beneficios: str | None = None,   # reservado para a2.recomendar_beneficios
        *,
        store: Store | None = None,
        embedder: Embedder | None = None,
        repositorio: Repositorio | None = None,
        config: ConfigA2 | None = None,
        registro: Any = None,                 # RegistroInteracoes (opcional)
        llm_planejador: ClienteLLM | None = None,   # reescrita da pergunta; None = heurística
        tamanho_idempotencia: int = 2000,
    ):
        self.config = config or ConfigA2()
        embedder = embedder or criar_embedder(
            self.config.embeddings_provedor, self.config.embeddings_modelo, self.config.embeddings_dim
        )
        if store is None:
            if self.config.store == "pgvector":
                store = StorePGVector(self.config.database_url, self.config.exigir_aprovacao)
            else:
                store = StoreMemoria(self.config.indice_local, self.config.exigir_aprovacao)
        if repositorio is None and db is not None:
            from .repositorio import RepositorioSQL

            repositorio = RepositorioSQL(db)
        self.dep = Dependencias(
            config=self.config,
            recuperador=Recuperador(store, embedder, self.config),
            llm=llm,
            repositorio=repositorio,
            llm_planejador=llm_planejador,
        )
        self.rede_beneficios = rede_beneficios
        self.registro = registro
        self._ja_respondidas: OrderedDict[str, Resultado] = OrderedDict()
        self._limite = tamanho_idempotencia

    # ------------------------------------------------------------------
    def executar(self, tarefa: Tarefa | dict | str, origem: str = "api") -> Resultado:
        return self.executar_detalhado(tarefa, origem).resultado

    def executar_detalhado(self, tarefa: Tarefa | dict | str, origem: str = "api") -> Execucao:
        inicio = time.perf_counter()
        try:
            t = self._validar(tarefa)
        except ValidationError as e:
            res = self._erro_bruto(tarefa, "TAREFA_INVALIDA", _resumo(e))
            return self._registrar(tarefa if isinstance(tarefa, dict) else {}, res, {"modo": "erro"}, inicio, origem)

        if t.id_mensagem in self._ja_respondidas:
            return Execucao(self._ja_respondidas[t.id_mensagem], {"modo": "idempotente"}, 0, None, True)

        telemetria: dict = {}
        if t.destino != "A2" or t.origem != "A0":
            res = self._envelope(t, Parcial(status="ERRO"), Erro(
                codigo="DESTINO_INVALIDO", mensagem=f"TAREFA de {t.origem} para {t.destino}", reprocessavel=False))
        elif t.acao in PENDENTES:
            res = self._envelope(t, Parcial(status="ERRO"), Erro(
                codigo="ACAO_NAO_IMPLEMENTADA", mensagem=f"{t.acao} ainda não implementada no A2",
                reprocessavel=False))
        elif t.acao not in ACOES:
            res = self._envelope(t, Parcial(status="ERRO"), Erro(
                codigo="ACAO_DESCONHECIDA", mensagem=f"Ação fora do catálogo do A2: {t.acao}", reprocessavel=False))
        else:
            try:
                parcial = ACOES[t.acao](t, self.dep)
                telemetria = parcial.telemetria
                res = self._envelope(t, parcial)
            except ValidationError as e:
                res = self._envelope(t, Parcial(status="ERRO"), Erro(
                    codigo="PAYLOAD_INVALIDO", mensagem=_resumo(e), reprocessavel=False))
            except Exception as e:  # nunca deixa a TAREFA sem RESULTADO
                log.exception("Erro interno no A2 (%s)", t.acao)
                res = self._envelope(t, Parcial(status="ERRO"), Erro(
                    codigo="ERRO_INTERNO", mensagem=type(e).__name__, reprocessavel=True))

        # Erro reprocessável não fica no cache de idempotência: o A0 pode tentar de novo.
        if not (res.erro and res.erro.reprocessavel):
            self._ja_respondidas[t.id_mensagem] = res
            if len(self._ja_respondidas) > self._limite:
                self._ja_respondidas.popitem(last=False)
        return self._registrar(t.model_dump(mode="json"), res, telemetria or {"modo": "erro" if res.erro else None},
                               inicio, origem)

    def _registrar(self, tarefa: dict, res: Resultado, telemetria: dict, inicio: float, origem: str) -> Execucao:
        latencia = round((time.perf_counter() - inicio) * 1000)
        exe = Execucao(res, telemetria, latencia)
        if self.registro is not None:
            try:
                from . import __version__

                hoje = datetime.now(ZoneInfo(self.config.fuso)).date()
                versoes = {b: v for b, (_, v) in self.dep.recuperador.store.bases_vigentes(hoje).items()}
                exe.id_interacao = self.registro.salvar(
                    tarefa=tarefa, resultado=res.model_dump(mode="json"), telemetria=telemetria,
                    latencia_ms=latencia, origem=origem, versoes_bases=versoes, versao_a2=__version__)
            except Exception:  # o registro nunca derruba o atendimento
                log.exception("Falha ao registrar interação")
        return exe

    # ------------------------------------------------------------------
    @staticmethod
    def _validar(tarefa: Tarefa | dict | str) -> Tarefa:
        if isinstance(tarefa, Tarefa):
            return tarefa
        if isinstance(tarefa, str):
            return Tarefa.model_validate_json(tarefa)
        return Tarefa.model_validate(tarefa)

    @staticmethod
    def _id_resultado(id_tarefa: str) -> str:
        if id_tarefa.startswith("t-"):
            return "r-" + id_tarefa[2:]
        return str(uuid.uuid5(_NAMESPACE, id_tarefa))

    def _envelope(self, t: Tarefa, p: Parcial, erro: Erro | None = None) -> Resultado:
        return Resultado(
            id_mensagem=self._id_resultado(t.id_mensagem),
            acao=t.acao,
            em_resposta_a=t.id_mensagem,
            correlacao=t.correlacao,
            status="ERRO" if erro else p.status,
            estado_proposto=None,
            payload=p.payload,
            saidas=p.saidas,
            eventos=p.eventos,
            decisao=p.decisao,
            erro=erro,
        )

    def _erro_bruto(self, tarefa: Any, codigo: str, mensagem: str) -> Resultado:
        bruto = tarefa if isinstance(tarefa, dict) else {}
        id_t = str(bruto.get("id_mensagem") or "desconhecida")
        return Resultado(
            id_mensagem=self._id_resultado(id_t),
            acao=str(bruto.get("acao") or "desconhecida"),
            em_resposta_a=id_t,
            correlacao=bruto.get("correlacao") or {},
            status="ERRO",
            erro=Erro(codigo=codigo, mensagem=mensagem, reprocessavel=False),
        )


def _resumo(e: ValidationError) -> str:
    return "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()[:5])


def criar_agente_a2(config: ConfigA2 | None = None, **kwargs) -> AgenteA2:
    """Monta o A2 a partir do ambiente (.env): Groq se houver chave, senão modo extrativo."""
    config = config or ConfigA2()
    llm = kwargs.pop("llm", None)
    if llm is None and config.groq_api_key:
        llm = ClienteGroq(config.groq_api_key, config.groq_modelo, config.llm_temperatura, config.llm_timeout_s)
    if llm is not None and config.rag_reescrita and "llm_planejador" not in kwargs:
        kwargs["llm_planejador"] = llm
    if "registro" not in kwargs and config.registrar_interacoes:
        from .interacoes import RegistroInteracoes

        kwargs["registro"] = RegistroInteracoes(config.interacoes_db_url, config.sal_pseudonimo, config.retencao_dias)
    db = kwargs.pop("db", None)
    if db is None and config.database_url and kwargs.get("repositorio") is None:
        from sqlalchemy import create_engine

        db = create_engine(config.database_url, pool_pre_ping=True)
    return AgenteA2(db=db, llm=llm, config=config, **kwargs)
