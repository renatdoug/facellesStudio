#!/usr/bin/env bash
# Prepara o Faceless Studio: cria o ambiente virtual e instala as dependências.
set -e
cd "$(dirname "$0")"

command -v python3 >/dev/null || { echo "Python 3.10+ não encontrado. Instale-o e rode de novo."; exit 1; }
command -v ffmpeg >/dev/null || { echo "FFmpeg não encontrado no PATH. Instale com seu gerenciador de pacotes (ex.: apt install ffmpeg, brew install ffmpeg)."; exit 1; }

[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip >/dev/null
pip install -r requirements.txt

[ -f .env ] || { cp .env.exemplo .env; echo "Criado .env — edite-o se for usar OpenAI ou Gemini."; }

echo
echo "Tudo pronto! Use ./run.sh para gerar um vídeo."
