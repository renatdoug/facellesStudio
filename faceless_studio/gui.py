"""Faceless Studio Desktop — Tkinter GUI for the existing CLI renderer.

The interface only orchestrates main.py; render logic remains unchanged.
Python 3.10+ and Tkinter are required; no extra pip packages for the GUI.
"""
from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

ROOT = Path(__file__).resolve().parent
CHANNELS = ROOT.parent / 'canais'
PROVIDERS = ('Do roteiro', 'pollinations', 'gemini', 'openai', 'comfyui', 'none')


def open_in_explorer(path: Path):
    path = Path(path)
    if not path.exists():
        messagebox.showwarning('Arquivo não encontrado', f'Não existe ainda:\n{path}')
        return
    try:
        if sys.platform == 'win32':
            os.startfile(str(path))
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', str(path)])
        else:
            subprocess.Popen(['xdg-open', str(path)])
    except Exception as err:
        messagebox.showerror('Falha ao abrir', str(err))


class StudioGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Faceless Studio — Produção de vídeos')
        self.geometry('1000x780')
        self.minsize(790, 630)
        self.configure(bg='#111827')
        self.script = tk.StringVar()
        self.channel = tk.StringVar()
        self.provider = tk.StringVar(value='Do roteiro')
        self.regen = tk.StringVar()
        self.dry = tk.BooleanVar(value=False)
        self.strict = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value='Selecione um canal e um roteiro para começar.')
        self.events = queue.Queue()
        self.proc = None
        self.running = False
        self.buttons = []
        self._style()
        self._layout()
        self._refresh_channels()
        self.after(120, self._poll)
        self.protocol('WM_DELETE_WINDOW', self._quit)

    def _style(self):
        style = ttk.Style(self)
        if 'clam' in style.theme_names():
            style.theme_use('clam')
        style.configure('.', font=('Segoe UI', 10))
        style.configure('TFrame', background='#111827')
        style.configure('TLabel', background='#111827', foreground='#e5e7eb')
        style.configure('Header.TLabel', font=('Segoe UI', 22, 'bold'), foreground='#f8fafc')
        style.configure('Hint.TLabel', foreground='#94a3b8')
        style.configure('TButton', padding=(12, 9))
        style.configure('Accent.TButton', padding=(13, 10), background='#0891b2', foreground='#ffffff')
        style.map('Accent.TButton', background=[('active', '#0e7490'), ('disabled', '#334155')])
        style.configure('TCombobox', fieldbackground='#f8fafc', padding=4)
        style.configure('TEntry', padding=6)
        style.configure('TCheckbutton', background='#111827', foreground='#e5e7eb')
        style.configure('TLabelframe', background='#111827', foreground='#e5e7eb')
        style.configure('TLabelframe.Label', background='#111827', foreground='#f8fafc', font=('Segoe UI', 10, 'bold'))

    def _layout(self):
        frame = ttk.Frame(self, padding=22)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='FACELESS STUDIO', style='Header.TLabel').pack(anchor='w')
        ttk.Label(frame, text='Imagens → revisão → prévia → vídeo final. Sem comandos no terminal.',
                  style='Hint.TLabel').pack(anchor='w', pady=(0, 18))

        box = ttk.LabelFrame(frame, text='1  Canal e roteiro', padding=13)
        box.pack(fill='x', pady=(0, 12))
        box.columnconfigure(1, weight=1)
        ttk.Label(box, text='Canal').grid(row=0, column=0, sticky='w', padx=(0, 12), pady=5)
        self.channels_combo = ttk.Combobox(box, textvariable=self.channel, state='readonly')
        self.channels_combo.grid(row=0, column=1, sticky='ew', pady=5)
        self.channels_combo.bind('<<ComboboxSelected>>', lambda e: self._select_channel())
        self.new_btn = ttk.Button(box, text='Novo canal', command=self._new_channel)
        self.new_btn.grid(row=0, column=2, padx=(8, 0), pady=5)
        self.buttons.append(self.new_btn)
        ttk.Label(box, text='Roteiro').grid(row=1, column=0, sticky='w', padx=(0, 12), pady=5)
        self.scripts_combo = ttk.Combobox(box, textvariable=self.script, state='readonly')
        self.scripts_combo.grid(row=1, column=1, sticky='ew', pady=5)
        self.scripts_combo.bind('<<ComboboxSelected>>', lambda e: self._inspect())
        pick_btn = ttk.Button(box, text='Procurar JSON...', command=self._pick_script)
        pick_btn.grid(row=1, column=2, padx=(8, 0), pady=5)
        self.buttons.append(pick_btn)
        ttk.Label(box, text='Arquivo selecionado:', style='Hint.TLabel').grid(row=2, column=0, sticky='nw', pady=5)
        self.script_path = ttk.Label(box, text='—', style='Hint.TLabel', wraplength=670)
        self.script_path.grid(row=2, column=1, columnspan=2, sticky='w', pady=5)
        row = ttk.Frame(box)
        row.grid(row=3, column=1, columnspan=2, sticky='w', pady=(7, 0))
        for label, action in [('Editar roteiro', self._edit_script), ('Abrir pasta do canal', self._open_project),
                              ('Configurar API (.env)', self._edit_env)]:
            btn = ttk.Button(row, text=label, command=action)
            btn.pack(side='left', padx=(0, 8))
            self.buttons.append(btn)

        opt = ttk.LabelFrame(frame, text='2  Preferências', padding=13)
        opt.pack(fill='x', pady=(0, 12))
        ttk.Label(opt, text='Gerador de imagens').grid(row=0, column=0, sticky='w', padx=(0, 12), pady=5)
        ttk.Combobox(opt, textvariable=self.provider, values=PROVIDERS, state='readonly', width=20).grid(
            row=0, column=1, sticky='w', pady=5)
        ttk.Label(opt, text='Regenerar cenas (ex.: 1,3)').grid(row=0, column=2, sticky='w', padx=(26, 10))
        ttk.Entry(opt, textvariable=self.regen, width=13).grid(row=0, column=3, sticky='w')
        ttk.Checkbutton(opt, text='Interromper se uma imagem falhar', variable=self.strict).grid(
            row=1, column=0, columnspan=2, sticky='w', pady=(8, 0))
        ttk.Checkbutton(opt, text='Teste sem voz (prévia técnica)', variable=self.dry).grid(
            row=1, column=2, columnspan=2, sticky='w', padx=(26, 0), pady=(8, 0))

        acts = ttk.LabelFrame(frame, text='3  Produção', padding=13)
        acts.pack(fill='x', pady=(0, 12))
        row = ttk.Frame(acts)
        row.pack(fill='x')
        for label, mode in [('Gerar imagens', 'images'), ('Prévia de 2 cenas', 'preview'), ('Gerar vídeo completo', 'render')]:
            btn = ttk.Button(row, text=label, style='Accent.TButton', command=lambda m=mode: self._run(m))
            btn.pack(side='left', padx=(0, 9))
            self.buttons.append(btn)
        self.stop_btn = ttk.Button(row, text='Cancelar execução', command=self._cancel, state='disabled')
        self.stop_btn.pack(side='right')
        row2 = ttk.Frame(acts)
        row2.pack(fill='x', pady=(12, 0))
        for label, action in [('Ver imagens', self._open_images), ('Abrir prévia', self._open_preview),
                              ('Abrir vídeo', self._open_video), ('Pasta de saída', self._open_output)]:
            btn = ttk.Button(row2, text=label, command=action)
            btn.pack(side='left', padx=(0, 9))
            self.buttons.append(btn)
        self.summary = ttk.Label(acts, text='Nenhum roteiro selecionado.', style='Hint.TLabel')
        self.summary.pack(anchor='w', pady=(12, 0))

        logs = ttk.LabelFrame(frame, text='Andamento e mensagens', padding=10)
        logs.pack(fill='both', expand=True)
        self.log = tk.Text(logs, height=12, bg='#0b1220', fg='#cbd5e1', insertbackground='white',
                           font=('Consolas', 10), wrap='word', relief='flat', padx=10, pady=10)
        self.log.pack(fill='both', expand=True)
        self.log.configure(state='disabled')
        ttk.Label(frame, textvariable=self.status, style='Hint.TLabel').pack(anchor='w', pady=(10, 0))

    def _candidate_dirs(self):
        paths = []
        if CHANNELS.is_dir():
            paths.extend(sorted(x for x in CHANNELS.iterdir() if x.is_dir()))
        # compatibility for legacy channels still kept under installation folder
        legacy = ROOT / 'canais'
        if legacy.is_dir():
            paths.extend(sorted(x for x in legacy.iterdir() if x.is_dir() and x not in paths))
        return paths

    def _refresh_channels(self, select=None):
        channels = self._candidate_dirs()
        self._channels = {f'{p.name}  [{p.parent}]': p for p in channels}
        self.channels_combo['values'] = list(self._channels)
        if select:
            for key, path in self._channels.items():
                if path == select:
                    self.channel.set(key)
                    break
        elif channels and self.channel.get() not in self._channels:
            self.channel.set(next(iter(self._channels)))
        self._select_channel()

    def _select_channel(self):
        folder = self._channels.get(self.channel.get())
        paths = sorted(folder.glob('*.json')) if folder else []
        self._scripts = {p.name: p for p in paths}
        self.scripts_combo['values'] = list(self._scripts)
        self.script.set(paths[0].name if paths else '')
        self._inspect()

    def _current(self):
        if self.script.get() in getattr(self, '_scripts', {}):
            return self._scripts[self.script.get()]
        path = Path(self.script.get())
        return path if path.is_file() else None

    def _inspect(self):
        path = self._current()
        self.script_path.configure(text=str(path) if path else 'Nenhum arquivo JSON selecionado')
        if not path:
            self.summary.configure(text='Crie um canal ou selecione um roteiro JSON.')
            return
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            n = len(data.get('scenes', []))
            imgs = sum(1 for s in data.get('scenes', []) if 'prompt' in s or 'image' in s)
            self.summary.configure(text=f'{data.get("channel", path.parent.name)}  •  {n} cenas  •  {imgs} cenas com imagem  •  saída: {path.parent / "output"}')
        except (OSError, ValueError, TypeError) as err:
            self.summary.configure(text=f'Erro de leitura: {err}')

    def _new_channel(self):
        name = simpledialog.askstring('Novo canal', 'Nome da pasta do canal (ex.: geeklab):', parent=self)
        if not name:
            return
        name = name.strip().lower().replace(' ', '-')
        if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{1,49}', name):
            messagebox.showwarning('Nome inválido', 'Use letras sem acento, números, hífen ou sublinhado (mínimo 2 caracteres).')
            return
        folder = CHANNELS / name
        if folder.exists():
            messagebox.showinfo('Canal existente', f'Esta pasta já existe:\n{folder}')
            return
        try:
            folder.mkdir(parents=True)
            sample = ROOT / 'roteiro_uti.json'
            if sample.exists():
                data = json.loads(sample.read_text(encoding='utf-8'))
                data['channel'] = name.replace('-', ' ').title()
                (folder / 'roteiro_inicial.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            else:
                data = {'channel': name.title(), 'theme': 'health', 'images': {'provider': 'pollinations'},
                        'scenes': [{'title': 'Abertura', 'narration': 'Este é o primeiro vídeo do canal.',
                                    'prompt': 'Cenário de abertura cinematográfico 16:9'}]}
                (folder / 'roteiro_inicial.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            self._refresh_channels(folder)
            self._write(f'Novo canal criado: {folder}\n')
        except Exception as err:
            messagebox.showerror('Não foi possível criar canal', str(err))

    def _pick_script(self):
        current = self._current()
        initial = current.parent if current else CHANNELS
        selected = filedialog.askopenfilename(title='Escolher roteiro JSON', initialdir=str(initial),
                                               filetypes=[('Roteiros JSON', '*.json')])
        if selected:
            path = Path(selected).resolve()
            self._scripts = {path.name: path}
            self.scripts_combo['values'] = [path.name]
            self.script.set(path.name)
            self._inspect()

    def _edit_script(self):
        path = self._current()
        if path:
            open_in_explorer(path)
        else:
            messagebox.showinfo('Roteiro', 'Selecione um roteiro primeiro.')

    def _open_project(self):
        path = self._current()
        if path:
            open_in_explorer(path.parent)

    def _edit_env(self):
        path = self._current()
        if not path:
            messagebox.showinfo('API', 'Selecione um roteiro primeiro.')
            return
        env = path.parent / '.env'
        if not env.exists():
            if not messagebox.askyesno('Criar .env', 'Criar configuração de API neste canal?\nNão compartilhe este arquivo.'):
                return
            template = ROOT / '.env.exemplo'
            try:
                env.write_text(template.read_text(encoding='utf-8') if template.exists() else 'GEMINI_API_KEY=\nOPENAI_API_KEY=\n', encoding='utf-8')
            except OSError as err:
                messagebox.showerror('Erro', str(err))
                return
        open_in_explorer(env)

    def _output_dir(self):
        path = self._current()
        return path.parent / 'output' if path else None

    def _open_images(self):
        directory = self._output_dir()
        if directory:
            open_in_explorer(directory / 'revisao_imagens.jpg')

    def _open_preview(self):
        directory = self._output_dir()
        if directory:
            open_in_explorer(directory / 'preview.mp4')

    def _open_video(self):
        directory = self._output_dir()
        if directory:
            open_in_explorer(directory / 'video_final.mp4')

    def _open_output(self):
        directory = self._output_dir()
        if directory:
            open_in_explorer(directory)

    def _write(self, line):
        self.log.configure(state='normal')
        self.log.insert('end', line)
        self.log.see('end')
        self.log.configure(state='disabled')

    def _command(self, path, mode):
        cmd = [sys.executable, '-u', str(ROOT / 'main.py'), '--script', str(path)]
        if mode == 'images':
            cmd.append('--images-only')
        if mode == 'preview':
            cmd.append('--preview')
        provider = self.provider.get()
        if provider and provider != 'Do roteiro':
            cmd.extend(['--image-provider', provider])
        regen = self.regen.get().strip()
        if regen:
            if not re.fullmatch(r'\d+(,\d+)*', regen):
                raise ValueError('Use apenas números de cenas separados por vírgula, ex.: 1,3')
            cmd.extend(['--regen', regen])
        if self.strict.get():
            cmd.append('--strict-images')
        if self.dry.get() and mode != 'images':
            cmd.append('--no-voice')
        if mode == 'preview':
            cmd.extend(['--output', 'output/preview.mp4'])
        return cmd

    def _run(self, mode):
        if self.running:
            return
        path = self._current()
        if not path or not path.exists():
            messagebox.showwarning('Selecione o roteiro', 'Escolha um arquivo JSON para produzir o vídeo.')
            return
        try:
            # Validate JSON before starting the subprocess, keeping any detailed CLI errors in log.
            data = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(data.get('scenes'), list) or not data['scenes']:
                raise ValueError('O roteiro precisa de pelo menos uma cena.')
            cmd = self._command(path, mode)
        except (ValueError, OSError) as err:
            messagebox.showerror('Roteiro ou configuração inválida', str(err))
            return
        self.running = True
        for btn in self.buttons:
            btn.configure(state='disabled')
        self.stop_btn.configure(state='normal')
        label = {'images': 'Gerando imagens', 'preview': 'Gerando prévia', 'render': 'Gerando vídeo'}[mode]
        self.status.set(f'{label}…')
        self._write(f'\n──── {label}: {path.name} ────\n')
        threading.Thread(target=self._worker, args=(cmd,), daemon=True).start()

    def _worker(self, cmd):
        try:
            # O filho escreve na codificação do Windows (cp1252) por padrão; forçamos UTF-8 para
            # casar com a leitura abaixo, senão acentos viram "�" no log.
            env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
            proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding='utf-8', errors='replace', bufsize=1, env=env,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            self.proc = proc
            assert proc.stdout is not None
            for line in proc.stdout:
                self.events.put(('line', line))
            ret = proc.wait()
            self.events.put(('done', ret))
        except Exception as err:
            self.events.put(('error', str(err)))
        finally:
            self.proc = None

    def _poll(self):
        try:
            while True:
                event, value = self.events.get_nowait()
                if event == 'line':
                    self._write(value)
                else:
                    self.running = False
                    for btn in self.buttons:
                        btn.configure(state='normal')
                    self.stop_btn.configure(state='disabled')
                    if event == 'done':
                        self.status.set('Concluído com sucesso.' if value == 0 else f'Execução terminou com erro (código {value}).')
                        if value == 0:
                            self._write('✓ Concluído. Use os botões acima para abrir o resultado.\n')
                        else:
                            self._write(f'✗ Erro na execução (código {value}). Confira as últimas linhas acima.\n')
                    else:
                        self.status.set('Erro ao iniciar a execução.')
                        self._write('✗ ' + value + '\n')
        except queue.Empty:
            pass
        self.after(120, self._poll)

    @staticmethod
    def _kill_tree(proc):
        """Encerra o main.py e os processos filhos (ffmpeg), que sobreviveriam a terminate()."""
        if sys.platform == 'win32':
            try:
                subprocess.run(['taskkill', '/T', '/F', '/PID', str(proc.pid)], capture_output=True,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                return
            except OSError:
                pass
        proc.terminate()

    def _cancel(self):
        if self.running and self.proc is not None:
            if messagebox.askyesno('Cancelar', 'Interromper o processo de renderização atual?'):
                self._kill_tree(self.proc)
                self.status.set('Cancelando…')

    def _quit(self):
        if self.running:
            messagebox.showwarning('Produção em andamento', 'Cancele a produção antes de fechar a janela.')
            return
        self.destroy()


if __name__ == '__main__':
    StudioGUI().mainloop()
