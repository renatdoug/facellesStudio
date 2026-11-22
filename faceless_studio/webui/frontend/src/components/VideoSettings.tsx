import type { Script } from '../types'

export const FORMATS: { id: string; label: string; hint: string }[] = [
  { id: '1920x1080', label: 'Horizontal 16:9 (YouTube)', hint: '1920x1080' },
  { id: '1080x1920', label: 'Vertical 9:16 (Shorts, Reels, TikTok)', hint: '1080x1920' },
  { id: '1080x1080', label: 'Quadrado 1:1', hint: '1080x1080' },
]

export const CAPTIONS: [string, string][] = [
  ['karaoke', 'Karaokê (padrão)'],
  ['pop', 'Pop — blocos grandes que saltam'],
  ['box', 'Caixa colorida'],
  ['simple', 'Simples'],
  ['off', 'Sem legenda'],
]

export const PAUSES: [string, string][] = [
  ['0', 'Sem pausa (0 s)'], ['0.1', 'Curta (0,1 s) — Shorts rápidos'], ['0.2', 'Normal (0,2 s)'],
  ['0.4', 'Longa (0,4 s) — vídeos calmos'],
]

export const ENTRIES: [string, string][] = [
  ['cut', 'Corte seco'],
  ['fade', 'Fade'],
  ['punch', 'Punch (zoom rápido)'],
  ['flash', 'Flash (clarão branco)'],
]

/** "1080x1920" -> "1080 / 1920" para usar em aspect-ratio. */
export function aspectOf(resolution: unknown): string {
  const m = /^(\d+)x(\d+)$/i.exec(String(resolution ?? ''))
  return m ? `${m[1]} / ${m[2]}` : '16 / 9'
}

interface Props {
  script: Script
  onChange: (patch: Record<string, unknown>) => void
}

export default function VideoSettings({ script, onChange }: Props) {
  const resolution = String(script.resolution ?? '1920x1080')
  const known = FORMATS.some((f) => f.id === resolution)
  return (
    <details className="options">
      <summary>Vídeo</summary>
      <div className="popover">
        <label className="field"><span>Formato</span>
          <select value={resolution} onChange={(e) => onChange({ resolution: e.target.value })}>
            {!known && <option value={resolution}>Personalizado ({resolution})</option>}
            {FORMATS.map((f) => <option key={f.id} value={f.id}>{f.label}</option>)}
          </select>
        </label>
        <small className="hint">Trocar o formato gera as imagens de novo no tamanho certo (as antigas ficam no cache).</small>
        <label className="field"><span>Legendas</span>
          <select value={script.subtitles ?? 'karaoke'} onChange={(e) => onChange({ subtitles: e.target.value })}>
            {CAPTIONS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
          </select>
        </label>
        <label className="field"><span>Entrada padrão das cenas</span>
          <select value={script.default_transition ?? 'cut'} onChange={(e) => onChange({ default_transition: e.target.value })}>
            {ENTRIES.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
          </select>
        </label>
        <small className="hint">Cada cena pode ter a sua própria entrada no painel da direita.</small>
        <label className="field"><span>Pausa entre as cenas</span>
          <select value={String(script.pause ?? 0.2)} onChange={(e) => onChange({ pause: Number(e.target.value) })}>
            {PAUSES.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
            {!PAUSES.some(([v]) => Number(v) === Number(script.pause ?? 0.2)) && <option value={String(script.pause)}>{script.pause} s</option>}
          </select>
        </label>
      </div>
    </details>
  )
}
