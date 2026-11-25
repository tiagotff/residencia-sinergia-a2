"""Ingestão: PDF -> perguntas -> trechos -> embeddings -> store.

Idempotente pelo sha256 do arquivo: reprocessar o mesmo PDF não grava nada.
Uma versão nova do PDF (outro sha) substitui a versão ativa da base.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict
from pathlib import Path

from .catalogo import BASES
from .chunking import gerar_trechos
from .embeddings import Embedder
from .parser_pdf import ler_pdf
from .stores import Store

log = logging.getLogger(__name__)


ARQUIVO_EXTRAS = "variacoes_extras.json"


def carregar_extras(pasta: Path) -> dict[str, list[str]]:
    """Variações extras por ID (aprendidas com as interações). Chaves com '_' são comentários."""
    caminho = pasta / ARQUIVO_EXTRAS
    if not caminho.exists():
        return {}
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    return {k: [str(v).strip() for v in vs if str(v).strip()] for k, vs in dados.items()
            if not k.startswith("_") and isinstance(vs, list)}


def ingerir_pasta(pasta: Path, store: Store, embedder: Embedder) -> dict[str, dict]:
    relatorio: dict[str, dict] = {}
    extras = carregar_extras(pasta)
    for base in BASES.values():
        caminho = pasta / base.arquivo
        if not caminho.exists():
            relatorio[base.slug] = {"status": "arquivo_ausente", "arquivo": str(caminho)}
            log.warning("Base %s sem arquivo (%s)", base.slug, caminho)
            continue
        doc = ler_pdf(caminho, base.slug)
        esperado = base.prefixo_id
        fora = [p.id_pergunta for p in doc.perguntas if not p.id_pergunta.startswith(esperado)]
        if fora:
            raise ValueError(f"{caminho.name}: IDs fora do prefixo {esperado}: {fora[:5]}")
        extras_base = {k: v for k, v in extras.items() if k.startswith(esperado)}
        if extras_base:
            # A assinatura do documento inclui as variações extras: editar o JSON reindexa a base.
            doc.sha256 = hashlib.sha256((doc.sha256 + json.dumps(extras_base, sort_keys=True,
                                                                 ensure_ascii=False)).encode()).hexdigest()
        trechos = gerar_trechos(doc, extras=extras_base)
        vetores = embedder.embed_documentos([t.texto_indexado for t in trechos])
        for t, v in zip(trechos, vetores):
            t.embedding = v
        gravou = store.salvar_documento(base.slug, trechos)
        relatorio[base.slug] = {
            "status": "ingerido" if gravou else "sem_mudanca",
            "titulo": doc.titulo,
            "versao": doc.versao,
            "vigencia_inicio": doc.vigencia_inicio.isoformat() if doc.vigencia_inicio else None,
            "aprovacao": doc.aprovacao,
            "perguntas": len(doc.perguntas),
            "trechos": len(trechos),
            "variacoes_extras": sum(len(v) for v in extras_base.values()),
            "modelo_embedding": embedder.nome,
        }
    return relatorio


def exportar_json(pasta: Path, destino: Path) -> None:
    """Exporta o que o parser entendeu de cada PDF, para revisão humana."""
    saida = {}
    for base in BASES.values():
        caminho = pasta / base.arquivo
        if caminho.exists():
            doc = ler_pdf(caminho, base.slug)
            d = asdict(doc)
            d["vigencia_inicio"] = doc.vigencia_inicio.isoformat() if doc.vigencia_inicio else None
            saida[base.slug] = d
    destino.write_text(json.dumps(saida, ensure_ascii=False, indent=2), encoding="utf-8")
