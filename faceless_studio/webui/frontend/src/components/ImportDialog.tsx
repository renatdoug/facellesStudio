import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { fmtTime, kindLabel } from '../scenes'
import type { Channel, ImportPreview, Issue } from '../types'

interface Props {
  channels: Channel[]
  currentChannel: string
  onImported: (channel: string, script: string) => void
  onClose: () => void
}

const ICON: Record<Issue['level'], string> = { erro: '⛔', verificar: '🔎', aviso: '⚠️' }
const LABEL: Record<Issue['level'], string> = { erro: 'vai falhar ao renderizar', verificar: 'conferir antes de publicar', aviso: 'atenção' }

function IssueList({ issues }: { issues: Issue[] }) {
  if (issues.length === 0) return null
  const count = (lv: Issue['level']) => issues.filter((i) => i.level === lv).length
  return (
    <div className="issues">
      <p className="hint">
        {(['erro', 'verificar', 'aviso'] as const).filter(count).map((lv) => `${count(lv)} ${lv === 'erro' ? 'erro(s)' : lv === 'verificar' ? 'para verificar' : 'aviso(s)'}`).join(' · ')}
      </p>
      <ul>
        {issues.map((i, k) => (
          <li key={k} className={i.level}>
            <span title={LABEL[i.level]}>{ICON[i.level]}</span>{' '}
            <b>{i.scene ? `Cena ${i.scene}` : 'Roteiro'}{i.field ? ` · ${i.field}` : ''}</b>: {i.message}
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function ImportDialog({ channels, currentChannel, onImported, onClose }: Props) {
  const [text, setText] = useState('')
  const [channel, setChannel] = useState(currentChannel || channels[0]?.name || '')
  const [name, setName] = useState('')
  const [result, setResult] = useState<ImportPreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [netError, setNetError] = useState('')
  const [guide, setGuide] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const seq = useRef(0)

  // pré-visualização ao vivo: valida enquanto você cola (com um pequeno atraso)
  useEffect(() => {
    if (!text.trim()) { setResult(null); setNetError(''); return }
    const mine = ++seq.current
    const timer = window.setTimeout(async () => {
      try {
        const r = await api.importPreview(text, channel || null)
        if (mine === seq.current) { setResult(r); setNetError('') }
      } catch (e) {
        if (mine === seq.current) setNetError((e as Error).message)
      }
    }, 400)
    return () => window.clearTimeout(timer)
  }, [text, channel])

  const copyGuide = async () => {
    try {
      const { text: g } = await api.guide()
      setGuide(g)
      try { await navigator.clipboard.writeText(g); setCopied(true); window.setTimeout(() => setCopied(false), 2500) }
      catch { setCopied(false) /* sem permissão da área de transferência: o guia fica visível para copiar à mão */ }
    } catch (e) { setNetError((e as Error).message) }
  }

  const doImport = async () => {
    setBusy(true)
    try {
      const r = await api.importScript(text, channel, name.trim() || null)
      onImported(r.channel, r.script)
    } catch (e) { setNetError((e as Error).message); setBusy(false) }
  }

  const ok = !!result?.ok && !!channel
  const s = result?.summary

  return (
    <div className="modal-back" onClick={onClose}>
      <div className="modal xwide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3>Importar roteiro de uma IA</h3>
          <button className="secondary" onClick={() => void copyGuide()}>{copied ? '✓ Guia copiado' : 'Copiar guia para a IA'}</button>
        </div>
        <p className="hint">
          1) Copie o guia e cole no Claude, ChatGPT ou Gemini junto com o seu pedido (tema, formato, duração).
          2) Cole abaixo o JSON que ele devolver. Nada é gravado até você clicar em importar.
        </p>
        {guide !== null && !copied && (
          <label className="field"><span>Não consegui copiar sozinho — selecione e copie este texto:</span>
            <textarea className="mono" rows={6} readOnly value={guide} onFocus={(e) => e.target.select()} /></label>
        )}

        <label className="field">
          <span>JSON do roteiro</span>
          <textarea className="mono big" rows={9} spellCheck={false} value={text} autoFocus
                    placeholder={'Cole aqui o que a IA respondeu (pode vir com texto em volta ou dentro de um bloco ```json).'}
                    onChange={(e) => setText(e.target.value)} />
        </label>

        <div className="import-opts">
          <label className="field"><span>Canal</span>
            <select value={channel} onChange={(e) => setChannel(e.target.value)}>
              {channels.length === 0 && <option value="">(crie um canal primeiro)</option>}
              {channels.map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
            </select>
          </label>
          <label className="field"><span>Nome do arquivo (opcional)</span>
            <input value={name} placeholder="usa o título do vídeo" onChange={(e) => setName(e.target.value)} />
          </label>
        </div>

        {netError && <p className="error">{netError}</p>}
        {result?.error && (
          <div className="import-error">
            <b>Não deu para importar:</b> {result.error.message}
          </div>
        )}
        {result?.notes.map((n, i) => <p key={i} className="hint">ℹ️ {n}</p>)}

        {s && (
          <div className="import-summary">
            <p><b>{s.title || '(sem título)'}</b> · {s.format} · legendas: {s.subtitles} · {s.scenes.length} cenas · ≈ {fmtTime(s.seconds)}</p>
            <table>
              <thead><tr><th>#</th><th>Cena</th><th>Tipo</th><th>Palavras</th><th>≈ Tempo</th><th>A conferir</th></tr></thead>
              <tbody>
                {s.scenes.map((c) => (
                  <tr key={c.index}>
                    <td>{c.index}</td><td>{c.title || c.id}</td><td>{kindLabel(c.layout)}</td><td>{c.words}</td>
                    <td>{fmtTime(c.seconds)}</td><td>{c.revisar ? `🔎 ${c.revisar}` : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {result && <IssueList issues={result.issues} />}

        <div className="modal-actions">
          <small className="hint grow">{ok ? `Cria um arquivo NOVO em “${channel}”; nada existente é alterado.` : ''}</small>
          <button className="ghost" onClick={onClose}>Cancelar</button>
          <button className="primary" disabled={!ok || busy} onClick={() => void doImport()}>Importar como novo projeto</button>
        </div>
      </div>
    </div>
  )
}
