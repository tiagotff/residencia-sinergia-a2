"""Textos fixos do A2 (sem LLM).

Mantidos curtos e no tom das bases (cordial, acolhedor e direto). Os textos de
crise e emergência NÃO estão aqui: vêm da própria base de Saúde Ocupacional
(SO-Q048 e SO-Q049), que é o conteúdo aprovado pelo serviço de saúde.
"""

ESCOPO = (
    "Posso ajudar com dúvidas sobre EPI, pausas e ergonomia, saúde ocupacional e "
    "direitos e benefícios. Pode me contar a sua dúvida sobre um desses temas?"
)

INJECAO = (
    "Não consigo atender a esse pedido. Posso ajudar com dúvidas sobre EPI, pausas e "
    "ergonomia, saúde ocupacional e direitos e benefícios."
)

TERCEIROS = (
    "Por privacidade, não posso compartilhar informações de outras pessoas. "
    "Se a dúvida for sobre você, posso ajudar por aqui."
)

SEM_DOCUMENTO = (
    "Não encontrei essa informação nos documentos vigentes que eu consulto. "
    "Vou encaminhar a sua dúvida ao RH, que vai responder por aqui."
)

# Quem responde quando a base não cobre a pergunta (encaminhamento por tema).
ENCAMINHAMENTO = {
    "epi": ("TST", "Não encontrei essa informação nas orientações de EPI que eu consulto. Vou encaminhar a sua "
                   "dúvida ao Técnico de Segurança do Trabalho, que vai responder por aqui."),
    "saude_ocupacional": ("SESMT", "Não encontrei essa informação nas orientações de saúde ocupacional que eu "
                                   "consulto. Vou encaminhar a sua dúvida ao serviço de saúde da empresa, que vai "
                                   "responder por aqui."),
    "pausas_ergonomia": ("RH", SEM_DOCUMENTO),
    "direitos_beneficios": ("RH", SEM_DOCUMENTO),
}


def sem_documento(base: str | None) -> tuple[str, str]:
    """(quem recebe, texto) para a base do assunto; RH quando o tema não é claro."""
    return ENCAMINHAMENTO.get(base or "", ("RH", SEM_DOCUMENTO))

INDISPONIVEL = (
    "Não consegui consultar as orientações agora. Vou encaminhar a sua dúvida ao RH, "
    "que vai responder por aqui."
)

SOLICITACAO_EPI_ABERTA = (
    "Abri o pedido de reposição nº {id}, e o seu gestor e o TST serão avisados. "
    "A reposição deve acontecer em até 24 horas."
)

SOLICITACAO_EPI_EXISTENTE = (
    "Você já tem o pedido de reposição nº {id} aberto para esse EPI. O seu gestor e o TST já foram "
    "avisados, e a reposição deve acontecer em até 24 horas."
)

PEDIDO_SEM_MOTIVO = (
    "Para eu abrir o pedido, me conte o que aconteceu com {epi}: danificou, perdeu, "
    "ainda não foi entregue ou o tamanho não serve?"
)

SOLICITACAO_EPI_FALHOU = (
    "Não consegui abrir o pedido de reposição automaticamente. Por favor, avise o seu "
    "gestor e o TST."
)
