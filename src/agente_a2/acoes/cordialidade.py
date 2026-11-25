"""Cordialidade: saudação, agradecimento e despedida, sem LLM e sem busca.

* Mensagem só de cumprimento ("oi", "bom dia", "tudo bem?") → boas-vindas com o primeiro nome,
  saudação pela hora do dia e os temas em que o A2 ajuda.
* Cumprimento + dúvida ("oi, perdi minhas luvas") → a dúvida segue o fluxo normal e a resposta
  ganha a saudação na frente, só no início da conversa (sem histórico).
* "obrigado", "valeu", "tchau" → resposta curta e calorosa.

O nome vem do cadastro (só o primeiro nome) e é colocado pelo código, nunca enviado ao LLM.
No banco de interações, o nome é trocado por [NOME].
"""

from __future__ import annotations

import re
from datetime import datetime

from ..texto import dobrar

_CUMPRIMENTO = (r"(oi+|ola|ole|opa|e ai|eai|hey|hello|hi|bom dia|boa tarde|boa noite|bom diaa+|"
                r"saudacoes|salve|alo|tudo bem|tudo bom|tudo certo|como vai|como voce esta|beleza|blz)")
_RE_SO_CUMPRIMENTO = re.compile(rf"^\s*({_CUMPRIMENTO}[\s,!.?]*)+(a2|assistente|sinergia)?[\s,!.?]*$")
_RE_INICIO = re.compile(rf"^\s*{_CUMPRIMENTO}\b[\s,!.]*")
_RE_AGRADECIMENTO = re.compile(r"^\s*((ok|certo|entendi|perfeito|otimo|show)[\s,!.]*)?(muito )?"
                               r"(obrigad[oa]s?|obg|brigad[oa]|valeu|vlw|agradeco|grat[oa])[\s,!.]*"
                               r"(pela ajuda|mesmo|demais)?[\s!.]*$")
_RE_CONFIRMACAO = re.compile(r"^\s*(ok+|okay|certo|entendi|entendido|combinado|beleza|blz|sim|tá bom|ta bom|"
                             r"ah,? (ta|ok)|perfeito|show|otimo)[\s,!.]*$")
_RE_DESPEDIDA = re.compile(r"^\s*(tchau|ate logo|ate mais|ate amanha|falou|flw|bom descanso|boa semana)[\s,!.]*$")

TEMAS = "EPI, pausas e ergonomia, saúde ocupacional e direitos e benefícios"


def saudacao_do_horario(momento: datetime) -> str:
    h = momento.hour
    return "Bom dia" if 5 <= h < 12 else "Boa tarde" if 12 <= h < 18 else "Boa noite"


def classificar(pergunta: str) -> str | None:
    """'cumprimento' | 'agradecimento' | 'despedida' | None (mensagem com conteúdo)."""
    d = dobrar(pergunta).strip()
    if _RE_SO_CUMPRIMENTO.match(d):
        return "cumprimento"
    if _RE_AGRADECIMENTO.match(d):
        return "agradecimento"
    if _RE_DESPEDIDA.match(d):
        return "despedida"
    if _RE_CONFIRMACAO.match(d):
        return "confirmacao"
    return None


def tem_cumprimento(pergunta: str) -> bool:
    return bool(_RE_INICIO.match(dobrar(pergunta)))


def _vocativo(nome: str | None) -> str:
    return f", {nome}" if nome else ""


def boas_vindas(nome: str | None, momento: datetime, primeira: bool) -> str:
    if primeira:
        return (f"{saudacao_do_horario(momento)}{_vocativo(nome)}! Que bom falar com você. Sou o assistente de "
                f"bem-estar e posso ajudar com {TEMAS}. Como posso ajudar hoje?")
    return f"Oi{_vocativo(nome)}! Estou por aqui. Em que mais posso ajudar?"


def agradecimento(nome: str | None) -> str:
    return (f"Por nada{_vocativo(nome)}! Fico feliz em ajudar. Se surgir outra dúvida sobre {TEMAS}, "
            "é só escrever aqui.")


def confirmacao(nome: str | None) -> str:
    return f"Combinado{_vocativo(nome)}! Se surgir outra dúvida, é só escrever aqui."


def despedida(nome: str | None, momento: datetime) -> str:
    fim = "um bom dia" if 5 <= momento.hour < 12 else "uma boa tarde" if momento.hour < 18 else "uma boa noite"
    return f"Até logo{_vocativo(nome)}! Tenha {fim} e cuide-se."


def prefixo(nome: str | None, momento: datetime) -> str:
    """Saudação curta para abrir a 1ª resposta da conversa."""
    return f"{saudacao_do_horario(momento)}{_vocativo(nome)}!"


def fora_do_escopo(nome: str | None) -> str:
    return (f"Essa eu não consigo responder por aqui{_vocativo(nome)}, mas posso ajudar com {TEMAS}. "
            "Qual é a sua dúvida?")
