// Cliente do backend local do Console A2. Toda chamada leva o token de sessão
// (X-A2-Token), entregue só a esta página. Em dev, o Vite faz proxy de /api para :8000.

let token = null

async function obterToken(renovar = false) {
  if (token && !renovar) return token
  const r = await fetch('/api/sessao', { credentials: 'same-origin', cache: 'no-store' })
  if (!r.ok) throw new Error(`${r.status} · não foi possível abrir a sessão`)
  token = (await r.json()).token
  return token
}

async function chamar(caminho, opcoes = {}, tentativa = 0) {
  const r = await fetch(caminho, {
    ...opcoes,
    credentials: 'same-origin',
    cache: 'no-store',
    headers: { 'Content-Type': 'application/json', 'X-A2-Token': await obterToken(), ...(opcoes.headers || {}) },
    body: opcoes.body !== undefined ? JSON.stringify(opcoes.body) : undefined,
  })
  // Servidor reiniciado = token novo: renova uma vez e repete.
  if (r.status === 401 && tentativa === 0) {
    await obterToken(true)
    return chamar(caminho, opcoes, 1)
  }
  return r
}

async function req(caminho, opcoes = {}) {
  const r = await chamar(caminho, opcoes)
  if (!r.ok) {
    let msg = r.statusText
    try {
      const j = await r.json()
      msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail ?? j)
    } catch { /* corpo não é JSON */ }
    throw new Error(`${r.status} · ${msg}`)
  }
  return r.json()
}

const qs = (params) => {
  const p = new URLSearchParams()
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') p.set(k, v)
  })
  const s = p.toString()
  return s ? `?${s}` : ''
}

export const api = {
  status: () => req('/api/status'),
  ingerir: () => req('/api/ingerir', { method: 'POST' }),
  prompt: () => req('/api/prompt'),
  colaboradores: () => req('/api/colaboradores'),
  chat: (corpo) => req('/api/chat', { method: 'POST', body: corpo }),
  interacoes: (filtros) => req(`/api/interacoes${qs(filtros)}`),
  interacao: (id) => req(`/api/interacoes/${id}`),
  feedback: (id, corpo) => req(`/api/interacoes/${id}/feedback`, { method: 'POST', body: corpo }),
  situacaoFeedback: (id, situacao) => req(`/api/feedback/${id}`, { method: 'PATCH', body: { situacao } }),
  categorias: () => req('/api/feedback/categorias'),
  melhoria: (filtros) => req(`/api/melhoria${qs(filtros)}`),
  metricas: (dias) => req(`/api/metricas${qs({ dias })}`),
  bases: () => req('/api/bases'),
  perguntas: (slug) => req(`/api/bases/${slug}/perguntas`),
  fixtures: () => req('/api/fixtures'),
  playground: (corpo) => req('/api/playground', { method: 'POST', body: corpo }),
  avaliacao: () => req('/api/avaliacao', { method: 'POST' }),
  // Download com o token no cabeçalho (link direto não levaria o token).
  exportar: async (formato, filtros) => {
    const r = await chamar(`/api/exportar${qs({ formato, ...filtros })}`)
    if (!r.ok) throw new Error(`${r.status} · falha ao exportar`)
    const nome = (r.headers.get('Content-Disposition') || '').match(/filename="([^"]+)"/)?.[1] || `a2_${formato}`
    const url = URL.createObjectURL(await r.blob())
    const a = document.createElement('a')
    a.href = url; a.download = nome; document.body.appendChild(a); a.click(); a.remove()
    setTimeout(() => URL.revokeObjectURL(url), 2000)
  },
}
