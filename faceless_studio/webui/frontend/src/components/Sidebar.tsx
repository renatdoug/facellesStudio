import type { Channel } from '../types'

interface Props {
  version: string
  channels: Channel[]
  channel: string
  script: string
  dirty: boolean
  onPick: (channel: string, script: string) => void
  onNewChannel: () => void
  onNewScript: () => void
  onSettings: () => void
  onImport: () => void
}

export default function Sidebar({ version, channels, channel, script, dirty, onPick, onNewChannel, onNewScript, onSettings, onImport }: Props) {
  return (
    <nav className="sidebar">
      <div className="brand"><span className="logo">▶</span><div><b>FACELESS</b><small>STUDIO{version ? ` · v${version}` : ''}</small></div></div>
      <div className="panel-title"><span>Projetos</span><button className="ghost" onClick={onNewChannel}>+ Canal</button></div>
      <div className="channels">
        {channels.length === 0 && <p className="empty small">Nenhum canal ainda. Crie o primeiro.</p>}
        {channels.map((c) => (
          <div key={c.name} className="channel">
            <div className="channel-name">{c.name}</div>
            {c.scripts.map((s) => (
              <button key={s} className={'script' + (c.name === channel && s === script ? ' on' : '')}
                      onClick={() => onPick(c.name, s)}>
                {s.replace(/\.json$/, '')}{c.name === channel && s === script && dirty ? ' •' : ''}
              </button>
            ))}
            {c.name === channel && <button className="script add" onClick={onNewScript}>+ Novo roteiro</button>}
          </div>
        ))}
      </div>
      <div className="side-foot">
        <button className="ghost wide" onClick={onImport}>⬇ Importar roteiro de IA</button>
        <button className="ghost wide" disabled={!channel} onClick={onSettings}>⚙ Chaves de API</button>
      </div>
    </nav>
  )
}
