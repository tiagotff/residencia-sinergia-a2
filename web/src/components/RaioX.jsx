import clsx from 'clsx'
import {
  ArrowRight, Braces, CheckCircle2, CircleDashed, FileText, Search, ShieldAlert, ShieldCheck, Sparkles, Workflow, XCircle,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { BASES, STATUS, corBase, ms, nomeBase, pct, rotuloModo } from '../lib/formato'
import { Abas, BlocoCodigo, PontoBase, Selo, Vazio } from './ui'

// Mostra como o A2 chegou numa resposta. Aceita os dados do /api/chat ou de uma interação gravada.
export default function RaioX({ tarefa, resultado, telemetria = {}, prompt = {}, latencia }) {
  const [aba, setAba] = useState('pipeline')
  const diag = telemetria.diag || {}
  const tentativas = telemetria.tentativas || []
  const candidatos = diag.candidatos || []
  const promptUsuario = prompt.usuario ?? telemetria.prompt_usuario

  const abas = [
    { id: 'pipeline', rotulo: 'Pipeline', icone: Workflow },
    { id: 'busca', rotulo: 'Busca', icone: Search, contagem: candidatos.length || undefined },
    { id: 'prompt', rotulo: 'Prompt', icone: FileText },
    { id: 'llm', rotulo: 'LLM e validação', icone: Sparkles, contagem: tentativas.length || undefined },
    { id: 'json', rotulo: 'JSON', icone: Braces },
  ]
  return (
    <div>
      <Abas abas={abas} ativa={aba} aoMudar={setAba} />
      <div className="pt-4">
        {aba === 'pipeline' && <Pipeline tarefa={tarefa} resultado={resultado} telemetria={telemetria} latencia={latencia} />}
        {aba === 'busca' && <Busca diag={diag} />}
        {aba === 'prompt' && (promptUsuario
          ? <div className="space-y-4">
              {prompt.system && <div><p className="rotulo">System (regras e papel do especialista)</p><BlocoCodigo conteudo={prompt.system} altura="max-h-72" /></div>}
              <div><p className="rotulo">Mensagem do usuário (dados delimitados por tags)</p><BlocoCodigo conteudo={promptUsuario} altura="max-h-96" /></div>
              {!prompt.system && <p className="text-xs text-slate-500">O texto completo do system desta versão está em Configurações → Prompt.</p>}
            </div>
          : <Vazio titulo="O LLM não foi chamado" texto="Guardrail, cache, fora do escopo, modelo fixo ou modo extrativo: nenhum prompt foi montado." />)}
        {aba === 'llm' && <Tentativas tentativas={tentativas} modo={telemetria.modo} />}
        {aba === 'json' && (
          <div className="grid gap-4 xl:grid-cols-2">
            <div><p className="rotulo">TAREFA (A0 → A2)</p><BlocoCodigo conteudo={tarefa} linguagem="json" altura="max-h-[520px]" /></div>
            <div><p className="rotulo">RESULTADO (A2 → A0)</p><BlocoCodigo conteudo={resultado} linguagem="json" altura="max-h-[520px]" /></div>
          </div>
        )}
      </div>
    </div>
  )
}

function Etapa({ estado, titulo, children, ultima }) {
  const estilo = {
    ok: { icone: CheckCircle2, cor: 'text-emerald-600 bg-emerald-50 ring-emerald-200' },
    alerta: { icone: ShieldAlert, cor: 'text-amber-600 bg-amber-50 ring-amber-200' },
    bloqueio: { icone: XCircle, cor: 'text-rose-600 bg-rose-50 ring-rose-200' },
    pulado: { icone: CircleDashed, cor: 'text-slate-400 bg-slate-50 ring-slate-200' },
  }[estado]
  return (
    <li className="relative flex gap-3 pb-5">
      {!ultima && <span className="absolute left-[15px] top-8 h-[calc(100%-24px)] w-px bg-slate-200" />}
      <span className={clsx('relative grid h-8 w-8 shrink-0 place-items-center rounded-full ring-1', estilo.cor)}>
        <estilo.icone className="h-4 w-4" />
      </span>
      <div className="min-w-0 flex-1 pt-1">
        <p className={clsx('text-sm font-semibold', estado === 'pulado' ? 'text-slate-400' : 'text-slate-900')}>{titulo}</p>
        <div className="mt-1 text-sm text-slate-600">{children}</div>
      </div>
    </li>
  )
}

function Pipeline({ tarefa, resultado, telemetria, latencia }) {
  if (!resultado) return null
  const modo = telemetria.modo
  const sinais = telemetria.sinais || []
  const bloqueio = (modo || '').startsWith('guardrail_')
  const social = modo === 'saudacao'
  const diag = telemetria.diag || {}
  const tent = telemetria.tentativas || []
  const recusadas = tent.filter((t) => t.aprovada === false).length
  const falhas = tent.filter((t) => t.erro).length
  const payload = resultado.payload || {}
  const decisao = resultado.decisao || {}
  const ehResponder = (tarefa?.acao ?? resultado.acao) === 'a2.responder'
  const st = STATUS[resultado.status] ?? STATUS.ERRO

  return (
    <ol>
      <Etapa estado="ok" titulo="TAREFA recebida do A0">
        <span className="font-mono text-xs">{tarefa?.acao ?? resultado.acao}</span>
        {tarefa?.payload?.intencao && <> · intenção <Selo tom="info">{tarefa.payload.intencao}</Selo></>}
      </Etapa>

      {ehResponder && (
        <Etapa estado={bloqueio ? 'bloqueio' : sinais.length ? 'alerta' : 'ok'} titulo="Guardrails de entrada">
          {sinais.length === 0 ? 'Nenhum sinal de crise, emergência, injeção ou dados de terceiros.' : (
            <div className="flex flex-wrap gap-1.5">{sinais.map((s, i) => <Selo key={i} tom={s.peso >= 1 ? 'bloqueio' : 'alerta'}>{s.regra}</Selo>)}</div>
          )}
          {telemetria.mascarados?.length > 0 && (
            <p className="mt-1.5 text-xs">Mascarado antes do LLM: <b>{telemetria.mascarados.join(', ')}</b></p>
          )}
          {bloqueio && <p className="mt-1.5 text-xs font-medium text-rose-700">{rotuloModo(modo)}: resposta fixa, sem chamar o LLM.</p>}
        </Etapa>
      )}

      {ehResponder && social && (
        <Etapa estado="ok" titulo="Cordialidade">Cumprimento, agradecimento ou despedida: resposta acolhedora feita pelo código, sem busca e sem LLM.</Etapa>
      )}

      {ehResponder && !bloqueio && !social && (telemetria.deteccao_epi || telemetria.intencao_invalida || telemetria.relato_llm_descartado) && (
        <Etapa estado="alerta" titulo="Ajustes antes da busca">
          {telemetria.deteccao_epi && (
            <p>EPI na mensagem: <Selo tom="marca">{telemetria.deteccao_epi.situacao.replace('_', ' ')}</Selo>
              {telemetria.deteccao_epi.epi && <> · {telemetria.deteccao_epi.epi}</>} → roteiro da base de EPI priorizado</p>
          )}
          {telemetria.intencao_invalida && <p className="mt-1 text-xs">Intenção "{telemetria.intencao_invalida}" fora do catálogo: ignorada.</p>}
          {telemetria.relato_llm_descartado && <p className="mt-1 text-xs">O LLM apontou relato de EPI sem evidência na mensagem atual: descartado (não abre pedido).</p>}
        </Etapa>
      )}

      {ehResponder && !social && !bloqueio && telemetria.plano && (
        <Etapa estado="ok" titulo="R · Entendimento da pergunta">
          <p className="text-xs text-slate-500">{telemetria.plano.usou_llm ? `Reescrita pelo LLM (${ms(telemetria.plano.ms)})` : telemetria.plano.motivo}</p>
          <p className="mt-1 text-sm text-slate-800">“{telemetria.plano.autonoma}”</p>
          {telemetria.plano.subconsultas?.length > 0 && (
            <div className="mt-1.5 flex flex-wrap gap-1.5">{telemetria.plano.subconsultas.map((q, i) => <Selo key={i} tom="info">{q}</Selo>)}</div>
          )}
          {telemetria.plano.tema && <p className="mt-1 text-xs text-slate-500">Tema provável: {nomeBase(telemetria.plano.tema)}</p>}
        </Etapa>
      )}

      {ehResponder && !social && (
        <Etapa estado={bloqueio ? 'pulado' : diag.bases?.length ? 'ok' : 'alerta'} titulo="R · Busca híbrida, fusão e roteamento">
          {!bloqueio && diag.metodo && <p className="mb-1.5 text-xs text-slate-500">{diag.metodo}{diag.relacionados?.length ? ` · relacionados: ${diag.relacionados.join(', ')}` : ''}</p>}
          {!bloqueio && telemetria.consulta_busca && (
            <p className="mb-1.5 text-xs text-sky-700">Mensagem de continuação: a busca usou o contexto da conversa.</p>
          )}
          {bloqueio ? 'Não executada.' : diag.bases?.length ? (
            <div className="flex flex-wrap items-center gap-1.5">
              {diag.base_intencao && <><Selo tom="neutro">intenção → {nomeBase(diag.base_intencao)}</Selo><ArrowRight className="h-3 w-3 text-slate-400" /></>}
              {diag.bases.map((b, i) => (
                <Selo key={b} classe={BASES[b]?.classe}>{i === 0 ? 'principal: ' : ''}{nomeBase(b)}</Selo>
              ))}
              <span className="text-xs text-slate-500">· {(diag.candidatos || []).filter((c) => c.situacao === 'escolhido').length} trechos escolhidos de {(diag.candidatos || []).length} candidatos</span>
            </div>
          ) : modo === 'fora_escopo' ? 'Nenhuma base cobre o tema: resposta de escopo.' : 'Tema reconhecido, mas sem trecho vigente: encaminha ao RH.'}
        </Etapa>
      )}

      {ehResponder && !social && (
        <Etapa titulo="A + G · Contexto, geração e validação"
          estado={bloqueio || !diag.bases?.length ? 'pulado' : modo === 'llm' || modo === 'cache' ? 'ok' : 'alerta'}>
          {bloqueio || !diag.bases?.length ? 'Não executada.' : (
            <>
              <Selo tom={modo === 'llm' ? 'ok' : modo === 'extrativo' ? 'neutro' : 'alerta'}>{rotuloModo(modo)}</Selo>
              {tent.length > 0 && <span className="ml-2 text-xs">{tent.length} chamada(s) ao LLM{recusadas ? ` · ${recusadas} recusada(s) pela validação` : ''}{falhas ? ` · ${falhas} falha(s)` : ''}</span>}
              {telemetria.motivos_falha?.length > 0 && <p className="mt-1 text-xs text-slate-500">{telemetria.motivos_falha.join('; ')}</p>}
              {telemetria.roteiro_epi_aplicado && <p className="mt-1 text-xs text-slate-500">O LLM não viu cobertura; o A2 respondeu pelo roteiro {telemetria.roteiro_epi_aplicado}.</p>}
              {telemetria.fundamentacao && (
                <div className="mt-2">
                  <div className="flex items-center gap-2 text-xs">
                    <span className="text-slate-500">Fundamentação nas fontes</span>
                    <div className="h-1.5 w-28 rounded-full bg-slate-100"><div className={clsx('h-1.5 rounded-full', telemetria.fundamentacao.score >= 0.6 ? 'bg-emerald-500' : 'bg-amber-500')} style={{ width: `${telemetria.fundamentacao.score * 100}%` }} /></div>
                    <b>{pct(telemetria.fundamentacao.score)}</b>
                  </div>
                  {telemetria.fundamentacao.sem_apoio?.length > 0 && <p className="mt-1 text-xs text-amber-700">Sem apoio claro: “{telemetria.fundamentacao.sem_apoio.join('” · “')}”</p>}
                </div>
              )}
              {telemetria.complemento && <p className="mt-2 text-xs text-sky-700">Complemento de conhecimento geral (validado, sem regras nem números): “{telemetria.complemento}”</p>}
              {telemetria.complemento_descartado && <p className="mt-2 text-xs text-amber-700">Complemento descartado ({telemetria.complemento_descartado.motivo}): “{telemetria.complemento_descartado.texto}”</p>}
            </>
          )}
        </Etapa>
      )}

      {!ehResponder && (
        <Etapa estado="ok" titulo="Mensagem por modelo fixo">{rotuloModo(modo)} · sem LLM, tom previsível.</Etapa>
      )}

      {(resultado.eventos || []).length > 0 && (
        <Etapa estado="ok" titulo="Ação no sistema">
          {resultado.eventos.map((e, i) => <div key={i}><span className="font-mono text-xs">{e.tipo}</span> · {JSON.stringify(e.dados)}</div>)}
        </Etapa>
      )}

      <Etapa ultima estado={resultado.status === 'OK' ? 'ok' : resultado.status === 'ERRO' ? 'bloqueio' : 'alerta'} titulo="RESULTADO devolvido ao A0">
        <div className="flex flex-wrap items-center gap-2">
          <Selo classe={st.classe}>{st.rotulo}</Selo>
          {decisao.confianca != null && <span className="text-xs">confiança {pct(decisao.confianca)}</span>}
          {latencia != null && <span className="text-xs">· {ms(latencia)}</span>}
          {payload.encaminhar_para && <Selo tom="alerta">encaminhar para {payload.encaminhar_para}</Selo>}
        </div>
        {decisao.motivo && <p className="mt-1.5 text-xs text-slate-500">{decisao.motivo}</p>}
      </Etapa>
    </ol>
  )
}

function Busca({ diag }) {
  const candidatos = diag.candidatos || []
  const dados = useMemo(() => candidatos.slice(0, 12).map((c) => ({ ...c, rotulo: c.id })), [candidatos])
  if (!candidatos.length) return <Vazio titulo="Sem candidatos" texto="A busca não rodou ou não encontrou nada parecido nas 4 bases." />
  const lim = diag.limiares || {}
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-3">
        <Info rotulo="Intenção do A0 aponta para" valor={nomeBase(diag.base_intencao) === '—' ? 'sem intenção' : nomeBase(diag.base_intencao)} />
        <Info rotulo="Base principal (evidência)" valor={diag.base_principal ? nomeBase(diag.base_principal) : 'nenhuma'} cor={corBase(diag.base_principal)} />
        <Info rotulo="Termos do léxico" valor={Object.entries(diag.lexico || {}).map(([b, t]) => `${nomeBase(b)}: ${t.join(', ')}`).join(' · ') || '—'} pequeno />
      </div>
      <div className="h-[340px] rounded-lg border border-slate-200 p-2">
        <ResponsiveContainer>
          <BarChart data={dados} layout="vertical" margin={{ left: 8, right: 16, top: 8, bottom: 8 }}>
            <CartesianGrid horizontal={false} stroke="#f1f5f9" />
            <XAxis type="number" domain={[0, 'auto']} tick={{ fontSize: 11, fill: '#64748b' }} />
            <YAxis type="category" dataKey="rotulo" width={92} tick={{ fontSize: 11, fill: '#334155' }} />
            <Tooltip content={<DicaCandidato />} cursor={{ fill: '#f8fafc' }} />
            {lim.pontuacao != null && <ReferenceLine x={lim.pontuacao} stroke="#94a3b8" strokeDasharray="4 4" label={{ value: 'mínimo', fontSize: 10, fill: '#64748b', position: 'insideBottomRight' }} />}
            <Bar dataKey="nota" radius={[0, 4, 4, 0]}>
              {dados.map((c) => <Cell key={c.id} fill={corBase(c.base)} fillOpacity={c.situacao === 'escolhido' ? 1 : 0.3} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="text-xs text-slate-500">
        Nota = 0,6 × cosseno + 0,4 × BM25 normalizado + bônus (intenção +0,05; léxico até +0,09). Barras cheias foram enviadas ao LLM.
        Entra quem tem cosseno ≥ {lim.cosseno} ou BM25 ≥ {lim.bm25}.
      </p>
      <div className="overflow-x-auto rounded-lg border border-slate-200">
        <table className="min-w-full text-xs">
          <thead className="bg-slate-50 text-left text-slate-500">
            <tr>{['ID', 'Base', 'Pergunta', 'Cosseno', 'BM25', 'Bônus', 'Nota', 'Situação'].map((h) => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}</tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {candidatos.slice(0, 20).map((c) => (
              <tr key={c.id} className={c.situacao === 'escolhido' ? 'bg-marca-50/40' : ''}>
                <td className="whitespace-nowrap px-3 py-2 font-mono">{c.id}</td>
                <td className="whitespace-nowrap px-3 py-2"><span className="flex items-center gap-1.5"><PontoBase cor={corBase(c.base)} />{nomeBase(c.base)}</span></td>
                <td className="max-w-[280px] truncate px-3 py-2" title={c.titulo}>{c.titulo}</td>
                <td className="px-3 py-2 tabular-nums">{c.cosseno.toFixed(3)}</td>
                <td className="px-3 py-2 tabular-nums">{c.bm25.toFixed(2)}</td>
                <td className="px-3 py-2 tabular-nums">{c.bonus.toFixed(2)}</td>
                <td className="px-3 py-2 font-semibold tabular-nums">{c.nota.toFixed(3)}</td>
                <td className="whitespace-nowrap px-3 py-2"><Selo tom={c.situacao === 'escolhido' ? 'ok' : 'neutro'}>{c.situacao}</Selo></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function DicaCandidato({ active, payload }) {
  if (!active || !payload?.length) return null
  const c = payload[0].payload
  return (
    <div className="max-w-xs rounded-lg border border-slate-200 bg-white p-3 text-xs shadow-lg">
      <p className="font-semibold text-slate-900">{c.id} · {nomeBase(c.base)}</p>
      <p className="mt-1 text-slate-600">{c.titulo}</p>
      <p className="mt-2 tabular-nums text-slate-500">cosseno {c.cosseno.toFixed(3)} · BM25 {c.bm25.toFixed(2)} · bônus {c.bonus.toFixed(2)}</p>
      <p className="font-semibold tabular-nums text-slate-900">nota {c.nota.toFixed(3)} · {c.situacao}</p>
    </div>
  )
}

function Info({ rotulo, valor, cor, pequeno }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/60 px-3 py-2.5">
      <p className="text-[11px] font-medium text-slate-500">{rotulo}</p>
      <p className={clsx('mt-0.5 flex items-center gap-1.5 font-semibold text-slate-900', pequeno ? 'text-xs' : 'text-sm')}>
        {cor && <PontoBase cor={cor} />}{valor}
      </p>
    </div>
  )
}

function Tentativas({ tentativas, modo }) {
  if (!tentativas.length) {
    return <Vazio icone={ShieldCheck} titulo="Sem chamadas ao LLM"
      texto={modo === 'extrativo' ? 'LLM não configurado: a resposta é o texto aprovado do melhor trecho.' : 'Esta resposta não passou pelo LLM.'} />
  }
  return (
    <div className="space-y-4">
      {tentativas.map((t) => (
        <div key={t.n} className={clsx('rounded-lg border p-4', t.erro ? 'border-rose-200 bg-rose-50/40' : t.aprovada ? 'border-emerald-200 bg-emerald-50/30' : 'border-amber-200 bg-amber-50/40')}>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold text-slate-900">Tentativa {t.n}</span>
            {t.erro ? <Selo tom="bloqueio">falha na chamada</Selo> : t.aprovada ? <Selo tom="ok">aprovada</Selo> : <Selo tom="alerta">recusada pela validação</Selo>}
            <span className="text-xs text-slate-500">{ms(t.ms)}</span>
          </div>
          {t.erro && <p className="text-sm text-rose-700">{t.erro}</p>}
          {t.motivos?.length > 0 && (
            <ul className="mb-3 space-y-1">
              {t.motivos.map((m, i) => <li key={i} className="flex gap-2 text-xs text-amber-900"><XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />{m}</li>)}
            </ul>
          )}
          {t.resposta && <BlocoCodigo conteudo={formatarJson(t.resposta)} altura="max-h-64" />}
        </div>
      ))}
      {modo === 'extrativo' && <p className="text-xs text-slate-500">Depois de duas recusas (ou falha), o A2 usou o texto aprovado da base.</p>}
    </div>
  )
}

function formatarJson(bruto) {
  try { return JSON.stringify(JSON.parse(bruto), null, 2) } catch { return bruto }
}
