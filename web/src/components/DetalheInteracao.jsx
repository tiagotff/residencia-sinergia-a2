import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { BASES, MOTIVOS_FILA, STATUS, dataHora, ms, nomeBase, pct, rotuloModo } from '../lib/formato'
import { FormFeedback, ListaFeedbacks } from './Feedback'
import RaioX from './RaioX'
import { Cartao, Carregando, Erro, Gaveta, Selo } from './ui'

export default function DetalheInteracao({ id, aoFechar, aoMudar }) {
  const [d, setD] = useState(null)
  const [erro, setErro] = useState(null)
  const carregar = useCallback(() => {
    if (!id) return
    api.interacao(id).then(setD).catch(setErro)
  }, [id])
  useEffect(() => { setD(null); setErro(null); carregar() }, [carregar])
  const atualizado = () => { carregar(); aoMudar?.() }

  return (
    <Gaveta aberta={!!id} aoFechar={aoFechar} titulo={`Interação #${id ?? ''}`}
      subtitulo={d ? `${dataHora(d.criado_em)} · ${d.acao} · origem ${d.origem} · colaborador ${d.colaborador ?? '—'} (pseudônimo)` : ''}>
      <Erro erro={erro} />
      {!d && !erro && <Carregando />}
      {d && (
        <div className="space-y-5">
          <div className="flex flex-wrap gap-2">
            <Selo classe={STATUS[d.status]?.classe}>{STATUS[d.status]?.rotulo ?? d.status}</Selo>
            <Selo>{rotuloModo(d.modo)}</Selo>
            {d.base && <Selo classe={BASES[d.base]?.classe}>{nomeBase(d.base)}</Selo>}
            {d.confianca != null && <Selo tom="info">confiança {pct(d.confianca)}</Selo>}
            <Selo>{ms(d.latencia_ms)}</Selo>
            {d.versao_prompt && <Selo tom="marca">prompt {d.versao_prompt}</Selo>}
            {d.motivos_fila.map((m) => <Selo key={m} tom={MOTIVOS_FILA[m]?.tom}>{MOTIVOS_FILA[m]?.rotulo ?? m}</Selo>)}
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Cartao titulo="Pergunta (mascarada)" corpo="p-4">
              <p className="whitespace-pre-wrap text-sm text-slate-800">{d.pergunta ?? '— (ação sem pergunta)'}</p>
              {d.intencao && <p className="mt-2 text-xs text-slate-500">Intenção enviada: {d.intencao}</p>}
            </Cartao>
            <Cartao titulo="Resposta do A2" corpo="p-4">
              <p className="whitespace-pre-wrap text-sm text-slate-800">{d.resposta ?? '—'}</p>
              {d.ids_trechos?.length > 0 && <p className="mt-2 text-xs text-slate-500">Fontes: {d.ids_trechos.join(', ')}</p>}
            </Cartao>
          </div>

          <Cartao titulo="Raio-X" subtitulo="Como o A2 chegou nessa resposta">
            <RaioX tarefa={d.tarefa} resultado={d.resultado} telemetria={d.telemetria} latencia={d.latencia_ms} />
          </Cartao>

          <div className="grid gap-4 lg:grid-cols-2">
            <Cartao titulo="Registrar análise"><FormFeedback idInteracao={d.id} baseAtual={d.base} aoSalvar={atualizado} /></Cartao>
            <Cartao titulo="Análises anteriores"><ListaFeedbacks feedbacks={d.feedbacks} aoMudar={atualizado} /></Cartao>
          </div>
        </div>
      )}
    </Gaveta>
  )
}
