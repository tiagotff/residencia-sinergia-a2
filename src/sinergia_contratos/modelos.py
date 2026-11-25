"""Envelope sinergia/1 em Pydantic (relatório v0.7, capítulo 7).

Regras de versão: campo opcional novo pode entrar a qualquer momento; remover
ou renomear exige sinergia/2. Por isso a TAREFA aceita campos extras (o A0 pode
evoluir antes do A2) e o RESULTADO os proíbe (o A2 nunca manda o que o contrato
não conhece, exceto os opcionais declarados aqui).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

PROTOCOLO = "sinergia/1"

Agente = Literal["A0", "A1", "A2", "A3"]
Status = Literal["OK", "PRECISA_HUMANO", "ERRO"]
TipoSaida = Literal["mensagem", "lembrete", "alerta"]
NivelDetalhe = Literal["agregado", "pseudonimizado", "individual"]


class _Tolerante(BaseModel):
    model_config = ConfigDict(extra="allow")


class _Estrito(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Correlacao(_Tolerante):
    id_caso: int | None = None
    thread_id: str | None = None
    id_tarefa: str | None = None


class Contexto(_Tolerante):
    id_colaborador: int | None = None
    id_empresa: int | None = None
    perfil: str | None = None
    canal: str | None = None
    data_hora: str | None = None


class Tarefa(_Tolerante):
    protocolo: Literal["sinergia/1"]
    id_mensagem: str
    tipo: Literal["TAREFA"]
    acao: str
    origem: Agente
    destino: Agente
    correlacao: Correlacao = Field(default_factory=Correlacao)
    contexto: Contexto = Field(default_factory=Contexto)
    registro_inicial: dict[str, Any] | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class Fonte(_Estrito):
    base: str
    titulo: str
    versao: str
    # Opcional (campo novo permitido no sinergia/1): IDs das perguntas usadas,
    # para auditoria e para o Judge conferir a Fundamentação.
    refs: list[str] | None = None


class Destinatario(_Estrito):
    perfil: str
    id_colaborador: int | None = None


class Saida(_Estrito):
    tipo: TipoSaida
    para: Destinatario
    nivel_detalhe: NivelDetalhe = "individual"
    texto: str
    fontes: list[Fonte] = Field(default_factory=list)
    agendar_para: str | None = None
    sensivel: bool = False


class Evento(_Estrito):
    tipo: str
    dados: dict[str, Any]


class Decisao(_Estrito):
    motivo: str
    usou_llm: bool
    confianca: float | None = None
    modelo: str | None = None


class Erro(_Estrito):
    codigo: str
    mensagem: str
    reprocessavel: bool


class Resultado(_Estrito):
    protocolo: Literal["sinergia/1"] = PROTOCOLO
    id_mensagem: str
    tipo: Literal["RESULTADO"] = "RESULTADO"
    acao: str
    origem: Agente = "A2"
    destino: Agente = "A0"
    em_resposta_a: str
    correlacao: Correlacao
    status: Status
    estado_proposto: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    saidas: list[Saida] = Field(default_factory=list)
    eventos: list[Evento] = Field(default_factory=list)
    decisao: Decisao | None = None
    erro: Erro | None = None
