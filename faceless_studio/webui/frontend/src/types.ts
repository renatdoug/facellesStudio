// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type Scene = Record<string, any>
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type Script = Record<string, any> & { scenes: Scene[] }

export interface Channel { name: string; scripts: string[] }

export interface LibraryItem {
  name: string
  size: number
  mtime: number
  duration: number | null
  url: string
  thumb: string | null
}

export interface VideoInfo {
  path: string | null
  exists: boolean | null // null = ainda não conferido pelo servidor (escolhido e não salvo)
  in_library: boolean
  name?: string
  duration?: number | null
  url?: string
  thumb?: string | null
}

export interface SceneInfo {
  index: number
  id: string
  layout: string
  seconds: number
  image: {
    kind: 'ai' | 'file'; url: string | null; stale: boolean; provider?: string
    prompt?: string | null // prompt usado quando a imagem foi gerada
  } | null
  video: VideoInfo | null
}

export interface FileInfo { url: string; mtime: number; size: number }

export interface ScriptState {
  script: Script
  scenes: SceneInfo[]
  outputs: {
    preview: FileInfo | null; final: FileInfo | null; sheet: FileInfo | null
    scenes: Record<string, FileInfo> // prévias por cena (chave = número da cena)
  }
  keys: Record<string, string | null>
}

export interface Job {
  id: number
  mode: 'images' | 'preview' | 'render' | 'scene'
  channel: string
  script: string
  status: 'running' | 'done' | 'error' | 'cancelled'
  returncode: number | null
  percent: number
  label: string
  elapsed: number
  offset: number
  lines: string[]
}

export interface Meta { providers: string[]; layouts: string[]; busy: boolean }
