from pathlib import Path

import pytest

from agente_a2.rag.catalogo import BASES, base_do_id
from agente_a2.rag.chunking import gerar_trechos
from agente_a2.rag.parser_pdf import ler_pdf

PASTA = Path(__file__).resolve().parents[1] / "bases_pdf"

ESPERADO = {
    "epi": (70, "1.3", "2026-11-25"),
    "pausas_ergonomia": (27, "2.1", "2026-11-25"),
    "saude_ocupacional": (63, "1.1", "2026-11-25"),
    "direitos_beneficios": (30, "1.1", "2026-11-25"),
}


@pytest.mark.parametrize("slug", list(ESPERADO))
def test_documento_completo(slug):
    doc = ler_pdf(PASTA / BASES[slug].arquivo, slug)
    n, versao, vigencia = ESPERADO[slug]
    assert len(doc.perguntas) == n
    assert doc.versao == versao
    assert doc.vigencia_inicio.isoformat() == vigencia
    ids = [p.id_pergunta for p in doc.perguntas]
    assert len(set(ids)) == n, "IDs duplicados"
    for p in doc.perguntas:
        assert p.titulo and p.resposta and p.variacoes, p.id_pergunta
        assert p.tipos_fonte, f"{p.id_pergunta} sem (OFICIAL)/(INTERNO) na fonte"
        assert base_do_id(p.id_pergunta) == slug


def test_simbolos_preservados():
    doc = ler_pdf(PASTA / "direitos_beneficios.pdf", "direitos_beneficios")
    q2 = next(p for p in doc.perguntas if p.id_pergunta == "RH-BEN-Q002")
    assert "13º" in q2.titulo and "1ª parcela" in q2.resposta   # sem virar "13o"/"1a"


def test_lista_numerada_e_secao_quebrada():
    doc = ler_pdf(PASTA / "epi.pdf", "epi")
    q21 = next(p for p in doc.perguntas if p.id_pergunta == "EPI-Q021")
    assert q21.resposta.startswith("1 Relato") and "o que acontece depois que eu peço" in q21.variacoes
    assert q21.secao.endswith("tamanho inadequado)")
    assert "perdi minhas luvas" in next(p for p in doc.perguntas if p.id_pergunta == "EPI-Q026").variacoes


def test_um_trecho_por_pergunta():
    doc = ler_pdf(PASTA / "saude_ocupacional.pdf", "saude_ocupacional")
    trechos = gerar_trechos(doc)
    assert len(trechos) == len(doc.perguntas)
    t = trechos[0]
    assert t.id_trecho == "SO-Q001#1" and "Também perguntam" in t.texto_indexado
    assert t.documento_versao == "1.1"
