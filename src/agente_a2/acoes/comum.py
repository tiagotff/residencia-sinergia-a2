"""Peças comuns às ações do A2."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from sinergia_contratos import Decisao, Destinatario, Evento, Fonte, Saida, Tarefa

from ..config import ConfigA2
from ..llm.cliente import ClienteLLM
from ..rag.chunking import Trecho
from ..rag.recuperador import Recuperador
from ..repositorio import Repositorio


@dataclass
class Dependencias:
    config: ConfigA2
    recuperador: Recuperador
    llm: ClienteLLM | None = None
    repositorio: Repositorio | None = None
    cache: dict[str, Any] = field(default_factory=dict)
    llm_planejador: ClienteLLM | None = None    # reescrita da pergunta (pré-recuperação)


@dataclass
class Parcial:
    """O que cada ação devolve; o agente completa o envelope."""

    status: str = "OK"
    payload: dict[str, Any] = field(default_factory=dict)
    saidas: list[Saida] = field(default_factory=list)
    eventos: list[Evento] = field(default_factory=list)
    decisao: Decisao | None = None
    # Dados internos para o registro de interações (não fazem parte do RESULTADO)
    telemetria: dict[str, Any] = field(default_factory=dict)


def agora(tarefa: Tarefa, fuso: str) -> datetime:
    tz = ZoneInfo(fuso)
    if tarefa.contexto.data_hora:
        try:
            dt = datetime.fromisoformat(tarefa.contexto.data_hora)
            return dt if dt.tzinfo else dt.replace(tzinfo=tz)
        except ValueError:
            pass
    return datetime.now(tz)


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def no_horario(dia: date, hhmm: str | None, fuso: str, padrao: str = "10:00") -> datetime:
    h, m = (int(x) for x in (hhmm or padrao).split(":")[:2])
    return datetime.combine(dia, time(h, m), tzinfo=ZoneInfo(fuso))


def mais_horas(hhmm: str | None, horas: int, padrao: str = "10:00") -> str:
    if not hhmm:
        return padrao
    h, m = (int(x) for x in hhmm.split(":")[:2])
    return f"{min(h + horas, 23):02d}:{m:02d}"


def para_colaborador(tarefa: Tarefa, id_colaborador: int | None = None) -> Destinatario:
    return Destinatario(perfil="colaborador", id_colaborador=id_colaborador or tarefa.contexto.id_colaborador)


def fontes_de(trechos: list[Trecho]) -> list[Fonte]:
    """Agrupa os trechos citados por documento: {base, titulo, versao, refs}."""
    grupos: dict[tuple[str, str, str], list[str]] = {}
    for t in trechos:
        chave = (t.base, t.documento_titulo, t.documento_versao)
        grupos.setdefault(chave, [])
        if t.id_pergunta not in grupos[chave]:
            grupos[chave].append(t.id_pergunta)
    return [Fonte(base=b, titulo=ti, versao=v, refs=refs) for (b, ti, v), refs in grupos.items()]


_REF_INTERNA = re.compile(r"[^.]*\b[A-Z]{2,3}(?:-[A-Z]{3})?-Q\d{3}\b[^.]*\.?\s*")


def sem_referencias_internas(texto: str) -> str:
    """Remove frases que citam IDs da base ("veja a pergunta EPI-Q013"): o colaborador não vê a base."""
    limpo = _REF_INTERNA.sub("", texto).strip()
    return limpo or texto


def texto_corrido(resposta: str, max_chars: int) -> str:
    """Resposta da base em texto corrido de chat (sem bullets), cortada em frase."""
    resposta = sem_referencias_internas(resposta)
    linhas = [re.sub(r"^(•|\d{1,2})\s*", "", l).strip() for l in resposta.split("\n") if l.strip()]
    texto = ""
    for l in linhas:
        if texto and not texto.endswith((".", ":", ";", "!", "?")):
            texto += ";"
        texto = f"{texto} {l}".strip()
    texto = re.sub(r":;", ":", texto)
    if len(texto) <= max_chars:
        return texto
    corte = texto[:max_chars]
    fim = max(corte.rfind(". "), corte.rfind("; "))
    return (corte[: fim + 1] if fim > 60 else corte.rsplit(" ", 1)[0] + "…").rstrip(";") .strip()


def primeiro_nome(nome: str | None) -> str | None:
    if not nome:
        return None
    return nome.strip().split()[0].rstrip(".,")
