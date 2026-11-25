"""Detecção de relato de EPI na mensagem ATUAL do colaborador (nunca no histórico).

Aprendizados das interações reais (v0.3):
  * "perdi as minhas luvas", "perdi luvas" não eram reconhecidos (a regra exigia artigo depois
    do verbo) e o A2 mandava procurar o RH;
  * "quero novas luvas", "preciso de luvas" são pedidos sem motivo: o roteiro é o EPI-Q021 e
    o A2 deve perguntar o que aconteceu, sem abrir pedido às cegas;
  * "luvas", sozinho, depois de uma conversa sobre luva rasgada, abriu um 2º pedido porque o
    LLM inferiu o relato pelo histórico.

Situações: avariado, perdido, nao_recebido, tamanho_inadequado (abrem solicitação) e
pedido (sem motivo: orienta e pergunta).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..texto import dobrar

_EPI = (r"(epis?|equipamentos? de protecao|luvas?|botas?|botinas?|calcados?(?: de seguranca)?|sapatos?(?: de seguranca)?|"
        r"oculos|protetor(?:es)?(?: auricular(?:es)?| facial)?|plugues?|tampoes?|abafador(?:es)?|mascaras?|respirador(?:es)?|"
        r"pff2|capacetes?|aventa(?:l|is)|jaquetas?(?: termicas?)?|japonas?|toucas?|viseiras?|mangotes?|perneiras?|"
        r"cintos?(?: de seguranca)?)")
RE_EPI = re.compile(rf"\b{_EPI}\b")

_DANO = (r"(rasg\w*|fur(?:ou|ad[oa]s?|aram)|quebr\w*|trinc\w*|descol\w*|estrag\w*|danific\w*|romp\w*|arrebent\w*|"
         r"rachad[oa]s?|rachou|solt(?:ou|aram)|desfi\w*|gast[oa]s? demais|nao veda|nao protege|com defeito|defeituos[oa]s?)")
_PERDA = r"(perdi|perdeu|perderam|sumiu|sumiram|extravi\w*|roubaram|furtaram|esqueci|deixei cair no)"
_NAO_RECEBI = (r"(nao recebi|ainda nao (?:recebi|tenho|chegou|chegaram)|nao me (?:deram|entregaram)|nao tenho|"
               r"estou sem|to sem|tô sem|fiquei sem|nunca recebi)")
_TAMANHO = r"(apertad[oa]s?|aperta|larg[oa]s?|grande demais|pequen[oa]s? demais|nao serve|escorrega|machuca|tamanho errado)"
# Pedido em 1ª pessoa ("quero novas luvas", "preciso de luva"). Pergunta sobre o processo
# ("qual o prazo da reposição?", "como peço EPI novo?") não é pedido: a busca responde.
_PEDIDO = r"(quero|queria|preciso|precisava|precisando|gostaria de|solicito|me (?:da|de|manda|mande|arruma|arrume))"
_INTERROGATIVA = re.compile(r"^\s*(qual|quais|quanto|quantos|quantas|como|quando|onde|por que|porque|o que|quem)\b")
# Pergunta em tese: "o que faço SE a luva rasgar", "CASO eu perca", "QUANDO a bota descolar"
_HIPOTESE = re.compile(r"\b(se|caso|quando|e se)\b[^.?!]{0,30}\b(rasgar|furar|quebrar|trincar|descolar|estragar|perder|"
                       r"perca|sumir|romper|danificar|apertar|nao servir)\b")


@dataclass
class DeteccaoEPI:
    situacao: str            # avariado | perdido | nao_recebido | tamanho_inadequado | pedido
    epi: str | None

    @property
    def abre_solicitacao(self) -> bool:
        return self.situacao != "pedido"


def _perto(texto: str, a: str, b: str, janela: int = 45) -> bool:
    """a e b na mesma frase, em qualquer ordem, a até `janela` caracteres."""
    return bool(re.search(rf"\b{a}\b[^.?!]{{0,{janela}}}\b{b}\b", texto) or
                re.search(rf"\b{b}\b[^.?!]{{0,{janela}}}\b{a}\b", texto))


def detectar(pergunta: str) -> DeteccaoEPI | None:
    d = dobrar(pergunta)
    m = RE_EPI.search(d)
    if not m:
        return None
    epi = m.group(0)
    if _HIPOTESE.search(d):
        return None
    if _perto(d, _DANO, _EPI):
        return DeteccaoEPI("avariado", epi)
    if _perto(d, _PERDA, _EPI):
        return DeteccaoEPI("perdido", epi)
    if _perto(d, _NAO_RECEBI, _EPI):
        return DeteccaoEPI("nao_recebido", epi)
    if _perto(d, _TAMANHO, _EPI, 30):
        return DeteccaoEPI("tamanho_inadequado", epi)
    if _perto(d, _PEDIDO, _EPI, 30) and not _INTERROGATIVA.search(d):
        return DeteccaoEPI("pedido", epi)
    return None


def tem_sinal_de_problema(pergunta: str) -> bool:
    """Confirma um relato apontado pelo LLM: precisa de EPI + algum problema na mensagem atual."""
    d = dobrar(pergunta)
    if _HIPOTESE.search(d):
        return False
    return bool(RE_EPI.search(d) and re.search(rf"\b({_DANO}|{_PERDA}|{_NAO_RECEBI}|{_TAMANHO}|problema)\b", d))


_NOMES = {"luva": "a sua luva", "bota": "a sua bota", "botina": "a sua botina", "mascara": "a sua máscara",
          "jaqueta": "a sua jaqueta", "japona": "a sua japona", "touca": "a sua touca", "viseira": "a sua viseira",
          "perneira": "a sua perneira", "capacete": "o seu capacete", "oculos": "os seus óculos",
          "protetor": "o seu protetor", "avental": "o seu avental", "calcado": "o seu calçado",
          "sapato": "o seu sapato", "cinto": "o seu cinto", "respirador": "o seu respirador",
          "plugue": "o seu protetor auricular", "abafador": "o seu abafador", "mangote": "o seu mangote",
          "pff2": "a sua máscara PFF2"}


def nome_com_artigo(epi: str | None) -> str:
    """'luvas' -> 'a sua luva'; desconhecido -> 'o EPI'."""
    if not epi:
        return "o EPI"
    raiz = epi.split()[0]
    for chave, nome in _NOMES.items():
        if raiz == chave or raiz.rstrip("s") == chave or raiz.removesuffix("es") == chave:
            return nome
    return "o EPI"
