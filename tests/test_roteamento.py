from datetime import date

import pytest

from agente_a2.avaliacao import avaliar
from agente_a2.rag.recuperador import Recuperador

HOJE = date(2026, 11, 25)


@pytest.fixture
def rec(store, embedder, config):
    return Recuperador(store, embedder, config)


@pytest.mark.parametrize("pergunta,intencao,base", [
    ("minha luva rasgou, o que eu faço?", None, "epi"),
    ("de quanto em quanto tempo devo fazer pausa no computador?", "F1", "pausas_ergonomia"),
    ("quando faço o exame periódico?", None, "saude_ocupacional"),
    ("posso vender parte das minhas férias?", "F2", "direitos_beneficios"),
    ("quando cai o vale refeição?", None, "direitos_beneficios"),
    ("tenho que pagar o exame?", None, "saude_ocupacional"),
    ("vão descontar a bota que perdi?", "F5", "epi"),
    ("como faço alongamento de pescoço", None, "pausas_ergonomia"),
    # intenção errada do A0: a evidência dos trechos vence
    ("a máscara PFF2 pode ser lavada?", "F2", "epi"),
])
def test_base_principal(rec, pergunta, intencao, base):
    res = rec.buscar(pergunta, HOJE, intencao)
    assert res.base_principal == base, [(p.trecho.id_pergunta, p.pontuacao) for p in res.trechos]


def test_pergunta_transversal_consulta_duas_bases(rec):
    res = rec.buscar("trabalho na câmara fria, qual luva usar?", HOJE)
    assert res.base_principal == "epi"
    assert "saude_ocupacional" in res.bases


@pytest.mark.parametrize("pergunta", ["qual a senha do wifi", "quero saber do torneio de futebol"])
def test_fora_do_escopo(rec, pergunta):
    assert rec.buscar(pergunta, HOJE).vazio


def test_vigencia_futura_nao_entra(rec):
    # As versões atuais vigoram a partir de 25/11/2026: antes disso, nada é respondido.
    assert rec.buscar("quando faço o exame periódico?", date(2026, 11, 24)).vazio


def test_regressao_recall(rec):
    rel = avaliar(rec, HOJE)
    # embeddings de teste (hashing); com MiniLM os números sobem. Serve de piso contra regressão.
    assert rel.recall_3 >= 0.85, rel.texto()
    assert rel.roteamento >= 0.85, rel.texto()
