import { fmtTime } from '../scenes'
import type { Scene, SceneInfo } from '../types'

interface Props {
  scenes: Scene[]
  infos: SceneInfo[]
  selected: number
  onSelect: (i: number) => void
}

/** Duração estimada por contagem de palavras; a real sai da voz (edge-tts) na renderização. */
function estimate(scene: Scene): number {
  const words = String(scene.narration ?? '').split(/\s+/).filter(Boolean).length
  return words / 2.5 + 0.8
}

export default function Timeline({ scenes, selected, onSelect }: Props) {
  const secs = scenes.map(estimate)
  const total = secs.reduce((a, b) => a + b, 0)
  return (
    <footer className="timeline">
      <div className="panel-title"><span>Linha do tempo</span><small>{scenes.length} cenas · ≈ {fmtTime(total)} (estimado)</small></div>
      <div className="track">
        {scenes.map((s, i) => (
          <div key={i} className={'clip' + (i === selected ? ' on' : '')} style={{ flexGrow: Math.max(secs[i], 2) }}
               onClick={() => onSelect(i)} title={s.narration}>
            <b>{String(i + 1).padStart(2, '0')} · {s.title}</b><small>{fmtTime(secs[i])}</small>
          </div>
        ))}
      </div>
    </footer>
  )
}
