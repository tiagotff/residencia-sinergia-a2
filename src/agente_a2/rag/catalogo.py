"""Catálogo das bases RAG do A2.

Cada base é tratada como um "especialista" do A2: tem um slug (gravado em
rag.base e devolvido em payload.base / fontes[].base), um prefixo de ID das
perguntas, o arquivo PDF de origem, as funcionalidades que atende e um
léxico usado pelo roteador para desempatar a escolha da base.

A base de Procedimentos e Treinamentos (F3) está prevista no relatório v0.7,
mas não existe documento dela ainda: o slug fica reservado e qualquer pergunta
que só ela responderia cai na regra "sem documento vigente -> encaminha ao RH".
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BaseRAG:
    slug: str
    nome: str
    especialista: str
    prefixo_id: str
    arquivo: str
    funcionalidades: tuple[str, ...]
    lexico: tuple[str, ...] = field(default_factory=tuple)


BASES: dict[str, BaseRAG] = {
    "epi": BaseRAG(
        slug="epi",
        nome="EPI",
        especialista="Especialista em EPI",
        prefixo_id="EPI-Q",
        arquivo="epi.pdf",
        funcionalidades=("F5", "F6"),
        lexico=(
            "epi", "epis", "luva", "luvas", "bota", "botina", "calcado", "oculos",
            "protetor auricular", "plugue", "tampao", "respirador", "pff2", "mascara",
            "avental", "capacete", "certificado de aprovacao", "nr-6", "nr 6",
            "reposicao", "avariado", "rasgou", "rasgada", "furou", "furada", "quebrou",
            "trincou", "perdi", "extravi", "vida util", "higieniz", "anticorte",
            "nitrilica", "biqueira", "equipamento de protecao", "abafador", "botinas", "calcado de seguranca",
            "jaqueta termica", "japona", "viseira", "descolou",
        ),
    ),
    "pausas_ergonomia": BaseRAG(
        slug="pausas_ergonomia",
        nome="Pausas e Ergonomia",
        especialista="Especialista em Pausas e Ergonomia",
        prefixo_id="RH-ERG-Q",
        arquivo="pausas_ergonomia.pdf",
        funcionalidades=("F1",),
        lexico=(
            "pausa", "pausas", "ergonomia", "ergonomic", "alongamento", "alongar",
            "postura", "cadeira", "mobiliario", "apoio para os pes", "suporte de tela",
            "20-20-20", "20 20 20", "fadiga ocular", "descanso visual", "tela",
            "teleatendimento", "call center", "computador", "nr-17", "nr 17",
            "pescoco", "ombro", "punho", "antebraco", "pausa ativa", "almoco", "refeicao", "intervalo",
            "expediente", "pausar",
        ),
    ),
    "saude_ocupacional": BaseRAG(
        slug="saude_ocupacional",
        nome="Saúde Ocupacional",
        especialista="Especialista em Saúde Ocupacional",
        prefixo_id="SO-Q",
        arquivo="saude_ocupacional.pdf",
        funcionalidades=("F4",),
        lexico=(
            "exame", "exames", "periodico", "admissional", "demissional", "aso",
            "pcmso", "pgr", "audiometria", "vacina", "vacinacao", "campanha", "sipat",
            "cipa", "medico do trabalho", "sesmt", "burnout", "estresse", "estressado",
            "ansiedade", "assedio", "cat", "acidente", "doenca ocupacional", "sono",
            "turno", "calor", "frio", "camara fria", "carregar peso", "levantar peso",
            "ler/dort", "dort", "saude mental", "inapto", "apto", "ginastica laboral",
        ),
    ),
    "direitos_beneficios": BaseRAG(
        slug="direitos_beneficios",
        nome="Benefícios e Direitos Trabalhistas",
        especialista="Especialista em Direitos e Benefícios",
        prefixo_id="RH-BEN-Q",
        arquivo="direitos_beneficios.pdf",
        funcionalidades=("F2",),
        lexico=(
            "ferias", "13", "decimo terceiro", "gratificacao natalina", "licenca",
            "maternidade", "paternidade", "casamento", "gala", "luto", "nojo", "inss",
            "estabilidade", "convencao coletiva", "acordo coletivo", "sindicato",
            "vale refeicao", "vale alimentacao", "vr", "va", "creche", "plano de saude",
            "odontologico", "convenio", "plr", "bonus", "abono", "vender ferias",
            "vale transporte", "vale-transporte", "falta", "dsr", "beneficio",
            "beneficios", "salario", "extrato",
        ),
    ),
}

# Reservada: ainda sem documento (F3 — procedimentos e treinamentos).
BASE_RESERVADA_F3 = "procedimentos"

# Intenção vinda do A0 -> base preferida. Aceita o código F* e o rótulo da
# classificação de intenção do A0 (seção 10.2 do relatório).
INTENCAO_PARA_BASE: dict[str, str] = {
    "f1": "pausas_ergonomia",
    "pausa": "pausas_ergonomia",
    "pausas": "pausas_ergonomia",
    "ergonomia": "pausas_ergonomia",
    "f2": "direitos_beneficios",
    "direito": "direitos_beneficios",
    "beneficio": "direitos_beneficios",
    "direito_ou_beneficio": "direitos_beneficios",
    "direitos_beneficios": "direitos_beneficios",
    "f3": BASE_RESERVADA_F3,
    "procedimento": BASE_RESERVADA_F3,
    "f4": "saude_ocupacional",
    "saude": "saude_ocupacional",
    "saude_ocupacional": "saude_ocupacional",
    "f5": "epi",
    "f6": "epi",
    "epi": "epi",
}


def base_da_intencao(intencao: str | None) -> str | None:
    if not intencao:
        return None
    return INTENCAO_PARA_BASE.get(intencao.strip().lower())


def base_do_id(id_pergunta: str) -> str | None:
    """Descobre a base pelo prefixo do ID (ex.: 'SO-Q010' -> saude_ocupacional)."""
    # prefixos mais longos primeiro (RH-ERG-Q antes de qualquer outro)
    for base in sorted(BASES.values(), key=lambda b: -len(b.prefixo_id)):
        if id_pergunta.startswith(base.prefixo_id):
            return base.slug
    return None
