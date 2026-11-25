"""Utilitários de texto em português (normalização, tokens, stopwords)."""

from __future__ import annotations

import re
import unicodedata

STOPWORDS = frozenset(
    """a o as os um uma uns umas de da do das dos dum duma em no na nos nas num numa por pelo pela
    pelos pelas para pra pro com sem sob sobre e ou mas que se ao aos à às é ser sao são esta está
    estao estão foi era sou meu minha meus minhas seu sua seus suas teu tua eu voce você vc ele ela
    eles elas nos nós isso isto esse essa este esta aquele aquela lhe me te mais muito muita qual
    quais quando como onde ja já tem têm ter ha há posso pode podem preciso devo fazer faço
    quero queria gostaria saber sobre empresa trabalho trabalhar colaborador colaboradora aqui
    alguem alguém coisa tudo nada ola olá oi bom boa dia tarde noite obrigado obrigada favor""".split()
)


def sem_acentos(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def dobrar(texto: str) -> str:
    """Minúsculas e sem acento — base de todas as comparações lexicais."""
    return sem_acentos(texto).lower()


def _radical(token: str) -> str:
    # Stemming leve: plural e algumas terminações comuns. Suficiente para BM25
    # num corpus pequeno e não cria dependência de NLTK/spaCy.
    for suf in ("coes", "cao", "mente", "idades", "idade", "oes", "aes", "ais", "eis", "res", "es", "s"):
        if len(token) > len(suf) + 3 and token.endswith(suf):
            return token[: -len(suf)]
    return token


def tokens(texto: str, *, radical: bool = True) -> list[str]:
    brutos = re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)?", dobrar(texto))
    saida = [t for t in brutos if t not in STOPWORDS and (len(t) > 1 or t.isdigit())]
    return [_radical(t) for t in saida] if radical else saida


def numeros(texto: str) -> set[str]:
    """Números citados num texto (para checar números inventados na resposta)."""
    return {n.lstrip("0") or "0" for n in re.findall(r"\d+", texto)}
