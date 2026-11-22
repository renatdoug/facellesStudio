import { useEffect, useState } from 'react'
import { KINDS, changeKind, hasContent } from '../scenes'
import type { Scene } from '../types'

interface Props {
  scene: Scene
  layout: string
  onChange: (scene: Scene) => void
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

export default function Inspector({ scene, layout, onChange }: Props) {
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
          {KINDS.map((k) => (
            <button key={k.id} className={'chip' + (k.id === layout ? ' on' : '')} title={k.hint} onClick={() => setKind(k.id)}>
              {k.label}
            </button>
          ))}
        </div>
      </label>

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
            <textarea rows={4} value={scene.prompt ?? ''} onChange={(e) => patch({ prompt: e.target.value })} />
          </label>
          <label className="check">
            <input type="checkbox" checked={!!scene.overlay_title} onChange={(e) => patch({ overlay_title: e.target.checked })} />
            Mostrar o destaque sobre a imagem
          </label>
        </>
      )}
      {layout === 'list' && <ItemsEditor items={scene.items ?? []} onChange={(items) => patch({ items })} />}
      {layout === 'number' && <JsonField label="Número (JSON)" value={scene.number} onValid={(v) => patch({ number: v })} />}
      {layout === 'chart' && <JsonField label="Gráfico (JSON)" value={scene.chart} onValid={(v) => patch({ chart: v })} />}
      {layout === 'compare' && <JsonField label="Comparação (JSON)" value={scene.compare} onValid={(v) => patch({ compare: v })} />}
      {layout === 'quote' && <JsonField label="Citação (JSON)" value={scene.quote} onValid={(v) => patch({ quote: v })} />}

      <label className="field">
        <span>Transição de entrada</span>
        <select value={scene.transition ?? 'cut'} onChange={(e) => patch({ transition: e.target.value })}>
          <option value="cut">Corte seco</option>
          <option value="fade">Fade</option>
        </select>
      </label>
    </div>
  )
}
