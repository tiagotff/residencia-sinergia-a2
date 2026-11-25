"""Guardrails de entrada: tudo o que roda ANTES do LLM.

Camadas (em ordem):

1. ``sanitizar`` — Unicode NFC, remove caracteres invisíveis/de controle,
   colapsa espaços, corta no limite e neutraliza delimitadores do prompt
   (``<``/``>`` viram ``‹``/``›``) para que o texto do usuário nunca feche
   uma tag ``<pergunta_colaborador>`` ou abra uma ``<system>``.
2. ``mascarar_dados_pessoais`` — CPF, e-mail, telefone e código CID saem do
   texto antes de ir ao provedor externo de LLM (LGPD art. 11; relatório 18).
3. ``classificar`` — detecta, por regras explicáveis:
   * **crise** (risco à vida) e **emergência** (acidente/mal-estar agora):
     resposta aprovada da base, sem LLM, ``sensivel=True`` e escalonamento;
   * **injeção de prompt** (PT/EN/ES): bloqueia sem chamar o LLM;
   * **dados de terceiros** (salário/atestado/doença de outra pessoa): recusa.

As regras são deliberadamente conservadoras e auditáveis; o sinal fica em
``decisao.motivo``. A defesa não depende só delas: o prompt trata entrada
como dado, a saída é validada e o LLM nunca tem ferramenta para agir.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from ..texto import dobrar

_INVISIVEIS = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff\u00ad]")
_CONTROLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


@dataclass
class Sinal:
    tipo: str
    peso: float
    regra: str


@dataclass
class AnaliseEntrada:
    texto: str                      # sanitizado + mascarado: é o que vai ao LLM
    truncado: bool = False
    mascarados: list[str] = field(default_factory=list)
    sinais: list[Sinal] = field(default_factory=list)

    def pontos(self, tipo: str) -> float:
        return sum(s.peso for s in self.sinais if s.tipo == tipo)

    @property
    def crise(self) -> bool:
        return self.pontos("crise") >= 1.0

    @property
    def emergencia(self) -> bool:
        return self.pontos("emergencia") >= 1.0

    @property
    def injecao(self) -> bool:
        return self.pontos("injecao") >= 1.0

    @property
    def suspeita_injecao(self) -> bool:
        return 0 < self.pontos("injecao") < 1.0

    @property
    def terceiros(self) -> bool:
        return self.pontos("terceiros") >= 1.0

    def regras(self) -> list[str]:
        return [s.regra for s in self.sinais]


def sanitizar(texto: str, max_chars: int) -> tuple[str, bool]:
    texto = unicodedata.normalize("NFC", texto or "")
    texto = _INVISIVEIS.sub("", texto)
    texto = _CONTROLE.sub(" ", texto)
    texto = texto.replace("<", "‹").replace(">", "›")
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto).strip()
    truncado = len(texto) > max_chars
    return (texto[:max_chars], truncado)


_PII = [
    ("cpf", re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"), "[CPF]"),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[EMAIL]"),
    ("telefone", re.compile(r"(?<!\d)(?:\+?55\s?)?\(?\d{2}\)?\s?9?\d{4}[-\s]?\d{4}(?!\d)"), "[TELEFONE]"),
    # CID só quando nomeado ("CID F32", "cid: M54.5") ou no formato com subcategoria
    # (letra + 2 dígitos + .dígito). "B91" (espécie de benefício do INSS) não é mascarado.
    ("cid", re.compile(r"(?i)\bcid[\s:.\-]*(?:10[\s:\-]*)?[a-z]\d{2}(?:\.\d{1,2})?\b"), "[CID]"),
    ("cid", re.compile(r"\b[A-TV-Z]\d{2}\.\d{1,2}\b"), "[CID]"),
]


def mascarar_dados_pessoais(texto: str) -> tuple[str, list[str]]:
    achados: list[str] = []
    for nome, padrao, troca in _PII:
        texto, n = padrao.subn(troca, texto)
        if n:
            achados.append(nome)
    return texto, sorted(set(achados))


# ---------------- regras (sobre texto dobrado: minúsculo, sem acento) -----------------

_REGRAS_INJECAO: list[tuple[str, float, re.Pattern]] = [
    ("ignorar_instrucoes", 1.0, re.compile(
        r"\b(ignor\w*|desconsider\w*|esquec\w*|esqueca|descart\w*|disregard|forget|olvid\w*|override|sobrescrev\w*)\b"
        r"[^.?!\n]{0,60}\b(instruc\w*|regras?|prompt|orientac\w*|diretriz\w*|instructions?|rules?|anteriores|previous|above|acima|sistema|system)")),
    ("troca_de_papel", 1.0, re.compile(
        r"\b(a partir de agora|de agora em diante|from now on|desde ahora)\b[^.?!\n]{0,60}\b(voce|you|tu|seja|e|is|eres|aja|responda)\b")),
    ("roleplay", 0.6, re.compile(r"\b(aja|atue|finja|comporte-se|se comporte|act|pretend|roleplay|simule|imagine que voce e)\s+(como|as|que|ser|to be)\b")),
    ("pede_prompt", 1.0, re.compile(
        r"\b(revel\w*|mostr\w*|repit\w*|imprim\w*|exib\w*|diga|liste|copie|reveal|print|show|repeat|output|leak)\b"
        r"[^.?!\n]{0,50}\b(prompt|instruc\w*|regras internas|system message|mensagem de sistema|configurac\w*|instructions)")),
    ("cita_prompt", 0.7, re.compile(r"\b(system prompt|prompt do sistema|prompt de sistema|suas instrucoes|your instructions|instrucoes iniciais|initial instructions)\b")),
    ("modo_especial", 1.0, re.compile(r"\b(modo|mode)\s+(desenvolvedor|developer|dev|admin|administrador|deus|god|debug|sem restric\w*|jailbreak|dan)\b")),
    ("jailbreak", 1.0, re.compile(r"\b(jailbreak|do anything now|dan prompt|sem (restricoes|filtros?|censura)|without (restrictions|filters))\b")),
    ("marcador_de_papel", 0.8, re.compile(r"(^|\n)\s*(system|assistant|sistema|assistente|developer)\s*[:›]")),
    ("tag_do_prompt", 1.0, re.compile(r"[‹<]\s*/?\s*(system|sistema|trechos?|pergunta_colaborador|historico_resumo|perfil|instruc\w*|im_start|im_end)\b")),
    ("campos_de_saida", 0.6, re.compile(r"\b(ids_usados|relato_epi|cobertura\s*[:=]|sensivel\s*[:=]|\"resposta\"\s*:)")),
    ("autoridade_falsa", 0.6, re.compile(r"\b(sou (o )?(administrador|desenvolvedor|admin)|mensagem (do|da) (anthropic|openai|groq|sistema|equipe sinergia)|ordem do rh para voce)\b")),
    ("bloco_codificado", 0.6, re.compile(r"[a-z0-9+/]{80,}={0,2}")),
    ("cerca_de_codigo", 0.4, re.compile(r"```")),
]

_REGRAS_CRISE: list[tuple[str, float, re.Pattern]] = [
    ("ideacao", 1.0, re.compile(r"\b(suicid\w*|me matar|tirar (a )?minha (propria )?vida|acabar com (a minha vida|tudo de vez)|quero morrer|nao quero (mais )?viver|me machucar|me cortar de proposito|autolesao|automutil\w*)\b")),
    ("desespero", 0.6, re.compile(r"\b(nao aguento mais|nao vejo saida|estou em crise|sem esperanca|ninguem se importa)\b")),
    ("pedido_ajuda", 0.5, re.compile(r"\b(preciso de ajuda agora|nao estou bem)\b")),
]

_REGRAS_EMERGENCIA: list[tuple[str, float, re.Pattern]] = [
    ("acidente_agora", 1.0, re.compile(r"\b(me cortei|me machuquei|me queimei|cai |sofri um acidente|estou sangrando|sangrando muito|desmaiei|desmaiou|bati a cabeca|quebrei o (braco|pe|dedo))\b")),
    ("mal_estar_agora", 1.0, re.compile(r"\b(estou|to|tô) (passando mal|tonto|tonta|com falta de ar|com dor no peito)\b|\bfalta de ar\b|\bdor no peito\b")),
]

_ASSUNTOS_PESSOAIS = r"(salario|holerite|atestado|cid|doenca|diagnostico|afastamento|ferias|endereco|telefone|exame|ponto|remedio)"

_REGRAS_TERCEIROS: list[tuple[str, float, re.Pattern]] = [
    ("dado_de_colega", 1.0, re.compile(
        _ASSUNTOS_PESSOAIS + r"\s+(d[oa]s?|de)\s+(meu |minha |nosso |nossa |um |uma )?"
        r"(colega|gestor|gestora|chefe|supervisor\w*|funcionari\w*|outr[oa]s?|lider|coordenador\w*)\b")),
    ("quem_esta", 1.0, re.compile(r"\bquem (esta|estao|ficou|ficaram) (afastad\w*|de atestado|doente|de ferias)\b")),
    ("lista_pessoas", 1.0, re.compile(r"\b(lista|relacao|nomes) (de|dos|das) (colaboradores|funcionarios|pessoas) (afastad\w*|doentes|com atestado)\b")),
]
# Nome próprio depois do assunto ("salário do João"): roda no texto sem acento, com maiúsculas.
_REGRA_NOME_PROPRIO = re.compile(r"(?i:" + _ASSUNTOS_PESSOAIS + r")\s+(?i:d[oa]|de)\s+[A-Z][a-z]{2,}")


def _aplicar(texto_dobrado: str, regras, tipo: str) -> list[Sinal]:
    return [Sinal(tipo, peso, f"{tipo}:{nome}") for nome, peso, padrao in regras if padrao.search(texto_dobrado)]


def analisar(texto_bruto: str, max_chars: int = 1500) -> AnaliseEntrada:
    sanitizado, truncado = sanitizar(texto_bruto, max_chars)
    dobrado = dobrar(sanitizado)
    sinais = (
        _aplicar(dobrado, _REGRAS_INJECAO, "injecao")
        + _aplicar(dobrado, _REGRAS_CRISE, "crise")
        + _aplicar(dobrado, _REGRAS_EMERGENCIA, "emergencia")
        + _aplicar(dobrado, _REGRAS_TERCEIROS, "terceiros")
    )
    if _REGRA_NOME_PROPRIO.search(_sem_acento(sanitizado)):
        sinais.append(Sinal("terceiros", 1.0, "terceiros:nome_proprio"))
    if truncado:
        sinais.append(Sinal("injecao", 0.2, "injecao:texto_longo_truncado"))
    mascarado, achados = mascarar_dados_pessoais(sanitizado)
    return AnaliseEntrada(texto=mascarado, truncado=truncado, mascarados=achados, sinais=sinais)


def _sem_acento(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def neutralizar_contexto(texto: str | None, max_chars: int = 1200) -> str:
    """Para campos que viram contexto do prompt (historico_resumo, trechos)."""
    if not texto:
        return ""
    limpo, _ = sanitizar(texto, max_chars)
    limpo, _ = mascarar_dados_pessoais(limpo)
    return limpo
