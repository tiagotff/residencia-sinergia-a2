from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from agente_a2 import AgenteA2, ConfigA2
from agente_a2.rag.embeddings import HashingEmbedder
from agente_a2.rag.ingestao import ingerir_pasta
from agente_a2.rag.stores import StoreMemoria
from agente_a2.repositorio import EPI, Colaborador, RepositorioMemoria

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def config() -> ConfigA2:
    return ConfigA2(embeddings_provedor="hashing", groq_api_key=None, cache_respostas=True)


@pytest.fixture(scope="session")
def embedder():
    return HashingEmbedder()


@pytest.fixture(scope="session")
def store(embedder):
    s = StoreMemoria()
    rel = ingerir_pasta(RAIZ / "bases_pdf", s, embedder)
    assert all(r["status"] == "ingerido" for r in rel.values()), rel
    return s


@pytest.fixture
def repositorio():
    return RepositorioMemoria(
        colaboradores={
            42: Colaborador(42, "Carla Souza", 15, "Auxiliar de câmara fria", "07:00", "16:00"),
            57: Colaborador(57, "Bruno Lima", 16, "Operador de empilhadeira", "08:00", "17:00"),
            63: Colaborador(63, "Ana Reis", 15, "Auxiliar de câmara fria", "07:00", "16:00"),
        },
        epis={7: EPI(7, "Luva térmica"), 8: EPI(8, "Luva anticorte"), 12: EPI(12, "Protetor auricular")},
        cargo_epis={15: [7, 8], 16: [12]},
        periodos=[(63, date(2026, 11, 22), date(2026, 12, 2), "ferias")],
    )


@pytest.fixture
def agente(store, embedder, config, repositorio):
    def _criar(llm=None):
        return AgenteA2(llm=llm, store=store, embedder=embedder, repositorio=repositorio, config=config)
    return _criar


@pytest.fixture
def tarefa():
    contador = {"n": 0}

    def _t(payload: dict, acao: str = "a2.responder", id_colaborador: int = 42, **extra) -> dict:
        contador["n"] += 1
        idm = extra.pop("id_mensagem", f"t-900-{contador['n']:02d}")
        base = {
            "protocolo": "sinergia/1", "id_mensagem": idm, "tipo": "TAREFA", "acao": acao,
            "origem": "A0", "destino": "A2",
            "correlacao": {"id_caso": None, "thread_id": f"chat-{id_colaborador}-900", "id_tarefa": idm},
            "contexto": {"id_colaborador": id_colaborador, "id_empresa": 1, "perfil": "colaborador",
                         "canal": "chat", "data_hora": "2026-11-25T09:00:00-03:00"},
            "payload": payload,
        }
        base.update(extra)
        return base
    return _t


def json_llm(resposta: str, ids: list[str], cobertura="total", relato=None, sensivel=False) -> str:
    return json.dumps({"resposta": resposta, "ids_usados": ids, "cobertura": cobertura,
                       "sensivel": sensivel, "relato_epi": relato}, ensure_ascii=False)
