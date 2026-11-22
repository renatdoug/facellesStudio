import { fmtTime, kindLabel } from '../scenes'
import type { FileInfo, Scene, SceneInfo } from '../types'

export type View = 'scene' | 'gallery' | 'preview' | 'final'

interface Props {
  view: View
  setView: (v: View) => void
  scene: Scene | undefined
  info: SceneInfo | undefined
  scenes: Scene[]
  infos: SceneInfo[]
  preview: FileInfo | null
  scenePreview: FileInfo | null
  previewKind: 'general' | 'scene'
  setPreviewKind: (k: 'general' | 'scene') => void
  final: FileInfo | null
  busy: boolean
  onScenePreview: (index: number) => void
  onRegen: (index: number) => void
  onSelect: (index: number) => void
}

function Summary({ scene, layout }: { scene: Scene; layout: string }) {
  if (layout === 'list')
    return <ul className="summary">{(scene.items ?? []).map((it: Scene, i: number) => <li key={i}><b>{it.key}</b> {it.text}</li>)}</ul>
  if (layout === 'number')
    return <div className="summary big">{scene.number?.value}<small>{scene.number?.label}</small></div>
  if (layout === 'chart')
    return <div className="summary">{(scene.chart?.labels ?? []).map((l: string, i: number) => {
      const v = scene.chart?.values?.[i] ?? scene.chart?.series?.[0]?.values?.[i] ?? 0
      const max = Math.max(...(scene.chart?.values ?? scene.chart?.series?.[0]?.values ?? [1]), 1)
      return <div className="bar" key={i}><span>{l}</span><i style={{ width: `${(v / max) * 100}%` }} /><em>{v}</em></div>
    })}</div>
  if (layout === 'compare')
    return <div className="summary two"><div><b>{scene.compare?.left?.title}</b>{(scene.compare?.left?.items ?? []).map((t: string, i: number) => <p key={i}>{t}</p>)}</div>
      <div><b>{scene.compare?.right?.title}</b>{(scene.compare?.right?.items ?? []).map((t: string, i: number) => <p key={i}>{t}</p>)}</div></div>
  if (layout === 'quote')
    return <blockquote className="summary">“{scene.quote?.text}”<footer>{scene.quote?.author}</footer></blockquote>
  return null
}

export default function Stage(p: Props) {
  const tabs: [View, string][] = [['scene', 'Cena'], ['gallery', 'Galeria'], ['preview', 'Prévia'], ['final', 'Vídeo final']]
  return (
    <section className="stage">
      <div className="tabs">
        {tabs.map(([id, label]) => (
          <button key={id} className={'tab' + (p.view === id ? ' on' : '')} onClick={() => p.setView(id)}>{label}</button>
        ))}
      </div>

      {p.view === 'scene' && p.scene && p.info && (
        <div className="canvas-wrap">
          <div className="canvas">
            {p.info.layout === 'video'
              ? (p.info.video?.url
                ? <video key={p.info.video.url + (p.scene.video_start ?? 0)} src={`${p.info.video.url}#t=${p.scene.video_start ?? 0}`}
                         muted loop controls playsInline />
                : <div className="placeholder">{p.scene.video ? 'Pré-visualização indisponível (salve para conferir)' : 'Escolha um vídeo no painel à direita'}</div>)
              : p.info.image?.url ? <img src={p.info.image.url} alt="" />
                : <div className="placeholder">{p.info.layout === 'image' ? 'Imagem ainda não gerada' : kindLabel(p.info.layout)}</div>}
            {p.info.layout !== 'image' && p.info.layout !== 'video' && <Summary scene={p.scene} layout={p.info.layout} />}
            {p.scene.headline && p.info.layout !== 'video' && <div className="headline">{p.scene.headline}</div>}
            {p.info.image?.stale && <div className="badge warn">Prompt alterado — gere de novo</div>}
          </div>
          <div className="caption">
            <p>{p.scene.narration}</p>
            <div className="meta">
              <span>{kindLabel(p.info.layout)}</span><span>≈ {fmtTime(p.info.seconds)}</span>
              <button className="ghost" disabled={p.busy} onClick={() => p.onScenePreview(p.info!.index)}
                      title="Renderiza só esta cena em 720p, com legendas e narração">▶ Prévia desta cena</button>
              {p.info.layout === 'image' && !p.scene.image && (
                <button className="ghost" disabled={p.busy} onClick={() => p.onRegen(p.info!.index)}>
                  {p.info.image ? 'Gerar imagem de novo' : 'Gerar imagem'}
                </button>
              )}
            </div>
            <small className="hint">Esquema da cena — o visual final (animações, gráficos, legendas) é produzido na prévia e no vídeo.</small>
          </div>
        </div>
      )}

      {p.view === 'gallery' && (
        <div className="gallery">
          {p.infos.filter((i) => i.layout === 'image').length === 0 && <p className="empty">Nenhuma cena deste roteiro usa imagem.</p>}
          {p.infos.filter((i) => i.layout === 'image').map((i) => (
            <figure key={i.index}>
              <div className="thumb" onClick={() => p.onSelect(i.index - 1)}>
                {i.image?.url ? <img src={i.image.url} alt="" /> : <div className="placeholder">sem imagem</div>}
                {i.image?.stale && <div className="badge warn">desatualizada</div>}
              </div>
              <figcaption>
                <b>{String(i.index).padStart(2, '0')} · {p.scenes[i.index - 1]?.title}</b>
                <small>{i.image?.provider ?? (p.scenes[i.index - 1]?.image ? 'arquivo próprio' : '—')}</small>
                {!p.scenes[i.index - 1]?.image &&
                  <button className="ghost" disabled={p.busy} onClick={() => p.onRegen(i.index)}>
                    {i.image ? 'Gerar de novo' : 'Gerar'}
                  </button>}
              </figcaption>
            </figure>
          ))}
        </div>
      )}

      {p.view === 'preview' && (
        <>
          {p.preview && p.scenePreview && (
            <div className="tabs sub">
              <button className={'tab' + (p.previewKind === 'general' ? ' on' : '')} onClick={() => p.setPreviewKind('general')}>Prévia de 2 cenas</button>
              <button className={'tab' + (p.previewKind === 'scene' ? ' on' : '')} onClick={() => p.setPreviewKind('scene')}>Cena {p.info?.index}</button>
            </div>
          )}
          {(() => {
            const file = p.scenePreview && (p.previewKind === 'scene' || !p.preview) ? p.scenePreview : p.preview
            return file
              ? <div className="player"><video key={file.url} src={file.url} controls /></div>
              : <p className="empty">Ainda não há prévia. Use “Prévia de 2 cenas” ou “Prévia desta cena”.</p>
          })()}
        </>
      )}
      {p.view === 'final' && (p.final
        ? <div className="player"><video key={p.final.url} src={p.final.url} controls /></div>
        : <p className="empty">Ainda não há vídeo final. Use “Gerar vídeo”.</p>)}
    </section>
  )
}
