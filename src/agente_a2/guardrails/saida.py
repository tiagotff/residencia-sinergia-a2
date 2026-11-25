"""Guardrails de saída: validação da resposta do LLM antes de virar ``saidas``.

Checagens (qualquer falha -> uma nova tentativa com o motivo; se falhar de
novo, cai na resposta extrativa, que só usa texto aprovado da base):

* JSON válido no esquema ``RespostaLLM``;
* ``ids_usados`` ⊂ IDs recuperados (nada de fonte inventada) e não vazio
  quando ``cobertura != "nenhuma"``;
* **números** citados na resposta precisam aparecer nos trechos usados ou na
  pergunta (pega prazo/valor alucinado: "30 dias" onde a base diz "24 horas");
* sem **vazamento** do prompt (tags, nomes de campos, trechos das regras);
* sem **orientação médica** (remédio, dose, diagnóstico);
* sem **tom punitivo** (demissão, justa causa, fraude) que não esteja na base;
* tamanho e formato (sem markdown, até ``max_chars``).

É a "checagem prévia de F2 e F5" recomendada no relatório (19.1, item 3),
feita por regras e sem custo de LLM; o Judge continua avaliando depois.
"""

from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from ..texto import dobrar, numeros


class RelatoEPI(BaseModel):
    situacao: Literal["avariado", "perdido", "nao_recebido", "tamanho_inadequado"]
    epi_mencionado: str | None = Field(default=None, max_length=80)


class RespostaLLM(BaseModel):
    resposta: str
    ids_usados: list[str] = Field(default_factory=list)
    cobertura: Literal["total", "parcial", "nenhuma"]
    sensivel: bool = False
    relato_epi: RelatoEPI | None = None
    # Conhecimento geral do modelo (dica prática), separado da resposta fundamentada nas bases.
    complemento: str | None = Field(default=None, max_length=400)

    @field_validator("ids_usados", mode="before")
    @classmethod
    def _lista(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return v


_VAZAMENTO = re.compile(
    r"(‹|<)\s*/?\s*(trecho|trechos|pergunta_colaborador|historico_resumo|perfil|entendimento|system)|ids_usados|relato_epi|"
    r"regras de conteudo|protecao contra instrucoes|formato de saida",
)
_MEDICO = [
    re.compile(r"\b(tome|tomar|use|usar|aplique|aplicar|ingira)\b[^.]{0,30}\b\d+\s?(mg|ml|g|gotas?|comprimidos?|capsulas?)\b"),
    re.compile(r"\b(dipirona|paracetamol|ibuprofeno|nimesulida|diclofenaco|antibiotic\w*|antidepressiv\w*|ansiolitic\w*|"
               r"clonazepam|rivotril|fluoxetina|sertralina|corticoide|relaxante muscular|anti-inflamatorio)\b"),
    re.compile(r"\bvoce (tem|esta com|sofre de|provavelmente tem|deve ter)\b[^.]{0,25}\b(tendinite|burnout|depressao|"
               r"ansiedade|ler|dort|lesao|hernia|bursite|sindrome|doenca|infeccao|alergia)\b"),
]
_PUNITIVO = re.compile(r"\b(justa causa|demissao|demitid\w*|punic\w*|punid\w*|advertencia|suspensao|fraude|mentir\w*)\b")
_MARKDOWN = re.compile(r"(\*\*|__|^#+\s|^\s*[-*]\s)", re.MULTILINE)


def extrair_json(bruto: str) -> dict:
    texto = bruto.strip()
    texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto)
    ini, fim = texto.find("{"), texto.rfind("}")
    if ini < 0 or fim <= ini:
        raise ValueError("sem objeto JSON")
    return json.loads(texto[ini:fim + 1])


_CARACTERES = str.maketrans({"\u202f": " ", "\u00a0": " ", "\u2009": " ", "\u2011": "-", "\u2010": "-",
                             "\u2012": "-", "\u2013": "–", "\u200b": ""})


def limpar_formato(texto: str) -> str:
    texto = texto.translate(_CARACTERES)
    texto = _MARKDOWN.sub("", texto)
    texto = re.sub(r"\s*\n\s*", " ", texto)
    return re.sub(r"\s{2,}", " ", texto).strip()


def validar(
    bruto: str,
    *,
    ids_recuperados: dict[str, str],   # id_pergunta -> texto do trecho (título + resposta + fonte)
    pergunta: str,
    max_chars: int = 700,
) -> tuple[RespostaLLM | None, list[str]]:
    """Devolve (resposta validada, []) ou (None, [motivos])."""
    try:
        r = RespostaLLM.model_validate(extrair_json(bruto))
    except (ValueError, ValidationError, json.JSONDecodeError) as e:
        return None, [f"json_invalido: {str(e)[:120]}"]

    motivos: list[str] = []
    r.resposta = limpar_formato(r.resposta)
    validos = [i for i in r.ids_usados if i in ids_recuperados]
    inventados = [i for i in r.ids_usados if i not in ids_recuperados]
    if inventados:
        motivos.append(f"ids_inexistentes: {inventados}")
    r.ids_usados = list(dict.fromkeys(validos))

    if r.cobertura != "nenhuma" and not r.ids_usados:
        motivos.append("sem_fonte: cobertura total/parcial exige ids_usados")
    minimo = 1 if r.cobertura == "nenhuma" else 15
    if not (minimo <= len(r.resposta) <= max_chars):
        motivos.append(f"tamanho_resposta: {len(r.resposta)} caracteres (limite {max_chars})")

    resposta_d = dobrar(r.resposta)
    if _VAZAMENTO.search(resposta_d):
        motivos.append("vazamento_de_prompt")
    if any(p.search(resposta_d) for p in _MEDICO):
        motivos.append("orientacao_medica")

    base_usada = dobrar(" ".join(ids_recuperados[i] for i in r.ids_usados)) if r.ids_usados else ""
    m = _PUNITIVO.search(resposta_d)
    if m and m.group(0) not in base_usada:
        motivos.append(f"tom_punitivo: '{m.group(0)}'")

    if r.cobertura != "nenhuma":
        permitidos = numeros(base_usada) | numeros(pergunta)
        soltos = sorted(numeros(r.resposta) - permitidos)
        if soltos:
            motivos.append(f"numeros_sem_fonte: {soltos}")

    return (None, motivos) if motivos else (r, [])


# ---------------------------------------------------------------- complemento (conhecimento geral)
_COMPLEMENTO_PROIBIDO = re.compile(
    r"\d|\b(lei|leis|nr|clt|norma\w*|sumula|artigo|direito a|tem direito|obrigatori\w*|proibid\w*|empresa deve|"
    r"a empresa (paga|oferece|garante)|prazo|salario|desconto|beneficio|ferias|licenca|inss|fgts|estabilidade|"
    r"justa causa|demiss\w*|advertencia)\b")


def validar_complemento(texto: str | None) -> tuple[str | None, str | None]:
    """(complemento aceito, motivo da recusa). Dica geral não pode trazer regra, número, direito ou saúde clínica."""
    if not texto or not texto.strip():
        return None, None
    t = limpar_formato(texto)
    d = dobrar(t)
    if len(t) > 260:
        return None, "complemento_longo"
    if _COMPLEMENTO_PROIBIDO.search(d):
        return None, "complemento_normativo"
    if any(p.search(d) for p in _MEDICO):
        return None, "complemento_medico"
    if _VAZAMENTO.search(d) or _PUNITIVO.search(d):
        return None, "complemento_inadequado"
    return t, None


# ---------------------------------------------------------------- fundamentação (groundedness)
def fundamentacao(resposta: str, textos_fonte: list[str], minimo: float = 0.5) -> tuple[float, list[str]]:
    """Fração das frases da resposta com apoio lexical nas fontes citadas (radicais em comum).

    Medida simples e explicável para acompanhar a qualidade da geração (Painel, Fila de melhoria).
    Frases curtas (menos de 3 termos de conteúdo) não entram na conta.
    """
    from ..texto import tokens

    base = set(tokens(" ".join(textos_fonte)))
    if not base:
        return 0.0, []
    avaliadas, sem_apoio = 0, []
    for frase in re.split(r"(?<=[.!?;])\s+", resposta.strip()):
        termos = set(tokens(frase))
        if len(termos) < 3:
            continue
        avaliadas += 1
        if len(termos & base) / len(termos) < minimo:
            sem_apoio.append(frase[:160])
    if not avaliadas:
        return 1.0, []
    return round((avaliadas - len(sem_apoio)) / avaliadas, 2), sem_apoio
