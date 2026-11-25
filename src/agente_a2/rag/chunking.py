"""Chunking das bases.

Estratégia: **um chunk por pergunta** (ID EPI-Qnnn, SO-Qnnn...). Nas quatro
bases a maior resposta tem ~600 caracteres, então a pergunta inteira cabe num
trecho e a unidade de citação (o ID) coincide com a unidade de recuperação —
o que deixa a fundamentação verificável. Respostas maiores que
``max_chars`` são divididas por parágrafo/bullet com sobreposição de uma
unidade, repetindo o cabeçalho em cada parte.

O texto indexado (embedding e BM25) junta título + "Também perguntam" +
resposta: as variações são exatamente as formas como o colaborador pergunta,
e por isso aumentam bastante o recall.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .parser_pdf import DocumentoBase, PerguntaBase


@dataclass
class Trecho:
    id_trecho: str            # "<id_pergunta>#<parte>"
    id_pergunta: str
    parte: int
    base: str
    documento_titulo: str
    documento_versao: str
    documento_sha256: str
    vigencia_inicio: date | None
    aprovacao: str | None
    secao: str
    titulo: str
    variacoes: list[str]
    resposta: str
    fonte: str
    tipos_fonte: list[str]
    ordem: int
    texto_indexado: str = ""
    variacoes_extras: list[str] = field(default_factory=list)   # vindas de variacoes_extras.json
    embedding: list[float] | None = field(default=None, repr=False)

    def texto_para_prompt(self) -> str:
        return f"Pergunta: {self.titulo}\nResposta: {self.resposta}\nFonte: {self.fonte}"


def _texto_indexado(p: PerguntaBase, resposta: str, extras: list[str] | None = None) -> str:
    variacoes = " | ".join(list(p.variacoes) + list(extras or []))
    return f"{p.titulo}\nTambém perguntam: {variacoes}\n{resposta}"


def _dividir(resposta: str, max_chars: int) -> list[str]:
    if len(resposta) <= max_chars:
        return [resposta]
    unidades = [u for u in resposta.split("\n") if u.strip()]
    partes: list[str] = []
    atual: list[str] = []
    for u in unidades:
        if atual and len("\n".join(atual + [u])) > max_chars:
            partes.append("\n".join(atual))
            atual = [atual[-1]]  # sobreposição de uma unidade
        atual.append(u)
    if atual:
        partes.append("\n".join(atual))
    return partes


def gerar_trechos(doc: DocumentoBase, max_chars: int = 1200,
                  extras: dict[str, list[str]] | None = None) -> list[Trecho]:
    extras = extras or {}
    trechos: list[Trecho] = []
    for p in doc.perguntas:
        ext = [v for v in extras.get(p.id_pergunta, []) if v not in p.variacoes]
        for i, parte in enumerate(_dividir(p.resposta, max_chars), start=1):
            trechos.append(
                Trecho(
                    id_trecho=f"{p.id_pergunta}#{i}",
                    id_pergunta=p.id_pergunta,
                    parte=i,
                    base=doc.base,
                    documento_titulo=doc.titulo,
                    documento_versao=doc.versao,
                    documento_sha256=doc.sha256,
                    vigencia_inicio=doc.vigencia_inicio,
                    aprovacao=doc.aprovacao,
                    secao=p.secao,
                    titulo=p.titulo,
                    variacoes=list(p.variacoes),
                    resposta=parte,
                    fonte=p.fonte,
                    tipos_fonte=list(p.tipos_fonte),
                    ordem=p.ordem,
                    texto_indexado=_texto_indexado(p, parte, ext),
                    variacoes_extras=ext,
                )
            )
    return trechos
