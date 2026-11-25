"""a2.acompanhar_afastamento — F7: contato de cuidado nos marcos do caso.

MVP com os três marcos aprovados (meio, véspera, retorno) e textos por modelo
fixo, sem LLM: mensagem de cuidado a quem está afastado precisa de tom
previsível e não pode tocar em saúde. Orientações legais só aparecem quando
``prazos_legais`` indica, e sempre com fonte:

* ``exame_retorno`` (30 dias ou mais)  -> SO-Q010
* ``inss_16_dias`` (mais de 15 dias)    -> RH-BEN-Q003

F7 é a exceção à regra "não falar com quem está afastado" (relatório 12.7).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel

from sinergia_contratos import Decisao, Saida, Tarefa

from .comum import Dependencias, Parcial, agora, fontes_de, iso, no_horario, para_colaborador, primeiro_nome

DIAS_SEMANA = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


class Periodo(BaseModel):
    inicio: date
    fim: date


class PayloadAcompanhar(BaseModel):
    id_caso: int
    marco: Literal["meio", "vespera_retorno", "retorno"]
    dias: int | None = None
    prazos_legais: list[str] = []
    periodo: Periodo | None = None   # opcional; se ausente, vem do registro_inicial


def _quando(fim: date, hoje: date) -> str:
    delta = (fim - hoje).days
    if delta == 0:
        return "hoje"
    if delta == 1:
        return "amanhã"
    if 1 < delta < 7:
        return DIAS_SEMANA[fim.weekday()]
    return fim.strftime("%d/%m")


def executar(tarefa: Tarefa, dep: Dependencias) -> Parcial:
    cfg = dep.config
    p = PayloadAcompanhar.model_validate(tarefa.payload)
    ri = tarefa.registro_inicial or {}
    momento = agora(tarefa, cfg.fuso)
    hoje = momento.date()
    nome = primeiro_nome(ri.get("nome"))
    ola = f"Olá, {nome}." if nome else "Olá."

    fim = p.periodo.fim if p.periodo else None
    if fim is None and ri.get("inicio_informado"):
        dias = p.dias or ri.get("dias_informados")
        if dias:
            fim = date.fromisoformat(ri["inicio_informado"]) + timedelta(days=int(dias) - 1)

    ids: list[str] = []
    if p.marco == "meio":
        ate = f" Seu afastamento vai até {_quando(fim, hoje)}." if fim else ""
        texto = f"{ola}{ate} Se precisar de algo para o retorno, é só escrever aqui."
        if "inss_16_dias" in p.prazos_legais:
            texto += (" Como o afastamento passa de 15 dias, a partir do 16º dia o pagamento é feito pelo INSS; "
                      "o RH vai orientar você sobre os próximos passos.")
            ids.append("RH-BEN-Q003")
    elif p.marco == "vespera_retorno":
        texto = f"{ola} Amanhã é o seu dia de retorno."
        if "exame_retorno" in p.prazos_legais or (p.dias or 0) >= 30:
            texto += (" Como o afastamento foi de 30 dias ou mais, o exame de retorno ao trabalho é feito antes de "
                      "você voltar às suas funções; o serviço de saúde vai orientar o agendamento.")
            ids.append("SO-Q010")
        texto += " Se precisar de algo, é só escrever aqui."
    else:
        bem_vindo = f"Que bom ter você de volta, {nome}!" if nome else "Que bom ter você de volta!"
        texto = (f"{bem_vindo} Lembre-se de entregar o original do atestado ao RH. "
                 "Qualquer dúvida, estou por aqui.")

    # Mensagem de cuidado sai às 10h do dia do marco (ou já, se passou desse horário).
    alvo = no_horario(hoje, "10:00", cfg.fuso)
    agendar = iso(alvo) if momento < alvo else None
    trechos = dep.recuperador.por_ids(ids, hoje) if ids else []

    return Parcial(
        payload={"id_caso": p.id_caso, "marco": p.marco, "ids_trechos": ids},
        saidas=[Saida(tipo="mensagem", para=para_colaborador(tarefa, ri.get("id_colaborador")), texto=texto,
                      fontes=fontes_de(trechos), agendar_para=agendar)],
        telemetria={"modo": "fixo_f7"},
        decisao=Decisao(motivo=f"modelo fixo F7 (marco {p.marco})", usou_llm=False, confianca=1.0),
    )
