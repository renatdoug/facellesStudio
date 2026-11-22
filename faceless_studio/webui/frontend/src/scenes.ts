import type { Scene } from './types'

export const CONTENT_KEYS = ['image', 'prompt', 'video', 'video_start', 'video_end', 'items', 'number',
  'chart', 'compare', 'quote'] as const

export interface Kind { id: string; label: string; hint: string; soon?: boolean }

export const KINDS: Kind[] = [
  { id: 'image', label: 'Imagem', hint: 'Ilustração gerada por IA (ou arquivo seu)' },
  { id: 'video', label: 'Vídeo', hint: 'Clipe seu como fundo, com a narração e as legendas por cima' },
  { id: 'ai_video', label: 'Vídeo IA', hint: 'Em breve: transformar a imagem gerada em um clipe animado', soon: true },
  { id: 'list', label: 'Lista', hint: 'Itens que surgem conforme a narração' },
  { id: 'number', label: 'Número', hint: 'Valor em destaque com contagem' },
  { id: 'chart', label: 'Gráfico', hint: 'Barras ou linha' },
  { id: 'compare', label: 'Comparação', hint: 'Dois lados, antes e depois' },
  { id: 'quote', label: 'Citação', hint: 'Frase com autor' },
  { id: 'card', label: 'Cartão', hint: 'Só título e texto' },
]

export const kindLabel = (layout: string) => KINDS.find((k) => k.id === layout)?.label ?? layout

const SKELETON: Record<string, Scene> = {
  image: { prompt: 'descreva a imagem desta cena' },
  video: { layout: 'video' }, // o arquivo é escolhido depois; ao escolher, "layout" deixa de ser necessário
  list: { items: [{ key: 'A', text: 'Primeiro item' }, { key: 'B', text: 'Segundo item' }] },
  number: { number: { value: 100, label: 'descrição do número', source: '' } },
  chart: {
    chart: { type: 'bar', labels: ['A', 'B', 'C'], values: [50, 30, 20], unit: '%', highlight: 0, source: '' },
  },
  compare: {
    compare: {
      left: { title: 'Antes', items: ['Ponto 1'] },
      right: { title: 'Depois', items: ['Ponto 1'] },
    },
  },
  quote: { quote: { text: 'Escreva a citação aqui.', author: '' } },
  card: {},
}

/** Troca o tipo da cena: remove o conteúdo dos outros tipos e cria um esqueleto do novo. */
export function changeKind(scene: Scene, kind: string): Scene {
  const next: Scene = { ...scene }
  for (const key of CONTENT_KEYS) delete next[key]
  delete next.layout
  return { ...next, ...SKELETON[kind] }
}

export function hasContent(scene: Scene): boolean {
  return CONTENT_KEYS.some((k) => scene[k] !== undefined && scene[k] !== '')
}

export function newScene(existing: Scene[]): Scene {
  let n = existing.length + 1
  const ids = new Set(existing.map((s) => s.id))
  while (ids.has(`cena${n}`)) n++
  return {
    id: `cena${n}`,
    title: `Cena ${existing.length + 1}`,
    headline: '',
    narration: 'Escreva aqui a narração desta cena.',
    ...SKELETON.image,
  }
}

export function duplicateScene(scene: Scene, existing: Scene[]): Scene {
  const ids = new Set(existing.map((s) => s.id))
  let n = 2
  const base = String(scene.id ?? 'cena')
  while (ids.has(`${base}-${n}`)) n++
  return { ...JSON.parse(JSON.stringify(scene)), id: `${base}-${n}` }
}

/** Espelha layouts.detect_layout() do Python, para o rascunho ainda não salvo. */
export function detectLayout(scene: Scene): string {
  if (scene.layout) return scene.layout
  if (scene.video) return 'video'
  if (scene.image || scene.prompt) return 'image'
  for (const [key, name] of [['chart', 'chart'], ['number', 'number'], ['items', 'list'],
    ['compare', 'compare'], ['quote', 'quote']] as const) {
    if (scene[key]) return name
  }
  return 'card'
}

export const fmtTime = (s: number) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`
