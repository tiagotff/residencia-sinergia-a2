# A2 v0.5: bases ampliadas e RAG completo (R + A + G)

## 1. Bases de conhecimento

Os PDFs seguem o mesmo padrão: cabeçalho em tabela; seções numeradas; e, em cada pergunta, o ID, a
linha "Também perguntam", a resposta e a linha "Fonte" com OFICIAL e INTERNO. As perguntas
existentes mantêm o ID e o texto; as novas continuam a numeração.

| Base | Antes | Agora | Versão | O que entrou |
|---|---|---|---|---|
| EPI | 58 | **70** | 1.2 → **1.3** | Seção 7 "Pedidos e dúvidas frequentes no chat" (pedir EPI novo, esqueci em casa, EPI próprio, adornos, barba e PFF2, EPI certo para a tarefa); japona/jaqueta térmica; luva de malha de aço; levar EPI para casa; EPI desconfortável; consequência de não usar (CLT art. 158) |
| Pausas e Ergonomia | 8 | **27** | 2.0 → **2.1** | Intervalo de refeição (art. 71), **pausa × almoço**, descanso entre jornadas e semanal (arts. 66 e 67), **pausa térmica da câmara fria** (art. 253 e Súmula 438), digitação (art. 72), teleatendimento (NR-17, Anexo II), assento para quem trabalha em pé, **gestor pode impedir a pausa?**, intervalo suprimido (art. 71, § 4º), acumular pausas, pausa conta como jornada, avaliação ergonômica, ajuste de cadeira e tela, postura em pé, movimentos repetitivos, alongamentos, respiração, sinais de alerta, ginástica laboral |
| Saúde Ocupacional | 55 | **63** | 1.0 → **1.1** | Afastamento menor que 30 dias, hidratação e alimentação, gestante, **riscos psicossociais na NR-1 (em fiscalização desde 26/05/2026)**, saúde mental no dia a dia, prazo e quem emite a CAT, quase acidente, acompanhamento pelo PCMSO |
| Direitos e Benefícios | 11 | **30** | 1.0 → **1.1** | Férias fracionadas (art. 134), quem marca as férias (arts. 135 e 136), faltas × férias (art. 130), faltas justificadas (art. 473), **nova licença-paternidade (Lei nº 15.371/2026)**, gestante e amamentação, hora extra e banco de horas, adicional noturno, insalubridade e periculosidade, data do salário, feriado trabalhado, FGTS, aviso prévio, atestado, dependente no plano, PLR, VT em dinheiro, holerite, folga aos domingos no comércio |
| **Total** | **132** | **190** | | |

**Correções no conteúdo existente**
- **RH-BEN-Q003**: a licença-paternidade de 5 dias vale até 31/12/2026. Pela Lei nº 15.371/2026
  (publicada em 01/04/2026), passa a 10 dias em 2027, 15 em 2028 e 20 em 2029.
- **EPI-Q026**: a regra de desconto está escrita na própria resposta, em vez de "veja a pergunta EPI-Q013".
- Cabeçalhos: Pausas aponta F1 (antes F5, F6) e Direitos aponta F2 (antes F7, F8).
- As variações aprendidas no chat (`variacoes_extras.json` da v0.4) agora estão nos PDFs.

**Fonte editável**: `bases_fonte/<base>.json` traz o conteúdo estruturado das 4 bases, e
`python ferramentas/gerar_bases_pdf.py` gera os PDFs nesse padrão. O time das bases pode editar o
JSON (ou os PDFs, como antes); o parser lê os dois formatos.

**Para validar com RH e TST** (todas as bases continuam com aprovação PENDENTE):
- textos INTERNOS novos que descrevem políticas da empresa: RH-ERG-Q016 ("fazer a pausa não gera
  punição"), RH-ERG-Q010 (a regra "fora da refeição" estendida a todas as pausas), EPI-Q061, EPI-Q068
  e RH-BEN-Q026;
- se a OBA está no programa Empresa Cidadã, e o limite de temperatura da câmara fria pela zona
  climática de cada unidade (RH-ERG-Q012).

Fontes conferidas: [Senado — Lei nº 15.371/2026](https://www12.senado.leg.br/noticias/materias/2026/04/01/sancionado-o-aumento-gradual-da-licenca-paternidade) ·
[CLT art. 253 comentado](https://www.aurum.com.br/blog/clt-comentado/art-253-clt/) ·
[CLT art. 473](https://www.pontotel.com.br/artigo-473-clt/) ·
[MTE — Perguntas e respostas GRO/PGR (maio/2026)](https://www.gov.br/trabalho-e-emprego/pt-br/assuntos/inspecao-do-trabalho/manuais-e-publicacoes/2026/perguntas-e-respostas-gro-pgr-maio-2026)

## 2. RAG completo

Antes, o A2 já buscava (R), montava o prompt com os trechos (A) e gerava com o LLM (G). Mas a busca
usava só a frase digitada, e o prompt obrigava o LLM a "usar apenas os trechos". Na prática, ele
devolvia algo muito próximo do texto da base. Agora cada letra tem um papel claro:

```
mensagem ─► R1 Entendimento (LLM): pergunta autônoma + até 3 subconsultas + tema
          ─► R2 Busca híbrida (cosseno + BM25) para CADA consulta
          ─► R3 Fusão RRF  ─► R4 MMR (diversidade)  ─► R5 Vizinhos (referência cruzada / mesmo assunto)
          ─► A  Contexto: trechos com seção, tipo de fonte e relação (principal/relacionado)
                 + perfil (cargo, jornada, EPIs do cargo) + entendimento + histórico
          ─► G1 Síntese pelo LLM: junta os trechos e adapta ao perfil; fatos normativos só das fontes
          ─► G2 Complemento de conhecimento geral: uma "Dica:" prática, em campo separado
          ─► Validação: saída (JSON, IDs, números, médico, punitivo, vazamento) + complemento + fundamentação
```

**R (recuperação)**: `rag/consulta.py` e `Recuperador.buscar_multi`
- O LLM reescreve a pergunta para ela fazer sentido sem o histórico ("meu chefe está certo?" vira
  "a pausa pode ser feita no horário de almoço?") e quebra perguntas compostas em subconsultas.
  Sem LLM, ou se a chamada falhar, entra a heurística da v0.4.
- A busca híbrida roda para cada consulta, e os resultados são fundidos por **RRF**. Por exemplo,
  "posso vender férias e dividir em partes?" traz as duas respostas (RH-BEN-Q008 e Q012), e não
  apenas a primeira.
- O **MMR** escolhe os trechos equilibrando relevância e diversidade.
- **Vizinhos**: perguntas citadas no texto e o par do mesmo assunto ("Luva térmica: para que serve"
  e "Luva térmica: como conservar") entram como contexto relacionado.

**A (aumento)**: `llm/prompts.montar`
- Os trechos vão com seção, tipo de fonte e relação (principal ou relacionado).
- O perfil inclui os **EPIs do cargo**, além do cargo e da jornada. Continua sem nome, CID ou dados
  de saúde.
- A tag `<entendimento>` leva a pergunta reescrita e os aspectos que a resposta deve cobrir.

**G (geração)**
- O prompt pede **síntese**: juntar os trechos, explicar o "como" e o "porquê" e adaptar ao perfil.
  Fatos normativos (prazos, valores, números, direitos, regras da empresa) continuam vindo **só das
  fontes**, e a validação de números barra qualquer número que não esteja nelas.
- **Conhecimento geral**: o LLM pode acrescentar uma dica prática no campo `complemento`, e ela
  aparece como "Dica: …". A dica passa por uma validação própria: sem números, leis, normas,
  direitos, regras da empresa, diagnóstico ou remédio. Se for reprovada, sai só a dica e a resposta
  fica. A dica não aparece em crise, emergência, relato de EPI nem em respostas sem cobertura.
- **Fundamentação**: cada frase da resposta é comparada com as fontes citadas. A nota aparece no
  raio-X, entra no cálculo da confiança, no Painel ("Fundamentação média") e na Fila de melhoria
  ("Pouco apoio nas fontes", abaixo de 60%).

**Custos e controles**: com `RAG_REESCRITA=1` há uma chamada curta a mais ao LLM por pergunta (cerca
de 0,3 a 1 segundo). Use `RAG_REESCRITA=0` se o limite do Groq apertar. `RAG_COMPLEMENTO=0` desliga
as dicas. O limite da resposta passou para 900 caracteres, para caber a síntese.

**No console**: o raio-X mostra as etapas "R · Entendimento", "R · Busca, fusão e roteamento" (com
as consultas, o método e os relacionados) e "A + G" (com a barra de fundamentação e a dica aceita ou
descartada). O Painel ganhou os indicadores de fundamentação média, perguntas reescritas e dicas. A
planilha de análise ganhou as colunas da pergunta reescrita, subconsultas, relacionados,
fundamentação, frases sem apoio e complemento.

**Testes**: 111, dos quais 7 novos em `tests/test_rag_completo.py`.
