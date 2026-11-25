import clsx from 'clsx'
import { ChevronDown, Search } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { CabecalhoPagina, Cartao, Carregando, Erro, Selo, Vazio } from '../components/ui'
import { corBase } from '../lib/formato'

export default function Bases() {
  const [bases, setBases] = useState(null)
  const [ativa, setAtiva] = useState(null)
  const [perguntas, setPerguntas] = useState(null)
  const [filtro, setFiltro] = useState('')
  const [aberta, setAberta] = useState(null)
  const [erro, setErro] = useState(null)

  useEffect(() => { api.bases().then((b) => { setBases(b); setAtiva(b[0]?.slug) }).catch(setErro) }, [])
  useEffect(() => { if (ativa) { setPerguntas(null); api.perguntas(ativa).then(setPerguntas).catch(setErro) } }, [ativa])

  const visiveis = useMemo(() => {
    if (!perguntas) return []
    const f = filtro.trim().toLowerCase()
    return f ? perguntas.filter((p) => `${p.id} ${p.titulo} ${p.resposta} ${p.variacoes.join(' ')}`.toLowerCase().includes(f)) : perguntas
  }, [perguntas, filtro])
  const secoes = useMemo(() => [...new Set(visiveis.map((p) => p.secao))], [visiveis])

  return (
    <>
      <CabecalhoPagina titulo="Bases de conhecimento" descricao="As 4 bases que o A2 consulta. Cada pergunta (ID) é um chunk; o texto indexado junta título, variações e resposta." />
      <Erro erro={erro} />
      {!bases ? <Carregando /> : bases.length === 0 ? <Vazio titulo="Índice vazio" texto="Vá em Configurações → Reindexar bases." /> : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {bases.map((b) => (
              <button key={b.slug} onClick={() => setAtiva(b.slug)}
                className={clsx('overflow-hidden rounded-xl border bg-white text-left shadow-cartao transition-all',
                  ativa === b.slug ? 'border-transparent ring-2' : 'border-slate-200 hover:border-slate-300')}
                style={ativa === b.slug ? { '--tw-ring-color': corBase(b.slug) } : undefined}>
                <div className="h-1.5" style={{ backgroundColor: corBase(b.slug) }} />
                <div className="p-4">
                  <div className="flex items-start justify-between gap-2">
                    <p className="font-semibold text-slate-900">{b.nome}</p>
                    <Selo tom="neutro">v{b.versao}</Selo>
                  </div>
                  <p className="mt-0.5 text-xs text-slate-500">{b.especialista} · {b.funcionalidades.join(', ')}</p>
                  <p className="mt-3 text-3xl font-semibold text-slate-900">{b.perguntas}<span className="ml-1 text-sm font-normal text-slate-500">perguntas</span></p>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    <Selo tom="info">{b.oficial} oficial</Selo>
                    <Selo tom="marca">{b.interno} interno</Selo>
                    <Selo tom={b.aprovacao?.toUpperCase().startsWith('APROVAD') ? 'ok' : 'alerta'}>{b.aprovacao?.split(' ')[0] ?? '—'}</Selo>
                  </div>
                  <p className="mt-2 text-[11px] text-slate-400">vigente desde {b.vigencia ? new Date(b.vigencia + 'T12:00').toLocaleDateString('pt-BR') : '—'}</p>
                </div>
              </button>
            ))}
          </div>

          <Cartao className="mt-6" titulo={bases.find((b) => b.slug === ativa)?.titulo} subtitulo={`${visiveis.length} pergunta(s)`}
            acoes={<div className="relative w-64"><Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
              <input className="campo pl-9" placeholder="Filtrar perguntas" value={filtro} onChange={(e) => setFiltro(e.target.value)} /></div>}>
            {!perguntas ? <Carregando /> : visiveis.length === 0 ? <Vazio titulo="Nenhuma pergunta com esse filtro" /> : (
              <div className="space-y-6">
                {secoes.map((s) => (
                  <div key={s}>
                    <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{s}</p>
                    <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">
                      {visiveis.filter((p) => p.secao === s).map((p) => (
                        <li key={p.id}>
                          <button onClick={() => setAberta(aberta === p.id ? null : p.id)} className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-slate-50">
                            <span className="w-24 shrink-0 font-mono text-xs text-slate-500">{p.id}</span>
                            <span className="flex-1 text-sm text-slate-800">{p.titulo}</span>
                            {p.tipos_fonte.map((t) => <Selo key={t} tom={t === 'OFICIAL' ? 'info' : 'marca'}>{t.toLowerCase()}</Selo>)}
                            <ChevronDown className={clsx('h-4 w-4 shrink-0 text-slate-400 transition-transform', aberta === p.id && 'rotate-180')} />
                          </button>
                          {aberta === p.id && (
                            <div className="space-y-3 border-t border-slate-100 bg-slate-50/60 px-4 py-4 sm:pl-[124px]">
                              <div className="flex flex-wrap gap-1.5">
                                {p.variacoes.map((v, i) => <span key={i} className="rounded-full bg-white px-2.5 py-0.5 text-xs text-slate-600 ring-1 ring-slate-200">{v}</span>)}
                                {(p.variacoes_extras || []).map((v, i) => <span key={`x${i}`} title="Variação extra (variacoes_extras.json), aprendida com as interações" className="rounded-full bg-marca-50 px-2.5 py-0.5 text-xs text-marca-700 ring-1 ring-marca-200">+ {v}</span>)}
                              </div>
                              <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-700">{p.resposta}</p>
                              <p className="text-xs text-slate-500">Fonte: {p.fonte}</p>
                            </div>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            )}
          </Cartao>
        </>
      )}
    </>
  )
}
