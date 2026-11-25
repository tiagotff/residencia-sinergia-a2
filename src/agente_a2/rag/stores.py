"""Armazenamento do índice RAG.

* ``StoreMemoria`` — índice num arquivo JSON local (``indice_local/``). Bom
  para desenvolvimento e testes: as 4 bases somam ~130 trechos.
* ``StorePGVector`` — schema ``rag`` do PostgreSQL + pgvector (DDL em
  ``sql/001_rag_schema.sql``), que é o alvo do relatório v0.7.

Regra de vigência (relatório 12.7): só entram na busca trechos de documento
ativo, com ``vigencia_inicio <= hoje`` e, se ``exigir_aprovacao``, aprovado.
Uma nova versão do mesmo documento desativa a anterior na ingestão.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Protocol

from .catalogo import BASES
from .chunking import Trecho


class Store(Protocol):
    def salvar_documento(self, base: str, trechos: list[Trecho]) -> bool: ...

    def trechos_vigentes(self, hoje: date) -> list[Trecho]: ...

    def buscar_vetorial(self, vetor: list[float], k: int, hoje: date) -> list[tuple[Trecho, float]]: ...

    def bases_vigentes(self, hoje: date) -> dict[str, tuple[str, str]]: ...

    def assinatura(self, hoje: date) -> str: ...


def _aprovado(aprovacao: str | None) -> bool:
    return bool(aprovacao) and aprovacao.strip().upper().startswith("APROVAD")


def _vigente(t: Trecho, hoje: date, exigir_aprovacao: bool) -> bool:
    if t.vigencia_inicio and t.vigencia_inicio > hoje:
        return False
    return _aprovado(t.aprovacao) if exigir_aprovacao else True


def _cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))  # vetores já normalizados


class StoreMemoria:
    def __init__(self, caminho: Path | None = None, exigir_aprovacao: bool = False):
        self.caminho = caminho
        self.exigir_aprovacao = exigir_aprovacao
        # base -> lista de trechos do documento ativo (uma versão ativa por base)
        self._ativos: dict[str, list[Trecho]] = {}
        if caminho and (caminho / "indice.json").exists():
            self._carregar()

    # ---------- persistência ----------
    def _carregar(self) -> None:
        dados = json.loads((self.caminho / "indice.json").read_text(encoding="utf-8"))
        for base, lista in dados["bases"].items():
            trechos = []
            for d in lista:
                d["vigencia_inicio"] = date.fromisoformat(d["vigencia_inicio"]) if d["vigencia_inicio"] else None
                trechos.append(Trecho(**d))
            self._ativos[base] = trechos

    def _gravar(self) -> None:
        if not self.caminho:
            return
        self.caminho.mkdir(parents=True, exist_ok=True)
        serial = {
            base: [{**asdict(t), "vigencia_inicio": t.vigencia_inicio.isoformat() if t.vigencia_inicio else None}
                   for t in lista]
            for base, lista in self._ativos.items()
        }
        (self.caminho / "indice.json").write_text(
            json.dumps({"versao_indice": 1, "bases": serial}, ensure_ascii=False), encoding="utf-8"
        )

    # ---------- API ----------
    def salvar_documento(self, base: str, trechos: list[Trecho]) -> bool:
        """Substitui a versão ativa da base. Devolve False se o arquivo é o mesmo."""
        atuais = self._ativos.get(base)
        if atuais and trechos and atuais[0].documento_sha256 == trechos[0].documento_sha256:
            return False
        self._ativos[base] = trechos
        self._gravar()
        return True

    def trechos_vigentes(self, hoje: date) -> list[Trecho]:
        return [t for lista in self._ativos.values() for t in lista if _vigente(t, hoje, self.exigir_aprovacao)]

    def buscar_vetorial(self, vetor: list[float], k: int, hoje: date) -> list[tuple[Trecho, float]]:
        pontuados = [(t, _cos(vetor, t.embedding)) for t in self.trechos_vigentes(hoje) if t.embedding]
        pontuados.sort(key=lambda x: x[1], reverse=True)
        return pontuados[:k]

    def bases_vigentes(self, hoje: date) -> dict[str, tuple[str, str]]:
        """base -> (título, versão) dos documentos vigentes."""
        saida: dict[str, tuple[str, str]] = {}
        for t in self.trechos_vigentes(hoje):
            saida.setdefault(t.base, (t.documento_titulo, t.documento_versao))
        return saida

    def assinatura(self, hoje: date) -> str:
        shas = sorted({t.documento_sha256 for t in self.trechos_vigentes(hoje)})
        return hashlib.sha256("|".join(shas).encode()).hexdigest()[:16]


class StorePGVector:
    """Schema rag (rag.base, rag.documento, rag.trecho) com pgvector.

    Usa SQLAlchemy Core com SQL explícito para ficar legível para o grupo.
    Nota: escrito contra o DDL de ``sql/001_rag_schema.sql``; validar no banco
    semente antes do commit.
    """

    def __init__(self, database_url: str, exigir_aprovacao: bool = False):
        from sqlalchemy import create_engine

        self.engine = create_engine(database_url, pool_pre_ping=True)
        self.exigir_aprovacao = exigir_aprovacao

    @staticmethod
    def _vec(v: list[float]) -> str:
        return "[" + ",".join(f"{x:.6f}" for x in v) + "]"

    def _filtro_vigencia(self) -> str:
        filtro = "d.ativo AND (d.vigencia_inicio IS NULL OR d.vigencia_inicio <= :hoje) " \
                 "AND (d.vigencia_fim IS NULL OR d.vigencia_fim >= :hoje)"
        if self.exigir_aprovacao:
            filtro += " AND upper(d.aprovacao) LIKE 'APROVAD%'"
        return filtro

    def salvar_documento(self, base: str, trechos: list[Trecho]) -> bool:
        from sqlalchemy import text

        if not trechos:
            return False
        t0 = trechos[0]
        with self.engine.begin() as cx:
            existe = cx.execute(text("SELECT 1 FROM rag.documento WHERE sha256 = :s"), {"s": t0.documento_sha256}).first()
            if existe:
                return False
            id_base = cx.execute(
                text("INSERT INTO rag.base (slug, nome, funcionalidades) VALUES (:slug, :nome, :f) "
                     "ON CONFLICT (slug) DO UPDATE SET nome = EXCLUDED.nome RETURNING id"),
                {"slug": base, "nome": BASES[base].nome if base in BASES else base,
                 "f": list(BASES[base].funcionalidades) if base in BASES else []},
            ).scalar_one()
            # desativa versões anteriores da mesma base
            cx.execute(
                text("UPDATE rag.documento SET ativo = false, vigencia_fim = COALESCE(vigencia_fim, :fim) "
                     "WHERE id_base = :b AND ativo"),
                {"b": id_base, "fim": t0.vigencia_inicio},
            )
            id_doc = cx.execute(
                text("INSERT INTO rag.documento (id_base, titulo, versao, vigencia_inicio, aprovacao, sha256, ativo) "
                     "VALUES (:b, :t, :v, :vi, :a, :s, true) RETURNING id"),
                {"b": id_base, "t": t0.documento_titulo, "v": t0.documento_versao, "vi": t0.vigencia_inicio,
                 "a": t0.aprovacao, "s": t0.documento_sha256},
            ).scalar_one()
            for t in trechos:
                cx.execute(
                    text("INSERT INTO rag.trecho (id_documento, id_trecho, id_pergunta, parte, ordem, secao, titulo, "
                         "variacoes, resposta, fonte, tipos_fonte, texto_indexado, embedding) VALUES "
                         "(:d, :it, :ip, :p, :o, :s, :t, :var, :r, :f, :tf, :ti, CAST(:e AS vector))"),
                    {"d": id_doc, "it": t.id_trecho, "ip": t.id_pergunta, "p": t.parte, "o": t.ordem, "s": t.secao,
                     "t": t.titulo, "var": t.variacoes, "r": t.resposta, "f": t.fonte, "tf": t.tipos_fonte,
                     "ti": t.texto_indexado, "e": self._vec(t.embedding or [])},
                )
        return True

    _SELECT = (
        "SELECT t.id_trecho, t.id_pergunta, t.parte, b.slug AS base, d.titulo AS documento_titulo, "
        "d.versao AS documento_versao, d.sha256 AS documento_sha256, d.vigencia_inicio, d.aprovacao, t.secao, "
        "t.titulo, t.variacoes, t.resposta, t.fonte, t.tipos_fonte, t.ordem, t.texto_indexado "
        "FROM rag.trecho t JOIN rag.documento d ON d.id = t.id_documento JOIN rag.base b ON b.id = d.id_base "
    )

    def trechos_vigentes(self, hoje: date) -> list[Trecho]:
        from sqlalchemy import text

        with self.engine.connect() as cx:
            linhas = cx.execute(text(self._SELECT + "WHERE " + self._filtro_vigencia()), {"hoje": hoje}).mappings()
            return [Trecho(**dict(l)) for l in linhas]

    def buscar_vetorial(self, vetor: list[float], k: int, hoje: date) -> list[tuple[Trecho, float]]:
        from sqlalchemy import text

        sql = (self._SELECT.replace("SELECT ", "SELECT 1 - (t.embedding <=> CAST(:q AS vector)) AS similaridade, ", 1)
               + "WHERE " + self._filtro_vigencia() + " ORDER BY t.embedding <=> CAST(:q AS vector) LIMIT :k")
        with self.engine.connect() as cx:
            linhas = cx.execute(text(sql), {"q": self._vec(vetor), "k": k, "hoje": hoje}).mappings()
            saida = []
            for l in linhas:
                d = dict(l)
                sim = float(d.pop("similaridade"))
                saida.append((Trecho(**d), sim))
            return saida

    def bases_vigentes(self, hoje: date) -> dict[str, tuple[str, str]]:
        from sqlalchemy import text

        sql = ("SELECT b.slug, d.titulo, d.versao FROM rag.documento d JOIN rag.base b ON b.id = d.id_base WHERE "
               + self._filtro_vigencia())
        with self.engine.connect() as cx:
            return {r.slug: (r.titulo, r.versao) for r in cx.execute(text(sql), {"hoje": hoje})}

    def assinatura(self, hoje: date) -> str:
        from sqlalchemy import text

        sql = "SELECT string_agg(d.sha256, '|' ORDER BY d.sha256) FROM rag.documento d WHERE " + self._filtro_vigencia()
        with self.engine.connect() as cx:
            v = cx.execute(text(sql), {"hoje": hoje}).scalar() or ""
        return hashlib.sha256(v.encode()).hexdigest()[:16]

