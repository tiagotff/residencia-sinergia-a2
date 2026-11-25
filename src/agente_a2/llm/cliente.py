"""Cliente de LLM.

``ClienteGroq`` usa LangChain (``langchain-groq``) com JSON mode. Qualquer
objeto com ``gerar(mensagens) -> str`` e ``nome`` serve — os testes usam
``LLMFalso`` e o grupo pode trocar o provedor sem mexer no agente.
"""

from __future__ import annotations

from typing import Callable, Protocol

Mensagens = list[tuple[str, str]]  # [("system", ...), ("user", ...), ("assistant", ...)]


class ClienteLLM(Protocol):
    nome: str

    def gerar(self, mensagens: Mensagens) -> str: ...


class ClienteGroq:
    def __init__(self, api_key: str, modelo: str, temperatura: float = 0.1, timeout_s: float = 20):
        from langchain_groq import ChatGroq  # import tardio

        self.nome = f"groq/{modelo}"
        self._chat = ChatGroq(
            api_key=api_key,
            model=modelo,
            temperature=temperatura,
            timeout=timeout_s,
            max_retries=1,
            model_kwargs={"response_format": {"type": "json_object"}},
        )

    def gerar(self, mensagens: Mensagens) -> str:
        papel = {"system": "system", "user": "human", "assistant": "ai"}
        resposta = self._chat.invoke([(papel[p], c) for p, c in mensagens])
        return str(resposta.content)


class LLMFalso:
    """LLM de teste: devolve respostas programadas (str ou função das mensagens)."""

    def __init__(self, respostas: list[str | Callable[[Mensagens], str]] | None = None):
        self.nome = "falso/teste"
        self.respostas = list(respostas or [])
        self.chamadas: list[Mensagens] = []

    def gerar(self, mensagens: Mensagens) -> str:
        self.chamadas.append(mensagens)
        if not self.respostas:
            raise RuntimeError("LLMFalso sem respostas programadas")
        r = self.respostas.pop(0) if len(self.respostas) > 1 else self.respostas[0]
        return r(mensagens) if callable(r) else r
