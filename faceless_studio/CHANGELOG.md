# Changelog

## v0.3.2

Correções de uma segunda revisão:
- O README já dizia que cada canal podia ter seu próprio `.env`, mas o código só lia o `.env` da pasta de instalação. Agora lê primeiro o `.env` da pasta do roteiro (tem prioridade) e depois o da instalação (serve de padrão compartilhado, para quem não define um por canal).
- `setup.bat` e `run.bat` agora começam com `cd /d "%~dp0"`, então funcionam mesmo se chamados a partir de outra pasta ou atalho.
- `run.bat`/`run.sh` não repetem mais um caminho fixo ("output/revisao_imagens.jpg") para a folha de revisão — isso ficava errado para um roteiro em outra pasta. Agora apontam para o caminho real que o próprio programa já imprime.
- Mais 1 teste automático (prioridade do `.env` por canal). Total: 27 testes.

## v0.3.1

Correções de uma revisão do projeto:
- O log de progresso mostrava o título em branco quando a cena só tinha `headline` (sem `title`). Agora usa um ou outro.
- Cada roteiro agora tem suas próprias pastas `assets/generated`, `temp` e `output` **na pasta onde ele está**, em vez da pasta de instalação. Antes, dois roteiros diferentes (dois canais) podiam disputar o mesmo cache de imagens se usassem o mesmo número ou `id` de cena. O workflow padrão do ComfyUI continua sendo encontrado mesmo que o roteiro esteja em outra pasta.
- Scripts `setup.bat`/`run.bat` (Windows) e `setup.sh`/`run.sh` (Linux/macOS) para instalar e rodar sem digitar os comandos manualmente; `run` já guia pelas duas etapas (gerar imagens → revisar → gerar vídeo).
- Mais 1 teste automático (fallback do workflow do ComfyUI). Total: 26 testes.

Pendente (não dá para testar neste ambiente, sem acesso às APIs pagas): rodar `--images-only` de verdade com Pollinations, OpenAI e Gemini. Os quatro fornecedores foram validados contra um servidor que imita o formato de cada API, mas isso não substitui testar com a API real.

## v0.3

Cenas conforme o conteúdo
- Layouts `list`, `number`, `chart`, `compare` e `quote`, escolhidos automaticamente pelos campos da cena.
- Textos dos layouts entram quando a narração fala deles (`on_word`); na lista, o item anterior fica esmaecido.
- Número com contagem crescente; gráficos (barras, barras horizontais, linha, várias séries) no visual do canal, com fonte.
- Títulos dos layouts deixam espaço para as tarjas de destaque.

Imagens por IA
- Fornecedores: Pollinations (grátis), OpenAI, Gemini e ComfyUI local, configuráveis no roteiro ou com `--image-provider`.
- Estilo único para todas as imagens e "sem texto" automático.
- Cache com manifesto por cena: só gera de novo quando o prompt muda ou com `--regen`.
- `--images-only` com folha de revisão (`revisao_imagens.jpg`) antes de renderizar.
- Falha de imagem não derruba o vídeo: vira cartão com aviso (`--strict-images` para interromper).
- Título opcional sobre a imagem (`overlay_title`) e escurecimento automático para a legenda.
- Chaves lidas de `.env`.

Testes
- 25 testes: legendas, layouts e os quatro fornecedores contra APIs simuladas.

## v0.2

Correções
- Zoom/pan agora acontecem de fato. Na v0.1 o zoom reiniciava a cada quadro e a imagem ficava parada.
- A imagem é ampliada uma única vez antes do zoom, evitando tremidas e deixando o render mais rápido.
- Legenda não cobre mais o texto do cartão: a faixa inferior fica reservada para ela.
- Resolução padrão passou a ser realmente 1920x1080.
- Áudio e vídeo de cada cena têm a mesma duração exata, sem atraso acumulado em vídeos longos.
- Fontes das legendas são copiadas para o projeto, funcionando igual no Windows e no Linux.

Novidades
- Legenda sincronizada palavra a palavra (tempos do próprio edge-tts), com estilo karaokê opcional.
- Blocos de legenda curtos, de uma linha, sem artigo ou preposição pendurado no fim.
- Tarjas de destaque (`callouts`) que surgem quando uma palavra é falada.
- Transições `fade` por cena; fade de entrada e saída no vídeo.
- Trilha sonora em loop com ducking automático e fades.
- Loudness normalizado para -14 LUFS.
- Arquivo `.srt` e lista de capítulos para o YouTube.
- Cache da narração por texto/voz/velocidade (substitui `--reuse-audio`).
- Opções `--scenes`, `--res`, `--subtitles`, `--music`, `--force-voice`, `--preset`.
- Código dividido em módulos (`studio/`) e testes automatizados das legendas.
