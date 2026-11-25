"""Acesso do A2 às tabelas de negócio (fora do schema rag).

Leitura: cadastro.colaborador/cargo/epi/cargo_epi/ferias e afastamento.atestado
(só período e situação, nunca CID). Escrita: apoio.solicitacao_epi.

``RepositorioMemoria`` serve para testes e para o simulador.
``RepositorioSQL`` concentra as consultas num lugar só; os nomes de colunas
seguem o rascunho do relatório v0.7 (capítulo 5) e devem ser conferidos com o
DDL do banco semente antes do commit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Protocol


@dataclass
class Colaborador:
    id_colaborador: int
    nome: str
    id_cargo: int | None = None
    cargo: str | None = None
    jornada_inicio: str | None = None   # "07:00"
    jornada_fim: str | None = None


@dataclass
class Situacao:
    estado: str                          # "ativo" | "afastado" | "ferias"
    retorno: date | None = None


@dataclass
class EPI:
    id_epi: int
    nome: str


class Repositorio(Protocol):
    def colaborador(self, id_colaborador: int) -> Colaborador | None: ...

    def situacao(self, id_colaborador: int, dia: date) -> Situacao: ...

    def epi(self, id_epi: int) -> EPI | None: ...

    def epis_do_cargo(self, id_cargo: int) -> list[EPI]: ...

    def abrir_solicitacao_epi(
        self, *, id_colaborador: int, id_epi: int | None, situacao: str, descricao: str, origem_id_mensagem: str
    ) -> int: ...

    def solicitacao_aberta(self, id_colaborador: int, id_epi: int | None) -> int | None:
        """ID de uma solicitação ainda ABERTA do mesmo colaborador para o mesmo EPI (evita pedido duplicado)."""
        ...


@dataclass
class RepositorioMemoria:
    colaboradores: dict[int, Colaborador] = field(default_factory=dict)
    epis: dict[int, EPI] = field(default_factory=dict)
    cargo_epis: dict[int, list[int]] = field(default_factory=dict)
    # (id_colaborador, inicio, fim, estado)
    periodos: list[tuple[int, date, date, str]] = field(default_factory=list)
    solicitacoes: dict[str, dict] = field(default_factory=dict)   # origem_id_mensagem -> registro
    _proximo_id: int = 58

    def colaborador(self, id_colaborador):
        return self.colaboradores.get(id_colaborador)

    def situacao(self, id_colaborador, dia):
        for idc, ini, fim, estado in self.periodos:
            if idc == id_colaborador and ini <= dia <= fim:
                return Situacao(estado, fim + timedelta(days=1))
        return Situacao("ativo")

    def epi(self, id_epi):
        return self.epis.get(id_epi)

    def epis_do_cargo(self, id_cargo):
        return [self.epis[i] for i in self.cargo_epis.get(id_cargo, []) if i in self.epis]

    def solicitacao_aberta(self, id_colaborador, id_epi):
        for reg in self.solicitacoes.values():
            if reg["id_colaborador"] == id_colaborador and reg["id_epi"] == id_epi and reg["status"] == "ABERTA":
                return reg["id"]
        return None

    def abrir_solicitacao_epi(self, *, id_colaborador, id_epi, situacao, descricao, origem_id_mensagem):
        if origem_id_mensagem in self.solicitacoes:          # idempotência
            return self.solicitacoes[origem_id_mensagem]["id"]
        sid = self._proximo_id
        self._proximo_id += 1
        self.solicitacoes[origem_id_mensagem] = {
            "id": sid, "id_colaborador": id_colaborador, "id_epi": id_epi,
            "situacao": situacao, "descricao": descricao, "status": "ABERTA",
        }
        return sid


class RepositorioSQL:
    # Consultas isoladas para ajuste fácil ao DDL final do banco semente.
    SQL_COLABORADOR = """
        SELECT c.id_colaborador, c.nome, c.id_cargo, cg.nome AS cargo,
               to_char(c.jornada_inicio, 'HH24:MI') AS jornada_inicio,
               to_char(c.jornada_fim, 'HH24:MI') AS jornada_fim
        FROM cadastro.colaborador c LEFT JOIN cadastro.cargo cg ON cg.id_cargo = c.id_cargo
        WHERE c.id_colaborador = :id"""
    SQL_AFASTADO = """
        SELECT fim FROM afastamento.atestado
        WHERE id_colaborador = :id AND situacao IN ('VALIDADO', 'REGISTRADO') AND :dia BETWEEN inicio AND fim
        ORDER BY fim DESC LIMIT 1"""
    SQL_FERIAS = """
        SELECT fim FROM cadastro.ferias WHERE id_colaborador = :id AND :dia BETWEEN inicio AND fim
        ORDER BY fim DESC LIMIT 1"""
    SQL_EPI = "SELECT id_epi, nome FROM cadastro.epi WHERE id_epi = :id"
    SQL_EPIS_CARGO = """
        SELECT e.id_epi, e.nome FROM cadastro.cargo_epi ce JOIN cadastro.epi e ON e.id_epi = ce.id_epi
        WHERE ce.id_cargo = :id"""
    SQL_SOLICITACAO_ABERTA = """
        SELECT id_solicitacao FROM apoio.solicitacao_epi
        WHERE id_colaborador = :c AND id_epi IS NOT DISTINCT FROM :e AND status = 'ABERTA'
        ORDER BY id_solicitacao DESC LIMIT 1"""
    SQL_SOLICITACAO_EXISTENTE = "SELECT id_solicitacao FROM apoio.solicitacao_epi WHERE origem_id_mensagem = :m"
    SQL_ABRIR_SOLICITACAO = """
        INSERT INTO apoio.solicitacao_epi
            (id_colaborador, id_epi, situacao, descricao, status, origem, origem_id_mensagem)
        VALUES (:c, :e, :s, :d, 'ABERTA', 'A2', :m)
        ON CONFLICT (origem_id_mensagem) DO NOTHING
        RETURNING id_solicitacao"""

    def __init__(self, engine):
        self.engine = engine

    def _um(self, sql, **params):
        from sqlalchemy import text

        with self.engine.connect() as cx:
            return cx.execute(text(sql), params).mappings().first()

    def colaborador(self, id_colaborador):
        r = self._um(self.SQL_COLABORADOR, id=id_colaborador)
        return Colaborador(**dict(r)) if r else None

    def situacao(self, id_colaborador, dia):
        r = self._um(self.SQL_AFASTADO, id=id_colaborador, dia=dia)
        if r:
            return Situacao("afastado", r["fim"] + timedelta(days=1))
        r = self._um(self.SQL_FERIAS, id=id_colaborador, dia=dia)
        if r:
            return Situacao("ferias", r["fim"] + timedelta(days=1))
        return Situacao("ativo")

    def epi(self, id_epi):
        r = self._um(self.SQL_EPI, id=id_epi)
        return EPI(**dict(r)) if r else None

    def epis_do_cargo(self, id_cargo):
        from sqlalchemy import text

        with self.engine.connect() as cx:
            return [EPI(**dict(r)) for r in cx.execute(text(self.SQL_EPIS_CARGO), {"id": id_cargo}).mappings()]

    def solicitacao_aberta(self, id_colaborador, id_epi):
        r = self._um(self.SQL_SOLICITACAO_ABERTA, c=id_colaborador, e=id_epi)
        return int(r["id_solicitacao"]) if r else None

    def abrir_solicitacao_epi(self, *, id_colaborador, id_epi, situacao, descricao, origem_id_mensagem):
        from sqlalchemy import text

        with self.engine.begin() as cx:
            novo = cx.execute(text(self.SQL_ABRIR_SOLICITACAO), {
                "c": id_colaborador, "e": id_epi, "s": situacao, "d": descricao[:500], "m": origem_id_mensagem,
            }).scalar()
            if novo is not None:
                return int(novo)
            return int(cx.execute(text(self.SQL_SOLICITACAO_EXISTENTE), {"m": origem_id_mensagem}).scalar_one())
