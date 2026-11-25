import { CheckCircle2, Play, RotateCcw, XCircle } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../api'
import RaioX from '../components/RaioX'
import { Botao, CabecalhoPagina, Cartao, Carregando, Erro, Interruptor, Selo, Vazio } from '../components/ui'
import { useApp } from '../contexto'
import { STATUS } from '../lib/formato'

export default function Playground() {
  const { status } = useApp()
  const [fixtures, setFixtures] = useState(null)
  const [sel, setSel] = useState('')
  const [json, setJson] = useState('')
  const [usarLlm, setUsarLlm] = useState(true)
  const [rodando, setRodando] = useState(false)
  const [res, setRes] = useState(null)
  const [erro, setErro] = useState(null)

  useEffect(() => { api.fixtures().then((f) => { setFixtures(f); if (f[0]) escolher(f[0]) }).catch(setErro) }, [])
  const escolher = (f) => { setSel(f.nome); setJson(JSON.stringify(f.tarefa, null, 2)); setRes(null); setErro(null) }
  const atual = fixtures?.find((f) => f.nome === sel)

  const rodar = async () => {
    setErro(null); setRodando(true)
    try {
      const tarefa = JSON.parse(json)
      setRes(await api.playground({ tarefa, usar_llm: usarLlm && !!status?.llm }))
    } catch (e) { setErro(e instanceof SyntaxError ? new Error(`JSON inválido: ${e.message}`) : e) } finally { setRodando(false) }
  }

  const esp = atual?.esperado
  const r = res?.resultado
  const comparacoes = r && esp ? [
    ['status', r.status, esp.status], ['ação', r.acao, esp.acao], ['base', r.payload?.base, esp.payload?.base],
    ['estado_proposto', r.estado_proposto, esp.estado_proposto], ['nº de saídas', r.saidas.length, esp.saidas.length],
  ] : []

  return (
    <>
      <CabecalhoPagina titulo="TAREFA → RESULTADO" descricao="Rode as TAREFAs do contrato sinergia/1 como o A0 faria, edite o JSON e compare com o RESULTADO esperado (gerado em modo extrativo)." />
      <div className="grid gap-6 xl:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <Cartao titulo="TAREFA" acoes={<Botao onClick={rodar} carregando={rodando} icone={Play}>Executar</Botao>}>
          {!fixtures ? <Carregando /> : (
            <div className="space-y-3">
              <div className="flex flex-wrap items-end gap-3">
                <div className="min-w-[240px] flex-1">
                  <label className="rotulo">Fixture</label>
                  <select className="campo" value={sel} onChange={(e) => escolher(fixtures.find((f) => f.nome === e.target.value))}>
                    {fixtures.map((f) => <option key={f.nome} value={f.nome}>{f.nome}</option>)}
                  </select>
                </div>
                <Botao variante="secundario" icone={RotateCcw} onClick={() => atual && escolher(atual)}>Restaurar</Botao>
              </div>
              <Interruptor ligado={usarLlm && !!status?.llm} desabilitado={!status?.llm} aoMudar={setUsarLlm} rotulo="Usar LLM" />
              <textarea value={json} onChange={(e) => setJson(e.target.value)} spellCheck={false}
                className="rolagem h-[520px] w-full rounded-lg border border-slate-800 bg-slate-900 p-4 font-mono text-xs leading-relaxed text-slate-100 focus:outline-none focus:ring-2 focus:ring-marca-500/40" />
              <p className="text-[11px] text-slate-400">O id_mensagem ganha um sufixo a cada execução para não cair na idempotência.</p>
            </div>
          )}
        </Cartao>

        <div className="space-y-6">
          <Erro erro={erro} />
          {!r ? <Cartao><Vazio icone={Play} titulo="Execute uma TAREFA" texto="O RESULTADO aparece aqui, com a comparação com o esperado e o raio-X." /></Cartao> : (
            <>
              <Cartao titulo="RESULTADO" subtitulo={`Interação #${res.id_interacao ?? '—'}`}
                acoes={<Selo classe={STATUS[r.status]?.classe}>{STATUS[r.status]?.rotulo ?? r.status}</Selo>}>
                {r.saidas[0] && <p className="rounded-lg bg-slate-50 p-4 text-sm leading-relaxed text-slate-800">{r.saidas[0].texto}</p>}
                {r.erro && <p className="text-sm text-rose-700">{r.erro.codigo}: {r.erro.mensagem}</p>}
                {comparacoes.length > 0 && (
                  <table className="mt-4 w-full text-sm">
                    <thead className="text-left text-xs text-slate-500"><tr><th className="pb-2">Campo</th><th>Agora</th><th>Esperado</th><th /></tr></thead>
                    <tbody className="divide-y divide-slate-100">
                      {comparacoes.map(([c, a, e]) => (
                        <tr key={c}><td className="py-2 text-slate-600">{c}</td><td className="font-mono text-xs">{String(a)}</td><td className="font-mono text-xs">{String(e)}</td>
                          <td>{a === e ? <CheckCircle2 className="h-4 w-4 text-emerald-500" /> : <XCircle className="h-4 w-4 text-amber-500" />}</td></tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </Cartao>
              <Cartao titulo="Raio-X">
                <RaioX tarefa={JSON.parse(json)} resultado={r} telemetria={res.raio_x.telemetria} prompt={res.raio_x.prompt} latencia={res.raio_x.latencia_ms} />
              </Cartao>
            </>
          )}
        </div>
      </div>
    </>
  )
}
