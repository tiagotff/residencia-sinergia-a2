"""Console A2: fluxo da API local e blindagem (só loopback, host fixo, token, sem API pública)."""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

LOCAL = ("127.0.0.1", 50000)


@pytest.fixture(scope="module")
def modulo(tmp_path_factory):
    import os

    pasta = tmp_path_factory.mktemp("web")
    antes = dict(os.environ)
    os.environ.update({"EMBEDDINGS_PROVEDOR": "hashing", "RAG_INDICE_LOCAL": str(pasta / "idx"),
                       "INTERACOES_DB_URL": f"sqlite:///{(pasta / 'i.db').as_posix()}", "GROQ_API_KEY": "",
                       "DATABASE_URL": ""})
    from agente_a2.web import app as m

    m._ctx = None
    yield m
    m._ctx = None
    os.environ.clear()
    os.environ.update(antes)


@pytest.fixture(scope="module")
def cliente(modulo):
    c = TestClient(modulo.app, base_url="http://127.0.0.1:8000", client=LOCAL)
    c.headers["X-A2-Token"] = c.get("/api/sessao").json()["token"]
    c.post("/api/ingerir")
    return c


def test_fluxo_completo(cliente):
    st = cliente.get("/api/status").json()
    assert not st["indice_vazio"] and len(st["bases"]) == 4
    assert st["registro"].startswith("SQLite local") and st["registro_local"] is True
    r = cliente.post("/api/chat", json={"pergunta": "posso vender minhas férias?", "id_colaborador": 42}).json()
    assert r["resultado"]["payload"]["base"] == "direitos_beneficios"
    assert r["raio_x"]["telemetria"]["diag"]["candidatos"]
    i = r["id_interacao"]
    assert cliente.post(f"/api/interacoes/{i}/feedback", json={"avaliacao": "negativo", "categoria": "base_errada"}).status_code == 200
    assert cliente.get("/api/interacoes").json()["total"] >= 1
    assert cliente.get(f"/api/interacoes/{i}").json()["feedbacks"][0]["categoria"] == "base_errada"
    assert cliente.get("/api/melhoria").json()["por_motivo"]["feedback_negativo"] >= 1
    assert cliente.get("/api/metricas").json()["total"] >= 1
    assert cliente.get("/api/exportar?formato=dataset").text.strip()
    assert len(cliente.get("/api/bases").json()) == 4
    assert cliente.get("/api/colaboradores").json()[0]["nome"]


def test_playground(cliente):
    fx = cliente.get("/api/fixtures").json()
    tarefa = next(f for f in fx if f["nome"] == "orientar_epi/vida_util_15d")["tarefa"]
    r = cliente.post("/api/playground", json={"tarefa": tarefa}).json()
    assert r["resultado"]["status"] == "OK" and r["raio_x"]["telemetria"]["modo"] == "fixo_f6"


def test_erros(cliente):
    assert cliente.get("/api/interacoes/999999").status_code == 404
    assert cliente.post("/api/interacoes/999999/feedback", json={"avaliacao": "positivo"}).status_code == 404
    assert cliente.get("/api/bases/inexistente/perguntas").status_code == 404


# ------------------------------------------------------------------ blindagem

def test_sem_api_publica(cliente):
    for rota in ("/docs", "/redoc", "/openapi.json"):
        r = cliente.get(rota)
        assert "swagger" not in r.text.lower() and "openapi" not in r.text.lower()
    assert cliente.post("/executar", json={}).status_code in (404, 405)


def test_exige_token(modulo, cliente):
    sem = TestClient(modulo.app, base_url="http://127.0.0.1:8000", client=LOCAL)
    assert sem.get("/api/status").status_code == 401
    assert sem.get("/api/exportar?formato=csv").status_code == 401
    assert sem.get("/api/status", headers={"X-A2-Token": "errado"}).status_code == 401


def test_bloqueia_outra_maquina(modulo, cliente):
    rede = TestClient(modulo.app, base_url="http://127.0.0.1:8000", client=("192.168.0.50", 50000))
    assert rede.get("/api/sessao").status_code == 403
    assert rede.get("/").status_code == 403


def test_bloqueia_dns_rebinding_e_origem(modulo, cliente):
    rebind = TestClient(modulo.app, base_url="http://site-malicioso.com", client=LOCAL)
    assert rebind.get("/api/sessao").status_code == 400
    r = cliente.get("/api/status", headers={"Origin": "https://site-malicioso.com"})
    assert r.status_code == 403


def test_cabecalhos_de_seguranca(cliente):
    r = cliente.get("/api/status")
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-frame-options"] == "DENY" and r.headers["cache-control"] == "no-store"
    assert "server" not in {k.lower() for k in r.headers} or "uvicorn" not in r.headers.get("server", "")
