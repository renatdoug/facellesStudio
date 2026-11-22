import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { fmtTime } from '../scenes'
import type { LibraryItem } from '../types'

interface Props {
  channel: string
  current: string | null // nome do arquivo hoje escolhido (para destacar)
  onPick: (item: LibraryItem) => void
  onClose: () => void
}

const mb = (n: number) => (n >= 1e9 ? `${(n / 1e9).toFixed(1)} GB` : `${Math.max(1, Math.round(n / 1e6))} MB`)

export default function LibraryDialog({ channel, current, onPick, onClose }: Props) {
  const [items, setItems] = useState<LibraryItem[] | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const input = useRef<HTMLInputElement>(null)

  const load = useCallback(async () => {
    try { setItems(await api.library(channel)) } catch (e) { setError((e as Error).message) }
  }, [channel])
  useEffect(() => { void load() }, [load])

  const importFile = async (file: File | undefined) => {
    if (!file) return
    setError('')
    setBusy(`Importando ${file.name}…`)
    try {
      const item = await api.uploadVideo(channel, file)
      onPick(item) // já escolhe o clipe recém-importado
    } catch (e) {
      setError((e as Error).message)
      setBusy('')
    }
  }

  const remove = async (item: LibraryItem) => {
    if (!confirm(`Apagar "${item.name}" da biblioteca deste canal? Cenas que usam este vídeo ficarão sem arquivo.`)) return
    try { await api.deleteVideo(channel, item.name); await load() } catch (e) { setError((e as Error).message) }
  }

  return (
    <div className="modal-back" onClick={onClose}>
      <div className="modal wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3>Biblioteca de vídeos · {channel}</h3>
          <button className="primary" disabled={!!busy} onClick={() => input.current?.click()}>Importar vídeo…</button>
          <input ref={input} type="file" hidden accept="video/*,.mkv,.mov,.m4v,.avi"
                 onChange={(e) => { void importFile(e.target.files?.[0]); e.target.value = '' }} />
        </div>
        <p className="hint">Os vídeos importados são copiados para a pasta do canal (<code>assets/media</code>) e podem ser reutilizados em qualquer roteiro dele.</p>
        {busy && <p className="hint">{busy} (arquivos grandes levam um pouco)</p>}
        {error && <p className="error">{error}</p>}
        {items === null && !error && <p className="hint">Carregando…</p>}
        {items?.length === 0 && <p className="empty">Nenhum vídeo ainda. Clique em “Importar vídeo…”.</p>}
        <div className="lib-grid">
          {items?.map((it) => (
            <figure key={it.name} className={'lib-item' + (it.name === current ? ' on' : '')}>
              <div className="lib-thumb" onClick={() => onPick(it)}>
                {it.thumb ? <img src={it.thumb} alt="" /> : <div className="placeholder">sem miniatura</div>}
                {it.duration != null && <span className="badge">{fmtTime(it.duration)}</span>}
              </div>
              <figcaption>
                <b title={it.name}>{it.name}</b>
                <small>{mb(it.size)}</small>
                <button className="icon" title="Apagar da biblioteca" onClick={() => void remove(it)}>🗑</button>
              </figcaption>
            </figure>
          ))}
        </div>
        <div className="modal-actions"><button className="ghost" onClick={onClose}>Fechar</button></div>
      </div>
    </div>
  )
}
