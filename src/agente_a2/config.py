"""Configuração do A2 lida do ambiente (.env)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


def _env(nome: str, padrao: str) -> str:
    return os.getenv(nome, padrao)


def _float(nome: str, padrao: float) -> float:
    return float(os.getenv(nome, str(padrao)))


@dataclass
class ConfigA2:
    # LLM (Groq via LangChain). Sem GROQ_API_KEY o A2 roda em modo extrativo.
    groq_api_key: str | None = field(default_factory=lambda: os.getenv("GROQ_API_KEY"))
    groq_modelo: str = field(default_factory=lambda: _env("GROQ_MODELO", "openai/gpt-oss-120b"))
    llm_temperatura: float = field(default_factory=lambda: _float("LLM_TEMPERATURA", 0.1))
    llm_timeout_s: float = field(default_factory=lambda: _float("LLM_TIMEOUT_S", 20))

    # Embeddings: "sentence_transformers" (padrão) ou "hashing" (testes, sem download)
    embeddings_provedor: str = field(default_factory=lambda: _env("EMBEDDINGS_PROVEDOR", "sentence_transformers"))
    embeddings_modelo: str = field(
        default_factory=lambda: _env(
            "EMBEDDINGS_MODELO", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        )
    )
    embeddings_dim: int = field(default_factory=lambda: int(_env("EMBEDDINGS_DIM", "384")))

    # Armazenamento do índice: "memoria" (arquivo local) ou "pgvector"
    store: str = field(default_factory=lambda: _env("RAG_STORE", "memoria"))
    database_url: str | None = field(default_factory=lambda: os.getenv("DATABASE_URL"))
    indice_local: Path = field(default_factory=lambda: Path(_env("RAG_INDICE_LOCAL", str(RAIZ / "indice_local"))))
    pasta_bases: Path = field(default_factory=lambda: Path(_env("RAG_PASTA_BASES", str(RAIZ / "bases_pdf"))))

    # Recuperação
    top_k: int = field(default_factory=lambda: int(_env("RAG_TOP_K", "4")))
    candidatos: int = field(default_factory=lambda: int(_env("RAG_CANDIDATOS", "20")))
    peso_vetorial: float = field(default_factory=lambda: _float("RAG_PESO_VETORIAL", 0.6))
    # Limiares de aceitação (calibrar por modelo com `python -m agente_a2 calibrar`)
    limiar_cosseno: float | None = field(
        default_factory=lambda: float(os.environ["RAG_LIMIAR_COSSENO"]) if "RAG_LIMIAR_COSSENO" in os.environ else None
    )
    limiar_bm25: float = field(default_factory=lambda: _float("RAG_LIMIAR_BM25", 4.0))
    # Pontuação final mínima do melhor trecho para considerar que a base cobre a pergunta
    limiar_pontuacao: float = field(default_factory=lambda: _float("RAG_LIMIAR_PONTUACAO", 0.40))
    margem_relativa: float = field(default_factory=lambda: _float("RAG_MARGEM_RELATIVA", 0.6))

    # RAG completo: reescrita da pergunta pelo LLM (multi-consulta) e complemento de conhecimento geral
    rag_reescrita: bool = field(default_factory=lambda: _env("RAG_REESCRITA", "1") == "1")
    rag_complemento: bool = field(default_factory=lambda: _env("RAG_COMPLEMENTO", "1") == "1")

    # Documento vigente: no protótipo as 4 bases estão com aprovação PENDENTE.
    # Em produção, ligar para exigir aprovação antes de responder.
    exigir_aprovacao: bool = field(default_factory=lambda: _env("RAG_EXIGIR_APROVACAO", "0") == "1")

    # Guardrails
    max_chars_pergunta: int = field(default_factory=lambda: int(_env("A2_MAX_CHARS_PERGUNTA", "1500")))
    max_chars_resposta: int = field(default_factory=lambda: int(_env("A2_MAX_CHARS_RESPOSTA", "900")))
    cache_respostas: bool = field(default_factory=lambda: _env("A2_CACHE_RESPOSTAS", "1") == "1")
    fuso: str = field(default_factory=lambda: _env("A2_FUSO", "America/Sao_Paulo"))

    # Registro de interações (melhoria contínua). SQLite local por padrão; Postgres pela URL.
    registrar_interacoes: bool = field(default_factory=lambda: _env("A2_REGISTRAR_INTERACOES", "1") == "1")
    interacoes_db_url: str = field(default_factory=lambda: _env(
        "INTERACOES_DB_URL", "sqlite:///" + (RAIZ / "dados" / "interacoes.db").as_posix()))
    sal_pseudonimo: str = field(default_factory=lambda: _env("A2_SAL_PSEUDONIMO", "sinergia-dev"))
    retencao_dias: int = field(default_factory=lambda: int(_env("A2_RETENCAO_DIAS", "180")))

    def limiar_cosseno_efetivo(self) -> float:
        if self.limiar_cosseno is not None:
            return self.limiar_cosseno
        # Valores iniciais; o comando `calibrar` sugere o ajuste fino.
        return 0.30 if self.embeddings_provedor == "hashing" else 0.45
