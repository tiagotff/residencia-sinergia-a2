"""Regressão a partir das interações reais da planilha a2_analise_20261125_1647.xlsx.

Cada teste reproduz um problema observado e trava a correção.
"""

import json
import re

from conftest import json_llm

from agente_a2.llm.cliente import LLMFalso


def _ids(msgs):
    return re.findall(r'<trecho id="([^"]+)"', msgs[1][1])


def test_perdi_luvas_abre_pedido_mesmo_com_llm_sem_cobertura(agente, tarefa, repositorio):
    # Interação #10: LLM disse "nenhuma" + "procure o RH"; o certo é o roteiro EPI-Q026 e abrir o pedido.
    llm = LLMFalso([json_llm("Não encontrei essa informação; procure o RH.", [], cobertura="nenhuma",
                             relato={"situacao": "perdido", "epi_mencionado": "luvas"})])
    res = agente(llm).executar(tarefa({"pergunta": "perdi as minhas luvas, o que devo fazer?"}))
    assert "EPI-Q026" in _ids(llm.chamadas[0])                      # roteiro chegou ao LLM
    assert res.status == "OK" and res.payload["id_solicitacao_epi"]
    assert "EPI-Q026" in res.payload["ids_trechos"] and "RH" not in res.saidas[0].texto
    assert next(iter(repositorio.solicitacoes.values()))["situacao"] == "perdido"


def test_perdi_luvas_sem_llm(agente, tarefa, repositorio):
    for q in ["perdi luvas", "perdi minhas luvas e agora?"]:
        repositorio.solicitacoes.clear()
        res = agente().executar(tarefa({"pergunta": q}))
        assert res.payload["ids_trechos"][0] == "EPI-Q026" and res.eventos, q


def test_pedido_sem_motivo_orienta_e_pergunta(agente, tarefa, repositorio):
    # Interações #14 e #15: "quero novas luvas" / "preciso de luvas" iam para o RH.
    llm = LLMFalso([json_llm("Não encontrei nas orientações; procure o RH.", [], cobertura="nenhuma")])
    res = agente(llm).executar(tarefa({"pergunta": "quero novas luvas"}))
    texto = res.saidas[0].texto
    assert res.status == "OK" and "EPI-Q021" in res.payload["ids_trechos"]
    assert "o que aconteceu com a sua luva" in texto and "RH" not in texto
    assert not repositorio.solicitacoes and res.payload["aguardando_motivo_epi"]


def test_relato_nao_vem_do_historico(agente, tarefa, repositorio):
    # Interação #11: "luvas" sozinho abriu um 2º pedido porque o LLM leu o histórico.
    llm = LLMFalso([json_llm("Troque a luva sempre que houver rasgo, furo ou perda de isolamento.", ["EPI-Q040"],
                             relato={"situacao": "avariado", "epi_mencionado": "luva térmica"})])
    res = agente(llm).executar(tarefa({"pergunta": "luvas", "historico_resumo": "Minha luva térmica rasgou"}))
    assert not repositorio.solicitacoes and not res.eventos


def test_pedido_duplicado_reaproveita(agente, tarefa, repositorio):
    a = agente()
    r1 = a.executar(tarefa({"pergunta": "Minha luva térmica rasgou agora na câmara fria"}))
    r2 = a.executar(tarefa({"pergunta": "a luva térmica rasgou de novo"}))
    assert len(repositorio.solicitacoes) == 1 and r2.payload["solicitacao_existente"]
    assert f"nº {r1.payload['id_solicitacao_epi']}" in r2.saidas[0].texto and not r2.eventos


def test_sem_prazo_repetido(agente, tarefa):
    # Interação #6: "24 horas" aparecia duas vezes (texto do LLM + confirmação do sistema).
    llm = LLMFalso([json_llm("Obrigado por avisar. Interrompa a atividade de risco e avise seu gestor. Você pode "
                             "solicitar a reposição aqui no chat e o TST entregará o novo em até 24 horas.",
                             ["EPI-Q025"], relato={"situacao": "avariado", "epi_mencionado": "luva térmica"})])
    texto = agente(llm).executar(tarefa({"pergunta": "minha luva térmica rasgou"})).saidas[0].texto
    assert texto.count("24 horas") == 1 and texto.startswith("Obrigado por avisar.")


def test_continuacao_usa_contexto_da_conversa(agente, tarefa):
    # Interações #3 e #4: continuação sobre pausas caiu em Saúde Ocupacional ou "fora do escopo".
    hist = "Tenho dúvida sobre pausas no expediente | posso pausar quantas vezes ao longo do dia?"
    llm = LLMFalso([lambda m: json_llm("As pausas integram a jornada e não se confundem com a refeição.",
                                       _ids(m)[:1])])
    a = agente(llm)
    r1 = a.executar_detalhado(tarefa({"pergunta": "meu chefe me disse que existe horário de almoço pra isso.",
                                      "historico_resumo": hist}))
    assert r1.telemetria["consulta_busca"] and r1.resultado.payload["base"] == "pausas_ergonomia"
    r2 = a.executar_detalhado(tarefa({"pergunta": "meu chefe está certo?", "historico_resumo": hist}))
    assert r2.telemetria["modo"] != "fora_escopo" and r2.resultado.payload["base"] == "pausas_ergonomia"


def test_intencao_invalida_e_ignorada(agente, tarefa):
    # Interação #19: intenção "string" (teste manual) entrou como viés.
    exe = agente().executar_detalhado(tarefa({"pergunta": "o que é EPI?", "intencao": "string"}))
    assert exe.telemetria["intencao_invalida"] == "string" and exe.telemetria["intencao"] is None


def test_sem_cobertura_de_epi_vai_para_tst(agente, tarefa):
    llm = LLMFalso([json_llm("Não encontrei.", [], cobertura="nenhuma")])
    res = agente(llm).executar(tarefa({"pergunta": "o capacete tem que ser de qual cor?"}))
    assert res.status == "PRECISA_HUMANO" and res.payload["encaminhar_para"] == "TST"
    assert "Técnico de Segurança" in res.saidas[0].texto and res.decisao.confianca is None


def test_caracteres_normalizados(agente, tarefa):
    llm = LLMFalso([json_llm("Recomenda‑se pausa de 5 a 10 minutos a cada 50 minutos.", ["RH-ERG-Q002"])])
    texto = agente(llm).executar(tarefa({"pergunta": "de quanto em quanto tempo faço pausa?"})).saidas[0].texto
    assert "‑" not in texto and " " not in texto and "Recomenda-se" in texto


def test_variacoes_do_chat_estao_no_pdf(store):
    t = next(x for x in store.trechos_vigentes(__import__("datetime").date(2026, 11, 25)) if x.id_pergunta == "EPI-Q026")
    assert "perdi minhas luvas" in t.variacoes and "perdi minhas luvas" in t.texto_indexado
    assert json.dumps(t.variacoes)
