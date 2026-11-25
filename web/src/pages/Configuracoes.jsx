import { Bot, Database, DatabaseZap, FileText, Layers, RefreshCw, ShieldCheck, Users } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../api'
import { BlocoCodigo, Botao, CabecalhoPagina, Cartao, Carregando, Erro, Selo } from '../components/ui'
import { useApp } from '../contexto'

export default function Configuracoes() {
  const { status, recarregar } = useApp()
  const [prompt, setPrompt] = useState(null)
  const [reindexando, setReindexando] = useState(false)
  const [relatorio, setRelatorio] = useState(null)
  const [erro, setErro] = useState(null)

  useEffect(() => { api.prompt().then(setPrompt).catch(setErro) }, [])

  const reindexar = async () => {
    setReindexando(true); setErro(null)
    try { setRelatorio(await api.ingerir()); await recarregar() } catch (e) { setErro(e) } finally { setReindexando(false) }
  }
  if (!status) return <Carregando />

  const itens = [
    { icone: Bot, rotulo: 'LLM', valor: status.llm ?? 'não configurado (modo extrativo)', ok: !!status.llm, dica: 'GROQ_API_KEY e GROQ_MODELO no .env' },
    { icone: Layers, rotulo: 'Embeddings', valor: status.embeddings, ok: true, dica: 'EMBEDDINGS_PROVEDOR / EMBEDDINGS_MODELO' },
    { icone: Database, rotulo: 'Índice RAG', valor: `${status.indice} · ${status.bases.length} base(s)`, ok: !status.indice_vazio, dica: 'RAG_STORE (memoria | pgvector)' },
    { icone: DatabaseZap, rotulo: 'Banco de interações', valor: status.registro ?? 'desligado', ok: !!status.registro && status.registro_local, dica: status.registro_local === false ? 'ATENÇÃO: banco fora desta máquina' : `local · retenção ${status.retencao_dias} dias` },
    { icone: Users, rotulo: 'Cadastro', valor: status.cadastro, ok: true, dica: 'DATABASE_URL liga o cadastro real' },
    { icone: Layers, rotulo: 'RAG completo', valor: `${status.rag_reescrita ? 'reescrita + multi-consulta' : 'consulta heurística'} · ${status.rag_complemento ? 'com dica geral' : 'sem dica geral'}`, ok: status.rag_reescrita, dica: 'RAG_REESCRITA / RAG_COMPLEMENTO' },
    { icone: ShieldCheck, rotulo: 'Exigir aprovação dos documentos', valor: status.exigir_aprovacao ? 'sim' : 'não (protótipo)', ok: status.exigir_aprovacao, dica: 'RAG_EXIGIR_APROVACAO' },
  ]

  return (
    <>
      <CabecalhoPagina titulo="Configurações" descricao="Ambiente atual, prompt em uso e regras dos guardrails. Mudanças de configuração são feitas no .env (reinicie o servidor depois)."
        acoes={<Botao onClick={reindexar} carregando={reindexando} icone={RefreshCw}>Reindexar bases</Botao>} />
      <Erro erro={erro} />
      {relatorio && (
        <div className="mb-6 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900">
          {Object.entries(relatorio).map(([b, r]) => <p key={b}><b>{b}</b>: {r.status}{r.perguntas ? ` · ${r.perguntas} perguntas · v${r.versao}` : ''}</p>)}
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {itens.map((i) => (
          <div key={i.rotulo} className="flex gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-cartao">
            <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-lg ${i.ok ? 'bg-marca-50 text-marca-600' : 'bg-amber-50 text-amber-600'}`}><i.icone className="h-[18px] w-[18px]" /></span>
            <div className="min-w-0">
              <p className="text-xs font-medium text-slate-500">{i.rotulo}</p>
              <p className="truncate text-sm font-semibold text-slate-900" title={i.valor}>{i.valor}</p>
              <p className="mt-0.5 font-mono text-[11px] text-slate-400">{i.dica}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-3">
        <Cartao titulo="Limiares da busca" icone={Layers}>
          <dl className="divide-y divide-slate-100 text-sm">
            {Object.entries(status.limiares).map(([k, v]) => (
              <div key={k} className="flex justify-between py-2"><dt className="text-slate-600">{k.replaceAll('_', ' ')}</dt><dd className="font-mono">{v}</dd></div>
            ))}
            <div className="flex justify-between py-2"><dt className="text-slate-600">cache de respostas</dt><dd className="font-mono">{status.cache ? 'ligado' : 'desligado'}</dd></div>
          </dl>
        </Cartao>
        <Cartao titulo="Validações de saída" subtitulo="Rodam em toda resposta do LLM" icone={ShieldCheck} className="xl:col-span-2">
          {!prompt ? <Carregando /> : (
            <ul className="grid gap-2 sm:grid-cols-2">
              {prompt.validacoes_saida.map((v) => <li key={v} className="flex gap-2 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-700"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-marca-600" />{v}</li>)}
            </ul>
          )}
        </Cartao>
      </div>

      {prompt && (
        <div className="mt-6 grid gap-6 xl:grid-cols-2">
          <Cartao titulo="Prompt de sistema" subtitulo="O {especialista} muda conforme a base escolhida" icone={FileText} acoes={<Selo tom="marca">versão {prompt.versao}</Selo>}>
            <BlocoCodigo conteudo={prompt.system} altura="max-h-[560px]" />
            <p className="mt-3 text-xs text-slate-500">Para alterar, edite <code className="font-mono">src/agente_a2/llm/prompts.py</code>. A versão muda sozinha e o Painel compara as versões.</p>
          </Cartao>
          <Cartao titulo="Regras dos guardrails de entrada" subtitulo={`${prompt.regras_entrada.length} regras · peso ≥ 1 bloqueia`} icone={ShieldCheck} corpo="p-0">
            <div className="rolagem max-h-[620px] overflow-auto">
              <table className="min-w-full text-xs">
                <thead className="sticky top-0 bg-slate-50 text-left text-slate-500"><tr><th className="px-4 py-2">Tipo</th><th className="px-4 py-2">Regra</th><th className="px-4 py-2">Peso</th><th className="px-4 py-2">Padrão</th></tr></thead>
                <tbody className="divide-y divide-slate-100">
                  {prompt.regras_entrada.map((r) => (
                    <tr key={r.tipo + r.regra}>
                      <td className="whitespace-nowrap px-4 py-2"><Selo tom={r.tipo === 'injeção' ? 'bloqueio' : r.tipo === 'terceiros' ? 'info' : 'alerta'}>{r.tipo}</Selo></td>
                      <td className="whitespace-nowrap px-4 py-2 font-mono">{r.regra}</td>
                      <td className="px-4 py-2">{r.peso}</td>
                      <td className="max-w-[340px] truncate px-4 py-2 font-mono text-slate-500" title={r.padrao}>{r.padrao}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Cartao>
        </div>
      )}
    </>
  )
}
