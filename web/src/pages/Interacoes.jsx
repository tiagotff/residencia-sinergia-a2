import { ChevronLeft, ChevronRight, Download, FileSpreadsheet, Search, ThumbsDown, ThumbsUp } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import DetalheInteracao from '../components/DetalheInteracao'
import { Botao, CabecalhoPagina, Cartao, Carregando, Erro, Selo, Vazio } from '../components/ui'
import { BASES, MODOS, STATUS, dataHora, ms, nomeBase, pct, rotuloModo } from '../lib/formato'

const VAZIO = { busca: '', base: '', status: '', modo: '', feedback: '', dias: '' }

export default function Interacoes() {
  const [filtros, setFiltros] = useState(VAZIO)
  const [busca, setBusca] = useState('')
  const [pagina, setPagina] = useState(1)
  const [dados, setDados] = useState(null)
  const [erro, setErro] = useState(null)
  const [aberta, setAberta] = useState(null)

  const carregar = useCallback(() => {
    api.interacoes({ ...filtros, pagina, tamanho: 20 }).then(setDados).catch(setErro)
  }, [filtros, pagina])
  useEffect(() => { carregar() }, [carregar])
  useEffect(() => { const t = setTimeout(() => { setPagina(1); setFiltros((f) => ({ ...f, busca })) }, 350); return () => clearTimeout(t) }, [busca])

  const set = (k) => (e) => { setPagina(1); setFiltros((f) => ({ ...f, [k]: e.target.value })) }
  const paginas = dados ? Math.max(1, Math.ceil(dados.total / dados.tamanho)) : 1
  const filtrosExport = Object.fromEntries(Object.entries(filtros).filter(([, v]) => v))

  return (
    <>
      <CabecalhoPagina titulo="Interações" descricao="Tudo o que o A2 respondeu, gravado com pergunta mascarada, colaborador pseudonimizado e o raio-X completo. Clique numa linha para analisar."
        acoes={<>
          <Botao icone={FileSpreadsheet} onClick={() => api.exportar('xlsx', { dias: filtros.dias || undefined }).catch(setErro)}>Planilha de análise</Botao>
          <Botao variante="secundario" icone={Download} onClick={() => api.exportar('csv', filtrosExport).catch(setErro)}>CSV</Botao>
          <Botao variante="secundario" icone={Download} onClick={() => api.exportar('jsonl', filtrosExport).catch(setErro)}>JSONL</Botao>
        </>} />

      <Cartao corpo="p-0">
        <div className="grid gap-3 border-b border-slate-100 p-4 md:grid-cols-3 xl:grid-cols-6">
          <div className="relative md:col-span-3 xl:col-span-2">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
            <input className="campo pl-9" placeholder="Buscar na pergunta, resposta ou motivo" value={busca} onChange={(e) => setBusca(e.target.value)} />
          </div>
          <select className="campo" value={filtros.base} onChange={set('base')}>
            <option value="">Todas as bases</option>
            {Object.entries(BASES).filter(([k]) => k !== 'procedimentos').map(([k, v]) => <option key={k} value={k}>{v.nome}</option>)}
          </select>
          <select className="campo" value={filtros.status} onChange={set('status')}>
            <option value="">Todos os status</option>
            {Object.entries(STATUS).map(([k, v]) => <option key={k} value={k}>{v.rotulo}</option>)}
          </select>
          <select className="campo" value={filtros.modo} onChange={set('modo')}>
            <option value="">Todos os modos</option>
            <option value="guardrail">Qualquer guardrail</option>
            {Object.entries(MODOS).map(([k, v]) => <option key={k} value={k}>{v.rotulo}</option>)}
          </select>
          <div className="grid grid-cols-2 gap-3">
            <select className="campo" value={filtros.feedback} onChange={set('feedback')}>
              <option value="">Feedback</option><option value="sem">Sem</option><option value="positivo">👍</option><option value="negativo">👎</option>
            </select>
            <select className="campo" value={filtros.dias} onChange={set('dias')}>
              <option value="">Sempre</option><option value="1">24h</option><option value="7">7 dias</option><option value="30">30 dias</option>
            </select>
          </div>
        </div>

        <Erro erro={erro} />
        {!dados ? <Carregando /> : dados.itens.length === 0 ? (
          <Vazio titulo="Nenhuma interação encontrada" texto="Ajuste os filtros ou converse com o A2 no Atendimento." />
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs font-medium text-slate-500">
                <tr>
                  {['#', 'Quando', 'Pergunta', 'Base', 'Status', 'Modo', 'Confiança', 'Tempo', ''].map((h) => <th key={h} className="whitespace-nowrap px-4 py-2.5">{h}</th>)}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {dados.itens.map((i) => (
                  <tr key={i.id} onClick={() => setAberta(i.id)} className="cursor-pointer hover:bg-slate-50">
                    <td className="px-4 py-3 font-mono text-xs text-slate-400">{i.id}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-xs text-slate-500">{dataHora(i.criado_em)}</td>
                    <td className="max-w-md px-4 py-3">
                      <p className="truncate text-slate-800">{i.pergunta ?? <span className="font-mono text-xs text-slate-500">{i.acao}</span>}</p>
                      <p className="truncate text-xs text-slate-400">{i.resposta}</p>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3">{i.base ? <Selo classe={BASES[i.base]?.classe}>{nomeBase(i.base)}</Selo> : <span className="text-slate-300">—</span>}</td>
                    <td className="whitespace-nowrap px-4 py-3"><Selo classe={STATUS[i.status]?.classe}>{STATUS[i.status]?.rotulo ?? i.status}</Selo></td>
                    <td className="whitespace-nowrap px-4 py-3 text-xs text-slate-600">{rotuloModo(i.modo)}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-xs tabular-nums">{pct(i.confianca)}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-xs tabular-nums text-slate-500">{ms(i.latencia_ms)}</td>
                    <td className="px-4 py-3">
                      {i.feedback === 'positivo' && <ThumbsUp className="h-4 w-4 text-emerald-500" />}
                      {i.feedback === 'negativo' && <ThumbsDown className={i.feedback_situacao === 'resolvido' ? 'h-4 w-4 text-slate-300' : 'h-4 w-4 text-rose-500'} />}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {dados && dados.total > 0 && (
          <div className="flex items-center justify-between border-t border-slate-100 px-4 py-3 text-xs text-slate-500">
            <span>{dados.total} interação(ões)</span>
            <div className="flex items-center gap-2">
              <Botao variante="secundario" tamanho="sm" icone={ChevronLeft} disabled={pagina <= 1} onClick={() => setPagina((p) => p - 1)} />
              <span>Página {pagina} de {paginas}</span>
              <Botao variante="secundario" tamanho="sm" icone={ChevronRight} disabled={pagina >= paginas} onClick={() => setPagina((p) => p + 1)} />
            </div>
          </div>
        )}
      </Cartao>

      <DetalheInteracao id={aberta} aoFechar={() => setAberta(null)} aoMudar={carregar} />
    </>
  )
}
