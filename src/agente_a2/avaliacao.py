"""Avaliação do recuperador sem rotulagem manual.

As bases já trazem o gabarito: cada linha "Também perguntam" é uma forma real
de fazer aquela pergunta. Usamos cada variação como consulta e medimos se o ID
dela volta no topo (recall@1 e @3) e se a base certa foi escolhida (acerto de
roteamento). É vazamento parcial (as variações também são indexadas), então
use como teste de regressão e para calibrar limiares; para medir
generalização, rode também ``PERGUNTAS_FORA`` e perguntas novas do grupo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .rag.recuperador import Recuperador

# Perguntas que NÃO devem ser respondidas pelas bases (calibra falso positivo).
PERGUNTAS_FORA = [
    "qual a senha do wifi?",
    "quem ganhou o jogo ontem?",
    "me recomenda um restaurante perto da empresa",
    "como faço um bolo de cenoura?",
    "qual o horário do ônibus fretado?",
    "como reseto a senha do meu e-mail corporativo?",
    "vai ter festa de fim de ano?",
    "qual a previsão do tempo para amanhã?",
]


@dataclass
class Relatorio:
    consultas: int
    recall_1: float
    recall_3: float
    roteamento: float
    fora_aceitas: int
    fora_total: int
    erros: list[tuple[str, str, str | None]]

    def texto(self) -> str:
        linhas = [
            f"consultas (variações): {self.consultas}",
            f"recall@1: {self.recall_1:.1%}   recall@3: {self.recall_3:.1%}   base certa: {self.roteamento:.1%}",
            f"perguntas fora do escopo aceitas: {self.fora_aceitas}/{self.fora_total}",
        ]
        if self.erros:
            linhas.append("piores erros (consulta | esperado | obtido):")
            linhas += [f"  {c[:60]} | {e} | {o}" for c, e, o in self.erros[:15]]
        return "\n".join(linhas)


def avaliar(recuperador: Recuperador, hoje: date) -> Relatorio:
    trechos = [t for t in recuperador.store.trechos_vigentes(hoje) if t.parte == 1]
    n = r1 = r3 = rot = 0
    erros = []
    for t in trechos:
        for v in list(t.variacoes) + list(getattr(t, "variacoes_extras", []) or []):
            n += 1
            res = recuperador.buscar(v, hoje)
            ids = [p.trecho.id_pergunta for p in res.trechos]
            r1 += bool(ids[:1] == [t.id_pergunta])
            r3 += t.id_pergunta in ids[:3]
            rot += res.base_principal == t.base
            if t.id_pergunta not in ids[:3]:
                erros.append((v, t.id_pergunta, ids[0] if ids else None))
    fora = sum(1 for q in PERGUNTAS_FORA if not recuperador.buscar(q, hoje).vazio)
    return Relatorio(n, r1 / n, r3 / n, rot / n, fora, len(PERGUNTAS_FORA), erros)


def calibrar(recuperador: Recuperador, hoje: date) -> str:
    """Sugere limiar de cosseno: entre o p10 das variações e o máximo das perguntas fora."""
    emb = recuperador.embedder
    trechos = [t for t in recuperador.store.trechos_vigentes(hoje) if t.parte == 1]
    positivos = []
    for t in trechos:
        for v in t.variacoes:
            q = emb.embed_consulta(v)
            positivos.append(sum(a * b for a, b in zip(q, t.embedding)))
    negativos = []
    for q in PERGUNTAS_FORA:
        vq = emb.embed_consulta(q)
        negativos.append(max(sum(a * b for a, b in zip(vq, t.embedding)) for t in trechos))
    positivos.sort()
    p10 = positivos[len(positivos) // 10]
    neg = max(negativos)
    sugestao = round((p10 + neg) / 2, 2) if p10 > neg else round(p10, 2)
    return (f"modelo: {emb.nome}\ncosseno das variações com a própria pergunta: p10={p10:.3f} "
            f"mediana={positivos[len(positivos) // 2]:.3f}\nmaior cosseno de pergunta fora do escopo: {neg:.3f}\n"
            f"sugestão: RAG_LIMIAR_COSSENO={sugestao}")
