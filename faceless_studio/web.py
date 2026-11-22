#!/usr/bin/env python3
"""Faceless Studio — abre a interface web local no navegador.

    python web.py              # http://127.0.0.1:8765
    python web.py --no-browser
"""
import argparse
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CHANNELS = ROOT.parent / 'canais'


def main():
    p = argparse.ArgumentParser(description='Interface web do Faceless Studio')
    p.add_argument('--port', type=int, default=8765)
    p.add_argument('--no-browser', action='store_true')
    p.add_argument('--channels', default=str(CHANNELS), help='Pasta com os canais (padrão: ../canais)')
    args = p.parse_args()
    try:
        import uvicorn
        from webui.app import create_app
    except ImportError as err:
        sys.exit(f'Dependência ausente ({err}). Rode setup.bat (ou: pip install -r requirements.txt).')
    channels = Path(args.channels).resolve()
    channels.mkdir(parents=True, exist_ok=True)
    app = create_app(channels, ROOT)
    url = f'http://127.0.0.1:{args.port}'
    if not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    print(f'Faceless Studio em {url}  (Ctrl+C para encerrar)', flush=True)
    uvicorn.run(app, host='127.0.0.1', port=args.port, log_level='warning')


if __name__ == '__main__':
    main()
