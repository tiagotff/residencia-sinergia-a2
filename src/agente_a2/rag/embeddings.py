"""Geradores de embeddings.

* ``SentenceTransformerEmbedder`` — padrão. Modelo multilíngue local
  (paraphrase-multilingual-MiniLM-L12-v2, 384 dim), roda em CPU e não envia
  texto para fora (o Groq não oferece embeddings e mandar perguntas de
  colaboradores a um terceiro só para indexar não vale o risco de LGPD).
  Para e5 (``intfloat/multilingual-e5-*``) use os prefixos query:/passage:.
* ``HashingEmbedder`` — determinístico, sem download; usado em testes e CI.
  Não é semântico (n-gramas de caracteres), então o BM25 faz o trabalho pesado.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

from ..texto import dobrar


class Embedder(Protocol):
    nome: str
    dim: int

    def embed_documentos(self, textos: list[str]) -> list[list[float]]: ...

    def embed_consulta(self, texto: str) -> list[float]: ...


class SentenceTransformerEmbedder:
    def __init__(self, modelo: str, dim: int = 384):
        from sentence_transformers import SentenceTransformer  # import tardio

        self.nome = modelo
        self._modelo = SentenceTransformer(modelo)
        self.dim = int(self._modelo.get_sentence_embedding_dimension() or dim)
        e5 = "e5" in modelo.lower()
        self._pref_doc = "passage: " if e5 else ""
        self._pref_q = "query: " if e5 else ""

    def embed_documentos(self, textos: list[str]) -> list[list[float]]:
        vetores = self._modelo.encode(
            [self._pref_doc + t for t in textos], normalize_embeddings=True, batch_size=32
        )
        return [v.tolist() for v in vetores]

    def embed_consulta(self, texto: str) -> list[float]:
        return self._modelo.encode(self._pref_q + texto, normalize_embeddings=True).tolist()


class HashingEmbedder:
    def __init__(self, dim: int = 384):
        self.nome = f"hashing-{dim}"
        self.dim = dim

    def _vetor(self, texto: str) -> list[float]:
        v = [0.0] * self.dim
        t = dobrar(texto)
        palavras = re.findall(r"[a-z0-9]+", t)
        feats = palavras + [f"#{p[i:i + 4]}" for p in palavras if len(p) > 4 for i in range(len(p) - 3)]
        for f in feats:
            h = int(hashlib.md5(f.encode()).hexdigest(), 16)
            v[h % self.dim] += 1.0 if (h >> 8) & 1 else -1.0
        norma = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norma for x in v]

    def embed_documentos(self, textos: list[str]) -> list[list[float]]:
        return [self._vetor(t) for t in textos]

    def embed_consulta(self, texto: str) -> list[float]:
        return self._vetor(texto)


def criar_embedder(provedor: str, modelo: str, dim: int) -> Embedder:
    if provedor == "hashing":
        return HashingEmbedder(dim)
    if provedor == "sentence_transformers":
        return SentenceTransformerEmbedder(modelo, dim)
    raise ValueError(f"EMBEDDINGS_PROVEDOR desconhecido: {provedor}")
