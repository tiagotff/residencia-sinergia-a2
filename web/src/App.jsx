import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import { Botao, Cartao, Vazio } from './components/ui'
import { useApp } from './contexto'
import Atendimento from './pages/Atendimento'
import Avaliacao from './pages/Avaliacao'
import Bases from './pages/Bases'
import Configuracoes from './pages/Configuracoes'
import Interacoes from './pages/Interacoes'
import Melhoria from './pages/Melhoria'
import Painel from './pages/Painel'
import Playground from './pages/Playground'
import { api } from './api'
import { useState } from 'react'
import { DatabaseZap, PlugZap } from 'lucide-react'

function Aviso() {
  const { status, erroStatus, recarregar } = useApp()
  const [ingerindo, setIngerindo] = useState(false)
  if (erroStatus) {
    return (
      <Cartao className="mb-6"><Vazio icone={PlugZap} titulo="Não consegui falar com o backend"
        texto="Inicie o console com: python -m agente_a2.web (com o .venv ativo) e recarregue a página."
        acao={<Botao variante="secundario" onClick={recarregar}>Tentar de novo</Botao>} /></Cartao>
    )
  }
  if (status?.indice_vazio) {
    return (
      <Cartao className="mb-6"><Vazio icone={DatabaseZap} titulo="O índice das bases está vazio"
        texto="Gere os chunks e embeddings dos 4 PDFs. Na primeira vez o modelo de embeddings é baixado (~470 MB)."
        acao={<Botao carregando={ingerindo} onClick={async () => { setIngerindo(true); try { await api.ingerir(); await recarregar() } finally { setIngerindo(false) } }}>Ingerir as 4 bases agora</Botao>} /></Cartao>
    )
  }
  return null
}

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<><Aviso /><Painel /></>} />
        <Route path="/atendimento" element={<><Aviso /><Atendimento /></>} />
        <Route path="/interacoes" element={<Interacoes />} />
        <Route path="/melhoria" element={<Melhoria />} />
        <Route path="/avaliacao" element={<><Aviso /><Avaliacao /></>} />
        <Route path="/bases" element={<><Aviso /><Bases /></>} />
        <Route path="/playground" element={<><Aviso /><Playground /></>} />
        <Route path="/configuracoes" element={<Configuracoes />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
