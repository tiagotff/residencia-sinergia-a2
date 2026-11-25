import clsx from 'clsx'
import { Check, Copy, Inbox, Loader2, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { TONS } from '../lib/formato'

export function Cartao({ titulo, subtitulo, acoes, children, className, corpo = 'p-5', icone: Icone }) {
  return (
    <section className={clsx('rounded-xl border border-slate-200 bg-white shadow-cartao', className)}>
      {(titulo || acoes) && (
        <header className="flex items-start justify-between gap-3 border-b border-slate-100 px-5 py-3.5">
          <div className="flex min-w-0 items-center gap-2.5">
            {Icone && <Icone className="h-4 w-4 shrink-0 text-marca-600" />}
            <div className="min-w-0">
              <h2 className="truncate text-sm font-semibold text-slate-900">{titulo}</h2>
              {subtitulo && <p className="mt-0.5 text-xs text-slate-500">{subtitulo}</p>}
            </div>
          </div>
          {acoes && <div className="flex shrink-0 items-center gap-2">{acoes}</div>}
        </header>
      )}
      <div className={corpo}>{children}</div>
    </section>
  )
}

export function Kpi({ rotulo, valor, detalhe, icone: Icone, tom = 'marca' }) {
  const fundo = {
    marca: 'bg-marca-50 text-marca-600', ok: 'bg-emerald-50 text-emerald-600', alerta: 'bg-amber-50 text-amber-600',
    bloqueio: 'bg-rose-50 text-rose-600', info: 'bg-sky-50 text-sky-600', neutro: 'bg-slate-100 text-slate-600',
  }[tom]
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-cartao">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-xs font-medium text-slate-500">{rotulo}</p>
          <p className="mt-1.5 text-2xl font-semibold tracking-tight text-slate-900">{valor}</p>
        </div>
        {Icone && (
          <span className={clsx('grid h-9 w-9 shrink-0 place-items-center rounded-lg', fundo)}>
            <Icone className="h-[18px] w-[18px]" />
          </span>
        )}
      </div>
      {detalhe && <p className="mt-2 truncate text-xs text-slate-500">{detalhe}</p>}
    </div>
  )
}

export function Selo({ children, tom = 'neutro', classe, className, title }) {
  return (
    <span title={title} className={clsx('inline-flex items-center gap-1 whitespace-nowrap rounded-md px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset',
      classe ?? TONS[tom], className)}>
      {children}
    </span>
  )
}

export function Botao({ children, variante = 'primario', tamanho = 'md', carregando, icone: Icone, className, ...props }) {
  const v = {
    primario: 'bg-marca-600 text-white hover:bg-marca-700 shadow-sm',
    secundario: 'bg-white text-slate-700 ring-1 ring-inset ring-slate-300 hover:bg-slate-50 shadow-sm',
    fantasma: 'text-slate-600 hover:bg-slate-100',
    perigo: 'bg-rose-600 text-white hover:bg-rose-700',
  }[variante]
  const t = { sm: 'h-8 px-2.5 text-xs gap-1.5', md: 'h-9 px-3.5 text-sm gap-2', lg: 'h-10 px-4 text-sm gap-2' }[tamanho]
  return (
    <button {...props} disabled={props.disabled || carregando}
      className={clsx('inline-flex items-center justify-center rounded-lg font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50', v, t, className)}>
      {carregando ? <Loader2 className="h-4 w-4 animate-spin" /> : Icone && <Icone className="h-4 w-4" />}
      {children}
    </button>
  )
}

export function Interruptor({ ligado, aoMudar, rotulo, desabilitado, dica }) {
  return (
    <label title={dica} className={clsx('inline-flex select-none items-center gap-2 text-sm', desabilitado ? 'cursor-not-allowed opacity-50' : 'cursor-pointer')}>
      <button type="button" role="switch" aria-checked={ligado} disabled={desabilitado} onClick={() => aoMudar(!ligado)}
        className={clsx('relative h-5 w-9 rounded-full transition-colors', ligado ? 'bg-marca-600' : 'bg-slate-300')}>
        <span className={clsx('absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-all', ligado ? 'left-[18px]' : 'left-0.5')} />
      </button>
      <span className="text-slate-700">{rotulo}</span>
    </label>
  )
}

export function Carregando({ texto = 'Carregando...' }) {
  return (
    <div className="flex items-center justify-center gap-2 py-12 text-sm text-slate-500">
      <Loader2 className="h-4 w-4 animate-spin text-marca-600" /> {texto}
    </div>
  )
}

export function Vazio({ titulo = 'Nada por aqui ainda', texto, acao, icone: Icone = Inbox }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
      <span className="grid h-12 w-12 place-items-center rounded-full bg-slate-100 text-slate-400"><Icone className="h-6 w-6" /></span>
      <p className="mt-3 text-sm font-semibold text-slate-800">{titulo}</p>
      {texto && <p className="mt-1 max-w-md text-sm text-slate-500">{texto}</p>}
      {acao && <div className="mt-4">{acao}</div>}
    </div>
  )
}

export function Erro({ erro }) {
  if (!erro) return null
  return <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{String(erro.message ?? erro)}</div>
}

export function Abas({ abas, ativa, aoMudar }) {
  return (
    <div className="flex gap-1 overflow-x-auto rolagem border-b border-slate-200">
      {abas.map((a) => (
        <button key={a.id} onClick={() => aoMudar(a.id)}
          className={clsx('-mb-px flex items-center gap-1.5 whitespace-nowrap border-b-2 px-3 py-2.5 text-sm font-medium transition-colors',
            ativa === a.id ? 'border-marca-600 text-marca-700' : 'border-transparent text-slate-500 hover:text-slate-800')}>
          {a.icone && <a.icone className="h-4 w-4" />}
          {a.rotulo}
          {a.contagem !== undefined && (
            <span className={clsx('rounded-full px-1.5 text-[10px]', ativa === a.id ? 'bg-marca-100 text-marca-700' : 'bg-slate-100 text-slate-500')}>{a.contagem}</span>
          )}
        </button>
      ))}
    </div>
  )
}

export function Gaveta({ aberta, aoFechar, titulo, subtitulo, children, largura = 'max-w-4xl' }) {
  useEffect(() => {
    const tecla = (e) => e.key === 'Escape' && aoFechar()
    if (aberta) window.addEventListener('keydown', tecla)
    return () => window.removeEventListener('keydown', tecla)
  }, [aberta, aoFechar])
  if (!aberta) return null
  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-slate-900/40 backdrop-blur-[1px]" onClick={aoFechar} />
      <aside className={clsx('relative flex h-full w-full flex-col bg-slate-50 shadow-2xl', largura)}>
        <header className="flex items-start justify-between gap-4 border-b border-slate-200 bg-white px-6 py-4">
          <div className="min-w-0">
            <h2 className="truncate text-base font-semibold text-slate-900">{titulo}</h2>
            {subtitulo && <p className="mt-0.5 text-xs text-slate-500">{subtitulo}</p>}
          </div>
          <button onClick={aoFechar} className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100" aria-label="Fechar"><X className="h-5 w-5" /></button>
        </header>
        <div className="rolagem flex-1 overflow-y-auto p-6">{children}</div>
      </aside>
    </div>
  )
}

export function BlocoCodigo({ conteudo, linguagem, altura = 'max-h-96' }) {
  const [copiado, setCopiado] = useState(false)
  const texto = typeof conteudo === 'string' ? conteudo : JSON.stringify(conteudo, null, 2)
  const copiar = async () => {
    try { await navigator.clipboard.writeText(texto); setCopiado(true); setTimeout(() => setCopiado(false), 1500) } catch { /* sem permissão */ }
  }
  return (
    <div className="group relative">
      <button onClick={copiar} className="absolute right-2 top-2 z-10 rounded-md bg-slate-700/80 p-1.5 text-slate-200 opacity-0 transition-opacity hover:bg-slate-600 group-hover:opacity-100" title="Copiar">
        {copiado ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
      </button>
      {linguagem && <span className="absolute left-3 top-2 text-[10px] uppercase tracking-wider text-slate-500">{linguagem}</span>}
      <pre className={clsx('rolagem overflow-auto rounded-lg bg-slate-900 p-4 text-xs leading-relaxed text-slate-100', linguagem && 'pt-7', altura)}>
        <code className="font-mono whitespace-pre-wrap break-words">{texto}</code>
      </pre>
    </div>
  )
}

export function CabecalhoPagina({ titulo, descricao, acoes }) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-slate-900">{titulo}</h1>
        {descricao && <p className="mt-1 max-w-3xl text-sm text-slate-500">{descricao}</p>}
      </div>
      {acoes && <div className="flex flex-wrap items-center gap-2">{acoes}</div>}
    </div>
  )
}

export function PontoBase({ cor, className }) {
  return <span className={clsx('inline-block h-2 w-2 shrink-0 rounded-full', className)} style={{ backgroundColor: cor }} />
}
