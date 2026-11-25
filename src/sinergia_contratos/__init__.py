"""Contratos do protocolo sinergia/1 (espelho local).

A fonte da verdade é o pacote compartilhado ``sinergia_contratos`` do grupo
(relatório v0.7, seção 7.2). Este módulo reproduz o envelope para o A2 rodar e
ser testado sozinho; quando o pacote oficial existir, basta trocar o import.
"""

from .modelos import (  # noqa: F401
    PROTOCOLO,
    Contexto,
    Correlacao,
    Decisao,
    Destinatario,
    Erro,
    Evento,
    Fonte,
    Resultado,
    Saida,
    Tarefa,
)
