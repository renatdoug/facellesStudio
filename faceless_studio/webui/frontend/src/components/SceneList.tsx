import { kindLabel } from '../scenes'
import type { Scene, SceneInfo } from '../types'

interface Props {
  scenes: Scene[]
  infos: SceneInfo[]
  selected: number
  onSelect: (i: number) => void
  onAdd: () => void
  onMove: (i: number, delta: number) => void
  onDuplicate: (i: number) => void
  onDelete: (i: number) => void
}

export default function SceneList({ scenes, infos, selected, onSelect, onAdd, onMove, onDuplicate, onDelete }: Props) {
  return (
    <aside className="scenes">
      <div className="panel-title"><span>Cenas</span><button className="ghost" onClick={onAdd}>+ Nova</button></div>
      <div className="scene-items">
        {scenes.map((s, i) => {
          const info = infos[i] // alinhado ao rascunho (ver App)
          return (
            <div key={i} className={'scene-item' + (i === selected ? ' on' : '')} onClick={() => onSelect(i)}>
              <div className="mini">
                {(info?.image?.url || info?.video?.thumb) ? <img src={(info.image?.url || info.video?.thumb) as string} alt="" /> : <span>{String(i + 1).padStart(2, '0')}</span>}
              </div>
              <div className="txt">
                <b>{String(i + 1).padStart(2, '0')} · {s.title || '(sem título)'}</b>
                <small>{info ? kindLabel(info.layout) : 'nova'}</small>
              </div>
              {i === selected && (
                <div className="ops" onClick={(e) => e.stopPropagation()}>
                  <button className="icon" title="Subir" disabled={i === 0} onClick={() => onMove(i, -1)}>↑</button>
                  <button className="icon" title="Descer" disabled={i === scenes.length - 1} onClick={() => onMove(i, 1)}>↓</button>
                  <button className="icon" title="Duplicar" onClick={() => onDuplicate(i)}>⧉</button>
                  <button className="icon" title="Excluir" disabled={scenes.length === 1} onClick={() => onDelete(i)}>🗑</button>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </aside>
  )
}
