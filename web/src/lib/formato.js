// Rótulos, cores e formatação usados em toda a interface.

export const BASES = {
  epi: { nome: 'EPI', cor: '#d97706', classe: 'bg-amber-50 text-amber-800 ring-amber-200' },
  pausas_ergonomia: { nome: 'Pausas e Ergonomia', cor: '#2563eb', classe: 'bg-blue-50 text-blue-800 ring-blue-200' },
  saude_ocupacional: { nome: 'Saúde Ocupacional', cor: '#059669', classe: 'bg-emerald-50 text-emerald-800 ring-emerald-200' },
  direitos_beneficios: { nome: 'Direitos e Benefícios', cor: '#7c3aed', classe: 'bg-violet-50 text-violet-800 ring-violet-200' },
  procedimentos: { nome: 'Procedimentos (F3)', cor: '#64748b', classe: 'bg-slate-100 text-slate-700 ring-slate-200' },
}
export const nomeBase = (slug) => BASES[slug]?.nome ?? slug ?? '—'
export const corBase = (slug) => BASES[slug]?.cor ?? '#94a3b8'

export const STATUS = {
  OK: { rotulo: 'OK', classe: 'bg-emerald-50 text-emerald-700 ring-emerald-200', cor: '#10b981' },
  PRECISA_HUMANO: { rotulo: 'Precisa humano', classe: 'bg-amber-50 text-amber-800 ring-amber-200', cor: '#f59e0b' },
  ERRO: { rotulo: 'Erro', classe: 'bg-rose-50 text-rose-700 ring-rose-200', cor: '#f43f5e' },
}

export const MODOS = {
  llm: { rotulo: 'LLM · 1ª tentativa', tom: 'ok' },
  llm_2a_tentativa: { rotulo: 'LLM · 2ª tentativa', tom: 'alerta' },
  extrativo: { rotulo: 'Extrativo (texto da base)', tom: 'neutro' },
  cache: { rotulo: 'Cache', tom: 'neutro' },
  guardrail_injecao: { rotulo: 'Guardrail · injeção', tom: 'bloqueio' },
  guardrail_crise: { rotulo: 'Guardrail · crise', tom: 'bloqueio' },
  guardrail_emergencia: { rotulo: 'Guardrail · emergência', tom: 'bloqueio' },
  guardrail_terceiros: { rotulo: 'Guardrail · terceiros', tom: 'bloqueio' },
  fora_escopo: { rotulo: 'Fora do escopo', tom: 'neutro' },
  saudacao: { rotulo: 'Cordialidade', tom: 'marca' },
  sem_trecho: { rotulo: 'Sem trecho vigente', tom: 'alerta' },
  fixo_f6: { rotulo: 'Modelo fixo · F6', tom: 'neutro' },
  fixo_f7: { rotulo: 'Modelo fixo · F7', tom: 'neutro' },
  erro: { rotulo: 'Erro', tom: 'bloqueio' },
  idempotente: { rotulo: 'Repetida (idempotência)', tom: 'neutro' },
}
export const rotuloModo = (m) => MODOS[m]?.rotulo ?? m ?? '—'

export const TONS = {
  ok: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  alerta: 'bg-amber-50 text-amber-800 ring-amber-200',
  bloqueio: 'bg-rose-50 text-rose-700 ring-rose-200',
  neutro: 'bg-slate-100 text-slate-700 ring-slate-200',
  info: 'bg-sky-50 text-sky-700 ring-sky-200',
  marca: 'bg-marca-50 text-marca-700 ring-marca-200',
}

export const MOTIVOS_FILA = {
  feedback_negativo: { rotulo: 'Feedback negativo', tom: 'bloqueio' },
  sem_cobertura: { rotulo: 'Sem cobertura', tom: 'alerta' },
  llm_recusado: { rotulo: 'LLM recusado', tom: 'alerta' },
  erro_llm: { rotulo: 'Falha no LLM', tom: 'bloqueio' },
  guardrail: { rotulo: 'Guardrail acionado', tom: 'info' },
  baixa_confianca: { rotulo: 'Confiança baixa', tom: 'neutro' },
  baixa_fundamentacao: { rotulo: 'Pouco apoio nas fontes', tom: 'alerta' },
}

export const INTENCOES = [
  { valor: '', rotulo: 'Automática (sem intenção)' },
  { valor: 'F1', rotulo: 'F1 · Pausas e ergonomia' },
  { valor: 'F2', rotulo: 'F2 · Direitos e benefícios' },
  { valor: 'F3', rotulo: 'F3 · Procedimentos e treinamentos' },
  { valor: 'F4', rotulo: 'F4 · Saúde ocupacional' },
  { valor: 'F5', rotulo: 'F5 · EPI' },
]

const fmtDataHora = new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short' })
export const dataHora = (iso) => (iso ? fmtDataHora.format(new Date(iso)) : '—')
export const pct = (v, casas = 0) => (v === null || v === undefined ? '—' : `${(v * 100).toFixed(casas)}%`)
export const num = (v) => (v === null || v === undefined ? '—' : new Intl.NumberFormat('pt-BR').format(v))
export const ms = (v) => (v === null || v === undefined ? '—' : v >= 1000 ? `${(v / 1000).toFixed(1)} s` : `${v} ms`)
