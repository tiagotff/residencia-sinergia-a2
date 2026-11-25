import {
  Activity, AlertTriangle, Bot, Clock, Gauge, MessagesSquare, ShieldAlert, ThumbsDown, ThumbsUp, Wrench,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { api } from '../api'
import { Botao, CabecalhoPagina, Cartao, Carregando, Erro, Kpi, PontoBase, Vazio } from '../components/ui'
import { STATUS, corBase, ms, nomeBase, num, pct, rotuloModo } from '../lib/formato'

const PERIODOS = [7, 30, 90]
const CORES_MODO = ['#088575', '#28c1a8', '#94a3b8', '#f59e0b', '#f43f5e', '#6366f1', '#0ea5e9', '#a855f7', '#64748b', '#84cc16']

export default function Painel() {
  const [dias, setDias] = useState(30)
  const [m, setM] = useState(null)
  const [erro, setErro] = useState(null)

  useEffect(() => { setM(null); api.metricas(dias).then(setM).catch(setErro) }, [dias])

  const seletor = (
    <div className="inline-flex rounded-lg bg-white p-0.5 shadow-sm ring-1 ring-slate-200">
      {PERIODOS.map((d) => (
        <button key={d} onClick={() => setDias(d)}
          className={`rounded-md px-3 py-1.5 text-xs font-medium ${dias === d ? 'bg-marca-600 text-white' : 'text-slate-600 hover:bg-slate-50'}`}>{d} dias</button>
      ))}
    </div>
  )

  if (erro) return <Erro erro={erro} />
  if (!m) return <><CabecalhoPagina titulo="Painel" acoes={seletor} /><Carregando /></>

  if (m.total === 0) {
    return (
      <>
        <CabecalhoPagina titulo="Painel" descricao="Indicadores das interações gravadas no banco." acoes={seletor} />
        <Cartao><Vazio icone={MessagesSquare} titulo="Ainda não há interações no período"
          texto="Converse com o A2 no Atendimento ou rode uma TAREFA no playground. Cada resposta é gravada com o raio-X completo."
          acao={<Link to="/atendimento"><Botao>Ir para o Atendimento</Botao></Link>} /></Cartao>
      </>
    )
  }

  const ok = m.status.OK ?? 0
  const humano = m.status.PRECISA_HUMANO ?? 0
  const guard = Object.entries(m.modos).filter(([k]) => k.startsWith('guardrail_')).reduce((a, [, v]) => a + v, 0)
  const llm = m.llm
  const modos = Object.entries(m.modos).map(([k, v]) => ({ nome: rotuloModo(k), valor: v })).sort((a, b) => b.valor - a.valor)
  const bases = Object.entries(m.bases).map(([k, v]) => ({ slug: k, nome: nomeBase(k), valor: v })).sort((a, b) => b.valor - a.valor)
  const recusas = Object.entries(m.recusas_llm).map(([k, v]) => ({ nome: k.replaceAll('_', ' '), valor: v }))

  return (
    <>
      <CabecalhoPagina titulo="Painel" descricao="Como o A2 está respondendo: volume, roteamento entre as bases, guardrails, uso do LLM e feedback humano." acoes={seletor} />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Kpi rotulo="Interações" valor={num(m.total)} icone={Activity} detalhe={`${num(m.epi_solicitacoes)} pedido(s) de EPI abertos`} />
        <Kpi rotulo="Resolvidas pelo A2" valor={pct(ok / m.total)} icone={Gauge} tom="ok" detalhe={`${num(ok)} com status OK`} />
        <Kpi rotulo="Encaminhadas a humano" valor={pct(humano / m.total)} icone={AlertTriangle} tom="alerta" detalhe={`${num(humano)} · RH, SESMT ou TST`} />
        <Kpi rotulo="Guardrails acionados" valor={num(guard)} icone={ShieldAlert} tom="bloqueio" detalhe="crise, emergência, injeção, terceiros" />
        <Kpi rotulo="LLM aprovado na 1ª" valor={llm.respostas_com_llm ? pct(llm.aprovadas_1a / llm.respostas_com_llm) : '—'} icone={Bot} tom="info"
          detalhe={`${num(llm.aprovadas_2a)} na 2ª · ${num(llm.fallback)} caíram no extrativo`} />
        <Kpi rotulo="Feedback" valor={<span className="flex items-center gap-3"><span className="flex items-center gap-1 text-emerald-600"><ThumbsUp className="h-5 w-5" />{m.feedback.positivo}</span><span className="flex items-center gap-1 text-rose-600"><ThumbsDown className="h-5 w-5" />{m.feedback.negativo}</span></span>}
          icone={Wrench} tom="neutro" detalhe={`${m.feedback.abertos} análise(s) em aberto`} />
        <Kpi rotulo="Latência" valor={ms(m.latencia_ms.media)} icone={Clock} tom="neutro" detalhe={`p95 ${ms(m.latencia_ms.p95)}`} />
        <Kpi rotulo="Confiança média" valor={pct(m.confianca_media)} icone={Gauge} tom="marca" detalhe="busca × cobertura × fundamentação" />
        <Kpi rotulo="Fundamentação média" valor={pct(m.rag?.fundamentacao_media)} icone={ShieldAlert} tom="ok" detalhe="frases da resposta apoiadas nas fontes" />
        <Kpi rotulo="Perguntas reescritas" valor={num(m.rag?.perguntas_reescritas)} icone={Bot} tom="info" detalhe="entendimento + multi-consulta pelo LLM" />
        <Kpi rotulo="Dicas de conhecimento geral" valor={num(m.rag?.com_complemento)} icone={MessagesSquare} tom="marca" detalhe={`${num(m.rag?.complementos_descartados)} descartada(s) pela validação`} />
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-3">
        <Cartao titulo="Volume por dia" subtitulo="Empilhado por status do RESULTADO" className="xl:col-span-2">
          <div className="h-72">
            <ResponsiveContainer>
              <BarChart data={m.por_dia} margin={{ left: -16, right: 8, top: 8 }}>
                <CartesianGrid vertical={false} stroke="#f1f5f9" />
                <XAxis dataKey="dia" tick={{ fontSize: 11, fill: '#64748b' }} tickFormatter={(d) => d.slice(8, 10) + '/' + d.slice(5, 7)} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#64748b' }} />
                <Tooltip contentStyle={{ borderRadius: 8, fontSize: 12 }} cursor={{ fill: '#f8fafc' }} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                {Object.entries(STATUS).map(([k, s], i, arr) => (
                  <Bar key={k} dataKey={k} name={s.rotulo} stackId="1" fill={s.cor} maxBarSize={48}
                    radius={i === arr.length - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]} />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Cartao>

        <Cartao titulo="Modo de resposta" subtitulo="Por onde cada resposta saiu">
          <div className="h-72">
            <ResponsiveContainer>
              <PieChart>
                <Pie data={modos} dataKey="valor" nameKey="nome" innerRadius={55} outerRadius={85} paddingAngle={2}>
                  {modos.map((_, i) => <Cell key={i} fill={CORES_MODO[i % CORES_MODO.length]} />)}
                </Pie>
                <Tooltip contentStyle={{ borderRadius: 8, fontSize: 12 }} />
                <Legend wrapperStyle={{ fontSize: 11 }} layout="vertical" verticalAlign="middle" align="right" />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </Cartao>

        <Cartao titulo="Base que respondeu" subtitulo="Roteamento dinâmico entre as 4 bases">
          {bases.length === 0 ? <Vazio titulo="Sem respostas com base" /> : (
            <div className="h-64">
              <ResponsiveContainer>
                <BarChart data={bases} layout="vertical" margin={{ left: 8, right: 16 }}>
                  <CartesianGrid horizontal={false} stroke="#f1f5f9" />
                  <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11, fill: '#64748b' }} />
                  <YAxis type="category" dataKey="nome" width={130} tick={{ fontSize: 11, fill: '#334155' }} />
                  <Tooltip contentStyle={{ borderRadius: 8, fontSize: 12 }} cursor={{ fill: '#f8fafc' }} />
                  <Bar dataKey="valor" name="Interações" radius={[0, 4, 4, 0]}>
                    {bases.map((b) => <Cell key={b.slug} fill={corBase(b.slug)} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Cartao>

        <Cartao titulo="Por que o LLM foi recusado" subtitulo="Motivos da validação de saída">
          {recusas.length === 0 ? <Vazio titulo="Nenhuma recusa" texto="Todas as respostas do LLM passaram na validação (ou o LLM não foi usado)." /> : (
            <div className="h-64">
              <ResponsiveContainer>
                <BarChart data={recusas} layout="vertical" margin={{ left: 8, right: 16 }}>
                  <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11, fill: '#64748b' }} />
                  <YAxis type="category" dataKey="nome" width={140} tick={{ fontSize: 11, fill: '#334155' }} />
                  <Tooltip contentStyle={{ borderRadius: 8, fontSize: 12 }} cursor={{ fill: '#f8fafc' }} />
                  <Bar dataKey="valor" name="Recusas" fill="#f59e0b" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Cartao>

        <Cartao titulo="Guardrails de entrada" subtitulo="Sinais que bloquearam o LLM">
          {Object.keys(m.guardrails).length === 0 ? <Vazio titulo="Nenhum bloqueio" /> : (
            <ul className="space-y-3">
              {Object.entries(m.guardrails).sort((a, b) => b[1] - a[1]).map(([k, v]) => {
                const max = Math.max(...Object.values(m.guardrails))
                return (
                  <li key={k}>
                    <div className="mb-1 flex justify-between text-sm"><span className="capitalize text-slate-700">{k}</span><span className="font-semibold tabular-nums">{v}</span></div>
                    <div className="h-2 rounded-full bg-slate-100"><div className="h-2 rounded-full bg-rose-400" style={{ width: `${(v / max) * 100}%` }} /></div>
                  </li>
                )
              })}
            </ul>
          )}
        </Cartao>

        <Cartao titulo="Perguntas sem cobertura" subtitulo="Candidatas a entrar nas bases" className="xl:col-span-2">
          {m.sem_cobertura_top.length === 0 ? <Vazio titulo="Todas as perguntas tiveram cobertura" /> : (
            <ul className="divide-y divide-slate-100">
              {m.sem_cobertura_top.map((p, i) => (
                <li key={i} className="flex items-center justify-between gap-4 py-2.5 text-sm">
                  <span className="text-slate-700">{p.pergunta}</span>
                  <span className="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-600">{p.vezes}×</span>
                </li>
              ))}
            </ul>
          )}
        </Cartao>

        <Cartao titulo="Versões do prompt" subtitulo="Compare antes e depois de cada ajuste">
          {Object.keys(m.por_versao_prompt).length === 0 ? <Vazio titulo="Sem respostas com LLM" texto="Configure a GROQ_API_KEY para comparar versões." /> : (
            <table className="w-full text-xs">
              <thead className="text-left text-slate-500"><tr><th className="pb-2">Versão</th><th>Resp.</th><th>1ª ok</th><th>Fallback</th><th>👍/👎</th></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {Object.entries(m.por_versao_prompt).map(([v, x]) => (
                  <tr key={v}><td className="py-2 font-mono">{v}</td><td>{x.interacoes}</td><td>{pct(x.aprovadas_1a)}</td><td>{pct(x.fallback)}</td><td>{x.feedback_positivo}/{x.feedback_negativo}</td></tr>
                ))}
              </tbody>
            </table>
          )}
          <div className="mt-4 flex flex-wrap gap-3 text-[11px] text-slate-500">
            {Object.entries(m.acoes).map(([a, v]) => <span key={a} className="flex items-center gap-1.5"><PontoBase cor="#94a3b8" />{a}: {v}</span>)}
          </div>
        </Cartao>
      </div>
    </>
  )
}
