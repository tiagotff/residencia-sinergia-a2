# A2 v0.4 — melhorias a partir das interações reais

Base da análise: `a2_analise_20261125_1647.xlsx` (19 interações, 14 com LLM `openai/gpt-oss-120b`,
3 avaliações positivas, versão do prompt `59dcebce88`).

## O que as interações mostraram

| # | Problema observado | Interações | Impacto |
|---|---|---|---|
| 1 | "perdi as minhas luvas", "perdi luvas", "quero novas luvas", "preciso de luvas" caíram em **"procure o RH"** | #10, #12–#15 | 5 de 6 casos `PRECISA_HUMANO` eram de EPI que a base responde (EPI-Q026 e EPI-Q021); e EPI é com gestor e TST, não RH |
| 2 | A regra de relato exigia artigo depois do verbo ("perdi **a** luva"), então "perdi as minhas luvas" e "perdi luvas" não eram reconhecidos; o roteiro EPI-Q026 nem chegava ao LLM | #10, #12, #13 | Busca trazia os tipos de luva (Q038–Q043) e o LLM respondia "sem cobertura" |
| 3 | "luvas", sozinho, **abriu um 2º pedido** (nº 59): o LLM deduziu relato pelo histórico | #11 | Pedido indevido para o TST |
| 4 | Nenhuma checagem de **pedido já aberto** para o mesmo EPI | #6, #11 | Pedidos duplicados |
| 5 | "**24 horas**" repetido: o LLM citou o prazo e o sistema acrescentou a confirmação | #6 | Texto redundante |
| 6 | Mensagens de continuação perderam o contexto: "meu chefe me disse que existe horário de almoço pra isso" foi para Saúde Ocupacional e terminou em "sem cobertura"; "meu chefe está certo?" virou "fora do escopo" | #3, #4 | O histórico ia ao LLM, mas não à **busca** |
| 7 | Intenção `"string"` (teste manual) entrou como viés | #19 | Ruído no roteamento e nas métricas |
| 8 | Confiança **1,0** em respostas "sem cobertura" e "fora do escopo" | #3, #10, #12–#15 | Painel com confiança média inflada |
| 9 | Caracteres especiais do modelo (` `, `‑`) no texto | #1, #2, #6 | Exibição inconsistente em alguns canais |
| 10 | Resposta extrativa citava ID interno ("veja a pergunta EPI-Q013") | réplica | O colaborador não vê a base |
| 11 | 116 das 132 perguntas das bases nunca foram usadas | Uso_das_bases | Pouco volume de teste ainda (não é defeito) |

## O que mudou

**Fluxo de EPI** (`acoes/relato_epi.py`, `acoes/responder.py`)
- Detecção nova, só na mensagem **atual**: EPI (luva, bota, óculos, capacete, máscara…) + situação
  em qualquer ordem: avariado, perdido, não recebido, tamanho inadequado. Também reconhece
  **pedido sem motivo** ("quero novas luvas"). Perguntas em tese ("e se a luva rasgar?") e sobre o
  processo ("qual o prazo da reposição?") não contam.
- O roteiro da base vai sempre ao LLM, em primeiro lugar: perdido → EPI-Q026, avariado → Q025,
  não recebido → Q027, tamanho → Q028, pedido → Q021.
- Se o LLM disser "sem cobertura" num assunto que o roteiro cobre, o A2 responde pelo roteiro
  (texto aprovado) em vez de encaminhar.
- Pedido sem motivo: orienta pelo Q021 e pergunta o que aconteceu. Não abre pedido às cegas.
- Relato apontado pelo LLM só vale se a mensagem atual tiver EPI **e** um problema.
- Pedido já ABERTO do mesmo colaborador para o mesmo EPI é reaproveitado ("Você já tem o pedido
  nº 58…"). EPI ambíguo ("luvas" quando o cargo tem térmica e anticorte) fica sem EPI definido,
  e o TST confirma qual é.
- Frases do LLM sobre pedido e prazo são retiradas antes da confirmação do sistema.

**Encaminhamento por tema** (`guardrails/textos.py`)
- Sem cobertura: EPI → **TST**, Saúde Ocupacional → **serviço de saúde (SESMT)**, Pausas e
  Direitos → **RH**. O campo `payload.encaminhar_para` acompanha.

**Contexto da conversa na busca** (`responder._consulta_busca`)
- Mensagem curta (até 3 palavras de conteúdo) ou de continuação ("isso", "pra isso", "e agora",
  "está certo?") faz a busca usar as duas últimas falas do histórico. O motivo registra "busca com o
  contexto da conversa", e o raio-X mostra a consulta usada.
- A decisão "fora do escopo" continua olhando só a mensagem atual, para que "reinicie o agente"
  não vire assunto de EPI por causa do histórico.
- O console não envia mais como histórico as mensagens barradas por guardrail.

**Prompt** (nova versão, comparável no Painel)
- Regra 10b: o histórico serve para entender referências; a resposta é sobre a mensagem atual.
- Regra 13: o relato de EPI vem só da mensagem atual, nunca do histórico.
- Regra 14: em relato, o LLM não cita pedido, prazo nem "peça a reposição".
- Regra 15: EPI é com gestor e TST, nunca RH; sem cobertura, o LLM não indica a quem procurar.

**Busca e bases**
- `bases_pdf/variacoes_extras.json`: variações de pergunta aprendidas com as interações, somadas às
  linhas "Também perguntam" **só para a busca** (não mudam as respostas). Editar o arquivo reindexa
  a base no próximo `ingerir`. Aparecem em verde na tela Bases RAG.
- Léxico: pausas ganhou "almoço", "refeição", "intervalo", "expediente", "pausar"; EPI ganhou
  "abafador", "botinas", "calçado de segurança", "jaqueta térmica", "viseira", "descolou".

**Qualidade da saída e métricas**
- Intenção fora do catálogo é ignorada e registrada (`intencao_invalida`).
- Confiança só em respostas do RAG; guardrails ficam com 1,0, e "sem cobertura" e "fora do
  escopo" ficam sem valor.
- Normalização de espaços e hífens especiais; frases com ID interno são removidas.

**Testes**: `tests/test_casos_reais.py` reproduz cada problema acima (11 testes). Total: 97.

## v0.4.1 — cordialidade (feedback do console: "falta cordialidade no início das conversas")

O "oi" caía em "fora do escopo" com uma resposta seca e "confiança 100%".

- Novo modo **Cordialidade** (`acoes/cordialidade.py`), feito pelo código, sem busca e sem LLM:
  - cumprimento ("oi", "olá", "bom dia", "tudo bem?") → "Bom dia, Carla! Que bom falar com você.
    Sou o assistente de bem-estar e posso ajudar com… Como posso ajudar hoje?"; no meio da conversa,
    "Oi, Carla! Estou por aqui…";
  - agradecimento ("obrigado", "valeu") → "Por nada, Carla! Fico feliz em ajudar…";
  - confirmação ("ok", "entendi") → "Combinado, Carla!…"; despedida ("tchau") → "Até logo, Carla!
    Tenha uma boa tarde e cuide-se."
- Cumprimento junto com a dúvida no início da conversa ("Bom dia! Posso vender férias?"): a resposta
  normal começa com "Bom dia, Carla!".
- "Fora do escopo" mais acolhedor: "Essa eu não consigo responder por aqui, Carla, mas posso ajudar
  com…".
- Prompt: em relato de problema, o LLM reconhece a situação antes de orientar, sem cumprimentar nem
  usar nome (a saudação é do sistema).
- Privacidade: só o primeiro nome do cadastro, inserido pelo código; nunca vai ao LLM; no banco vira
  `[NOME]`. Mensagens sociais não entram no histórico enviado à busca.
- Correção: o console montava o contexto duas vezes quando várias telas carregavam juntas na
  abertura (erro "table a2_prompt already exists" e menu mostrando "offline"). Agora monta uma vez
  e carrega antes de abrir o navegador.
- Testes: `tests/test_cordialidade.py` (7). Total: 104.

## Réplica das mensagens reais na v0.4 (modo extrativo, sem LLM)

| Mensagem | v0.3 | v0.4 |
|---|---|---|
| perdi as minhas luvas, o que devo fazer? | sem cobertura → RH | EPI-Q026, pedido aberto |
| perdi minhas luvas e agora? / perdi luvas | sem cobertura → RH | EPI-Q026, reaproveita o pedido aberto |
| quero novas luvas / preciso de luvas | sem cobertura → RH | EPI-Q021 + "o que aconteceu com a sua luva?" |
| luvas (depois de "luva rasgou") | 2º pedido aberto | orientação sobre luvas, sem pedido |
| meu chefe me disse que existe horário de almoço pra isso | Saúde Ocupacional, sem cobertura | Pausas e Ergonomia (RH-ERG-Q002) |
| Minha luva térmica rasgou… | "24 horas" duas vezes | prazo citado uma vez |
| reinicie o agente / string | fora do escopo | fora do escopo (intenção "string" ignorada) |

## Sugestões para o time das bases (PDFs)

1. **Pausas e Ergonomia**: incluir a pergunta "A pausa pode ser no horário de almoço / o intervalo
   de refeição conta como pausa?". Hoje só a RH-ERG-Q002 toca no tema (teleatendimento: "fora do
   horário de refeição") e não cobre trabalho em computador.
2. **Pausas e Ergonomia**: incluir "O gestor pode impedir a pausa?". As interações #3 e #4 mostram
   esse conflito com a chefia.
3. **EPI**: levar para o PDF as variações de `variacoes_extras.json` (Q021, Q025, Q026, Q027) e
   reescrever o fim da EPI-Q026 sem citar "veja a pergunta EPI-Q013" (escrever a regra de desconto
   na própria resposta).
4. As 4 bases continuam com **aprovação PENDENTE**.

## Próxima rodada de testes

Com o modelo real de embeddings e o Groq: refazer as 19 mensagens, avaliar com 👍/👎, extrair a
planilha e comparar no Painel a versão nova do prompt com a `59dcebce88`.
