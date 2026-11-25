"""Leitura das bases de conhecimento em PDF.

Os quatro PDFs seguem a mesma convenção:

* cabeçalho em tabela (Título, Código, Versão, Vigência, Aprovação, Revisão...);
* seções numeradas ("1. Conceitos básicos");
* uma pergunta por bloco, com
    ``<ID> | <pergunta>``
    ``Também perguntam: var1 | var2 | ...``
    ``<resposta>``
    ``Fonte: <fonte> (OFICIAL|INTERNO); ...``

O parser devolve um ``DocumentoBase`` com uma ``PerguntaBase`` por ID. Nada é
inventado: se um campo não existir no PDF ele fica vazio.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

# Ligaduras tipográficas que alguns PDFs exportam (ﬁ, ﬂ...). NFKC resolveria,
# mas também transforma "nº" em "no" e "13º" em "13o", então trocamos só elas.
_LIGADURAS = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl"}

_RE_ID = re.compile(r"^(?P<id>(?:EPI|SO|RH-ERG|RH-BEN|[A-Z]{2,5}(?:-[A-Z]{2,5})?)-Q\d{3})\s*\|\s*(?P<titulo>.*)$")
_RE_SECAO = re.compile(r"^(?P<num>\d{1,2})\.\s+(?P<nome>[^\d].{2,})$")
_RE_TAMBEM = re.compile(r"^Também perguntam:\s*(?P<resto>.*)$", re.IGNORECASE)
_RE_FONTE = re.compile(r"^Fonte:\s*(?P<resto>.*)$")
_RE_DATA = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
_RE_TIPO_FONTE = re.compile(r"\((OFICIAL|INTERNO)\)")

_CHAVES_CABECALHO = (
    "Título", "Código", "Versão", "Vigência", "Tipo de fonte", "Fonte", "Base RAG",
    "Responsável", "Aprovação", "Revisão", "Convenções",
)


@dataclass
class PerguntaBase:
    id_pergunta: str
    titulo: str
    secao: str
    variacoes: list[str]
    resposta: str
    fonte: str
    tipos_fonte: list[str]
    ordem: int


@dataclass
class DocumentoBase:
    base: str
    titulo: str
    codigo: str | None
    versao: str
    vigencia_inicio: date | None
    aprovacao: str | None
    revisao: str | None
    arquivo: str
    sha256: str
    perguntas: list[PerguntaBase] = field(default_factory=list)


def limpar_texto(texto: str) -> str:
    for lig, sub in _LIGADURAS.items():
        texto = texto.replace(lig, sub)
    texto = unicodedata.normalize("NFC", texto)
    texto = texto.replace(" ", " ")
    return texto


def extrair_texto_pdf(caminho: Path) -> str:
    """Extrai o texto com pypdf (puro Python, roda no Windows sem dependências)."""
    from pypdf import PdfReader

    leitor = PdfReader(str(caminho))
    paginas = [p.extract_text() or "" for p in leitor.pages]
    return limpar_texto("\n".join(paginas))


def _juntar(linhas: list[str]) -> str:
    """Junta linhas quebradas pelo PDF preservando bullets como novas linhas."""
    saida: list[str] = []
    for bruta in linhas:
        linha = re.sub(r"\s+", " ", bruta).strip()
        if not linha:
            continue
        if linha in {"•", "-"} or re.fullmatch(r"\d{1,2}", linha):
            saida.append(linha if linha[0].isdigit() else "•")
            continue
        if linha.startswith(("•", "- ")) or re.match(r"^\d\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ]", linha):
            saida.append(linha)
        elif saida and (saida[-1] == "•" or re.fullmatch(r"\d{1,2}", saida[-1])):
            saida[-1] = saida[-1] + " " + linha
        elif saida:
            saida[-1] = saida[-1] + " " + linha
        else:
            saida.append(linha)
    return "\n".join(saida).strip()


def _parse_cabecalho(texto: str) -> dict[str, str]:
    chaves = "|".join(re.escape(c) for c in sorted(_CHAVES_CABECALHO, key=len, reverse=True))
    padrao = re.compile(rf"(?m)^\s*({chaves})\b[ \t]*")
    partes = padrao.split(texto)
    campos: dict[str, str] = {}
    # partes = [antes, chave1, valor1, chave2, valor2, ...]
    for i in range(1, len(partes) - 1, 2):
        chave = partes[i].strip()
        valor = re.sub(r"\s+", " ", partes[i + 1]).strip()
        if chave not in campos:  # "Fonte" do cabeçalho vem antes de qualquer pergunta
            campos[chave] = valor
    return campos


def _data(valor: str | None) -> date | None:
    if not valor:
        return None
    m = _RE_DATA.search(valor)
    if not m:
        return None
    d, mth, a = (int(x) for x in m.groups())
    return date(a, mth, d)


def parse_documento(texto: str, base: str, arquivo: str, sha256: str) -> DocumentoBase:
    linhas = texto.splitlines()

    # Cabeçalho: tudo antes da primeira seção numerada ou do primeiro ID.
    fim_cab = len(linhas)
    for i, l in enumerate(linhas):
        s = l.strip()
        if _RE_ID.match(s) or (_RE_SECAO.match(s) and not s.startswith(("1.0", "2.0"))):
            fim_cab = i
            break
    cab = _parse_cabecalho("\n".join(linhas[:fim_cab]))

    doc = DocumentoBase(
        base=base,
        titulo=cab.get("Título") or (linhas[0].strip() if linhas else base),
        codigo=cab.get("Código"),
        versao=(cab.get("Versão") or "0").split()[0],
        vigencia_inicio=_data(cab.get("Vigência")),
        aprovacao=cab.get("Aprovação"),
        revisao=cab.get("Revisão"),
        arquivo=arquivo,
        sha256=sha256,
    )

    secao_atual = ""
    secao_aberta = False  # título de seção quebrado em duas linhas
    bloco: dict | None = None
    estado = "titulo"  # titulo -> tambem -> resposta -> fonte

    def fechar():
        nonlocal bloco
        if bloco is None:
            return
        fonte = _juntar(bloco["fonte"]).replace("\n", " ")
        doc.perguntas.append(
            PerguntaBase(
                id_pergunta=bloco["id"],
                titulo=_juntar(bloco["titulo"]).replace("\n", " "),
                secao=bloco["secao"],
                variacoes=[v.strip() for v in _juntar(bloco["tambem"]).replace("\n", " ").split("|") if v.strip()],
                resposta=_juntar(bloco["resposta"]),
                fonte=fonte,
                tipos_fonte=sorted(set(_RE_TIPO_FONTE.findall(fonte))),
                ordem=len(doc.perguntas) + 1,
            )
        )
        bloco = None

    for bruta in linhas[fim_cab:]:
        linha = bruta.strip()
        m_id = _RE_ID.match(linha)
        if m_id:
            secao_aberta = False
            fechar()
            bloco = {"id": m_id["id"], "titulo": [m_id["titulo"]], "tambem": [], "resposta": [],
                     "fonte": [], "secao": secao_atual}
            estado = "titulo"
            continue
        m_sec = _RE_SECAO.match(linha)
        if m_sec and (bloco is None or estado == "fonte"):
            fechar()
            secao_atual = f"{m_sec['num']}. {m_sec['nome'].strip()}"
            secao_aberta = True
            continue
        if secao_aberta:
            if linha:
                secao_atual = f"{secao_atual} {linha}"
            continue
        if bloco is None:
            continue
        m_tb = _RE_TAMBEM.match(linha)
        if m_tb and estado == "titulo":
            estado = "tambem"
            bloco["tambem"].append(m_tb["resto"])
            continue
        m_ft = _RE_FONTE.match(linha)
        if m_ft and estado in {"resposta", "tambem"}:
            estado = "fonte"
            bloco["fonte"].append(m_ft["resto"])
            continue
        if not linha:
            # Linha em branco encerra "Também perguntam" (o PDF separa variações e resposta).
            if estado == "tambem":
                estado = "resposta"
            continue
        if estado == "titulo":
            bloco["titulo"].append(linha)
        elif estado == "tambem":
            # Sem linha em branco (pypdf): a variação continua se a linha anterior
            # terminou em "|" ou a linha começa em minúscula; senão é a resposta.
            anterior = bloco["tambem"][-1].rstrip()
            if re.match(r"^\d{1,2}(\s|$)", linha):
                estado = "resposta"
                bloco["resposta"].append(bruta)
                continue
            fragmento_curto = len(linha) < 40 and not linha.endswith((".", ":", "!"))
            if anterior.endswith("|") or linha[:1].islower() or linha.startswith("|") or fragmento_curto:
                bloco["tambem"].append(linha)
            else:
                estado = "resposta"
                bloco["resposta"].append(bruta)
        elif estado == "resposta":
            bloco["resposta"].append(bruta)
        elif estado == "fonte":
            # Fonte quebrada em duas linhas: continua até a próxima pergunta/seção.
            bloco["fonte"].append(linha)
    fechar()
    return doc


def ler_pdf(caminho: Path, base: str) -> DocumentoBase:
    dados = caminho.read_bytes()
    sha = hashlib.sha256(dados).hexdigest()
    return parse_documento(extrair_texto_pdf(caminho), base=base, arquivo=caminho.name, sha256=sha)
