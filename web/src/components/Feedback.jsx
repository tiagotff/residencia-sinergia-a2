import clsx from 'clsx'
import { CheckCircle2, RotateCcw, ThumbsDown, ThumbsUp } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../api'
import { BASES, dataHora } from '../lib/formato'
import { Botao, Erro, Selo } from './ui'

let cacheCategorias = null
export function useCategorias() {
  const [cats, setCats] = useState(cacheCategorias)
  useEffect(() => {
    if (!cacheCategorias) api.categorias().then((c) => { cacheCategorias = c; setCats(c) }).catch(() => {})
  }, [])
  return cats
}

// Formulário completo de análise (aba Interações e Fila de melhoria).
export function FormFeedback({ idInteracao, baseAtual, aoSalvar, inicial = 'negativo' }) {
  const cats = useCategorias()
  const [f, setF] = useState({ avaliacao: inicial, categoria: '', comentario: '', resposta_sugerida: '', base_correta: '', autor: '', situacao: 'aberto' })
  const [salvando, setSalvando] = useState(false)
  const [erro, setErro] = useState(null)
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target ? e.target.value : e }))

  const salvar = async () => {
    setSalvando(true); setErro(null)
    try {
      const corpo = Object.fromEntries(Object.entries(f).filter(([, v]) => v !== ''))
      await api.feedback(idInteracao, corpo)
      setF((x) => ({ ...x, comentario: '', resposta_sugerida: '' }))
      aoSalvar?.()
    } catch (e) { setErro(e) } finally { setSalvando(false) }
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        {[['positivo', ThumbsUp, 'Resposta boa'], ['negativo', ThumbsDown, 'Precisa melhorar']].map(([v, Icone, r]) => (
          <button key={v} onClick={() => setF((x) => ({ ...x, avaliacao: v, categoria: v === 'positivo' ? 'resposta_correta' : '' }))}
            className={clsx('flex flex-1 items-center justify-center gap-2 rounded-lg border px-3 py-2.5 text-sm font-medium transition-colors',
              f.avaliacao === v
                ? v === 'positivo' ? 'border-emerald-300 bg-emerald-50 text-emerald-700' : 'border-rose-300 bg-rose-50 text-rose-700'
                : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50')}>
            <Icone className="h-4 w-4" />{r}
          </button>
        ))}
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className="rotulo">Categoria</label>
          <select className="campo" value={f.categoria} onChange={set('categoria')}>
            <option value="">Selecione…</option>
            {cats && Object.entries(cats.categorias).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>
        <div>
          <label className="rotulo">Base que deveria responder</label>
          <select className="campo" value={f.base_correta} onChange={set('base_correta')}>
            <option value="">{baseAtual ? `Mantém (${BASES[baseAtual]?.nome ?? baseAtual})` : 'Não se aplica'}</option>
            {Object.entries(BASES).filter(([k]) => k !== 'procedimentos').map(([k, v]) => <option key={k} value={k}>{v.nome}</option>)}
          </select>
        </div>
      </div>
      {f.avaliacao === 'negativo' && (
        <div>
          <label className="rotulo">Resposta de referência (vira caso de teste no dataset)</label>
          <textarea className="campo min-h-[88px]" value={f.resposta_sugerida} onChange={set('resposta_sugerida')}
            placeholder="Como o A2 deveria ter respondido, com base nos documentos" />
        </div>
      )}
      <div>
        <label className="rotulo">Comentário / hipótese de ajuste</label>
        <textarea className="campo min-h-[72px]" value={f.comentario} onChange={set('comentario')}
          placeholder="Ex.: incluir 'vale-refeição' no léxico de Direitos; regra de injeção pegou pergunta legítima…" />
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className="rotulo">Analisado por</label>
          <input className="campo" value={f.autor} onChange={set('autor')} placeholder="Seu nome (opcional)" />
        </div>
        {f.avaliacao === 'negativo' && (
          <div>
            <label className="rotulo">Situação</label>
            <select className="campo" value={f.situacao} onChange={set('situacao')}>
              <option value="aberto">Aberto (fica na fila de melhoria)</option>
              <option value="resolvido">Resolvido</option>
            </select>
          </div>
        )}
      </div>
      <Erro erro={erro} />
      <div className="flex justify-end"><Botao onClick={salvar} carregando={salvando}>Registrar análise</Botao></div>
      <p className="text-[11px] text-slate-400">Comentários passam pelo mesmo mascaramento de CPF, CID, e-mail e telefone antes de gravar.</p>
    </div>
  )
}

export function ListaFeedbacks({ feedbacks, aoMudar }) {
  const cats = useCategorias()
  if (!feedbacks?.length) return <p className="text-sm text-slate-500">Nenhuma análise registrada.</p>
  const alternar = async (fb) => { await api.situacaoFeedback(fb.id, fb.situacao === 'aberto' ? 'resolvido' : 'aberto'); aoMudar?.() }
  return (
    <ul className="space-y-2">
      {feedbacks.map((fb) => (
        <li key={fb.id} className="rounded-lg border border-slate-200 bg-white p-3">
          <div className="flex flex-wrap items-center gap-2">
            {fb.avaliacao === 'positivo' ? <Selo tom="ok"><ThumbsUp className="h-3 w-3" />positivo</Selo> : <Selo tom="bloqueio"><ThumbsDown className="h-3 w-3" />negativo</Selo>}
            {fb.categoria && <Selo>{cats?.categorias?.[fb.categoria] ?? fb.categoria}</Selo>}
            {fb.base_correta && <Selo tom="info">base certa: {BASES[fb.base_correta]?.nome ?? fb.base_correta}</Selo>}
            <Selo tom={fb.situacao === 'resolvido' ? 'ok' : 'alerta'}>{fb.situacao}</Selo>
            <span className="ml-auto text-[11px] text-slate-400">{fb.autor ? `${fb.autor} · ` : ''}{dataHora(fb.criado_em)}</span>
          </div>
          {fb.comentario && <p className="mt-2 text-sm text-slate-700">{fb.comentario}</p>}
          {fb.resposta_sugerida && <p className="mt-2 rounded-md bg-slate-50 p-2 text-sm text-slate-700"><b className="text-xs text-slate-500">Referência: </b>{fb.resposta_sugerida}</p>}
          {fb.avaliacao === 'negativo' && (
            <button onClick={() => alternar(fb)} className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-marca-700 hover:underline">
              {fb.situacao === 'aberto' ? <><CheckCircle2 className="h-3.5 w-3.5" />Marcar como resolvido</> : <><RotateCcw className="h-3.5 w-3.5" />Reabrir</>}
            </button>
          )}
        </li>
      ))}
    </ul>
  )
}
