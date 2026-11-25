import clsx from 'clsx'
import { ArrowRight, Download, Lightbulb } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import DetalheInteracao from '../components/DetalheInteracao'
import { Botao, CabecalhoPagina, Cartao, Carregando, Erro, Interruptor, Selo, Vazio } from '../components/ui'
import { BASES, MOTIVOS_FILA, STATUS, dataHora, nomeBase, rotuloModo } from '../lib/formato'

const DICAS = {
  feedback_negativo: 'Leia a análise registrada e ajuste prompt, léxico ou base; depois marque como resolvido.',
  sem_cobertura: 'O tema é do A2 mas nenhum trecho respondeu: candidato a nova pergunta nas bases (time dos RAGs).',
  llm_recusado: 'Veja os motivos da validação: número inventado e ID inexistente costumam pedir regra mais clara no prompt.',
  erro_llm: 'Timeout ou limite do Groq. O A2 respondeu pelo texto da base; confira chave, modelo e limite de uso.',
  guardrail: 'Confirme se o bloqueio era devido. Bloqueio indevido = regra a afinar; registre como "guardrail bloqueou sem motivo".',
  baixa_confianca: 'Busca fraca: pode faltar variação "Também perguntam" ou termo no léxico da base.',
}

export default function Melhoria() {
  const [motivo, setMotivo] = useState('')
  const [resolvidas, setResolvidas] = useState(false)
  const [dados, setDados] = useState(null)
  const [erro, setErro] = useState(null)
  const [aberta, setAberta] = useState(null)

  const carregar = useCallback(() => {
    api.melhoria({ motivo: motivo || undefined, incluir_resolvidas: resolvidas || undefined }).then(setDados).catch(setErro)
  }, [motivo, resolvidas])
  useEffect(() => { carregar() }, [carregar])

  return (
    <>
      <CabecalhoPagina titulo="Fila de melhoria"
        descricao="Interações que merecem revisão: feedback negativo, perguntas sem cobertura, LLM recusado, falhas, guardrails e busca fraca. A análise registrada vira caso de teste no dataset."
        acoes={<Botao variante="secundario" icone={Download} onClick={() => api.exportar('dataset').catch(setErro)}>Dataset de avaliação (JSONL)</Botao>} />

      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        {Object.entries(MOTIVOS_FILA).map(([k, v]) => (
          <button key={k} onClick={() => setMotivo(motivo === k ? '' : k)}
            className={clsx('rounded-xl border bg-white p-4 text-left shadow-cartao transition-all',
              motivo === k ? 'border-marca-400 ring-2 ring-marca-500/20' : 'border-slate-200 hover:border-slate-300')}>
            <p className="text-xs font-medium text-slate-500">{v.rotulo}</p>
            <p className="mt-1 text-2xl font-semibold text-slate-900">{dados?.por_motivo?.[k] ?? '–'}</p>
          </button>
        ))}
      </div>

      {motivo && (
        <div className="mb-4 flex items-start gap-3 rounded-xl border border-marca-200 bg-marca-50/60 p-4 text-sm text-marca-900">
          <Lightbulb className="mt-0.5 h-4 w-4 shrink-0" />{DICAS[motivo]}
        </div>
      )}

      <Cartao titulo={motivo ? MOTIVOS_FILA[motivo].rotulo : 'Todos os itens'} subtitulo={dados ? `${dados.total} item(ns)` : ''}
        acoes={<Interruptor ligado={resolvidas} aoMudar={setResolvidas} rotulo="Mostrar resolvidas" />} corpo="p-0">
        <Erro erro={erro} />
        {!dados ? <Carregando /> : dados.itens.length === 0 ? (
          <Vazio icone={Lightbulb} titulo="Fila vazia" texto="Nada pendente com esse critério. Converse mais com o A2 ou avalie respostas no Atendimento." />
        ) : (
          <ul className="divide-y divide-slate-100">
            {dados.itens.map((i) => (
              <li key={i.id} className="flex flex-col gap-3 p-4 hover:bg-slate-50/70 md:flex-row md:items-center">
                <div className="min-w-0 flex-1">
                  <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
                    {i.motivos_fila.map((m) => <Selo key={m} tom={MOTIVOS_FILA[m]?.tom}>{MOTIVOS_FILA[m]?.rotulo}</Selo>)}
                    <span className="text-[11px] text-slate-400">#{i.id} · {dataHora(i.criado_em)}</span>
                  </div>
                  <p className="truncate text-sm font-medium text-slate-900">{i.pergunta ?? i.acao}</p>
                  <p className="truncate text-xs text-slate-500">{i.resposta}</p>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    <Selo classe={STATUS[i.status]?.classe}>{STATUS[i.status]?.rotulo}</Selo>
                    <Selo>{rotuloModo(i.modo)}</Selo>
                    {i.base && <Selo classe={BASES[i.base]?.classe}>{nomeBase(i.base)}</Selo>}
                  </div>
                </div>
                <Botao variante="secundario" tamanho="sm" onClick={() => setAberta(i.id)}>Analisar <ArrowRight className="h-3.5 w-3.5" /></Botao>
              </li>
            ))}
          </ul>
        )}
      </Cartao>

      <DetalheInteracao id={aberta} aoFechar={() => setAberta(null)} aoMudar={carregar} />
    </>
  )
}
