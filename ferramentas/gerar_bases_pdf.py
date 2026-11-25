"""Gera os PDFs das bases RAG a partir das fontes editáveis em ``bases_fonte/<base>.json``.

    python ferramentas/gerar_bases_pdf.py               # todas as bases -> bases_pdf/
    python ferramentas/gerar_bases_pdf.py epi           # só uma

Mantém o padrão dos documentos originais: cabeçalho em tabela, seções numeradas e, por pergunta,
``<ID> | <pergunta>``, ``Também perguntam: a | b``, resposta e ``Fonte: X (OFICIAL); Y (INTERNO)``.
Depois de gerar, rode ``python -m agente_a2 ingerir`` para reindexar.

Formato do JSON:
    {"cabecalho": {"Título": ..., "Versão": ..., ...},
     "secoes": [{"titulo": "1. Conceitos básicos",
                 "perguntas": [{"id": "EPI-Q001", "titulo": ..., "variacoes": [...],
                                "resposta": "texto; linhas com '• ' viram lista; '1 Texto' vira passo numerado",
                                "fonte": "NR-6 (OFICIAL)"}]}]}
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

RAIZ = Path(__file__).resolve().parents[1]
AZUL = colors.HexColor("#1F4E79")
CINZA = colors.HexColor("#6B7280")
FUNDO_ROTULO = colors.HexColor("#EEF2F7")
ARQUIVOS = {"epi": "epi.pdf", "pausas_ergonomia": "pausas_ergonomia.pdf",
            "saude_ocupacional": "saude_ocupacional.pdf", "direitos_beneficios": "direitos_beneficios.pdf"}
ORDEM_CABECALHO = ["Título", "Código", "Versão", "Vigência", "Tipo de fonte", "Fonte", "Base RAG", "Responsável",
                   "Aprovação", "Revisão", "Convenções"]


def _registrar_fontes() -> tuple[str, str, str]:
    """DejaVu (Linux) ou Arial (Windows); se nenhuma existir, Helvetica (também tem acentos)."""
    candidatos = [
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf"),
        ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/ariali.ttf"),
    ]
    for normal, negrito, italico in candidatos:
        if all(Path(p).exists() for p in (normal, negrito, italico)):
            pdfmetrics.registerFont(TTFont("Base", normal))
            pdfmetrics.registerFont(TTFont("Base-Bold", negrito))
            pdfmetrics.registerFont(TTFont("Base-Italic", italico))
            return "Base", "Base-Bold", "Base-Italic"
    return "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"


def _estilos(normal: str, negrito: str, italico: str) -> dict[str, ParagraphStyle]:
    return {
        "titulo": ParagraphStyle("titulo", fontName=negrito, fontSize=20, leading=24, textColor=AZUL, spaceAfter=10),
        "celula": ParagraphStyle("celula", fontName=normal, fontSize=8, leading=10.5),
        "rotulo": ParagraphStyle("rotulo", fontName=negrito, fontSize=8, leading=10.5),
        "secao": ParagraphStyle("secao", fontName=negrito, fontSize=13.5, leading=17, textColor=AZUL,
                                spaceBefore=12, spaceAfter=6),
        "pergunta": ParagraphStyle("pergunta", fontName=negrito, fontSize=10, leading=13, spaceBefore=8, spaceAfter=2),
        "variacoes": ParagraphStyle("variacoes", fontName=italico, fontSize=7.5, leading=9.5, textColor=CINZA,
                                    spaceAfter=3),
        "corpo": ParagraphStyle("corpo", fontName=normal, fontSize=9, leading=12.5, alignment=TA_LEFT, spaceAfter=2),
        "item": ParagraphStyle("item", fontName=normal, fontSize=9, leading=12.5, leftIndent=12, firstLineIndent=-8,
                               spaceAfter=1),
        "fonte": ParagraphStyle("fonte", fontName=negrito, fontSize=7.5, leading=10, textColor=AZUL, spaceBefore=2,
                                spaceAfter=4),
    }


def _linha_resposta(linha: str, est: dict, negrito: str) -> Paragraph:
    """'• Rótulo: texto' -> item com rótulo em negrito; '1 Passo: texto' -> passo numerado."""
    if linha.startswith("• "):
        corpo = linha[2:]
        m = re.match(r"^([^:]{2,60}):\s(.*)$", corpo)
        texto = f"<font name='{negrito}'>{escape(m.group(1))}:</font> {escape(m.group(2))}" if m else escape(corpo)
        return Paragraph(f"•&nbsp;&nbsp;{texto}", est["item"])
    m = re.match(r"^(\d{1,2})\s+(.*)$", linha)
    if m:
        return Paragraph(f"{m.group(1)}&nbsp;&nbsp;{escape(m.group(2))}", est["item"])
    return Paragraph(escape(linha), est["corpo"])


def gerar(slug: str, origem: Path | None = None, destino: Path | None = None) -> Path:
    origem = origem or RAIZ / "bases_fonte" / f"{slug}.json"
    destino = destino or RAIZ / "bases_pdf" / ARQUIVOS[slug]
    dados = json.loads(origem.read_text(encoding="utf-8"))
    normal, negrito, italico = _registrar_fontes()
    est = _estilos(normal, negrito, italico)
    cab = dados["cabecalho"]

    historia = [Paragraph(escape(cab["Título"]), est["titulo"])]
    linhas = [[Paragraph(escape(k), est["rotulo"]), Paragraph(escape(str(cab[k])), est["celula"])]
              for k in ORDEM_CABECALHO if cab.get(k)]
    tabela = Table(linhas, colWidths=[38 * mm, 132 * mm])
    tabela.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#B8C2CC")),
        ("BACKGROUND", (0, 0), (0, -1), FUNDO_ROTULO),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    historia += [tabela, Spacer(1, 8)]

    for secao in dados["secoes"]:
        historia.append(Paragraph(escape(secao["titulo"]), est["secao"]))
        for p in secao["perguntas"]:
            bloco = [Paragraph(f"{escape(p['id'])} | {escape(p['titulo'])}", est["pergunta"]),
                     Paragraph("Também perguntam: " + escape(" | ".join(p["variacoes"])), est["variacoes"])]
            bloco += [_linha_resposta(l.strip(), est, negrito) for l in p["resposta"].split("\n") if l.strip()]
            bloco.append(Paragraph("Fonte: " + escape(p["fonte"]), est["fonte"]))
            historia.append(KeepTogether(bloco))

    doc = SimpleDocTemplate(str(destino), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm,
                            bottomMargin=18 * mm, title=cab["Título"], author="Time SinergIA",
                            subject=f"Base RAG {slug} v{cab.get('Versão', '')}")
    destino.parent.mkdir(parents=True, exist_ok=True)
    doc.build(historia)
    return destino


if __name__ == "__main__":
    alvos = sys.argv[1:] or list(ARQUIVOS)
    for s in alvos:
        print("gerado:", gerar(s))
