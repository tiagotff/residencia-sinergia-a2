"""RAG completo: R (plano + multi-consulta + fusão + MMR + vizinhos), A (contexto) e G (síntese + complemento)."""

import json
from datetime import date

from conftest import json_llm

from agente_a2 import AgenteA2
from agente_a2.guardrails.saida import fundamentacao, validar_complemento
from agente_a2.llm.cliente import LLMFalso
from agente_a2.rag.consulta import heuristico, planejar
from agente_a2.rag.recuperador import Recuperador

HOJE = date(2026, 11, 25)


def plano_json(autonoma, subs, tema):
    return json.dumps({"pergunta_autonoma": autonoma, "subconsultas": subs, "tema": tema}, ensure_ascii=False)


def a2_com(store, embedder, config, repositorio, gerador, planejador):
    return AgenteA2(llm=gerador, llm_planejador=planejador, store=store, embedder=embedder,
                    repositorio=repositorio, config=config)


def test_plano_pelo_llm_e_fallback():
    p = planejar("e o meu chefe, está certo?", "a pausa pode ser no almoço?",
                 LLMFalso([plano_json("A pausa pode ser feita no horário do almoço?", ["intervalo de refeição"], "pausas_ergonomia")]))
    assert p.usou_llm and p.tema == "pausas_ergonomia" and p.consultas[0].startswith("A pausa pode")
    ruim = planejar("perdi luvas", "", LLMFalso(["isso não é json"]))
    assert not ruim.usou_llm and "heurística" in ruim.motivo
    assert heuristico("e agora?", "minha luva rasgou").usou_historico


def test_pergunta_composta_busca_as_duas_partes(store, embedder, config):
    rec = Recuperador(store, embedder, config)
    res = rec.buscar_multi(["Posso vender férias e dividir em partes?", "abono pecuniário", "fracionar férias"], HOJE)
    ids = [p.trecho.id_pergunta for p in res.trechos]
    assert "RH-BEN-Q008" in ids and "RH-BEN-Q012" in ids and "RRF" in res.diagnostico["metodo"]


def test_vizinho_do_mesmo_assunto_entra_como_relacionado(store, embedder, config):
    rec = Recuperador(store, embedder, config)
    res = rec.buscar_multi(["luva de malha de aço para que serve"], HOJE, k=1)
    assert res.trechos[0].trecho.id_pergunta == "EPI-Q067" or res.relacionados


def test_agente_usa_plano_entendimento_e_perfil(store, embedder, config, repositorio, tarefa):
    planejador = LLMFalso([plano_json("Qual luva usar e como conservar na câmara fria?",
                                      ["luva térmica conservação", "frio câmara fria cuidados"], "epi")])
    gerador = LLMFalso([json_llm("A luva térmica protege as mãos do frio intenso na câmara fria; mantenha a luva seca, "
                                 "porque úmida ela perde o isolamento.", ["EPI-Q040"])])
    exe = a2_com(store, embedder, config, repositorio, gerador, planejador).executar_detalhado(
        tarefa({"pergunta": "e na câmara fria, qual eu uso?", "historico_resumo": "dúvida sobre luvas"}))
    usuario = gerador.chamadas[0][1][1]
    assert "<entendimento>" in usuario and "Qual luva usar" in usuario and 'relacao="principal"' in usuario
    assert "EPIs do cargo: Luva térmica, Luva anticorte" in usuario
    t = exe.telemetria
    assert t["plano"]["usou_llm"] and len(t["diag"]["consultas"]) >= 3 and t["fundamentacao"]["score"] >= 0.5


def test_complemento_geral_aceito_e_marcado(store, embedder, config, repositorio, tarefa):
    gerador = LLMFalso([json.dumps({
        "resposta": "As pausas são obrigatórias e fazem parte da jornada; não devem ser compensadas ao final do expediente.",
        "ids_usados": ["RH-ERG-Q002"], "cobertura": "total",
        "complemento": "Deixar um lembrete no celular ajuda a não esquecer as pausas nos dias corridos."}, ensure_ascii=False)])
    exe = a2_com(store, embedder, config, repositorio, gerador, None).executar_detalhado(
        tarefa({"pergunta": "as pausas são obrigatórias?"}))
    texto = exe.resultado.saidas[0].texto
    assert "Dica: Deixar um lembrete" in texto and exe.resultado.payload["complemento_geral"]
    assert exe.resultado.saidas[0].fontes[0].refs == ["RH-ERG-Q002"]     # a dica não vira fonte


def test_complemento_normativo_e_descartado(store, embedder, config, repositorio, tarefa):
    gerador = LLMFalso([json.dumps({
        "resposta": "As pausas são obrigatórias e fazem parte da jornada.", "ids_usados": ["RH-ERG-Q007"],
        "cobertura": "total", "complemento": "Pela lei você tem direito a 15 minutos extras."}, ensure_ascii=False)])
    exe = a2_com(store, embedder, config, repositorio, gerador, None).executar_detalhado(
        tarefa({"pergunta": "posso pular as pausas?"}))
    assert "Dica" not in exe.resultado.saidas[0].texto
    assert exe.telemetria["complemento_descartado"]["motivo"] == "complemento_normativo"


def test_validadores_de_complemento_e_fundamentacao():
    assert validar_complemento("Beba água ao longo do dia.")[0]
    assert validar_complemento("Tome 1 comprimido de dipirona.")[1] in {"complemento_normativo", "complemento_medico"}
    assert validar_complemento("A empresa deve te dar folga.")[1] == "complemento_normativo"
    nota, sem = fundamentacao("A luva térmica protege do frio. O capacete azul é obrigatório para pilotos de avião.",
                              ["A luva térmica protege as mãos do frio intenso na câmara fria."])
    assert nota == 0.5 and "capacete" in sem[0]
