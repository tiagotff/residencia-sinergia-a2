-- Schema rag do A2 (PostgreSQL 16 + pgvector). Rodar antes de `python -m agente_a2 ingerir` com RAG_STORE=pgvector.
-- A dimensão do vetor acompanha o modelo de embeddings (MiniLM multilíngue = 384).
-- Validar contra o Alembic do banco semente antes de commitar.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS rag;

CREATE TABLE IF NOT EXISTS rag.base (
    id              serial PRIMARY KEY,
    slug            text NOT NULL UNIQUE,          -- epi | pausas_ergonomia | saude_ocupacional | direitos_beneficios
    nome            text NOT NULL,
    funcionalidades text[] NOT NULL DEFAULT '{}',
    ativa           boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS rag.documento (
    id              serial PRIMARY KEY,
    id_base         int NOT NULL REFERENCES rag.base (id),
    titulo          text NOT NULL,
    codigo          text,
    versao          text NOT NULL,
    vigencia_inicio date,
    vigencia_fim    date,
    aprovacao       text,                          -- "PENDENTE — ..." | "APROVADO ..."
    sha256          char(64) NOT NULL UNIQUE,      -- idempotência da ingestão
    ativo           boolean NOT NULL DEFAULT true,
    ingerido_em     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id_base, versao)
);
-- Uma única versão ativa por base
CREATE UNIQUE INDEX IF NOT EXISTS documento_ativo_por_base ON rag.documento (id_base) WHERE ativo;

CREATE TABLE IF NOT EXISTS rag.trecho (
    id              bigserial PRIMARY KEY,
    id_documento    int NOT NULL REFERENCES rag.documento (id) ON DELETE CASCADE,
    id_trecho       text NOT NULL,                 -- "EPI-Q025#1"
    id_pergunta     text NOT NULL,                 -- "EPI-Q025" (unidade de citação)
    parte           smallint NOT NULL DEFAULT 1,
    ordem           int NOT NULL,
    secao           text,
    titulo          text NOT NULL,
    variacoes       text[] NOT NULL DEFAULT '{}',
    resposta        text NOT NULL,
    fonte           text,
    tipos_fonte     text[] NOT NULL DEFAULT '{}',  -- {OFICIAL, INTERNO}
    texto_indexado  text NOT NULL,
    embedding       vector(384) NOT NULL,
    UNIQUE (id_documento, id_trecho)
);
CREATE INDEX IF NOT EXISTS trecho_embedding_hnsw ON rag.trecho USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS trecho_id_pergunta ON rag.trecho (id_pergunta);

INSERT INTO rag.base (slug, nome, funcionalidades) VALUES
    ('epi', 'EPI', '{F5,F6}'),
    ('pausas_ergonomia', 'Pausas e Ergonomia', '{F1}'),
    ('saude_ocupacional', 'Saúde Ocupacional', '{F4}'),
    ('direitos_beneficios', 'Benefícios e Direitos Trabalhistas', '{F2}')
ON CONFLICT (slug) DO NOTHING;

-- Conta de serviço do A2 (relatório 5.1): lê e grava rag e bem_estar; só grava apoio.solicitacao_epi.
-- CREATE ROLE svc_a2 LOGIN PASSWORD '...';
-- GRANT USAGE ON SCHEMA rag TO svc_a2;
-- GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA rag TO svc_a2;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA rag TO svc_a2;

-- Coluna esperada pelo A2 em apoio.solicitacao_epi (idempotência por TAREFA):
-- ALTER TABLE apoio.solicitacao_epi ADD COLUMN IF NOT EXISTS origem_id_mensagem text UNIQUE;
