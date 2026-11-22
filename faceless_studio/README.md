# Faceless Studio v0.3.2

Transforma um roteiro em JSON em um vídeo **MP4 1080p** narrado em português. Cada cena ganha o formato que combina com o conteúdo (ilustração por IA, lista, número, gráfico, comparação ou citação), com textos que aparecem no momento em que a narração fala deles, legenda palavra a palavra, trilha e arquivos prontos para o YouTube.

## Instalação

- Python 3.10+
- FFmpeg com **libass e libx264** e `ffprobe` no PATH (Windows: build "full" do gyan.dev)

**Windows:** rode `setup.bat` (uma vez) e depois `run.bat` para gerar um vídeo — eles conferem Python e FFmpeg, criam o ambiente e guiam você pelo fluxo de duas etapas abaixo.

**Linux/macOS:** `./setup.sh` e depois `./run.sh`.

Se preferir rodar os comandos você mesmo:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    |  Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

Para imagens por IA com chave, copie `.env.exemplo` para `.env` e preencha só a chave do fornecedor que for usar. O `.env` nunca deve ir para o GitHub (já está no `.gitignore`).

### Vários canais/roteiros

Cada roteiro gera suas imagens, cache e saída (`assets/`, `temp/`, `output/`) na **pasta onde ele está**, não na pasta de instalação. Para um segundo canal, crie uma pasta à parte com seu próprio roteiro JSON (e, se quiser, sua própria `.env`) e rode `python main.py --script /caminho/do/outro/roteiro.json` a partir da instalação — nada se mistura entre os canais.

## Fluxo recomendado

```bash
python main.py --images-only        # 1. gera as imagens e output/revisao_imagens.jpg
python main.py --images-only --regen 4   # 2. não gostou da imagem da cena 4? gera outra
python main.py --preview            # 3. confere voz e sincronia nas 2 primeiras cenas
python main.py                      # 4. vídeo completo
```

Revise as imagens antes de renderizar. Em conteúdo de saúde, uma ilustração errada (equipamento, posição, dispositivo) passa uma informação errada.

Outras opções: `--scenes 3-5`, `--music assets/trilha.mp3`, `--voice pt-BR-FranciscaNeural`, `--rate +8%`, `--subtitles simple`, `--image-provider gemini`, `--strict-images`, `--no-voice` (teste offline, áudio mudo), `--preset medium`.

Saídas em `output/`: `video_final.mp4`, `video_final.srt` (YouTube Studio → Legendas), `video_final_capitulos.txt` (colar na descrição) e `revisao_imagens.jpg`.

## Layouts

O layout é escolhido pelo conteúdo da cena; use `"layout"` para forçar um.

| Layout | Ativado por | Exemplo |
| --- | --- | --- |
| `image` | `"prompt"` (IA) ou `"image"` (arquivo seu) | `"prompt": "leito de UTI com monitor"`, `"overlay_title": true` |
| `list` | `"items"` | `[{"key": "A", "text": "Vias aéreas", "on_word": "vias"}]` — itens entram quando a palavra é falada; o anterior fica esmaecido |
| `number` | `"number"` | `{"value": 1240, "prefix": "", "suffix": "", "decimals": 0, "label": "...", "source": "...", "on_word": "..."}` — número com contagem crescente |
| `chart` | `"chart"` | `{"type": "bar"/"barh"/"line", "labels": [...], "values": [...], "unit": "%", "highlight": 2, "source": "..."}`; várias séries: `"series": [{"name", "values"}]` |
| `compare` | `"compare"` | `{"left": {"title", "items"}, "right": {"title", "on_word", "items"}}` |
| `quote` | `"quote"` | `{"text": "...", "author": "...", "on_word": "..."}` |
| `card` | nenhum dos acima | cartão com `headline` e `visual` |

Veja `exemplo_layouts.json` (dados ilustrativos) e rode: `python main.py --script exemplo_layouts.json --preview`.

Itens sem `on_word` são distribuídos ao longo da fala. Em vez da palavra, você pode usar `"at": 3.5` (segundos). Gráficos e números devem trazer `source`; não publique dado sem fonte.

## Imagens por IA

Configure no roteiro:

```json
"images": {
  "provider": "pollinations",
  "style": "editorial digital illustration, flat shapes, dark navy and teal palette",
  "seed": 1234
}
```

| Fornecedor | Chave | Custo aproximado | Observações |
| --- | --- | --- | --- |
| `pollinations` | opcional (`POLLINATIONS_API_KEY`) | grátis | Sem chave: 1 imagem a cada ~16 s e pode ter marca d'água. Bom para testar |
| `openai` | `OPENAI_API_KEY` | ~US$ 0,04 por imagem (gpt-image-2, qualidade medium, 1536x1024) | Opções: `model`, `size`, `quality` (`low` custa ~US$ 0,005) |
| `gemini` | `GEMINI_API_KEY` | ver tabela do Google | Opções: `model` (`gemini-3.1-flash-image`, `gemini-3.1-flash-lite-image`), `image_size` |
| `comfyui` | — (local, sua GPU) | grátis | ComfyUI aberto; workflow em `comfyui/sdxl_api.json` com marcadores `{{PROMPT}}`, `{{SEED}}`, `{{WIDTH}}`, `{{HEIGHT}}`, `{{CHECKPOINT}}`, `{{STEPS}}`, `{{NEGATIVE}}`. Opções: `url`, `workflow`, `checkpoint`, `steps`, `width`, `height` |
| `none` | — | — | Desliga a geração; cenas com `prompt` viram cartão |

Os modelos de imagem mudam rápido (vários da OpenAI saem do ar em dezembro de 2026). Se um modelo for descontinuado, troque `"model"` no roteiro.

Como funciona o cache: as imagens ficam em `assets/generated/` e o `manifest.json` lembra qual arquivo é de cada cena (pelo `"id"` da cena ou pelo número). A imagem só é gerada de novo se o prompt, o estilo ou o fornecedor mudarem, ou com `--regen`. Para usar uma imagem sua, troque `"prompt"` por `"image": "assets/minha.png"`.

Se uma imagem falhar, o vídeo sai com um cartão no lugar e um aviso no final. Use `--strict-images` para interromper.

O estilo recebe automaticamente "no text, no letters...", porque IA ainda escreve mal em português. Textos ficam a cargo dos layouts.

Para ComfyUI com outro modelo (FLUX etc.): monte o workflow no ComfyUI, use "Export (API)", troque os valores pelos marcadores e aponte `"workflow"` para o arquivo.

## Outros campos do roteiro

Gerais: `channel`, `theme` (`health`/`geek`), `voice`, `rate`, `resolution`, `fps`, `subtitles` (`karaoke`/`simple`/`off`), `music`, `music_volume_db`, `motion_amount`, `font_bold`, `font_regular`.

Por cena: `id`, `narration` (obrigatório), `headline`, `visual`, `motion` (`auto`, `zoom_in`, `zoom_out`, `pan_left`, `pan_right`, `static`), `motion_amount`, `transition` (`cut`/`fade`), `chapter`, `callouts` (`[{"text": "SBAR", "on_word": "comunicação"}]`).

## Testes

```bash
python -m unittest -v
```

Os testes de imagem usam um servidor local que imita as APIs: não precisam de internet nem gastam créditos.

## Roteiros escritos por IA (v0.8)

Você pode pedir o roteiro a qualquer IA de chat (Claude, ChatGPT, Gemini) e importá-lo, sem API:

1. Na barra lateral, clique em **⬇ Importar roteiro de IA** e em **Copiar guia para a IA** (ou abra `guia_roteiro_ia.md`).
2. Cole o guia no chat e preencha o **Pedido** no fim dele (tema, canal/tom, formato 9:16 ou 16:9, duração, dados que você fornece).
3. Cole de volta a resposta da IA na caixa do Studio. A prévia mostra as cenas, o tempo estimado e os avisos; escolha o canal e clique em **Importar como novo projeto**. Nada existente é alterado (nome repetido vira `-2`).

O guia obriga a IA a **não inventar dados**: números de exemplo vão com `"source": "A VERIFICAR"` e frases de conferência em `"revisar"` (por cena ou no roteiro). Esses itens aparecem num aviso no topo do editor e na caixa "Para verificar antes de publicar" da cena. **Confira tudo antes de publicar**, em especial conteúdo de saúde. Para comparar modelos, use o mesmo pedido nos três e olhe a prévia de cada um.

## Animações e formato vertical (v0.7)

```json
{"resolution": "1080x1920", "subtitles": "pop", "default_transition": "punch", "scenes": [ ... ]}
```

- **Formato**: `resolution` `1920x1080` (padrão), `1080x1920` (Shorts/Reels/TikTok) ou `1080x1080`. No vertical a legenda sobe para ficar acima da faixa inferior do Shorts e as imagens por IA são geradas em 9:16. Exemplo completo e sem imagens de IA: `exemplo_shorts.json`.
- **Legendas** (`subtitles`): `karaoke` (padrão), `pop` (blocos grandes em maiúsculas que saltam), `box` (sobre caixa colorida), `simple`, `off`.
- **Entrada da cena** (`transition`, por cena; `default_transition` para todas): `cut`, `fade`, `punch` (zoom rápido), `flash` (clarão branco).
- **Movimento** (`motion`): `zoom_in`, `zoom_out`, `pan_left`, `pan_right`, `pan_up`, `pan_down`, `shake`, `static`.
- **Gráficos animados** (padrão): barras crescem e a linha se desenha. Em `chart`: `"on_words": ["respiratórias", "cardiovasculares", ...]` faz cada barra entrar quando a palavra é dita; `"orient": "horizontal"|"vertical"` força a orientação (no vertical, rótulos longos já viram barras horizontais sozinhos); `"zero": true` força o zero no eixo da linha; `"animate": false` usa o gráfico estático.
- **Pausa entre as cenas** (`pause`, em segundos depois da fala; padrão `0.2`; `0.1` deixa o Short mais rápido). `fade` entre cenas acrescenta uma pausa maior: para ritmo rápido use `punch`, `flash` ou `cut`.
- **Prévias** (`--draft`, `--preview`, "Prévia desta cena") saem em 720p no mesmo formato do vídeo.
- Ainda não há vídeo gerado por IA nem personagens animados; o movimento vem de imagens, vídeos seus e das animações acima.

## Vídeo como fundo (v0.6)

Além de imagem parada com zoom, uma cena pode usar um **clipe de vídeo** como fundo:

```json
{"title": "UTI", "narration": "…", "video": "assets/media/uti.mp4", "video_start": 4, "video_end": 12}
```

- O clipe é recortado para 16:9 sem barras e **o áudio original é descartado** (só a narração e a trilha tocam). Legendas, `callouts` e `overlay_title` ficam por cima.
- `video_start`/`video_end` (segundos) escolhem o trecho; ambos são opcionais.
- Se o trecho for **mais curto** que a narração, ele se repete em loop; se for **mais longo**, é cortado quando a fala termina. Dica: escolha trechos de pelo menos a duração da fala para evitar a repetição.
- Na interface web: tipo de cena **Vídeo** → *Escolher ou importar…* (biblioteca de vídeos do canal, em `assets/media`, reaproveitável em qualquer roteiro) e **▶ Prévia desta cena** para conferir uma cena sem renderizar o vídeo todo.
- Use só vídeos que você tenha direito de usar (seus, ou de bancos com licença adequada). Os arquivos de `assets/media` não vão para o Git.

## Interface web (v0.5)

No Windows, execute `setup.bat` **uma vez** e depois dê duplo clique em
`abrir_studio.bat`: o programa abre no navegador em `http://127.0.0.1:8765`
(só acessível neste computador). Mantenha a janela preta aberta enquanto usa;
feche-a para encerrar. Em outro sistema: `python web.py`.

Na tela: a barra lateral lista canais e roteiros; no centro ficam as **cenas**
(com miniatura), a **galeria** de imagens (com "gerar de novo" por cena), o
player da **prévia** e do **vídeo final**; à direita, o **editor da cena**
(tipo, título, narração, prompt, itens da lista). Alterações são salvas com
`Ctrl+S` (o roteiro anterior vira `.json.bak`) e salvas automaticamente antes de
gerar. Botões do topo: **Gerar imagens → Prévia de 2 cenas → Gerar vídeo**, com
barra de progresso, log e cancelamento. **Chaves de API** grava no `.env` do
canal e nunca mostra o valor de volta. O front-end já vem compilado em
`webui/frontend/dist`; só é preciso Node para alterá-lo
(`cd webui/frontend && npm install && npm run build`).

A interface não mexe na geração: chama o `main.py` com os mesmos parâmetros do
terminal. Testes da interface: `pip install -r requirements-dev.txt` e `pytest`.

## Janela simples (v0.4.0, Tkinter)

Continua disponível em `abrir_studio_simples.bat` (`gui.py`), com o mesmo fluxo
em botões, sem editor de cenas nem player.

Na janela: (1) selecione o canal/roteiro, ou crie um canal novo; (2) escolha
um fornecedor de imagens (ou mantenha o configurado no JSON); (3) clique em
**Gerar imagens**, confira **Ver imagens**; (4) clique em **Prévia de 2 cenas**
e **Abrir prévia**; (5) clique em **Gerar vídeo completo** e **Abrir vídeo**.

Os canais são procurados prioritariamente em `../canais/`, isto é, numa
pasta irmã da instalação `faceless_studio`. O programa também reconhece
projetos antigos em `faceless_studio/canais/`, caso existam, sem duplicá-los.
**Novo canal** cria um roteiro inicial editável. **Procurar JSON** permite usar
qualquer roteiro em outra pasta. O arquivo `.env` de cada canal é editado
localmente pelo botão **Configurar API (.env)**: não o compartilhe.

`gui.py` não muda a geração de imagens, narração ou montagem: ela chama
`main.py` com os mesmos parâmetros que seriam usados no terminal. A prévia
vai para `output/preview.mp4` e o vídeo final para `output/video_final.mp4`.

## Limitações

- As integrações com OpenAI, Gemini, Pollinations e ComfyUI foram testadas contra APIs simuladas. Na primeira execução real, rode com `--images-only` e, se algo falhar, a mensagem de erro mostra a resposta da API.
- Sem efeitos sonoros (whoosh, pop) e sem voz própria com Whisper por enquanto.
- O edge-tts usa um serviço gratuito da Microsoft sem garantia de disponibilidade.

## Uso responsável

Revise conteúdo clínico, dados e imagens antes de publicar. O roteiro de demonstração é educativo e não substitui protocolos institucionais. Não use dados identificáveis de pacientes. No YouTube, marque "conteúdo alterado ou sintético" quando houver imagem ou voz realista que possa ser confundida com algo real; o estilo ilustrado padrão reduz esse risco.
