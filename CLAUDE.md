# Faceless Studio — guia para quem for trabalhar neste repositório

## O que é

Programa em Python que transforma um roteiro em JSON em um vídeo MP4 narrado: voz por IA (edge-tts),
legendas palavra a palavra em estilo karaokê, cenas com layout adaptado automaticamente ao conteúdo
(lista, número, gráfico, comparação, citação, imagem), e imagens geradas por IA. Serve para produzir
vídeos "faceless" para YouTube sem o criador aparecer na câmera. Está na v0.7.0 (versão única em
`studio/__init__.py`), desenvolvido de forma incremental (v0.1 → v0.3.2 no chat; v0.4 → v0.6 no Claude Code:
interface Tkinter, interface web e cenas com vídeo de fundo).

Dono do projeto: Renato Douglas, enfermeiro/coordenador com perfil técnico (Python, dados), cursando
pós em ML/MLOps. Primeiro canal: "Dados na Saúde".

## Estrutura de pastas (IMPORTANTE — não mudar sem avisar)

Este repositório tem DOIS tipos de conteúdo, deliberadamente separados:

```
D:\Faceless\                      <- raiz do repositório git
├── faceless_studio\              <- SÓ o código do programa (isto é "o produto")
│   ├── main.py
│   ├── web.py / webui\ / abrir_studio.bat  <- interface web (v0.5), só orquestra o main.py
│   ├── gui.py / abrir_studio_simples.bat   <- janela Tkinter antiga (v0.4.0)
│   ├── studio\
│   ├── tests\
│   ├── setup.bat / run.bat / setup.sh / run.sh
│   └── .env.exemplo
└── canais\                       <- dados dos canais, FORA do código
    └── dados-na-saude\
        ├── teste_3cenas.json     <- roteiro de teste validado
        ├── .env                 <- chaves de API deste canal (NUNCA commitar)
        ├── assets/generated/    <- cache de imagens IA
        ├── temp/                <- arquivos intermediários de uma renderização
        └── output/              <- vídeo final, srt, folha de revisão de imagens
```

Motivo da separação: quando o programa for atualizado (nova versão do `faceless_studio/`), os dados dos
canais (roteiros, imagens já geradas, vídeos) não podem ser perdidos. Por isso `canais/` nunca fica
dentro de `faceless_studio/`.

Isso é suportado nativamente pelo código: em `main.py`, `project_dir = script.parent` — ou seja, tudo
que um roteiro gera (assets/generated, temp, output) fica ao lado do PRÓPRIO arquivo de roteiro, não da
instalação do programa. Por isso o roteiro pode morar em qualquer lugar, incluindo fora do repositório
do programa.

## Arquitetura do código

- `web.py` + `webui/` — interface web local (v0.5, a principal): `webui/app.py` (FastAPI, só 127.0.0.1,
  confere Host/Origin; só serve `assets/generated` e `output`), `webui/jobs.py` (roda o `main.py` como
  subprocesso, UTF-8, progresso por parsing do log, 1 job por vez, cancelar = `taskkill /T`) e
  `webui/frontend/` (React + TypeScript + Vite). O `dist/` compilado É versionado (Node só é preciso para
  alterar o front: `npm install && npm run build`). Não contém lógica de render. `main.validate_script()`
  é reaproveitada pela API. Aberta por `abrir_studio.bat`; `web.py --channels PASTA` aponta outra pasta de
  canais (usado para testar sem tocar nos dados reais). Salvar reformata o JSON do roteiro e cria `.bak`.
  Testes em `tests/test_webui.py` (precisam de `requirements-dev.txt`).
- `gui.py` — janela Tkinter antiga (v0.4.0, agora `abrir_studio_simples.bat`), sem dependências pip. NÃO contém lógica de render: monta a linha
  de comando e roda `main.py` como subprocesso (`--script` absoluto, `--images-only`, `--preview`,
  `--image-provider`, `--regen`, `--strict-images`, `--no-voice`), lendo a saída em tempo real. Procura canais
  em `../canais`. Cancelar usa `taskkill /T` para matar também o ffmpeg. Aberta por
  `abrir_studio_simples.bat` (usa `.venv\Scripts\pythonw.exe`). Foi aberta e validada na máquina do Renato.
- Animação e vertical (v0.7): `studio/chart_anim.py` desenha barras/linha em ASS (`\\clip` animado dentro de
  `\\t`; linha = caminho ida-e-volta com `\\bord` grosso); `layouts.layout_chart` usa o animado por padrão e cai
  para `charts.py` (matplotlib) com `"animate": false` ou barras agrupadas. `studio/ass_helpers.py`
  (`style`, `ev(min_dur=...)`) é compartilhado; eventos de contagem DEVEM usar `min_dur` pequeno (senão se
  sobrepõem). `subtitles.caption_metrics()` + `write_scene_ass(font_path=...)` medem a largura real (o tamanho
  ASS rende texto 16% mais estreito que o do Pillow: `PIL_PER_ASS`). `Ctx.portrait/bottom/src_y` adaptam os
  layouts ao vertical (legenda sobe para ~78% da altura; conteúdo termina em 68%). Entradas `punch`/`flash`
  e movimentos novos em `studio/video.py` (`ENTRIES`, `motion_exprs(punch_frames=...)`). `ImageBank(orientation=)`
  gera imagens no formato do vídeo. `--draft`/`--preview` mantêm o formato em 720p (`draft_resolution`).
  Versão única: `studio/__init__.py`. Exemplo: `exemplo_shorts.json`. Ainda sem vídeo IA nem personagem animado.
- Cena de vídeo (v0.6): `"video"` (+ `video_start`/`video_end`) vira o layout `video` (prioridade sobre
  imagem). `studio/video.py`: `prepare_clip()` recorta/enche o quadro/descarta o áudio e guarda em cache em
  `temp/`; `render_video_scene()` faz o loop (`-stream_loop`), sobrepõe a sombra (`visuals.shade_overlay`) e
  as legendas. `main.resolve_videos()` valida os arquivos antes de renderizar. Biblioteca por canal em
  `assets/media` (ignorada pelo Git; API em `webui/library.py`). "Vídeo IA" = futuro: gerar um MP4 em
  `assets/media` e preencher `video`, sem mudar o motor. Vídeo importado vem do usuário: lembrar de licença.
  Detalhe: `--scenes N-N` + `--output` já fazia prévia de uma cena; a interface usa isso ("Prévia desta cena").
- `main.py` — CLI e orquestração. `ROOT` = pasta onde `main.py` está (só usada como fallback para achar
  o workflow padrão do ComfyUI). `project_dir = script.parent` (ver acima).
- `.env` — carregado em ordem de prioridade via `os.environ.setdefault` (quem carrega primeiro "ganha"):
  primeiro `project_dir/.env` (chaves específicas do canal), depois `ROOT/.env` (fallback compartilhado
  entre canais). Nunca commitar `.env` com chaves reais — `.env.exemplo` é o único template versionado,
  em branco. O `.gitignore` da raiz já exclui `.env`, `**/.env`, `.venv/`, `**/temp/`, `**/output/`,
  `**/assets/generated/` e os pacotes `.zip`/FFmpeg.
- `studio/util.py` — `check_ffmpeg()` valida que ffmpeg/ffprobe existem E que os filtros/encoders
  necessários estão disponíveis: `ass`, `zoompan`, `sidechaincompress`, `loudnorm`, `fade`, `libx264`.
- `studio/voice.py` — narração via edge-tts; captura os eventos `WordBoundary` (timing palavra a
  palavra, em unidades de 100ns); cache em disco por hash de voz+texto+rate.
- `studio/subtitles.py` — alinhamento fuzzy (NFKD, acentos) das palavras da narração com o texto do
  roteiro; gera legendas ASS (com tags `\k` de karaokê) e SRT.
- `studio/video.py` — zoompan usando a variável `on` (contínua pela cena inteira, não reseta por
  frame — isso foi um bug real da v0.1); concatenação final dos clipes.
- `studio/audio.py` — ducking de música de fundo (`sidechaincompress`) sob a narração + `loudnorm`
  mirando -14 LUFS integrado (referência do YouTube).
- `studio/charts.py` — gráficos via matplotlib (backend `Agg`, headless), compostos sobre o fundo
  temático da cena.
- `studio/layouts.py` — detecção automática do layout pelo CONTEÚDO do JSON da cena (presença de
  `items`, `number`, `chart`, `compare`, `quote`, `prompt`/`image`) — ver `detect_layout()`. Cada layout
  tem sua própria função de desenho em `BUILDERS`.
- `studio/images_ai.py` — geração de imagem por IA com fornecedores plugáveis via `PROVIDERS` dict:
  `pollinations`, `openai`, `gemini`, `comfyui`. Cache em `assets/generated/` + `manifest.json`
  (fingerprint de prompt+style+provider+config decide quando regenerar). Chaves via variáveis de
  ambiente: `OPENAI_API_KEY`, `GEMINI_API_KEY`, `POLLINATIONS_API_KEY` (opcional).

## Fornecedores de imagem — decisão já tomada

- Renato tem acesso de API tanto à OpenAI quanto ao Gemini (assinatura paga em ambos).
- Fornecedor principal escolhido: **Gemini** (`gemini-3.1-flash-image`), por custo/qualidade. OpenAI
  (`gpt-image-2`) fica como alternativa para comparar qualidade quando necessário.
- Achado real de teste: Pollinations grátis (`pollinations`) marca a imagem com um watermark
  "pollinations." no canto, **mesmo enviando `nologo=true`** — o nível anônimo ignora esse parâmetro.
  Registrar uma conta gratuita em enter.pollinations.ai e usar `POLLINATIONS_API_KEY` resolve, sem
  precisar de plano pago.
- Ideia para o futuro (NÃO prioridade agora, só documentando): um "comparador" que gere a mesma cena em
  2+ fornecedores ao mesmo tempo e deixe escolher a melhor antes da montagem final.

## Ambiente Windows do Renato — já resolvido, não precisa redescobrir

- FFmpeg: a build **"essentials"** do gyan.dev já basta (tem `libass` e `libx264`). O texto de erro
  dentro de `setup.bat` já foi corrigido para "essentials" (v0.4.0).
- Ele tem três Pythons instalados: Anaconda, Microsoft Store, e um em
  `C:\Users\User\AppData\Local\Python\bin\python.exe`. **O Python do Anaconda tem o módulo `ssl`
  quebrado nessa máquina** (`ImportError: DLL load failed while importing _ssl`), o que quebra o pip
  dentro do `.venv` se o `setup.bat` pegar esse Python primeiro no PATH. Resolvido recriando o `.venv`
  manualmente a partir do Python local funcional. Se o problema voltar (ex: numa reinstalação), a causa
  é essa.
- Primeiro vídeo real (narração edge-tts real + imagem real via Pollinations) já foi gerado e
  **validado de verdade** (não só "rodou sem erro"): 1920x1080 @ 30fps, áudio -17.6dB médio / -1.4dB
  pico, legendas karaokê sincronizadas palavra a palavra, lista e gráfico renderizando como esperado.
  Único problema real encontrado foi o watermark do Pollinations (acima).

## Testes

`tests/` usa pytest + `tests/fake_apis.py` (servidor HTTP local mockado) para testar os 4 fornecedores
de imagem offline, sem gastar API de verdade nem precisar de rede. Rodar a suíte depois de qualquer
mudança em `images_ai.py`, `layouts.py`, `subtitles.py` ou `video.py`. Doutrina já seguida nas versões
anteriores: toda correção reportada foi primeiro verificada (reproduzida de fato), depois corrigida com
o mínimo necessário, com teste de regressão adicionado, antes de reempacotar — manter essa disciplina.

## Estado atual / próximos passos

- Repositório GitHub: https://github.com/renatdoug/facellesStudio (raiz local em `D:\Faceless`). O push
  inicial falhou por causa dos binários do FFmpeg terem entrado no primeiro commit (>100MB) — corrigido
  com `git rm --cached` + `.gitignore` na raiz + `git commit --amend`. Repositório confirmado limpo
  (sem FFmpeg/zips no histórico).
- Em andamento: reteste do roteiro `canais/dados-na-saude/teste_3cenas.json` usando Gemini como
  fornecedor de imagem — o JSON ainda está com `"provider": "pollinations"` (conferido em 22/11/2026);
  para testar o Gemini, escolher "gemini" no seletor da interface (ou `--image-provider gemini`) e
  confirmar que `GEMINI_API_KEY` está no `.env` do canal e que a geração funciona sem o watermark.
- Janela Tkinter (v0.4.0) abriu na máquina do Renato e rodou "Gerar imagens" (cache do Pollinations) com log em
  tempo real, e a "Prévia de 2 cenas" gerou `output/preview.mp4` (16,9 s, 1280x720, 11 s de render).
  Ainda não testados: vídeo completo, Cancelar e o Gemini.
- Interface web v0.5 construída a pedido do Renato (ele não gostou da Tkinter). Verificada no navegador
  em cópia temporária do canal: carrega canais/cenas, edita e salva, roda a prévia (`--no-voice`) com
  progresso e toca no player. NÃO testado: geração real de imagem/voz pela web, Cancelar, chaves de API.
  Fora de escopo por ora: "Criar projeto com IA" (roteiro gerado a partir de tema, via Gemini).
- Achado: a imagem em cache da cena 1 do `teste_3cenas.json` AINDA tem o watermark "pollinations.ai"
  (visto na interface); o teste com Gemini continua pendente.
- Decisão em aberto, não antecipar: se vale a pena construir o comparador de fornecedores (acima) ou
  seguir para outras melhorias — aguardar o Renato decidir depois de ver os resultados reais.
