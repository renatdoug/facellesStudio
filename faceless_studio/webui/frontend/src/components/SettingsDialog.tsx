import { useState } from 'react'
import { api } from '../api'

const LABELS: Record<string, string> = {
  GEMINI_API_KEY: 'Gemini (recomendado)',
  OPENAI_API_KEY: 'OpenAI',
  POLLINATIONS_API_KEY: 'Pollinations (opcional, remove a marca d’água)',
}

interface Props {
  channel: string
  keys: Record<string, string | null>
  onClose: () => void
  onSaved: (keys: Record<string, string | null>) => void
}

export default function SettingsDialog({ channel, keys, onClose, onSaved }: Props) {
  const [values, setValues] = useState<Record<string, string>>({})
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const save = async () => {
    setSaving(true)
    setError('')
    try {
      let latest = keys
      for (const [key, value] of Object.entries(values)) {
        if (value.trim()) latest = (await api.setKey(channel, key, value)).keys
      }
      onSaved(latest)
      onClose()
    } catch (e) {
      setError((e as Error).message)
      setSaving(false)
    }
  }

  return (
    <div className="modal-back" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>Chaves de API · {channel}</h3>
        <p className="hint">Ficam no arquivo <code>.env</code> da pasta do canal, só neste computador. Nunca são exibidas de volta.</p>
        {Object.keys(LABELS).map((key) => (
          <label className="field" key={key}>
            <span>{LABELS[key]} <em className={keys[key] ? 'ok' : ''}>{keys[key] ? `configurada (${keys[key]})` : 'não configurada'}</em></span>
            <input type="password" autoComplete="off" placeholder={keys[key] ? 'Deixe vazio para manter' : 'Cole a chave aqui'}
                   value={values[key] ?? ''} onChange={(e) => setValues({ ...values, [key]: e.target.value })} />
          </label>
        ))}
        {error && <p className="error">{error}</p>}
        <div className="modal-actions">
          <button className="ghost" onClick={onClose}>Cancelar</button>
          <button className="primary" disabled={saving} onClick={save}>Salvar</button>
        </div>
      </div>
    </div>
  )
}
