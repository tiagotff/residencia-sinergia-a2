"""Cordialidade no início e no fim da conversa (feedback: faltava acolhimento no 'oi')."""

import json

from conftest import json_llm

from agente_a2 import AgenteA2
from agente_a2.interacoes import RegistroInteracoes
from agente_a2.llm.cliente import LLMFalso


def test_oi_recebe_boas_vindas_sem_llm(agente, tarefa):
    llm = LLMFalso([json_llm("x", [])])
    exe = agente(llm).executar_detalhado(tarefa({"pergunta": "oi"}))          # 09:00 no conftest
    texto = exe.resultado.saidas[0].texto
    assert texto.startswith("Bom dia, Carla!") and "Como posso ajudar" in texto
    assert exe.telemetria["modo"] == "saudacao" and not llm.chamadas and exe.resultado.status == "OK"


def test_oi_no_meio_da_conversa_e_curto(agente, tarefa):
    texto = agente().executar(tarefa({"pergunta": "oi", "historico_resumo": "posso vender férias?"})).saidas[0].texto
    assert texto.startswith("Oi, Carla!") and "Bom dia" not in texto


def test_cumprimento_com_duvida_abre_com_saudacao(agente, tarefa, repositorio):
    llm = LLMFalso([json_llm("Sim, você pode vender até 10 dias das férias.", ["RH-BEN-Q008"])])
    texto = agente(llm).executar(tarefa({"pergunta": "Bom dia! Posso vender parte das minhas férias?"})).saidas[0].texto
    assert texto.startswith("Bom dia, Carla! Sim, você pode vender")
    assert "Carla" not in llm.chamadas[0][1][1]                      # o nome não vai ao LLM


def test_saudacao_so_no_inicio(agente, tarefa):
    llm = LLMFalso([json_llm("Sim, até 10 dias.", ["RH-BEN-Q008"])])
    texto = agente(llm).executar(tarefa({"pergunta": "oi, posso vender férias?",
                                         "historico_resumo": "tenho dúvidas"})).saidas[0].texto
    assert texto.startswith("Sim")


def test_agradecimento_confirmacao_e_despedida(agente, tarefa):
    a = agente()
    assert a.executar(tarefa({"pergunta": "muito obrigada pela ajuda!"})).saidas[0].texto.startswith("Por nada, Carla!")
    assert a.executar(tarefa({"pergunta": "ok"})).saidas[0].texto.startswith("Combinado, Carla!")
    assert a.executar(tarefa({"pergunta": "tchau"})).saidas[0].texto.startswith("Até logo, Carla! Tenha um bom dia")


def test_fora_do_escopo_acolhedor(agente, tarefa):
    texto = agente().executar(tarefa({"pergunta": "qual a senha do wifi?"})).saidas[0].texto
    assert texto.startswith("Essa eu não consigo responder por aqui, Carla")


def test_nome_mascarado_no_banco(tmp_path, store, embedder, config, repositorio, tarefa):
    reg = RegistroInteracoes(f"sqlite:///{(tmp_path / 'i.db').as_posix()}", sal="t")
    a2 = AgenteA2(store=store, embedder=embedder, repositorio=repositorio, config=config, registro=reg)
    i = a2.executar_detalhado(tarefa({"pergunta": "oi"})).id_interacao
    d = reg.detalhe(i)
    assert "Carla" not in json.dumps(d, ensure_ascii=False) and d["resposta"].startswith("Bom dia, [NOME]!")
