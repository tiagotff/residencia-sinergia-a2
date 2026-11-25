import { Crosshair, FlaskConical, Route, Target, Undo2 } from 'lucide-react'
import { useState } from 'react'
import { api } from '../api'
import { Botao, BlocoCodigo, CabecalhoPagina, Cartao, Erro, Kpi, Vazio } from '../components/ui'
import { pct } from '../lib/formato'

export default function Avaliacao() {
  const [r, setR] = useState(null)
  const [rodando, setRodando] = useState(false)
  const [erro, setErro] = useState(null)
  const rodar = async () => {
    setRodando(true); setErro(null)
    try { setR(await api.avaliacao()) } catch (e) { setErro(e) } finally { setRodando(false) }
  }
  return (
    <>
      <CabecalhoPagina titulo="Avaliação da busca"
        descricao="Cada linha &quot;Também perguntam&quot; das bases vira uma consulta: o acerto é o ID dela voltar no topo e a base certa ser escolhida. Rode depois de mudar limiares, léxico, embeddings ou os PDFs."
        acoes={<Botao onClick={rodar} carregando={rodando} icone={FlaskConical}>Rodar avaliação</Botao>} />
      <Erro erro={erro} />
      {!r ? <Cartao><Vazio icone={FlaskConical} titulo="Nenhuma avaliação rodada nesta sessão" texto="Leva alguns segundos: são cerca de 370 consultas mais 8 perguntas fora do escopo." /></Cartao> : (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
            <Kpi rotulo="Consultas" valor={r.consultas} icone={Target} tom="neutro" />
            <Kpi rotulo="Recall@1" valor={pct(r.recall_1, 1)} icone={Crosshair} tom="marca" detalhe="ID certo em 1º" />
            <Kpi rotulo="Recall@3" valor={pct(r.recall_3, 1)} icone={Crosshair} tom="ok" detalhe="ID certo entre os 3" />
            <Kpi rotulo="Base certa" valor={pct(r.roteamento, 1)} icone={Route} tom="info" detalhe="roteamento entre as 4 bases" />
            <Kpi rotulo="Fora do escopo aceitas" valor={`${r.fora_aceitas}/${r.fora_total}`} icone={Undo2} tom={r.fora_aceitas ? 'alerta' : 'ok'} detalhe="quanto menor, melhor" />
          </div>
          <div className="mt-6 grid gap-6 xl:grid-cols-3">
            <Cartao titulo="Calibração do limiar de cosseno">
              <p className="text-sm text-slate-600">Atual: <b>{r.limiar_atual}</b> · sugerido: <b>{r.limiar_sugerido ?? '—'}</b></p>
              {r.limiar_sugerido != null && r.limiar_sugerido !== r.limiar_atual && (
                <p className="mt-2 rounded-lg bg-amber-50 p-3 text-xs text-amber-900">Para aplicar, coloque <code className="font-mono">RAG_LIMIAR_COSSENO={r.limiar_sugerido}</code> no .env e reinicie o servidor.</p>
              )}
              <div className="mt-3"><BlocoCodigo conteudo={r.calibracao} altura="max-h-60" /></div>
            </Cartao>
            <Cartao titulo="Consultas em que o ID certo ficou fora do top-3" subtitulo={`${r.erros.length} caso(s)`} className="xl:col-span-2" corpo="p-0">
              {r.erros.length === 0 ? <Vazio titulo="Nenhum erro" /> : (
                <div className="rolagem max-h-[420px] overflow-auto">
                  <table className="min-w-full text-sm">
                    <thead className="sticky top-0 bg-slate-50 text-left text-xs text-slate-500"><tr><th className="px-4 py-2">Consulta</th><th className="px-4 py-2">Esperado</th><th className="px-4 py-2">Obtido</th></tr></thead>
                    <tbody className="divide-y divide-slate-100">
                      {r.erros.map((e, i) => <tr key={i}><td className="px-4 py-2 text-slate-700">{e.consulta}</td><td className="px-4 py-2 font-mono text-xs">{e.esperado}</td><td className="px-4 py-2 font-mono text-xs text-slate-500">{e.obtido ?? 'nada (abaixo do limiar)'}</td></tr>)}
                    </tbody>
                  </table>
                </div>
              )}
            </Cartao>
          </div>
        </>
      )}
    </>
  )
}
