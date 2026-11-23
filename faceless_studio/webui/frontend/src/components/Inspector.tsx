import { useEffect, useState } from 'react'
import { KINDS, changeKind, fmtTime, hasContent } from '../scenes'
import type { LibraryItem, Scene, VideoInfo } from '../types'
import LibraryDialog from './LibraryDialog'
import { ENTRIES } from './VideoSettings'

const EMOTIONS: [string, string][] = [
  ['neutral', 'Neutra'], ['happy', 'Feliz'], ['angry', 'Brava'], ['sad', 'Triste'], ['surprised', 'Surpresa'],
  ['thinking', 'Pensando'], ['smug', 'Convencida'],
]
const GESTURES: [string, string][] = [
  ['none', 'Automático'], ['point', 'Apontar'], ['hip', 'Mãos na cintura'], ['open', 'Abrir os braços'], ['shrug', 'Dar de ombros'],
]
const CAMERAS: [string, string][] = [['auto', 'Automática'], ['wide', 'Plano aberto'], ['speaker', 'Close em quem fala']]

const MOTIONS: [string, string][] = [
  ['auto', 'Automático'], ['zoom_in', 'Aproximar'], ['zoom_out', 'Afastar'], ['pan_left', 'Deslizar ←'],
  ['pan_right', 'Deslizar →'], ['pan_up', 'Subir ↑'], ['pan_down', 'Descer ↓'], ['shake', 'Câmera na mão'],
  ['static', 'Parado'],
]

interface Props {
  scene: Scene
  layout: string
  channel: string
  video: VideoInfo | null
  narrationSeconds: number
  toonCharacters: { id: string; name: string }[]
  onChange: (scene: Scene) => void
  onPickVideo: (item: LibraryItem) => void
}

function VideoPanel({ scene, video, narrationSeconds, channel, onChange, onPickVideo }:
  Pick<Props, 'scene' | 'video' | 'narrationSeconds' | 'channel' | 'onChange' | 'onPickVideo'>) {
  const [open, setOpen] = useState(false)
  const name = typeof scene.video === 'string' ? scene.video.split(/[\/]/).pop() ?? '' : ''
  const duration = video?.duration ?? null
  const start = typeof scene.video_start === 'number' ? scene.video_start : 0
  const end = typeof scene.video_end === 'number' ? scene.video_end : duration
  const segment = end != null ? Math.max(0, end - start) : null
  const setTrim = (key: 'video_start' | 'video_end', v: string) => {
    const next = { ...scene }
    if (v === '' || Number.isNaN(Number(v))) delete next[key]
    else next[key] = Math.max(0, Number(v))
    onChange(next)
  }
  const pick = (item: LibraryItem) => {
    const { layout: _unused, ...rest } = scene // eslint-disable-line @typescript-eslint/no-unused-vars
    onChange({ ...rest, video: `assets/media/${item.name}` })
    onPickVideo(item)
    setOpen(false)
  }
  return (
    <div className="field">
      <span>Vídeo de fundo</span>
      <div className="media-card">
        <div className="media-thumb">
          {video?.thumb ? <img src={video.thumb} alt="" /> : <div className="placeholder">{name ? 'sem miniatura' : 'Nenhum vídeo'}</div>}
        </div>
        <div className="media-info">
          <b title={name}>{name || 'Escolha um vídeo'}</b>
          {duration != null && <small>{fmtTime(duration)} no total</small>}
          {name && video?.exists === false && <small className="error">Arquivo não encontrado.</small>}
          <button className="secondary" onClick={() => setOpen(true)}>{name ? 'Trocar…' : 'Escolher ou importar…'}</button>
        </div>
      </div>
      <div className="trim">
        <label className="field"><span>Começar em (s)</span>
          <input type="number" min={0} step={0.1} value={scene.video_start ?? ''} placeholder="0"
                 onChange={(e) => setTrim('video_start', e.target.value)} /></label>
        <label className="field"><span>Terminar em (s)</span>
          <input type="number" min={0} step={0.1} value={scene.video_end ?? ''} placeholder={duration != null ? String(duration) : 'fim'}
                 onChange={(e) => setTrim('video_end', e.target.value)} /></label>
      </div>
      {segment != null && segment > 0 && (
        <small className="hint">
          Trecho de {fmtTime(segment)}; narração ≈ {fmtTime(narrationSeconds)}.{' '}
          {segment + 0.25 < narrationSeconds ? 'O trecho é mais curto: ele se repete em loop.'
            : segment > narrationSeconds + 0.25 ? 'O trecho é mais longo: o que passar da narração é cortado.' : 'Duração compatível.'}
        </small>
      )}
      <small className="hint">O áudio original do vídeo é descartado; só a narração (e a trilha) tocam.</small>
      {open && <LibraryDialog channel={channel} current={name || null} onPick={pick} onClose={() => setOpen(false)} />}
    </div>
  )
}

function JsonField({ label, value, onValid }: { label: string; value: unknown; onValid: (v: unknown) => void }) {
  const pretty = JSON.stringify(value, null, 2)
  const [text, setText] = useState(pretty)
  const [error, setError] = useState('')
  useEffect(() => { setText(pretty); setError('') }, [pretty])
  return (
    <label className="field">
      <span>{label}</span>
      <textarea
        className="mono"
        rows={Math.min(14, text.split('\n').length + 1)}
        value={text}
        spellCheck={false}
        onChange={(e) => {
          setText(e.target.value)
          try { onValid(JSON.parse(e.target.value)); setError('') } catch (err) { setError(String(err)) }
        }}
      />
      {error && <small className="error">JSON inválido — não aplicado: {error}</small>}
    </label>
  )
}

function ItemsEditor({ items, onChange }: { items: Scene[]; onChange: (items: Scene[]) => void }) {
  const set = (i: number, patch: Scene) => onChange(items.map((it, j) => (j === i ? { ...it, ...patch } : it)))
  return (
    <div className="field">
      <span>Itens da lista</span>
      {items.map((it, i) => (
        <div className="item-row" key={i}>
          <input className="tiny" value={it.key ?? ''} placeholder="A" onChange={(e) => set(i, { key: e.target.value })} />
          <input value={it.text ?? ''} placeholder="Texto" onChange={(e) => set(i, { text: e.target.value })} />
          <input value={it.on_word ?? ''} placeholder="aparece em…" title="Palavra da narração em que o item surge"
                 onChange={(e) => set(i, { on_word: e.target.value })} />
          <button className="icon" title="Remover item" onClick={() => onChange(items.filter((_, j) => j !== i))}>×</button>
        </div>
      ))}
      <button className="ghost" onClick={() => onChange([...items, { key: '', text: '' }])}>+ Item</button>
    </div>
  )
}

export default function Inspector({ scene, layout, channel, video, narrationSeconds, toonCharacters, onChange, onPickVideo }: Props) {
  const patch = (p: Scene) => onChange({ ...scene, ...p })
  const setKind = (kind: string) => {
    if (kind === layout) return
    if (hasContent(scene) && !confirm('Trocar o tipo apaga o conteúdo específico do tipo atual. Continuar?')) return
    onChange(changeKind(scene, kind))
  }
  return (
    <div className="inspector">
      <h3>Cena {scene.title ? `· ${scene.title}` : ''}</h3>

      <label className="field">
        <span>Tipo de cena</span>
        <div className="kinds">
          {KINDS.filter((k) => !k.onlyWhenCurrent || k.id === layout).map((k) => (
            <button key={k.id} className={'chip' + (k.id === layout ? ' on' : '')} title={k.hint}
                    disabled={k.soon} onClick={() => setKind(k.id)}>
              {k.label}
            </button>
          ))}
        </div>
      </label>

      {Array.isArray(scene.revisar) && scene.revisar.length > 0 && (
        <div className="verify">
          <b>🔎 Para verificar antes de publicar</b>
          <ul>{scene.revisar.map((t: string, i: number) => <li key={i}>{t}</li>)}</ul>
          <button className="ghost" onClick={() => { const next = { ...scene }; delete next.revisar; onChange(next) }}>
            Marcar como verificado
          </button>
        </div>
      )}

      <label className="field">
        <span>Título (capítulo)</span>
        <input value={scene.title ?? ''} onChange={(e) => patch({ title: e.target.value })} />
      </label>
      <label className="field">
        <span>Destaque na tela</span>
        <input value={scene.headline ?? ''} placeholder="Ex.: ADMISSÃO NA UTI" onChange={(e) => patch({ headline: e.target.value })} />
      </label>
      <label className="field">
        <span>Narração <em>{String(scene.narration ?? '').split(/\s+/).filter(Boolean).length} palavras</em></span>
        <textarea rows={6} value={scene.narration ?? ''} onChange={(e) => patch({ narration: e.target.value })} />
      </label>

      {layout === 'image' && (
        <>
          <label className="field">
            <span>Descrição da imagem (prompt)</span>
            <textarea rows={4} value={scene.prompt ?? ''} onChange={(e) => {
              // apagar o texto não pode mudar o tipo da cena: sem prompt ela viraria "Cartão" e este campo sumiria
              const value = e.target.value
              const next: Scene = { ...scene, prompt: value }
              if (value.trim() === '') next.layout = 'image'
              else if (next.layout === 'image') delete next.layout
              onChange(next)
            }} />
          </label>
          <label className="check">
            <input type="checkbox" checked={!!scene.overlay_title} onChange={(e) => patch({ overlay_title: e.target.checked })} />
            Mostrar o destaque sobre a imagem
          </label>
        </>
      )}
      {layout === 'video' && (
        <>
          <VideoPanel scene={scene} video={video} narrationSeconds={narrationSeconds} channel={channel}
                      onChange={onChange} onPickVideo={onPickVideo} />
          <label className="check">
            <input type="checkbox" checked={!!scene.overlay_title} onChange={(e) => patch({ overlay_title: e.target.checked })} />
            Mostrar o destaque sobre o vídeo
          </label>
        </>
      )}
      {layout === 'toon' && (
        <>
          <label className="field"><span>Quem fala</span>
            <select value={scene.speaker ?? ''} onChange={(e) => patch({ speaker: e.target.value })}>
              {toonCharacters.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select></label>
          <div className="trim">
            <label className="field"><span>Emoção de quem fala</span>
              <select value={scene.emotion ?? 'neutral'} onChange={(e) => patch({ emotion: e.target.value })}>
                {EMOTIONS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label>
            <label className="field"><span>Reação de quem escuta</span>
              <select value={scene.reaction ?? 'neutral'} onChange={(e) => patch({ reaction: e.target.value })}>
                {EMOTIONS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label>
          </div>
          <div className="trim">
            <label className="field"><span>Gesto</span>
              <select value={scene.gesture ?? 'none'} onChange={(e) => patch({ gesture: e.target.value })}>
                {GESTURES.map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label>
            <label className="field"><span>Câmera</span>
              <select value={scene.camera ?? 'auto'} onChange={(e) => patch({ camera: e.target.value })}>
                {CAMERAS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label>
          </div>
          <small className="hint">Os bonecos são desenhados pelo programa: a boca acompanha a fala. Veja o resultado em “Prévia desta cena”.</small>
        </>
      )}
      {layout === 'list' && <ItemsEditor items={scene.items ?? []} onChange={(items) => patch({ items })} />}
      {layout === 'number' && <JsonField label="Número (JSON)" value={scene.number} onValid={(v) => patch({ number: v })} />}
      {layout === 'chart' && (
        <>
          <label className="check">
            <input type="checkbox" checked={scene.chart?.animate !== false}
                   onChange={(e) => patch({ chart: { ...scene.chart, animate: e.target.checked } })} />
            Animar o gráfico (barras crescem, linha se desenha)
          </label>
          <JsonField label="Gráfico (JSON)" value={scene.chart} onValid={(v) => patch({ chart: v })} />
        </>
      )}
      {layout === 'compare' && <JsonField label="Comparação (JSON)" value={scene.compare} onValid={(v) => patch({ compare: v })} />}
      {layout === 'quote' && <JsonField label="Citação (JSON)" value={scene.quote} onValid={(v) => patch({ quote: v })} />}

      <label className="field">
        <span>Entrada da cena</span>
        <select value={scene.transition ?? ''} onChange={(e) => {
          const next = { ...scene }
          if (e.target.value) next.transition = e.target.value
          else delete next.transition
          onChange(next)
        }}>
          <option value="">Padrão do vídeo</option>
          {ENTRIES.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
        </select>
      </label>
      {layout !== 'video' && layout !== 'toon' && (
        <label className="field">
          <span>Movimento da câmera</span>
          <select value={scene.motion ?? 'auto'} onChange={(e) => {
            const next = { ...scene }
            if (e.target.value === 'auto') delete next.motion
            else next.motion = e.target.value
            onChange(next)
          }}>
            {MOTIONS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
          </select>
        </label>
      )}
    </div>
  )
}
