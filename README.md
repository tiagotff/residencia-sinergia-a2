# SinergIA · A2 Bem-Estar (núcleo) — RAG, roteamento e guardrails

Agente A2 do SinergIA, no contrato **sinergia/1** (relatório técnico v0.7). Responde dúvidas
dos colaboradores a partir de **4 bases RAG** (os PDFs em `bases_pdf/`), escolhe a base de
forma dinâmica, cita a fonte e aplica guardrails antes e depois do LLM. Como todo agente do
projeto, é uma caixa-preta: `executar(tarefa) -> resultado`.

| Base (slug) | Especialista | PDF | IDs | Funcionalidade |
|---|---|---|---|---|
| `epi` | Especialista em EPI | `epi.pdf` (v1.3) | `EPI-Q001..070` | F5, F6 |
| `pausas_ergonomia` | Especialista em Pausas e Ergonomia | `pausas_ergonomia.pdf` (v2.1) | `RH-ERG-Q001..027` | F1 |
| `saude_ocupacional` | Especialista em Saúde Ocupacional | `saude_ocupacional.pdf` (v1.1) | `SO-Q001..063` | F4 |
| `direitos_beneficios` | Especialista em Direitos e Benefícios | `direitos_beneficios.pdf` (v1.1) | `RH-BEN-Q001..030` | F2 |

## Rodar localmente (Windows · Git Bash · Python 3.12 · Node 22+)

```bash
python -m venv .venv && source .venv/Scripts/activate
pip install -r requirements.txt && pip install -e .
cp .env.example .env            # coloque a GROQ_API_KEY (sem ela: modo extrativo)
python -m agente_a2 ingerir     # lê os 4 PDFs, gera chunks + embeddings, grava o índice

# Console A2 (já vem compilado; só abre neste computador)
python -m agente_a2.web                          # abre http://127.0.0.1:8000 no navegador
```

Outros comandos:

```bash
python -m agente_a2 calibrar    # sugere RAG_LIMIAR_COSSENO para o modelo de embeddings
python -m agente_a2 avaliar     # recall@1/@3 e acerto de base com as variações das bases
python -m agente_a2 perguntar "minha luva térmica rasgou" --intencao F5
python -m agente_a2 rodar fixtures/a2/responder/f2_vender_ferias.tarefa.json
python -m agente_a2 extrair     # planilha de análise + dataset das interações (pasta exportacoes/)
pytest -q                       # 111 testes, sem rede (embeddings "hashing" + LLM falso)
```

O primeiro `ingerir` baixa o modelo `paraphrase-multilingual-MiniLM-L12-v2` (~470 MB, uma vez).
Para PostgreSQL no RAG: rode `sql/001_rag_schema.sql`, defina `RAG_STORE=pgvector` e `DATABASE_URL`.

## Console A2 (React + servidor local)

Front em `web/` (React 18 + Vite + Tailwind + Recharts), no mesmo estilo do PrecificaAI, com
menu lateral recolhível (sanduíche no celular) e oito telas:

| Tela | Para quê |
|---|---|
| **Painel** | Volume por dia e status, % resolvida pelo A2, encaminhadas a humano, guardrails, LLM aprovado na 1ª/2ª tentativa e fallback, feedback, latência, confiança, base que respondeu, motivos de recusa do LLM, perguntas sem cobertura e comparação entre **versões do prompt** |
| **Atendimento** | Chat simulando o colaborador (escolhe colaborador fictício, intenção do A0, liga/desliga o LLM) com 👍/👎 em cada resposta e o **raio-X** ao lado: pipeline, notas da busca por base, prompt, tentativas do LLM com o veredito da validação, JSON da TAREFA e do RESULTADO |
| **Interações** | Histórico gravado no banco, com filtros, paginação, exportação CSV/JSONL e gaveta de detalhe para registrar a análise |
| **Fila de melhoria** | O que revisar: feedback negativo, sem cobertura, LLM recusado, falha no LLM, guardrail acionado e confiança baixa, com dica do que ajustar. Exporta o **dataset de avaliação** |
| **Avaliação da busca** | Recall@1/@3, acerto de base, falso positivo e sugestão de limiar |
| **Bases RAG** | As 4 bases pergunta por pergunta, com variações, fonte e texto indexado |
| **TAREFA → RESULTADO** | Roda as fixtures do sinergia/1 (ou JSON editado) e compara com o esperado |
| **Configurações** | Ambiente, limiares, prompt de sistema e versão, regras dos guardrails, reindexação |

Para editar as telas com recarga automática: deixe `python -m agente_a2.web` rodando e, em
outro terminal, `cd web && npm install && npm run dev` (http://127.0.0.1:5173). Depois de
editar, `npm run build` atualiza a versão servida em :8000.

### Segurança: uso só local

O console **não é uma API pública**. Ele roda num servidor que só existe para entregar as telas
a este computador:

- escuta apenas em `127.0.0.1` e recusa (403) qualquer conexão que não venha da própria máquina,
  mesmo que alguém o suba com `--host 0.0.0.0`;
- aceita apenas `Host` `127.0.0.1`/`localhost` (bloqueia *DNS rebinding*);
- toda chamada a `/api` exige um **token de sessão** aleatório, gerado a cada inicialização e
  entregue só à página do console; outro site aberto no navegador não consegue usá-lo;
- sem `/docs`, sem `/openapi.json` e sem `/executar`; cabeçalhos de segurança (CSP só
  `'self'`, sem *framing*, sem cache nas respostas);
- nenhum recurso externo nas telas (sem fontes ou scripts de CDN);
- dados no **banco local** (`dados/interacoes.db`); a tela Configurações avisa se o banco
  configurado não estiver nesta máquina.

O que ainda sai da máquina, e só se você configurar: a pergunta **já mascarada** e os trechos
das bases enviados ao Groq quando há `GROQ_API_KEY` (sem chave, o A2 responde só com o texto
das bases), e o download único do modelo de embeddings no primeiro `ingerir`.

A integração com o A0 é feita em Python (`criar_agente_a2().executar(tarefa)`), sem HTTP.

## Novidades da v0.5: bases ampliadas e RAG completo

Detalhes em [`docs/MELHORIAS_v0.5.md`](docs/MELHORIAS_v0.5.md).

- **Bases**: de 132 para 190 perguntas, no mesmo padrão. Licença-paternidade atualizada pela Lei nº
  15.371/2026, pausa térmica da câmara fria, pausa × almoço, faltas justificadas, férias fracionadas,
  riscos psicossociais da NR-1 e outras. Fonte editável em `bases_fonte/*.json` e gerador em
  `ferramentas/gerar_bases_pdf.py`.
- **R**: o LLM reescreve a pergunta (com o histórico) e cria subconsultas; a busca híbrida roda para
  cada uma; fusão RRF, diversidade MMR e vizinhos (referência cruzada e mesmo assunto).
- **A**: trechos com seção, tipo de fonte e relação; perfil com os EPIs do cargo; `<entendimento>`.
- **G**: síntese adaptada ao perfil, com fatos normativos só das fontes, mais uma "Dica:" de
  conhecimento geral validada à parte; fundamentação medida frase a frase.
- Liga e desliga com `RAG_REESCRITA` e `RAG_COMPLEMENTO`.

## Novidades da v0.4

Melhorias feitas a partir das interações reais. Detalhes, antes e depois, e sugestões para o time
das bases em [`docs/MELHORIAS_v0.4.md`](docs/MELHORIAS_v0.4.md):

- fluxo de EPI: reconhece perda, avaria, não recebimento, tamanho e **pedido sem motivo**, sempre
  pela mensagem atual; responde pelo roteiro da base (Q021, Q025–Q028) e não duplica pedido aberto;
- encaminhamento por tema quando a base não cobre: EPI → TST, Saúde → SESMT, Pausas e Direitos → RH;
- mensagens de continuação ("pra isso", "e agora?") usam o contexto da conversa na busca;
- `bases_pdf/variacoes_extras.json`: variações aprendidas com as interações, só para a busca;
- prompt com regras novas para histórico, relato de EPI e encaminhamento (nova versão no Painel);
- intenção inválida ignorada, confiança só em respostas do RAG, texto normalizado;
- **v0.4.1 — cordialidade**: "oi", "bom dia", "tudo bem?" recebem boas-vindas com o primeiro nome
  e a saudação do horário; "oi, perdi minhas luvas" responde já começando com "Bom dia, Carla!" (só
  no início da conversa); "obrigado", "ok" e "tchau" têm resposta calorosa; o "fora do escopo" ficou
  acolhedor. Tudo feito pelo código, sem LLM; o nome nunca vai ao LLM e é gravado como `[NOME]`.

## Extrair as interações para refinar o A2

`python -m agente_a2 extrair` (ou o botão **Planilha de análise** na tela Interações) gera, em
`exportacoes/`, um `.xlsx` e o dataset de avaliação em JSONL. Use `--dias 30` para limitar o
período. Abas da planilha:

| Aba | Use para |
|---|---|
| Interacoes | uma linha por resposta: pergunta, resposta, modo, base, confiança, recusas do LLM, sinais, feedback |
| Feedback | as análises do console, com a resposta de referência e a base que deveria responder |
| Busca_candidatos | todos os trechos avaliados em cada busca (cosseno, BM25, bônus, nota): ajustar léxico, variações e limiares |
| Tentativas_LLM | cada chamada ao LLM e o motivo de cada recusa: reforçar regras do prompt |
| Guardrails | sinais acionados: achar bloqueios indevidos |
| Uso_das_bases | as 132 perguntas das bases, quantas vezes foram usadas e quais nunca aparecem |
| Resumo | contagens por base, modo, status, versão do prompt e intenção do A0 |

Os textos já saem mascarados e o colaborador como pseudônimo; mesmo assim, compartilhe só no grupo.

## Registro de interações (melhoria contínua)

Toda TAREFA executada (chat, playground, CLI ou A0 via `criar_agente_a2`) é gravada em
banco, sem atrasar nem derrubar o atendimento se o banco falhar.

- **Banco**: `INTERACOES_DB_URL`. Padrão SQLite em `dados/interacoes.db` (nada a instalar). Para
  PostgreSQL: `INTERACOES_DB_URL=postgresql+psycopg://usuario:senha@localhost:5432/sinergia`.
  As tabelas `a2_interacao`, `a2_feedback` e `a2_prompt` são criadas na primeira execução.
- **O que grava**: pergunta e resposta, status, modo (LLM 1ª/2ª tentativa, extrativo, cache,
  guardrail, fora do escopo…), base e trechos citados, notas de todos os candidatos da busca,
  sinais dos guardrails, prompt do usuário, cada tentativa do LLM com os motivos de recusa,
  confiança, latência, versão do prompt, do A2 e das bases, TAREFA e RESULTADO.
- **Feedback**: positivo/negativo, categoria, base que deveria responder, resposta de
  referência, comentário e situação (aberto/resolvido).
- **LGPD**: pergunta gravada já mascarada (CPF, CID, e-mail, telefone); colaborador como
  pseudônimo HMAC (`A2_SAL_PSEUDONIMO` — troque em produção); sem `registro_inicial` (nome,
  matrícula) e sem ID do colaborador no RESULTADO; primeiro nome trocado por `[NOME]`;
  comentários também mascarados; expurgo após `A2_RETENCAO_DIAS` (padrão 180).
- **Ciclo de melhoria**: Fila de melhoria → analisar e registrar → ajustar prompt
  (`llm/prompts.py`), regras (`guardrails/`), léxico (`rag/catalogo.py`) ou limiares (`.env`)
  → a versão do prompt muda sozinha → comparar no Painel → exportar o dataset (JSONL com
  pergunta, base esperada e resposta de referência) como teste de regressão.

## Como o A0 chama

```python
from agente_a2 import criar_agente_a2
a2 = criar_agente_a2()                 # lê o .env: Groq, embeddings, store, banco
resultado = a2.executar(tarefa)        # Tarefa (Pydantic), dict ou JSON -> Resultado
```

Ações atendidas: `a2.responder`, `a2.orientar_epi`, `a2.acompanhar_afastamento`.
`a2.gerar_lembretes` e `a2.recomendar_beneficios` devolvem `ERRO / ACAO_NAO_IMPLEMENTADA`
(não dependem do RAG; ficam para a próxima entrega).

## Pipeline do `a2.responder`

```
TAREFA ─► guardrails de entrada ─┬─ crise / emergência ─► texto aprovado SO-Q048/SO-Q049, sensivel, PRECISA_HUMANO
                                 ├─ injeção de prompt ──► recusa fixa (o LLM nem é chamado)
                                 ├─ dados de terceiros ─► recusa fixa
                                 ▼
                 busca híbrida nas 4 bases (cosseno + BM25) + viés da intenção e do léxico
                                 ├─ nada relevante ─────► fora do escopo (OK) ou sem documento → RH (PRECISA_HUMANO)
                                 ▼
                 cache (pergunta + versões dos documentos vigentes)
                                 ▼
                 LLM no papel do Especialista da base ─► guardrails de saída ─► 1 correção ─► fallback extrativo
                                 ▼
                 relato de EPI? ─► apoio.solicitacao_epi + evento solicitacao_epi.aberta (idempotente)
                                 ▼
                 RESULTADO: saidas[mensagem{texto, fontes[{base, titulo, versao, refs}]}], payload, decisao
```

### RAG completo (v0.5)

R: entendimento (`rag/consulta.py`) → busca híbrida por consulta → RRF → MMR → vizinhos
(`Recuperador.buscar_multi`). A: `prompts.montar` (trechos com metadados, perfil, entendimento).
G: síntese + complemento validado (`guardrails/saida.validar_complemento`) + fundamentação
(`guardrails/saida.fundamentacao`). Veja `docs/MELHORIAS_v0.5.md`.

### Chunks e embeddings
- **1 chunk por pergunta** (ID). A maior resposta tem ~600 caracteres, então a unidade de
  citação é a unidade de busca, e a fundamentação fica verificável pelo ID. Respostas acima
  de 1.200 caracteres são divididas por parágrafo com sobreposição (não ocorre hoje).
- O texto indexado é **título + "Também perguntam" + resposta**: as variações são as formas
  reais de perguntar e aumentam o recall.
- Metadados por chunk: base, documento, versão, vigência, aprovação, seção, fonte e tipo
  (OFICIAL/INTERNO). O parser preserva `º`/`ª`, junta títulos quebrados e listas numeradas.
- Embeddings **locais** (MiniLM multilíngue, 384 dim): o Groq não oferece embeddings e
  mandar perguntas a um terceiro só para indexar não compensa o risco de LGPD.
- Ingestão idempotente por sha256; uma versão nova do PDF desativa a anterior.

### Roteamento dinâmico entre as bases
A busca roda **sempre nas 4 bases**. A intenção do A0 (`F1..F5` ou rótulo) dá +0,05 à base
indicada e termos do léxico de cada base dão até +0,09 — viés, não filtro. Se o A0 classificar
como F2 uma pergunta de EPI, a evidência vence e o desvio vai para `decisao.motivo`. Perguntas
transversais trazem mais de uma base (ex.: luva térmica na câmara fria → EPI + Saúde
Ocupacional); a base principal é a do melhor trecho citado.

### Prompt e proteção contra prompt injection
1. **Hierarquia**: só o system prompt instrui; pergunta, histórico, perfil e trechos vão em
   tags declaradas como dados, com `<`/`>` neutralizados (não fecham a própria tag).
2. **Detecção por regras** (PT/EN/ES): "ignore as instruções", troca de papel, pedido do
   prompt, modo desenvolvedor/jailbreak, marcadores `system:`, tags do prompt, nomes dos
   campos de saída, texto codificado. Caracteres invisíveis são removidos antes.
3. **Sem ferramentas**: o LLM não executa nada; a solicitação de EPI é aberta pelo código.
4. **Saída validada**: JSON no esquema, IDs citados ⊂ recuperados, números presentes na
   fonte, sem vazamento do prompt, sem orientação médica, sem tom punitivo, tamanho.
5. **Privacidade**: CPF, e-mail, telefone e CID são mascarados antes do LLM; o perfil enviado
   é só cargo e jornada.

## Estrutura

```
src/sinergia_contratos/   envelope sinergia/1 (espelho do pacote compartilhado)
web/                      Console A2: React + Vite + Tailwind (src/pages, src/components)
src/agente_a2/
  agente.py               AgenteA2.executar / executar_detalhado: validação, idempotência, erros, registro
  interacoes.py           registro de interações, feedback, fila de melhoria, métricas, exportação
  web/app.py              servidor local do Console (/api/* com token) e entrega do front compilado
  web/seguranca.py        blindagem: só loopback, host fixo, token de sessão, CSP
  demo.py                 cadastro fictício (sem DATABASE_URL)
  acoes/                  responder (RAG) · orientar_epi (F6) · acompanhar_afastamento (F7)
  rag/                    catalogo · parser_pdf · chunking · embeddings · stores · recuperador · ingestao · consulta
  acoes/relato_epi.py     detecção de relato/pedido de EPI na mensagem atual
  acoes/cordialidade.py   saudação, agradecimento e despedida (sem LLM)
  guardrails/             entrada · saida · textos
  llm/                    prompts · cliente (Groq/LangChain e LLM falso)
  repositorio.py          cadastro/afastamento (leitura) e apoio.solicitacao_epi (escrita)
  avaliacao.py            recall@k, acerto de base, calibração do limiar
bases_pdf/                os 4 PDFs + variacoes_extras.json (variações em teste, só para a busca)
bases_fonte/              conteúdo editável das 4 bases (JSON) → ferramentas/gerar_bases_pdf.py gera os PDFs
docs/MELHORIAS_v0.4.md    análise das interações reais e o que mudou
docs/MELHORIAS_v0.5.md    bases ampliadas e RAG completo (R + A + G)
sql/001_rag_schema.sql    schema rag + pgvector
fixtures/a2/              TAREFAs e RESULTADOs esperados (gerados em modo extrativo)
tests/                    parser, roteamento, guardrails, contrato, interações, console, blindagem e casos reais
```

## Pendências para o grupo

| Ponto | Situação nesta entrega |
|---|---|
| Relatório fala em **5 bases**; vieram 4 (sem Procedimentos e Treinamentos, F3) | F3 cai em "sem documento → RH" |
| `intencao` do `a2.responder` lista só F2, F3, F5; o A0 também classifica pausa e saúde | aceita F1..F5 e rótulos; propor ao A0 |
| Cabeçalhos dos PDFs: Pausas diz "F5, F6" (é F1); Benefícios diz "F7, F8" (é F2) | catálogo usa F1 e F2; corrigir os PDFs |
| As 4 bases estão com **aprovação PENDENTE** | `RAG_EXIGIR_APROVACAO=0` no protótipo |
| Fontes ganharam `refs` (IDs) — campo opcional novo, permitido no sinergia/1 | avisar o grupo do A0/Judge |
| Status em "sem documento" e crise: `PRECISA_HUMANO` + `payload.encaminhar_para` | confirmar com o A0 |
| F7 por modelos fixos, sem LLM (o resumo do A2 previa LLM) | decidir se mantém |
| `StorePGVector` e `RepositorioSQL` escritos contra o rascunho do schema | testar no banco semente |
| CrewAI não entrou: o RAG é uma função determinística e testável; os 4 "especialistas" são papéis no prompt | dá para envolver depois sem mudar o contrato |
