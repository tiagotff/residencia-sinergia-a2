import clsx from 'clsx'
import {
  BookOpenText, Bot, ChevronsLeft, FlaskConical, Gauge, HeartPulse, History, ListTodo, Lock, Menu, MessagesSquare,
  Settings, SquareTerminal,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useApp } from '../contexto'

export const MENU = [
  { grupo: 'Operação', itens: [
    { para: '/', rotulo: 'Painel', icone: Gauge, descricao: 'Visão geral das interações' },
    { para: '/atendimento', rotulo: 'Atendimento', icone: MessagesSquare, descricao: 'Converse com o A2 e veja o raio-X' },
  ] },
  { grupo: 'Qualidade', itens: [
    { para: '/interacoes', rotulo: 'Interações', icone: History, descricao: 'Histórico gravado no banco' },
    { para: '/melhoria', rotulo: 'Fila de melhoria', icone: ListTodo, descricao: 'O que revisar no prompt e nos guardrails' },
    { para: '/avaliacao', rotulo: 'Avaliação da busca', icone: FlaskConical, descricao: 'Recall e roteamento' },
  ] },
  { grupo: 'Conhecimento', itens: [
    { para: '/bases', rotulo: 'Bases RAG', icone: BookOpenText, descricao: 'As 4 bases de conhecimento' },
    { para: '/playground', rotulo: 'TAREFA → RESULTADO', icone: SquareTerminal, descricao: 'Contrato sinergia/1' },
  ] },
  { grupo: 'Sistema', itens: [
    { para: '/configuracoes', rotulo: 'Configurações', icone: Settings, descricao: 'Prompt, guardrails e ambiente' },
  ] },
]

const lerRecolhido = () => { try { return localStorage.getItem('a2.menuRecolhido') === '1' } catch { return false } }
const gravarRecolhido = (v) => { try { localStorage.setItem('a2.menuRecolhido', v ? '1' : '0') } catch { /* sem storage */ } }

function Marca({ recolhido }) {
  return (
    <div className="flex h-16 items-center gap-3 px-4">
      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-marca-400 to-marca-700 shadow-lg shadow-marca-900/30">
        <HeartPulse className="h-5 w-5 text-white" />
      </span>
      {!recolhido && (
        <div className="leading-tight">
          <p className="text-[15px] font-semibold text-white">SinergIA</p>
          <p className="text-[11px] text-slate-400">Console do A2 · Bem-Estar</p>
        </div>
      )}
    </div>
  )
}

function Navegacao({ recolhido, aoNavegar }) {
  return (
    <nav className="rolagem flex-1 space-y-6 overflow-y-auto px-3 py-4">
      {MENU.map((g) => (
        <div key={g.grupo}>
          {!recolhido && <p className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">{g.grupo}</p>}
          <ul className="space-y-0.5">
            {g.itens.map((i) => (
              <li key={i.para}>
                <NavLink to={i.para} end={i.para === '/'} onClick={aoNavegar} title={recolhido ? i.rotulo : undefined}
                  className={({ isActive }) => clsx(
                    'group flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                    recolhido && 'justify-center px-0',
                    isActive ? 'bg-marca-500/15 text-white' : 'text-slate-400 hover:bg-white/5 hover:text-slate-100')}>
                  {({ isActive }) => (
                    <>
                      <i.icone className={clsx('h-[18px] w-[18px] shrink-0', isActive ? 'text-marca-300' : 'text-slate-500 group-hover:text-slate-300')} />
                      {!recolhido && <span className="truncate">{i.rotulo}</span>}
                    </>
                  )}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  )
}

function RodapeMenu({ recolhido }) {
  const { status, erroStatus } = useApp()
  const online = status && !erroStatus
  const itens = [
    { rotulo: 'Servidor', ok: online, valor: online ? 'local · 127.0.0.1' : 'offline' },
    { rotulo: 'LLM', ok: !!status?.llm, valor: status?.llm ? status.llm.replace('groq/', '') : 'modo extrativo' },
    { rotulo: 'Bases', ok: status && !status.indice_vazio, valor: status ? `${status.bases.length} vigentes` : '—' },
  ]
  if (recolhido) {
    return (
      <div className="flex justify-center border-t border-white/5 py-4" title={itens.map((i) => `${i.rotulo}: ${i.valor}`).join('\n')}>
        <span className={clsx('h-2.5 w-2.5 rounded-full', online ? 'bg-emerald-400' : 'bg-rose-400')} />
      </div>
    )
  }
  return (
    <div className="space-y-1.5 border-t border-white/5 px-5 py-4">
      {itens.map((i) => (
        <div key={i.rotulo} className="flex items-center justify-between gap-2 text-xs">
          <span className="flex items-center gap-2 text-slate-500">
            <span className={clsx('h-1.5 w-1.5 rounded-full', i.ok ? 'bg-emerald-400' : 'bg-amber-400')} />{i.rotulo}
          </span>
          <span className="truncate text-slate-300">{i.valor}</span>
        </div>
      ))}
      <p className="pt-2 text-[10px] text-slate-600">A2 v{status?.versao_a2 ?? '—'} · uso local · dados no banco local</p>
    </div>
  )
}

export default function Layout() {
  const [recolhido, setRecolhido] = useState(lerRecolhido)
  const [gavetaAberta, setGavetaAberta] = useState(false)
  const local = useLocation()
  const atual = MENU.flatMap((g) => g.itens).find((i) => (i.para === '/' ? local.pathname === '/' : local.pathname.startsWith(i.para)))
  const { status } = useApp()

  useEffect(() => { setGavetaAberta(false) }, [local.pathname])

  const alternar = () => {
    if (window.matchMedia('(min-width: 1024px)').matches) {
      setRecolhido((v) => { gravarRecolhido(!v); return !v })
    } else {
      setGavetaAberta((v) => !v)
    }
  }

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Menu lateral fixo (desktop) */}
      <aside className={clsx('hidden shrink-0 flex-col bg-slate-950 transition-[width] duration-200 lg:flex', recolhido ? 'w-[72px]' : 'w-64')}>
        <Marca recolhido={recolhido} />
        <Navegacao recolhido={recolhido} />
        <RodapeMenu recolhido={recolhido} />
      </aside>

      {/* Menu sanduíche (celular/tablet) */}
      {gavetaAberta && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-slate-900/50" onClick={() => setGavetaAberta(false)} />
          <aside className="relative flex h-full w-72 flex-col bg-slate-950 shadow-2xl">
            <Marca />
            <Navegacao aoNavegar={() => setGavetaAberta(false)} />
            <RodapeMenu />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-16 shrink-0 items-center gap-3 border-b border-slate-200 bg-white/90 px-4 backdrop-blur sm:px-6">
          <button onClick={alternar} className="rounded-lg p-2 text-slate-600 hover:bg-slate-100" aria-label="Abrir ou recolher o menu">
            <span className="lg:hidden"><Menu className="h-5 w-5" /></span>
            <span className="hidden lg:inline">{recolhido ? <Menu className="h-5 w-5" /> : <ChevronsLeft className="h-5 w-5" />}</span>
          </button>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-slate-900">{atual?.rotulo ?? 'Console A2'}</p>
            <p className="hidden truncate text-xs text-slate-500 sm:block">{atual?.descricao}</p>
          </div>
          <div className="hidden items-center gap-2 md:flex">
            <span className={clsx('inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset',
              status?.llm ? 'bg-marca-50 text-marca-700 ring-marca-200' : 'bg-slate-100 text-slate-600 ring-slate-200')}>
              <Bot className="h-3.5 w-3.5" /> {status?.llm ? 'LLM ativo' : 'Modo extrativo'}
            </span>
            <span title="Console acessível só por este computador; dados no banco local"
              className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600 ring-1 ring-inset ring-slate-200">
              <Lock className="h-3.5 w-3.5" /> Local
            </span>
          </div>
        </header>
        <main className="rolagem min-w-0 flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-[1500px] p-4 sm:p-6 lg:p-8">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}
