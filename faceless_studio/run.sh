#!/usr/bin/env bash
# Gera o vídeo a partir de um roteiro. Rode ./setup.sh uma vez antes deste script.
# Uso: ./run.sh [roteiro.json]
set -e
cd "$(dirname "$0")"

[ -d .venv ] || { echo "Ambiente não preparado. Rode ./setup.sh primeiro."; exit 1; }
source .venv/bin/activate

SCRIPT="${1:-roteiro_uti.json}"

echo
echo "===== Passo 1 de 2: gerando e revisando as imagens ====="
python3 main.py --script "$SCRIPT" --images-only

echo
echo "Confira as imagens na \"Folha de revisão\" indicada acima (revisao_imagens.jpg)."
echo "Para trocar uma: edite o roteiro (prompt ou image) e rode de novo,"
echo "ou use: python3 main.py --script \"$SCRIPT\" --images-only --regen NUMERO_DA_CENA"
echo
read -rp "Continuar e gerar o vídeo completo agora? (s/n) " CONTINUAR
[[ "$CONTINUAR" =~ ^[sS]$ ]] || exit 0

echo
echo "===== Passo 2 de 2: gerando o vídeo ====="
python3 main.py --script "$SCRIPT"
