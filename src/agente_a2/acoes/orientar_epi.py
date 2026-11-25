"""a2.orientar_epi — F6: aviso de troca de EPI a partir do evento alerta.epi do A3.

Texto por modelo fixo (sem LLM): o conteúdo é curto, previsível e precisa sair
igual para todos. A fonte citada é a regra de aviso da base de EPI (EPI-Q031)
e a pergunta específica da situação.

``situacao`` aceita o que o A0 repassar do alerta do A3:
  * string: "vida_util", "vida_util_15d", "ca_vencendo", "novo_epi_cargo"...
  * objeto: {"tipo": "vida_util", "dias": 15}
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel

from sinergia_contratos import Decisao, Saida, Tarefa

from .comum import Dependencias, Parcial, agora, fontes_de, iso, mais_horas, no_horario, para_colaborador

MODELOS = {
    "vida_util": ("O seu {epi} chega ao fim da vida útil em {dias} dias. O TST já foi avisado e vai providenciar "
                  "a troca. Se ele estragar antes disso, é só pedir a reposição aqui no chat.",
                  ["EPI-Q031", "EPI-Q032"]),
    "ca_vencendo": ("O Certificado de Aprovação (CA) do seu {epi} vence em {dias} dias. O TST já foi avisado e vai "
                    "providenciar a troca.", ["EPI-Q031", "EPI-Q006"]),
    "novo_epi_cargo": ("O seu cargo agora exige {epi}, e ainda não há entrega registrada. O TST já foi avisado. Até "
                       "receber, por favor, não faça a atividade de risco que exige esse EPI.",
                       ["EPI-Q031", "EPI-Q033"]),
}
# Sem número de dias informado
MODELOS_SEM_DIAS = {
    "vida_util": "O seu {epi} está chegando ao fim da vida útil. O TST já foi avisado e vai providenciar a troca.",
    "ca_vencendo": "O Certificado de Aprovação (CA) do seu {epi} está para vencer. O TST já foi avisado e vai "
                   "providenciar a troca.",
}


class PayloadOrientarEPI(BaseModel):
    id_alerta: int | str
    id_colaborador: int
    id_epi: int
    situacao: Any = None


def _normalizar(situacao: Any) -> tuple[str, int | None]:
    if isinstance(situacao, dict):
        tipo = str(situacao.get("tipo") or situacao.get("codigo") or "vida_util").lower()
        dias = situacao.get("dias") or situacao.get("dias_para_troca")
    else:
        tipo = str(situacao or "vida_util").lower()
        m = re.search(r"(\d+)", tipo)
        dias = int(m.group(1)) if m else None
    if "ca" in re.split(r"[_\s-]", tipo) or "certificado" in tipo:
        chave = "ca_vencendo"
    elif "novo" in tipo or "cargo" in tipo:
        chave = "novo_epi_cargo"
    else:
        chave = "vida_util"
    return chave, int(dias) if dias is not None else None


def executar(tarefa: Tarefa, dep: Dependencias) -> Parcial:
    cfg = dep.config
    p = PayloadOrientarEPI.model_validate(tarefa.payload)
    momento = agora(tarefa, cfg.fuso)
    tipo, dias = _normalizar(p.situacao)

    nome_epi = "EPI"
    agendar = None
    if dep.repositorio:
        epi = dep.repositorio.epi(p.id_epi)
        nome_epi = epi.nome.lower() if epi else nome_epi
        # Cruzamento (relatório 12.7): não avisar durante afastamento ou férias.
        sit = dep.repositorio.situacao(p.id_colaborador, momento.date())
        if sit.estado != "ativo" and sit.retorno:
            colab = dep.repositorio.colaborador(p.id_colaborador)
            hora = mais_horas(colab.jornada_inicio if colab else None, 1, "09:00")
            agendar = iso(no_horario(sit.retorno, hora, cfg.fuso))

    modelo, ids = MODELOS[tipo]
    if dias is None and tipo in MODELOS_SEM_DIAS:
        texto = MODELOS_SEM_DIAS[tipo].format(epi=nome_epi)
    else:
        texto = modelo.format(epi=nome_epi, dias=dias)
    trechos = dep.recuperador.por_ids(ids, momento.date())

    return Parcial(
        payload={"base": "epi", "id_alerta": p.id_alerta, "situacao": tipo, "dias": dias,
                 "ids_trechos": [t.id_pergunta for t in trechos]},
        saidas=[Saida(tipo="mensagem", para=para_colaborador(tarefa, p.id_colaborador), texto=texto,
                      fontes=fontes_de(trechos), agendar_para=agendar)],
        telemetria={"modo": "fixo_f6"},
        decisao=Decisao(motivo=f"modelo fixo F6 ({tipo})" + ("; reagendado para o retorno" if agendar else ""),
                        usou_llm=False, confianca=1.0),
    )
