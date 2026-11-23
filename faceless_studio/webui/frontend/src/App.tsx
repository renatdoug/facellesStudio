import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from './api'
import ImportDialog from './components/ImportDialog'
import Inspector from './components/Inspector'
import SceneList from './components/SceneList'
import SettingsDialog from './components/SettingsDialog'
import Sidebar from './components/Sidebar'
import Stage, { type View } from './components/Stage'
import Timeline from './components/Timeline'
import VideoSettings, { aspectOf } from './components/VideoSettings'
import { detectLayout, duplicateScene, fmtTime, newScene } from './scenes'
import type { Channel, Job, LibraryItem, Meta, SceneInfo, Script, ScriptState, VideoInfo } from './types'

const KEY_FOR: Record<string, [string, string]> = {
  gemini: ['GEMINI_API_KEY', 'Gemini'],
  openai: ['OPENAI_API_KEY', 'OpenAI'],
}
const MODE_LABEL = { images: 'imagens', preview: 'prévia', render: 'vídeo', scene: 'prévia da cena' } as const

const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v))
const remember = (k: string, v: string) => {
  try { localStorage.setItem(k, v) } catch { /* sem armazenamento */ }
}
const recall = (k: string) => { try { return localStorage.getItem(k) } catch { return null } }

export default function App() {
  const [meta, setMeta] = useState<Meta | null>(null)
  const [channels, setChannels] = useState<Channel[]>([])
  const [channel, setChannel] = useState('')
  const [scriptName, setScriptName] = useState('')
  const [state, setState] = useState<ScriptState | null>(null)
  const [draft, setDraft] = useState<Script | null>(null)
  const [baseline, setBaseline] = useState('')
  const [selected, setSelected] = useState(0)
  const [view, setView] = useState<View>('scene')
  const [previewKind, setPreviewKind] = useState<'general' | 'scene'>('general')
  const [picked, setPicked] = useState<Record<string, LibraryItem>>({}) // vídeos escolhidos e ainda não salvos
  const [job, setJob] = useState<Job | null>(null)
  const [logs, setLogs] = useState<string[]>([])
  const [showLog, setShowLog] = useState(false)
  const [polling, setPolling] = useState(false)
  const [provider, setProvider] = useState('')
  const [strict, setStrict] = useState(true)
  const [noVoice, setNoVoice] = useState(false)
  const [toast, setToast] = useState<{ text: string; kind: 'ok' | 'err' } | null>(null)
  const [settings, setSettings] = useState(false)
  const [importing, setImporting] = useState(false)
  const offset = useRef(0)
  const logRef = useRef<HTMLPreElement>(null)

  const notify = useCallback((text: string, kind: 'ok' | 'err' = 'ok') => {
    setToast({ text, kind })
    window.setTimeout(() => setToast((t) => (t?.text === text ? null : t)), kind === 'err' ? 7000 : 3000)
  }, [])

  const dirty = !!draft && JSON.stringify(draft) !== baseline
  const busy = job?.status === 'running'

  // ------------------------------------------------------------ carregamento
  const loadState = useCallback(async (ch: string, sc: string) => {
    const s = await api.state(ch, sc)
    setState(s)
    setDraft(clone(s.script))
    setBaseline(JSON.stringify(s.script))
    return s
  }, [])

  const refreshChannels = useCallback(async () => {
    const list = await api.channels()
    setChannels(list)
    return list
  }, [])

  useEffect(() => {
    (async () => {
      try {
        setMeta(await api.meta())
        const list = await refreshChannels()
        const savedCh = recall('channel'), savedSc = recall('script')
        const ch = list.find((c) => c.name === savedCh) ?? list[0]
        if (ch) {
          const sc = ch.scripts.includes(savedSc ?? '') ? savedSc! : ch.scripts[0]
          if (sc) { setChannel(ch.name); setScriptName(sc); await loadState(ch.name, sc) }
        }
        const running = await api.job(0)
        if (running) {
          offset.current = running.offset
          setJob(running)
          setLogs(running.lines)
          if (running.status === 'running') setPolling(true)
        }
      } catch (e) { notify((e as Error).message, 'err') }
    })()
  }, [loadState, refreshChannels, notify])

  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => { if (dirty) e.preventDefault() }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  // ------------------------------------------------------------ acompanhamento da produção
  useEffect(() => {
    if (!polling) return
    const timer = window.setInterval(async () => {
      try {
        const snap = await api.job(offset.current)
        if (!snap) return
        offset.current = snap.offset
        if (snap.lines.length) setLogs((l) => [...l, ...snap.lines])
        setJob(snap)
        if (snap.status !== 'running') {
          setPolling(false)
          if (snap.channel === channel && snap.script === scriptName) {
            const s = await api.state(snap.channel, snap.script)
            setState(s) // não mexe no rascunho: só atualiza imagens e arquivos gerados
            if (snap.status === 'done') {
              setView(snap.mode === 'images' ? 'gallery' : snap.mode === 'render' ? 'final' : 'preview')
              if (snap.mode === 'scene') setPreviewKind('scene')
              if (snap.mode === 'preview') setPreviewKind('general')
            }
          }
          notify(snap.status === 'done' ? `Pronto: ${MODE_LABEL[snap.mode]} concluído.`
            : snap.status === 'cancelled' ? 'Produção cancelada.' : 'A produção terminou com erro — veja o log.',
          snap.status === 'done' ? 'ok' : 'err')
          if (snap.status === 'error') setShowLog(true)
        }
      } catch { /* servidor momentaneamente ocupado: tenta no próximo ciclo */ }
    }, 800)
    return () => window.clearInterval(timer)
  }, [polling, channel, scriptName, notify])

  useEffect(() => { logRef.current?.scrollTo(0, logRef.current.scrollHeight) }, [logs, showLog])

  // ------------------------------------------------------------ ações
  const save = useCallback(async () => {
    if (!draft) return false
    try {
      await api.save(channel, scriptName, draft)
      await loadState(channel, scriptName)
      notify('Roteiro salvo.')
      return true
    } catch (e) { notify((e as Error).message, 'err'); return false }
  }, [draft, channel, scriptName, loadState, notify])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); if (dirty) void save() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [dirty, save])

  const pick = async (ch: string, sc: string) => {
    if (dirty && !confirm('Há alterações não salvas neste roteiro. Descartar?')) return
    try {
      setChannel(ch); setScriptName(sc); setSelected(0); setView('scene')
      remember('channel', ch); remember('script', sc)
      await loadState(ch, sc)
    } catch (e) { notify((e as Error).message, 'err') }
  }

  const newChannel = async () => {
    const name = prompt('Nome do canal (letras sem acento, números e hífen):')
    if (!name) return
    try {
      const created = await api.createChannel(name)
      await refreshChannels()
      await pick(created.name, created.scripts[0])
    } catch (e) { notify((e as Error).message, 'err') }
  }

  const newScript = async () => {
    const name = prompt('Nome do novo roteiro (ex.: episodio-02):')
    if (!name) return
    try {
      const { script } = await api.createScript(channel, name)
      await refreshChannels()
      await pick(channel, script)
    } catch (e) { notify((e as Error).message, 'err') }
  }

  const run = async (mode: 'images' | 'preview' | 'render' | 'scene', regen = '', sceneNo?: number) => {
    if (!draft || busy) return
    if (dirty && !(await save())) return
    try {
      await api.startJob({ channel, script: scriptName, mode, provider: provider || null, regen, strict, no_voice: noVoice, scene: sceneNo ?? null })
      offset.current = 0
      setLogs([])
      setJob(null)
      setPolling(true)
      setJob(await api.job(0))
    } catch (e) { notify((e as Error).message, 'err') }
  }

  const cancel = async () => {
    if (confirm('Interromper a produção em andamento?')) await api.cancel()
  }

  const setVideoOptions = (patch: Record<string, unknown>) => edit((d) => { Object.assign(d, patch) })

  const edit = (fn: (d: Script) => void) => setDraft((d) => { if (!d) return d; const c = clone(d); fn(c); return c })

  // ------------------------------------------------------------ derivados
  const infos: SceneInfo[] = useMemo(() => {
    if (!draft) return []
    return draft.scenes.map((s, i) => {
      const id = String(s.id || String(i + 1).padStart(2, '0'))
      const server = state?.scenes.find((x) => x.id === id)
      const layout = detectLayout(s)
      let video: VideoInfo | null = null
      if (layout === 'video') {
        const ref = typeof s.video === 'string' ? s.video : null
        const lib = ref ? picked[ref] : undefined
        if (!ref) video = { path: null, exists: false, in_library: false }
        else if (server?.video?.path === ref) video = server.video
        else if (lib) video = { path: ref, exists: true, in_library: true, name: lib.name, duration: lib.duration, url: lib.url, thumb: lib.thumb }
        else video = { path: ref, exists: null, in_library: false }
      }
      const image = layout === 'image' && server?.image
        ? { ...server.image, stale: server.image.kind === 'ai' ? server.image.prompt !== s.prompt : false }
        : null
      return { index: i + 1, id, layout, seconds: server?.seconds ?? 0, image, video }
    })
  }, [draft, state, picked])

  const effectiveProvider = provider || draft?.images?.provider || 'pollinations'
  const needsKey = KEY_FOR[effectiveProvider]
  const missingKey = needsKey && !state?.keys[needsKey[0]]
  const imageScenes = infos.filter((i) => i.layout === 'image').length
  const videoProblems = infos.filter((i) => i.layout === 'video' && (!i.video?.path || i.video.exists === false))
  const scene = draft?.scenes[selected]
  const percent = Math.round((job?.percent ?? 0) * 100)

  if (!meta && !toast) return <div className="boot">Carregando…</div>

  return (
    <div className="app" style={{ ['--ar' as string]: aspectOf(draft?.resolution) }}>
      <Sidebar version={meta?.version ?? ''} channels={channels} channel={channel} script={scriptName} dirty={dirty}
               onPick={pick} onNewChannel={newChannel} onNewScript={newScript} onSettings={() => setSettings(true)} onImport={() => setImporting(true)} />

      <main className="workspace">
        <header className="topbar">
          <div className="title">
            <h1>{draft?.title || scriptName.replace(/\.json$/, '') || 'Faceless Studio'}</h1>
            <small>{draft ? `${draft.channel ?? channel} · ${draft.scenes.length} cenas · ${imageScenes} com imagem` : 'Crie ou escolha um projeto'}</small>
          </div>
          <div className="actions">
            {draft && <VideoSettings script={draft} onChange={setVideoOptions} />}
            <details className="options">
              <summary>Opções</summary>
              <div className="popover">
                <label className="field"><span>Gerador de imagens</span>
                  <select value={provider} onChange={(e) => setProvider(e.target.value)}>
                    <option value="">Do roteiro ({draft?.images?.provider ?? 'pollinations'})</option>
                    {meta?.providers.map((p) => <option key={p} value={p}>{p}</option>)}
                  </select>
                </label>
                <label className="check"><input type="checkbox" checked={strict} onChange={(e) => setStrict(e.target.checked)} /> Interromper se uma imagem falhar</label>
                <label className="check"><input type="checkbox" checked={noVoice} onChange={(e) => setNoVoice(e.target.checked)} /> Teste sem voz (não publicar)</label>
              </div>
            </details>
            <button className="ghost" disabled={!dirty || busy} onClick={() => void save()}>{dirty ? 'Salvar alterações' : 'Salvo'}</button>
            <button className="secondary" disabled={!draft || busy} onClick={() => void run('images')}>Gerar imagens</button>
            <button className="secondary" disabled={!draft || busy} onClick={() => void run('preview')}>Prévia de 2 cenas</button>
            <button className="primary" disabled={!draft || busy} onClick={() => void run('render')}>Gerar vídeo</button>
          </div>
        </header>

        {missingKey && imageScenes > 0 && (
          <div className="banner">Falta a chave de API do {needsKey[1]} neste canal.
            <button className="ghost" onClick={() => setSettings(true)}>Configurar</button></div>
        )}

        {(state?.warnings.length ?? 0) > 0 && (
          <details className={'banner issues-banner' + (state!.warnings.some((w) => w.level === 'erro') ? ' has-error' : '')}>
            <summary>
              {(['erro', 'verificar', 'aviso'] as const)
                .map((lv) => [lv, state!.warnings.filter((w) => w.level === lv).length] as const)
                .filter(([, n]) => n > 0)
                .map(([lv, n]) => `${n} ${lv === 'erro' ? 'erro(s) que impedem o vídeo' : lv === 'verificar' ? 'item(ns) para verificar antes de publicar' : 'aviso(s)'}`)
                .join(' · ')}
            </summary>
            <ul>
              {state!.warnings.map((w, i) => (
                <li key={i}><b>{w.scene ? `Cena ${w.scene}` : 'Roteiro'}{w.field ? ` · ${w.field}` : ''}</b>: {w.message}</li>
              ))}
            </ul>
          </details>
        )}

        {videoProblems.length > 0 && (
          <div className="banner">{videoProblems.length === 1 ? `Cena ${videoProblems[0].index}` : `Cenas ${videoProblems.map((i) => i.index).join(', ')}`}:
            {' '}falta escolher o vídeo (ou o arquivo não foi encontrado). A renderização vai parar nessa cena.</div>
        )}

        {job && (
          <div className={'progress ' + job.status}>
            <div className="bar-outer"><div className="bar-inner" style={{ width: `${percent}%` }} /></div>
            <span className="label">{job.label}{job.status === 'running' && ` · ${percent}%`} · {fmtTime(job.elapsed)}</span>
            <button className="ghost" onClick={() => setShowLog((v) => !v)}>{showLog ? 'Ocultar log' : 'Ver log'}</button>
            {job.status === 'running' && <button className="danger" onClick={() => void cancel()}>Cancelar</button>}
          </div>
        )}
        {showLog && <pre className="log" ref={logRef}>{logs.join('\n') || 'Sem mensagens.'}</pre>}

        {draft && scene ? (
          <div className="editor">
            <SceneList scenes={draft.scenes} infos={infos} selected={selected} onSelect={(i) => { setSelected(i); setView('scene') }}
              onAdd={() => { edit((d) => { d.scenes.push(newScene(d.scenes)) }); setSelected(draft.scenes.length); setView('scene') }}
              onMove={(i, delta) => { edit((d) => { const [s] = d.scenes.splice(i, 1); d.scenes.splice(i + delta, 0, s) }); setSelected(i + delta) }}
              onDuplicate={(i) => { edit((d) => { d.scenes.splice(i + 1, 0, duplicateScene(d.scenes[i], d.scenes)) }); setSelected(i + 1) }}
              onDelete={(i) => { if (confirm('Excluir esta cena?')) { edit((d) => { d.scenes.splice(i, 1) }); setSelected(Math.max(0, i - 1)) } }} />
            <Stage aspect={aspectOf(draft.resolution)} view={view} setView={setView} scene={scene} info={infos[selected]} scenes={draft.scenes} infos={infos}
                   preview={state?.outputs.preview ?? null} final={state?.outputs.final ?? null} busy={busy}
                   scenePreview={state?.outputs.scenes[String(selected + 1)] ?? null} previewKind={previewKind}
                   setPreviewKind={setPreviewKind} onScenePreview={(n) => void run('scene', '', n)}
                   onRegen={(index) => void run('images', String(index))} onSelect={(i) => { setSelected(i); setView('scene') }} />
            <aside className="props">
              <Inspector scene={scene} layout={infos[selected]?.layout ?? 'card'} channel={channel}
                         video={infos[selected]?.video ?? null}
                         toonCharacters={Object.entries((draft.toon?.characters ?? {}) as Record<string, { name?: string }>).map(([id, c]) => ({ id, name: c.name || id }))}
                         narrationSeconds={String(scene.narration ?? '').split(/\s+/).filter(Boolean).length / 2.5 + 0.8}
                         onChange={(s) => edit((d) => { d.scenes[selected] = s })}
                         onPickVideo={(item) => setPicked((m) => ({ ...m, [`assets/media/${item.name}`]: item }))} />
            </aside>
          </div>
        ) : (
          <div className="welcome">
            <h2>Bem-vindo ao Faceless Studio</h2>
            <p>Crie um canal na barra lateral para começar, ou escolha um roteiro existente.</p>
            <button className="primary" onClick={() => void newChannel()}>Criar canal</button>
          </div>
        )}

        {draft && <Timeline scenes={draft.scenes} infos={infos} selected={selected} onSelect={(i) => { setSelected(i); setView('scene') }} />}
      </main>

      {importing && (
        <ImportDialog channels={channels} currentChannel={channel}
                      onClose={() => setImporting(false)}
                      onImported={(ch, sc) => {
                        setImporting(false)
                        void (async () => {
                          await refreshChannels()
                          await pick(ch, sc)
                          notify(`Roteiro importado como “${sc.replace(/\.json$/, '')}”. Nada existente foi alterado.`)
                        })()
                      }} />
      )}
      {settings && state && (
        <SettingsDialog channel={channel} keys={state.keys} onClose={() => setSettings(false)}
                        onSaved={(keys) => { setState({ ...state, keys }); notify('Chave salva.') }} />
      )}
      {toast && <div className={'toast ' + toast.kind}>{toast.text}</div>}
    </div>
  )
}
