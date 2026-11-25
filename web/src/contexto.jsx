import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api } from './api'

// Status do backend (LLM, bases, registro) e a conversa do Atendimento,
// guardada aqui para não se perder ao trocar de tela.
const Ctx = createContext(null)

export function ProvedorApp({ children }) {
  const [status, setStatus] = useState(null)
  const [erroStatus, setErroStatus] = useState(null)
  const [conversa, setConversa] = useState([])
  const [preferencias, setPreferencias] = useState({ idColaborador: 42, intencao: '', usarLlm: true })

  const recarregar = useCallback(async () => {
    try {
      setStatus(await api.status())
      setErroStatus(null)
    } catch (e) {
      setErroStatus(e)
    }
  }, [])

  useEffect(() => { recarregar() }, [recarregar])

  return (
    <Ctx.Provider value={{ status, erroStatus, recarregar, conversa, setConversa, preferencias, setPreferencias }}>
      {children}
    </Ctx.Provider>
  )
}

export const useApp = () => useContext(Ctx)
