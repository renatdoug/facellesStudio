import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { fmtTime, kindLabel } from '../scenes'
import type { Channel, ImportPreview, Issue, TextOptions } from '../types'

interface Props {
  channels: Channel[]
  currentChannel: string
  onImported: (channel: string, script: string) => void
  onClose: () => void
}

const DEFAULT_OPTIONS: TextOptions = {
  format: 'vertical', scene_size: '', images: 'todas', provider: 'gemini', voice: 'pt-BR-FranciscaNeural', title: '',
}
const isJson = (t: string) => /^\s*(\{|```)/.test(t.replace(/^\uFEFF/, ''))
const brl = (v: number) => v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })

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
  const [opts, setOpts] = useState<TextOptions>(DEFAULT_OPTIONS)
  const [showGuide, setShowGuide] = useState(false)
  const seq = useRef(0)
  const asText = text.trim() !== '' && !isJson(text)
  const setOpt = <K extends keyof TextOptions>(k: K, v: TextOptions[K]) => setOpts((o) => ({ ...o, [k]: v }))

  // pré-visualização ao vivo: valida enquanto você cola (com um pequeno atraso)
  useEffect(() => {
    if (!text.trim()) { setResult(null); setNetError(''); return }
    const mine = ++seq.current
    const timer = window.setTimeout(async () => {
      try {
        const r = await api.importPreview(text, channel || null, asText ? opts : null)
        if (mine === seq.current) { setResult(r); setNetError('') }
      } catch (e) {
        if (mine === seq.current) setNetError((e as Error).message)
      }
    }, 400)
    return () => window.clearTimeout(timer)
  }, [text, channel, opts, asText])

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
      const r = await api.importScript(text, channel, name.trim() || null, asText ? opts : null)
      onImported(r.channel, r.script)
    } catch (e) { setNetError((e as Error).message); setBusy(false) }
  }

  const ok = !!result?.ok && !!channel
  const s = result?.summary

  return (
    <div className="modal-back" onClick={onClose}>
      <div className="modal xwide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3>Importar roteiro</h3>
          <button className="ghost" onClick={() => setShowGuide((v) => !v)}>{showGuide ? 'Ocultar' : 'Prefere que uma IA escreva o roteiro?'}</button>
        </div>
        <p className="hint">
          <b>Cole o seu roteiro em texto</b>: cada parágrafo (separado por uma linha em branco) vira uma cena. Primeira linha
          <code>Título: ...</code> define o título; linhas que começam com <code>Fonte:</code> não são narradas.
          Nada é gravado até você clicar em importar.
        </p>
        {showGuide && (
          <div className="guide-box">
            <p className="hint">
              Copie o guia, cole no Claude, ChatGPT ou Gemini junto com o seu pedido (tema, formato, duração, <b>e os seus
              dados com a fonte</b>) e cole abaixo o JSON que ele devolver.
            </p>
            <button className="secondary" onClick={() => void copyGuide()}>{copied ? '✓ Guia copiado' : 'Copiar guia para a IA'}</button>
          </div>
        )}
        {guide !== null && !copied && showGuide && (
          <label className="field"><span>Não consegui copiar sozinho — selecione e copie este texto:</span>
            <textarea className="mono" rows={6} readOnly value={guide} onFocus={(e) => e.target.select()} /></label>
        )}

        <label className="field">
          <span>Roteiro {asText ? '(texto simples)' : text.trim() ? '(JSON)' : '(texto ou JSON)'}</span>
          <textarea className={'big' + (asText ? '' : ' mono')} rows={9} spellCheck={asText} value={text} autoFocus
                    placeholder={'Cole aqui o seu roteiro.\n\nUm parágrafo por cena (linha em branco entre eles).\n\nOu o JSON que uma IA devolveu.'}
                    onChange={(e) => setText(e.target.value)} />
        </label>

        {asText && (
          <div className="text-opts">
            <label className="field"><span>Formato</span>
              <select value={opts.format} onChange={(e) => setOpt('format', e.target.value as TextOptions['format'])}>
                <option value="vertical">Vertical 9:16 (Shorts)</option>
                <option value="horizontal">Horizontal 16:9</option>
                <option value="square">Quadrado 1:1</option>
              </select></label>
            <label className="field"><span>Tamanho das cenas</span>
              <select value={opts.scene_size} onChange={(e) => setOpt('scene_size', e.target.value as TextOptions['scene_size'])}>
                <option value="">Automático (curtas no vertical)</option>
                <option value="curta">Curtas (~14 palavras)</option>
                <option value="media">Médias (~24 palavras)</option>
                <option value="longa">Longas (~45 palavras)</option>
              </select></label>
            <label className="field"><span>Imagens de IA</span>
              <select value={opts.images} onChange={(e) => setOpt('images', e.target.value as TextOptions['images'])}>
                <option value="todas">Uma imagem por cena</option>
                <option value="nenhuma">Nenhuma (só texto na tela)</option>
              </select></label>
            <label className="field"><span>Gerador de imagens</span>
              <select value={opts.provider} onChange={(e) => setOpt('provider', e.target.value)}>
                <option value="gemini">Gemini</option><option value="openai">OpenAI</option>
                <option value="pollinations">Pollinations (grátis)</option>
              </select></label>
            <label className="field"><span>Voz</span>
              <select value={opts.voice} onChange={(e) => setOpt('voice', e.target.value)}>
                <option value="pt-BR-FranciscaNeural">Francisca (feminina)</option>
                <option value="pt-BR-AntonioNeural">Antonio (masculina)</option>
              </select></label>
            <label className="field"><span>Título do vídeo (opcional)</span>
              <input value={opts.title} placeholder="usa a linha “Título:” ou o início do texto"
                     onChange={(e) => setOpt('title', e.target.value)} /></label>
          </div>
        )}

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
            {s.images > 0 && (
              <p className="cost">
                🖼️ {s.images} imagem(ns) de IA ({s.provider})
                {s.cost_brl != null && <> ≈ <b>{brl(s.cost_brl)}</b> <span className="hint">(estimativa: R$ 0,62 por imagem, pelo seu teste de 22/11/2026)</span></>}
                . Elas só são geradas quando você clicar em “Gerar imagens”.
              </p>
            )}
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
