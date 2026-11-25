"""Busca híbrida nas 4 bases e roteamento dinâmico.

Fluxo de ``Recuperador.buscar``:

1. **Candidatos** de todas as bases vigentes: top-N vetorial (cosseno) + BM25
   sobre título, variações e resposta.
2. **Pontuação híbrida**: ``peso_vetorial * cos + (1 - peso) * bm25_norm``.
3. **Viés de roteamento** (pequeno, não decide sozinho):
   * intenção enviada pelo A0 (F1..F5 ou rótulo) -> +0,05 na base indicada;
   * léxico da base presente na pergunta -> +0,03 por termo (até +0,09).
   A busca nunca é restrita à base da intenção: se o A0 classificou como F2
   mas a pergunta é de EPI, a evidência dos trechos vence e o desvio é
   registrado em ``decisao.motivo``.
4. **Aceitação**: o trecho entra se ``cos >= limiar_cosseno`` ou
   ``bm25 >= limiar_bm25``, e se a pontuação final ficar a até
   ``margem_relativa`` do melhor. Base principal = base do melhor trecho;
   outras bases entram como secundárias (pergunta transversal, ex.: luva
   térmica na câmara fria -> EPI + Saúde Ocupacional).
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from ..config import ConfigA2
from ..texto import dobrar, tokens
from .catalogo import BASES, base_da_intencao
from .chunking import Trecho
from .embeddings import Embedder
from .stores import Store


@dataclass
class TrechoPontuado:
    trecho: Trecho
    pontuacao: float
    cosseno: float
    bm25: float


@dataclass
class ResultadoBusca:
    trechos: list[TrechoPontuado]
    base_principal: str | None
    bases: list[str]
    base_intencao: str | None
    termos_lexico: dict[str, list[str]] = field(default_factory=dict)
    diagnostico: dict = field(default_factory=dict)
    relacionados: set[str] = field(default_factory=set)   # IDs trazidos por vizinhança (não pela busca)

    @property
    def vazio(self) -> bool:
        return not self.trechos

    @property
    def melhor(self) -> float:
        return self.trechos[0].pontuacao if self.trechos else 0.0


def _similaridade(a: Trecho, b: Trecho) -> float:
    """Cosseno entre os embeddings; sem embedding (pgvector), Jaccard dos tokens."""
    if a.embedding and b.embedding:
        return sum(x * y for x, y in zip(a.embedding, b.embedding))
    ta, tb = set(tokens(a.texto_indexado)), set(tokens(b.texto_indexado))
    return len(ta & tb) / max(1, len(ta | tb))


class IndiceBM25:
    def __init__(self, trechos: list[Trecho], k1: float = 1.4, b: float = 0.75):
        self.trechos = trechos
        self.k1, self.b = k1, b
        self.docs: list[Counter] = []
        for t in trechos:
            # título e variações contam em dobro: são a "cara" da pergunta
            cabeca = tokens(t.titulo + " " + " ".join(t.variacoes))
            self.docs.append(Counter(cabeca * 2 + tokens(t.resposta)))
        self.n = len(self.docs)
        self.media = (sum(sum(d.values()) for d in self.docs) / self.n) if self.n else 0.0
        df: Counter = Counter()
        for d in self.docs:
            df.update(d.keys())
        self.idf = {termo: math.log(1 + (self.n - f + 0.5) / (f + 0.5)) for termo, f in df.items()}

    def pontuar(self, consulta: str) -> list[float]:
        q = tokens(consulta)
        saida = []
        for d in self.docs:
            tam = sum(d.values())
            s = 0.0
            for termo in q:
                tf = d.get(termo, 0)
                if tf:
                    s += self.idf[termo] * tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * tam / self.media))
            saida.append(s)
        return saida


def termos_do_lexico(pergunta: str) -> dict[str, list[str]]:
    texto = f" {dobrar(pergunta)} "
    achados: dict[str, list[str]] = {}
    for base in BASES.values():
        hits = [t for t in base.lexico if f" {t} " in texto or (len(t) > 4 and t in texto)]
        if hits:
            achados[base.slug] = hits
    return achados


class Recuperador:
    def __init__(self, store: Store, embedder: Embedder, config: ConfigA2):
        self.store = store
        self.embedder = embedder
        self.config = config
        self._bm25: IndiceBM25 | None = None
        self._bm25_assinatura: str | None = None
        # Diagnóstico da última busca (todos os candidatos e por que entraram ou não).
        # Não altera o comportamento; serve à interface visual e à depuração.
        self.ultimo_diagnostico: dict = {}

    def _indice(self, hoje: date) -> IndiceBM25:
        assinatura = self.store.assinatura(hoje)
        if self._bm25 is None or assinatura != self._bm25_assinatura:
            self._bm25 = IndiceBM25(self.store.trechos_vigentes(hoje))
            self._bm25_assinatura = assinatura
        return self._bm25

    def buscar(self, pergunta: str, hoje: date, intencao: str | None = None, k: int | None = None) -> ResultadoBusca:
        cfg = self.config
        k = k or cfg.top_k
        base_int = base_da_intencao(intencao)
        lexico = termos_do_lexico(pergunta)

        indice = self._indice(hoje)
        bm25 = indice.pontuar(pergunta)
        por_id: dict[str, tuple[Trecho, float, float]] = {}
        for t, s in zip(indice.trechos, bm25):
            if s > 0:
                por_id[t.id_trecho] = (t, 0.0, s)
        for t, cos in self.store.buscar_vetorial(self.embedder.embed_consulta(pergunta), cfg.candidatos, hoje):
            _, _, s = por_id.get(t.id_trecho, (t, 0.0, 0.0))
            por_id[t.id_trecho] = (t, cos, s)

        diag = {
            "pergunta": pergunta, "base_intencao": base_int, "lexico": lexico, "candidatos": [],
            "limiares": {"cosseno": cfg.limiar_cosseno_efetivo(), "bm25": cfg.limiar_bm25,
                         "pontuacao": cfg.limiar_pontuacao, "margem_relativa": cfg.margem_relativa},
        }
        self.ultimo_diagnostico = diag
        if not por_id:
            return ResultadoBusca([], None, [], base_int, lexico, diag)

        # BM25 normalizado com piso: evita que uma consulta fraca vire 1,0.
        teto = max(max(s for _, _, s in por_id.values()), cfg.limiar_bm25 * 2)
        limiar_cos = cfg.limiar_cosseno_efetivo()
        pontuados: list[TrechoPontuado] = []
        for t, cos, s in por_id.values():
            nota = cfg.peso_vetorial * max(cos, 0.0) + (1 - cfg.peso_vetorial) * (s / teto)
            bonus = (0.05 if base_int and t.base == base_int else 0.0) + min(0.03 * len(lexico.get(t.base, [])), 0.09)
            nota += bonus
            aceito = not (cos < limiar_cos and s < cfg.limiar_bm25)
            diag["candidatos"].append({
                "id": t.id_pergunta, "base": t.base, "titulo": t.titulo, "cosseno": round(cos, 4),
                "bm25": round(s, 3), "bonus": round(bonus, 3), "nota": round(nota, 4),
                "situacao": "aceito" if aceito else "abaixo dos limiares",
            })
            if aceito:
                pontuados.append(TrechoPontuado(t, round(nota, 4), round(cos, 4), round(s, 3)))

        pontuados.sort(key=lambda p: p.pontuacao, reverse=True)
        diag["candidatos"].sort(key=lambda c: c["nota"], reverse=True)
        if not pontuados or pontuados[0].pontuacao < cfg.limiar_pontuacao:
            for c in diag["candidatos"]:
                if c["situacao"] == "aceito":
                    c["situacao"] = "melhor nota abaixo do mínimo"
            return ResultadoBusca([], None, [], base_int, lexico, diag)
        corte = pontuados[0].pontuacao * cfg.margem_relativa
        escolhidos: list[TrechoPontuado] = []
        vistos: set[str] = set()
        for p in pontuados:
            if p.pontuacao < corte or len(escolhidos) >= k:
                break
            if p.trecho.id_pergunta in vistos:
                continue
            vistos.add(p.trecho.id_pergunta)
            escolhidos.append(p)

        ids_escolhidos = {p.trecho.id_pergunta for p in escolhidos}
        for c in diag["candidatos"]:
            if c["id"] in ids_escolhidos:
                c["situacao"] = "escolhido"
            elif c["situacao"] == "aceito":
                c["situacao"] = "fora do corte (top-k / margem)"
        bases: list[str] = []
        for p in escolhidos:
            if p.trecho.base not in bases:
                bases.append(p.trecho.base)
        diag["base_principal"], diag["bases"] = bases[0], bases
        return ResultadoBusca(escolhidos, bases[0], bases, base_int, lexico, diag)

    # ------------------------------------------------------------------ busca múltipla (RAG completo)
    def buscar_multi(self, consultas: list[str], hoje: date, intencao: str | None = None, tema: str | None = None,
                     k: int | None = None, mmr_lambda: float = 0.75, max_relacionados: int = 2) -> ResultadoBusca:
        """Várias consultas (pergunta autônoma + subconsultas) -> fusão RRF -> MMR -> vizinhos.

        * **RRF** (Reciprocal Rank Fusion): soma 1/(60 + posição) de cada trecho em cada consulta; o tema
          do plano dá +10%. Um trecho que aparece bem em várias formulações sobe.
        * **MMR** (Maximal Marginal Relevance): escolhe os k trechos equilibrando relevância e diversidade,
          para não mandar ao LLM quatro trechos quase iguais.
        * **Vizinhos**: referências cruzadas citadas no texto ("veja a pergunta EPI-Q013") e o par do mesmo
          assunto ("Luva térmica: para que serve" + "Luva térmica: como conservar") entram como contexto
          relacionado, marcados assim no prompt.
        """
        cfg = self.config
        k = k or cfg.top_k
        consultas = [c for c in consultas if c and c.strip()] or [""]
        por_consulta = [(c, self.buscar(c, hoje, intencao, k=max(k * 2, 8))) for c in consultas]
        base = por_consulta[0][1]
        validos = [(c, r) for c, r in por_consulta if not r.vazio]
        diag_consultas = [{"consulta": c, "top": [p.trecho.id_pergunta for p in r.trechos[:5]],
                           "base": r.base_principal} for c, r in por_consulta]
        if not validos:
            d = dict(base.diagnostico)
            d["consultas"] = diag_consultas
            return ResultadoBusca([], None, [], base.base_intencao, base.termos_lexico, d)

        rrf: dict[str, float] = {}
        melhor: dict[str, TrechoPontuado] = {}
        for _, r in validos:
            for pos, p in enumerate(r.trechos, start=1):
                i = p.trecho.id_pergunta
                rrf[i] = rrf.get(i, 0.0) + 1.0 / (60 + pos)
                if i not in melhor or p.pontuacao > melhor[i].pontuacao:
                    melhor[i] = p
        if tema:
            for i, p in melhor.items():
                if p.trecho.base == tema:
                    rrf[i] *= 1.10
        ordem = sorted(rrf, key=rrf.get, reverse=True)
        teto = rrf[ordem[0]]

        escolhidos: list[TrechoPontuado] = []
        while ordem and len(escolhidos) < k:
            def valor(i: str) -> float:
                rel = rrf[i] / teto
                redund = max((_similaridade(melhor[i].trecho, e.trecho) for e in escolhidos), default=0.0)
                return mmr_lambda * rel - (1 - mmr_lambda) * redund
            prox = max(ordem, key=valor)
            ordem.remove(prox)
            if rrf[prox] / teto < 0.35:      # relevância residual baixa: para por aqui
                break
            escolhidos.append(melhor[prox])

        ids_escolhidos = {p.trecho.id_pergunta for p in escolhidos}
        relacionados = self._vizinhos(escolhidos[:2], hoje, ids_escolhidos)[:max_relacionados]
        piso = min(p.pontuacao for p in escolhidos) * 0.9
        trechos = escolhidos + [TrechoPontuado(t, round(piso, 4), 0.0, 0.0) for t in relacionados]

        candidatos: dict[str, dict] = {}
        for _, r in por_consulta:
            for c in r.diagnostico.get("candidatos", []):
                atual = candidatos.get(c["id"])
                if atual is None or c["nota"] > atual["nota"]:
                    candidatos[c["id"]] = dict(c)
        for c in candidatos.values():
            c["rrf"] = round(rrf.get(c["id"], 0.0), 5)
            if c["id"] in ids_escolhidos:
                c["situacao"] = "escolhido"
            elif c["situacao"] == "escolhido":
                c["situacao"] = "fora do corte (fusão / diversidade)"
        for t in relacionados:
            candidatos[t.id_pergunta] = {"id": t.id_pergunta, "base": t.base, "titulo": t.titulo, "cosseno": 0.0,
                                         "bm25": 0.0, "bonus": 0.0, "nota": round(piso, 4), "rrf": 0.0,
                                         "situacao": "relacionado"}

        bases: list[str] = []
        for p in trechos:
            if p.trecho.base not in bases:
                bases.append(p.trecho.base)
        diag = dict(base.diagnostico)
        diag.update({
            "consultas": diag_consultas,
            "candidatos": sorted(candidatos.values(), key=lambda c: (c["situacao"] != "escolhido", -c["nota"])),
            "base_principal": bases[0], "bases": bases, "tema_plano": tema,
            "relacionados": [t.id_pergunta for t in relacionados],
            "metodo": f"{len(consultas)} consulta(s) · fusão RRF · MMR λ={mmr_lambda}",
        })
        self.ultimo_diagnostico = diag
        return ResultadoBusca(trechos, bases[0], bases, base.base_intencao, base.termos_lexico, diag,
                              {t.id_pergunta for t in relacionados})

    def _vizinhos(self, escolhidos: list[TrechoPontuado], hoje: date, ja: set[str]) -> list[Trecho]:
        mapa = {t.id_pergunta: t for t in self._indice(hoje).trechos if t.parte == 1}
        saida: list[Trecho] = []
        for p in escolhidos:
            t = p.trecho
            refs = re.findall(r"\b[A-Z]{2,3}(?:-[A-Z]{3})?-Q\d{3}\b", t.resposta)
            if ":" in t.titulo:   # "Luva térmica: para que serve" <-> "Luva térmica: como conservar"
                prefixo = t.titulo.split(":")[0].strip()
                refs += [o.id_pergunta for o in mapa.values()
                         if o.base == t.base and o.id_pergunta != t.id_pergunta and o.titulo.startswith(prefixo + ":")]
            for r in refs:
                if r in mapa and r not in ja and mapa[r] not in saida:
                    saida.append(mapa[r])
        return saida

    def por_ids(self, ids: list[str], hoje: date) -> list[Trecho]:
        """Busca direta por ID de pergunta (ações com template: F6, F7, crise)."""
        mapa = {t.id_pergunta: t for t in self._indice(hoje).trechos if t.parte == 1}
        return [mapa[i] for i in ids if i in mapa]
