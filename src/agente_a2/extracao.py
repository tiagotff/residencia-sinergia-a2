"""Extração das interações gravadas para análise e refinamento do A2.

    python -m agente_a2 extrair                 # exportacoes/a2_analise_<data>.xlsx + dataset JSONL
    python -m agente_a2 extrair --dias 30       # só os últimos 30 dias

Gera uma planilha com uma aba por ângulo de análise (todas com filtro e cabeçalho fixo):

  Leia-me            o que é cada aba e como usar para ajustar o A2
  Interacoes         uma linha por resposta, achatada (pergunta, resposta, modo, base, feedback…)
  Feedback           as análises registradas no console
  Busca_candidatos   todos os trechos avaliados em cada busca, com cosseno, BM25, bônus e nota
  Tentativas_LLM     cada chamada ao LLM, aprovada ou não, com os motivos da validação
  Guardrails         cada sinal de entrada acionado (crise, emergência, injeção, terceiros)
  Uso_das_bases      as 132 perguntas das bases: quantas vezes foram citadas, viraram 1º
                     candidato ou receberam feedback negativo (mostra o que nunca é usado)
  Resumo             contagens por base, modo, status e versão do prompt

Os textos já estão mascarados (vêm assim do banco) e o colaborador aparece só como pseudônimo.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select

from .interacoes import CATEGORIAS_FEEDBACK, MOTIVOS_FILA, Interacao, RegistroInteracoes

LEIA_ME = [
    ("Interacoes", "Uma linha por resposta do A2. Filtre por modo, status, base ou feedback para achar padrões."),
    ("Feedback", "Análises feitas no console. 'resposta_referencia' é como o A2 deveria ter respondido."),
    ("Busca_candidatos", "Todos os trechos que a busca avaliou. Se o certo tem nota baixa: falta variação "
                         "'Também perguntam' ou termo no léxico. Se o errado ganha: ajuste limiares ou léxico."),
    ("Tentativas_LLM", "Cada chamada ao LLM. Motivos repetidos de recusa indicam regra a reforçar no prompt."),
    ("Guardrails", "Sinais de entrada acionados. Pergunta legítima bloqueada = regra a afinar."),
    ("Uso_das_bases", "Perguntas das bases nunca citadas podem estar mal escritas ou sem variações; "
                      "as com feedback negativo pedem revisão do texto."),
    ("Resumo", "Visão rápida por base, modo, status e versão do prompt."),
    ("", ""),
    ("Onde ajustar", "Prompt: src/agente_a2/llm/prompts.py · Guardrails: src/agente_a2/guardrails/ · "
                     "Léxico: src/agente_a2/rag/catalogo.py · Limiares: .env · Conteúdo: PDFs em bases_pdf/"),
    ("Privacidade", "Perguntas mascaradas (CPF, CID, e-mail, telefone) e colaborador pseudonimizado. "
                    "Não compartilhe fora do grupo do projeto."),
]


def _local(dt: datetime | None, fuso: ZoneInfo) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(fuso).replace(tzinfo=None)   # Excel não aceita fuso


def _lista(v) -> str:
    return ", ".join(map(str, v)) if v else ""


def coletar(registro: RegistroInteracoes, *, dias: int | None = None, fuso: str = "America/Sao_Paulo",
            perguntas_bases: list[dict] | None = None) -> dict[str, list[dict]]:
    """Lê o banco e devolve {aba: [linhas]} prontas para planilha ou CSV."""
    tz = ZoneInfo(fuso)
    q = select(Interacao).order_by(Interacao.id)
    if dias:
        q = q.where(Interacao.criado_em >= datetime.now(timezone.utc) - timedelta(days=dias))

    abas: dict[str, list[dict]] = defaultdict(list)
    citacoes: Counter = Counter()
    top1: Counter = Counter()
    negativos: Counter = Counter()

    with registro._sessao() as s:
        for i in s.scalars(q).all():
            tel = i.telemetria or {}
            diag = tel.get("diag") or {}
            tentativas = tel.get("tentativas") or []
            fb = i.feedbacks[-1] if i.feedbacks else None
            motivos_recusa = sorted({m.split(":")[0] for t in tentativas for m in t.get("motivos", [])})
            quando = _local(i.criado_em, tz)

            abas["Interacoes"].append({
                "id": i.id, "quando": quando, "origem": i.origem, "acao": i.acao, "colaborador": i.colaborador,
                "intencao": i.intencao, "pergunta": i.pergunta, "resposta": i.resposta, "status": i.status,
                "modo": i.modo, "base": i.base, "bases_consultadas": _lista(i.bases), "ids_citados": _lista(i.ids_trechos),
                "cobertura": i.cobertura, "usou_llm": i.usou_llm, "modelo": i.modelo, "confianca": i.confianca,
                "latencia_ms": i.latencia_ms, "tentativas_llm": i.tentativas_llm, "motivos_recusa_llm": _lista(motivos_recusa),
                "sinais_entrada": _lista(x["regra"] for x in tel.get("sinais", [])),
                "dados_mascarados": _lista(tel.get("mascarados")), "sensivel": i.sensivel,
                "pedido_epi": i.id_solicitacao_epi, "base_intencao": diag.get("base_intencao"),
                "intencao_divergiu": bool(diag.get("base_intencao") and diag.get("base_principal")
                                          and diag["base_intencao"] != diag["base_principal"]),
                "melhor_nota": (diag.get("candidatos") or [{}])[0].get("nota"),
                "pergunta_reescrita": (tel.get("plano") or {}).get("autonoma"),
                "subconsultas": _lista((tel.get("plano") or {}).get("subconsultas")),
                "relacionados": _lista(diag.get("relacionados")),
                "fundamentacao": (tel.get("fundamentacao") or {}).get("score"),
                "frases_sem_apoio": " | ".join((tel.get("fundamentacao") or {}).get("sem_apoio") or []),
                "complemento_geral": tel.get("complemento"),
                "complemento_descartado": (tel.get("complemento_descartado") or {}).get("motivo"),
                "versao_prompt": i.versao_prompt, "versao_a2": i.versao_a2,
                "fila_melhoria": _lista(MOTIVOS_FILA.get(m, m) for m in registro._motivos_fila(i)),
                "feedback": fb.avaliacao if fb else None,
                "categoria": CATEGORIAS_FEEDBACK.get(fb.categoria, fb.categoria) if fb and fb.categoria else None,
                "comentario": fb.comentario if fb else None,
                "resposta_referencia": fb.resposta_sugerida if fb else None,
                "base_correta": fb.base_correta if fb else None,
                "situacao_feedback": fb.situacao if fb else None,
                "motivo_decisao": i.motivo,
            })

            for f in i.feedbacks:
                abas["Feedback"].append({
                    "id_feedback": f.id, "id_interacao": i.id, "quando": _local(f.criado_em, tz),
                    "avaliacao": f.avaliacao, "categoria": CATEGORIAS_FEEDBACK.get(f.categoria, f.categoria),
                    "situacao": f.situacao, "pergunta": i.pergunta, "resposta_a2": i.resposta,
                    "resposta_referencia": f.resposta_sugerida, "base_obtida": i.base, "base_correta": f.base_correta,
                    "comentario": f.comentario, "autor": f.autor, "modo": i.modo, "versao_prompt": i.versao_prompt,
                })
                if f.avaliacao == "negativo":
                    for ref in i.ids_trechos or []:
                        negativos[ref] += 1

            for pos, c in enumerate(diag.get("candidatos") or [], start=1):
                abas["Busca_candidatos"].append({
                    "id_interacao": i.id, "pergunta": i.pergunta, "intencao": i.intencao, "posicao": pos,
                    "id_trecho": c.get("id"), "base": c.get("base"), "titulo_trecho": c.get("titulo"),
                    "cosseno": c.get("cosseno"), "bm25": c.get("bm25"), "bonus": c.get("bonus"), "nota": c.get("nota"),
                    "situacao": c.get("situacao"), "citado_na_resposta": c.get("id") in (i.ids_trechos or []),
                    "feedback": fb.avaliacao if fb else None,
                })
                if pos == 1:
                    top1[c.get("id")] += 1

            for t in tentativas:
                abas["Tentativas_LLM"].append({
                    "id_interacao": i.id, "pergunta": i.pergunta, "tentativa": t.get("n"),
                    "resultado": "falha" if t.get("erro") else ("aprovada" if t.get("aprovada") else "recusada"),
                    "motivos": "; ".join(t.get("motivos", [])), "erro": t.get("erro"), "ms": t.get("ms"),
                    "resposta_bruta": t.get("resposta"), "modo_final": i.modo, "versao_prompt": i.versao_prompt,
                    "modelo": i.modelo,
                })

            for x in tel.get("sinais", []):
                abas["Guardrails"].append({
                    "id_interacao": i.id, "quando": quando, "tipo": x.get("tipo"), "regra": x.get("regra"),
                    "peso": x.get("peso"), "bloqueou": (i.modo or "").startswith("guardrail_"),
                    "pergunta": i.pergunta, "feedback": fb.avaliacao if fb else None,
                    "categoria_feedback": fb.categoria if fb else None,
                })

            for ref in i.ids_trechos or []:
                citacoes[ref] += 1

    for p in perguntas_bases or []:
        abas["Uso_das_bases"].append({
            "id": p["id"], "base": p["base"], "secao": p["secao"], "pergunta": p["titulo"],
            "variacoes": len(p["variacoes"]), "vezes_citada": citacoes.get(p["id"], 0),
            "vezes_1o_candidato": top1.get(p["id"], 0), "feedback_negativo": negativos.get(p["id"], 0),
            "nunca_usada": citacoes.get(p["id"], 0) == 0 and top1.get(p["id"], 0) == 0,
        })

    inter = abas["Interacoes"]
    for titulo, chave in [("Por base", "base"), ("Por modo", "modo"), ("Por status", "status"),
                          ("Por versão do prompt", "versao_prompt"), ("Por intenção do A0", "intencao")]:
        cont = Counter(r[chave] or "—" for r in inter)
        for valor, n in cont.most_common():
            grupo = [r for r in inter if (r[chave] or "—") == valor]
            abas["Resumo"].append({
                "visao": titulo, "valor": valor, "interacoes": n,
                "percentual": round(n / len(inter), 4) if inter else 0,
                "feedback_positivo": sum(1 for r in grupo if r["feedback"] == "positivo"),
                "feedback_negativo": sum(1 for r in grupo if r["feedback"] == "negativo"),
                "confianca_media": round(sum(r["confianca"] for r in grupo if r["confianca"] is not None) /
                                         max(1, sum(1 for r in grupo if r["confianca"] is not None)), 3),
                "latencia_media_ms": round(sum(r["latencia_ms"] or 0 for r in grupo) / len(grupo)),
            })
    return abas


ORDEM = ["Interacoes", "Feedback", "Busca_candidatos", "Tentativas_LLM", "Guardrails", "Uso_das_bases", "Resumo"]
TEXTO_LONGO = {"pergunta_reescrita", "subconsultas", "frases_sem_apoio", "complemento_geral", "pergunta", "resposta", "resposta_a2", "resposta_referencia", "comentario", "motivo_decisao",
               "resposta_bruta", "motivos", "titulo_trecho", "fila_melhoria"}


def salvar_xlsx(abas: dict[str, list[dict]], destino: Path) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Leia-me"
    ws.append(["SinergIA · A2 — extração para análise", f"gerada em {datetime.now():%d/%m/%Y %H:%M}"])
    ws["A1"].font = Font(bold=True, size=14, color="0B6A5F")
    ws.append([])
    ws.append(["Aba", "Para que serve"])
    for c in ws[3]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="0B6A5F")
    for aba, texto in LEIA_ME:
        ws.append([aba, texto])
        ws.cell(ws.max_row, 1).font = Font(bold=True)
    ws.append([])
    ws.append(["Linhas por aba", ""])
    ws.cell(ws.max_row, 1).font = Font(bold=True)
    for nome in ORDEM:
        ws.append([nome, len(abas.get(nome, []))])
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 120
    for linha in ws.iter_rows(min_row=4):
        linha[1].alignment = Alignment(wrap_text=True, vertical="top")

    cabecalho = PatternFill("solid", fgColor="0B6A5F")
    for nome in ORDEM:
        linhas = abas.get(nome, [])
        ws = wb.create_sheet(nome)
        if not linhas:
            ws.append(["Sem dados no período."])
            continue
        colunas = list(linhas[0].keys())
        ws.append(colunas)
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = cabecalho
            c.alignment = Alignment(vertical="center")
        for r in linhas:
            ws.append([r.get(c) for c in colunas])
        ws.freeze_panes = "B2"
        ws.auto_filter.ref = ws.dimensions
        for idx, col in enumerate(colunas, start=1):
            letra = get_column_letter(idx)
            if col in TEXTO_LONGO:
                ws.column_dimensions[letra].width = 60
                for cel in ws[letra][1:]:
                    cel.alignment = Alignment(wrap_text=True, vertical="top")
            else:
                maior = max(len(str(col)), *(len(str(r.get(col) or "")) for r in linhas[:200]))
                ws.column_dimensions[letra].width = min(max(10, maior + 2), 40)
            if col == "quando":
                for cel in ws[letra][1:]:
                    cel.number_format = "dd/mm/yyyy hh:mm"
            if col in {"confianca", "percentual", "fundamentacao"}:
                for cel in ws[letra][1:]:
                    cel.number_format = "0.0%"

    destino.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destino)
    return destino


def extrair(registro: RegistroInteracoes, pasta: Path, *, dias: int | None = None, fuso: str = "America/Sao_Paulo",
            perguntas_bases: list[dict] | None = None) -> dict[str, Path | int]:
    abas = coletar(registro, dias=dias, fuso=fuso, perguntas_bases=perguntas_bases)
    carimbo = f"{date.today():%Y%m%d}_{datetime.now():%H%M}"
    xlsx = salvar_xlsx(abas, pasta / f"a2_analise_{carimbo}.xlsx")
    dataset = pasta / f"a2_dataset_avaliacao_{carimbo}.jsonl"
    dataset.write_text(registro.exportar_dataset(), encoding="utf-8")
    return {"planilha": xlsx, "dataset": dataset, **{k: len(v) for k, v in abas.items()}}


def perguntas_do_indice(store, hoje: date) -> list[dict]:
    return [{"id": t.id_pergunta, "base": t.base, "secao": t.secao, "titulo": t.titulo, "variacoes": t.variacoes}
            for t in sorted(store.trechos_vigentes(hoje), key=lambda x: (x.base, x.ordem)) if t.parte == 1]
