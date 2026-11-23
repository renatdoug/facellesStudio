# Changelog

## v0.10.0 — bonecos animados (cartum) — MVP

Pedido do Renato: vídeos de **bonecos de palito/cartum que se mexem**, como os Shorts de humor (referência: @meme_animado), começando pelo canal GeekLab, com dois personagens em diálogo.
- **Novo tipo de cena "cartum"** (`studio/toon.py`): personagens **desenhados por código** (sem IA e sem custo por vídeo) em cima de um cenário em preto e branco. Cada fala é uma cena com `speaker`, `emotion`, `reaction`, `gesture`, `camera` e (opcional) `voice`.
- **Animação**: boca que abre e fecha a cada sílaba, **sincronizada com o tempo de cada palavra**; piscar; olhar (quem escuta olha para quem fala); balanço e respiração; gestos (apontar, mãos na cintura, abrir os braços, dar de ombros); 7 emoções (neutra, feliz, brava, triste, surpresa, pensando, convencida) com sobrancelhas, pálpebras e boca próprias. **Câmera**: 1ª cena em plano aberto, depois close em quem fala com leve aproximação; o outro personagem aparece na borda.
- Personagens independentes do cenário e da narração: ficha por personagem (`hair`: none/ponytail/bob/spiky, cores, `glasses`, `voice`, `side`) e `toon.background` (`room`, `plain` ou uma imagem sua). Até 2 personagens por enquanto.
- **Duas vozes**: cada personagem tem a sua voz (`pt-BR-FranciscaNeural`, `pt-BR-AntonioNeural`...); `main.py` usa a voz da cena > a do personagem > a do roteiro.
- **Legenda `topbox`**: a frase inteira em caixa preta no topo (fora das áreas cobertas pela interface do Shorts), como no vídeo de referência.
- **Roteiro por texto**: cole um diálogo `Leo: ...` / `Ana (pensativa): ...` / `Leo [aponta]: ...` em **Importar roteiro** e o Studio monta o vídeo (emoção entre parênteses; gesto e câmera entre colchetes; sem marcação, a emoção vem da pontuação). Detecta diálogo com exatamente 2 nomes e ao menos 3 falas; a voz vem do nome (terminado em "a" = feminina), sem repetir a mesma nos dois; falas longas são divididas por frases.
- Interface: cenas aparecem como "Cartum" com os campos de quem fala, emoção, reação, gesto e câmera.
- Guia de IA ganhou a seção 5.1 (cartum). Achados nos testes: o piscar podia nunca fechar o olho por completo (corrigido com trecho fechado de 0,06 s); a medição do tamanho dos bonecos agora usa o menor lado útil (também serve ao horizontal).
- Limites do MVP: só em pé (sem sentar/andar), 2 personagens, cenário simples, voz sintética (sem timing de humor). 31 testes novos (total: 178), incluindo renderizações reais (boca em movimento, legenda no topo, troca de plano).

## v0.9.1 — legenda legível no vertical

Achado no Short vertical com 4 ilustrações: a palavra falada (verde-água) caía sobre partes claras e também verde-água da imagem.
- O escurecimento da base (feito para a legenda ficar legível) era o do horizontal, onde a legenda fica na base. No **vertical** ela fica em ~75% da altura, onde o escurecimento era só ~17%. Agora, em imagens e vídeos verticais, o degradê começa mais cedo e já está em ~66% na altura da legenda (o meio da imagem continua limpo; o horizontal não muda). Conferido num quadro antes/depois. 1 teste novo.
- **Guia de IA**: cada prompt de imagem deve ilustrar o que a narração diz *naquela* cena (função narrativa clara), sem imagens só decorativas.
- Custo do Gemini reconfirmado: 4 imagens = R$ 2,49 (saldo 27,51 -> 25,02), a estimativa da prévia era R$ 2,48.

## v0.9.0 — colar o roteiro em texto

Pedido do Renato: "seria mais prático se eu apenas colocasse um roteiro" (sem JSON).
- **Importar roteiro agora aceita texto simples** (sem IA e sem custo): um parágrafo (linha em branco) vira uma cena; texto corrido ou parágrafo longo é dividido por frases e reagrupado até o tamanho de cena escolhido (curtas ~14 palavras, médias ~24, longas ~45; automático: curtas no vertical, longas no horizontal). A divisão protege abreviações ("Dr. Silva", "p. ex.", iniciais) e nunca corta uma frase no meio. Primeira linha `Título: ...` (ou `# ...`) define o título; blocos que começam com `Fonte:`/`Fontes:`/`Referências:` **não são narrados** e vão para o campo novo `fontes`.
- Opções na própria janela: **formato** (vertical, horizontal, quadrado), tamanho das cenas, **imagens** (uma por cena ou só texto), gerador (Gemini, OpenAI, Pollinations), voz e título. Vertical sai com legenda `pop`, `punch` e o prompt de imagem "full-bleed"; horizontal com karaokê. Cada imagem parte do texto da cena (`prompt`), para refinar no editor.
- A prévia mostra as cenas, o tempo e **quantas imagens de IA serão geradas e o custo estimado**: ≈ R$ 0,62 por imagem do Gemini (medido por você: 3 imagens = R$ 1,87, igual em 16:9 e 9:16). Nada é gerado ao importar.
- O JSON de uma IA continua funcionando (detectado por começar com `{` ou vir em bloco ```json).
- **Guia de IA**: sem "A VERIFICAR" no vídeo. A IA usa só os dados e fontes que você fornecer (copiados exatamente, com a fonte em `source`); sem dado fornecido, **não cria número nem gráfico** e registra a lacuna em `revisar` (nota interna, nunca aparece no vídeo). O pedido ganhou o campo "Dados e fontes que EU forneço".
- O verificador continua só lembrando de gráfico/número sem fonte (nunca bloqueia).
- 16 testes novos de texto simples (divisão, abreviações, fontes, opções, custo, API, validação do roteiro gerado) e a suíte inteira: 146.

## v0.8.3 — imagens verticais e prompt vazio

Achados no 1º Short com imagens do Gemini (9:16):
- **Editor**: apagar todo o texto do prompt trocava a cena para "Cartão" e o campo sumia. Agora a cena continua do tipo Imagem (o aviso de "sem prompt" aparece no topo).
- **Motor**: cena de imagem com prompt vazio agora **para antes de chamar o fornecedor**, em vez de gerar (e cobrar) uma imagem só com o estilo. 1 teste novo.
- **Prompt vertical**: o Gemini devolveu uma cena horizontal no meio de um fundo liso quando o prompt não pedia que a imagem ocupasse o quadro. O exemplo `exemplo_shorts_imagens.json` e o guia de IA agora pedem `tall vertical full-bleed illustration that fills the entire frame edge to edge, no empty margins or flat bands`.
- **Tarja (`callouts`) não cobre mais o nome do canal**: nas cenas de texto (gráfico, número, cartão...) ela desce abaixo do "DADOS NA SAÚDE" do canto; nas de imagem/vídeo continua no alto. O título dá mais espaço à tarja. 1 teste novo.
- Novo exemplo `exemplo_shorts_imagens.json` (Short vertical com 2 imagens do Gemini e 2 gráficos), validado junto com os outros exemplos por um teste.

## v0.8.2 — gancho: o vídeo começa na hora

Achado no 1º Short vertical real: nos primeiros ~1,5 s a tela ficava só com o título (o número entrava na palavra "metade"), depois de 0,5 s de preto e silêncio.
- **Primeira cena com `punch` ou `flash` começa NA HORA**: sem os 0,5 s de entrada do preto (o vídeo fica 0,5 s mais curto) e com o **título já opaco no 1º quadro** (sem o fade de 0,3 s). Com `cut` ou `fade` nada muda (continua a entrada suave do preto).
- Número/gráfico aceitam `"at": 0` para já estarem na tela no primeiro quadro; o número passa a **contar durante o primeiro segundo**.
- `exemplo_shorts.json` e o guia de IA ganharam as regras de gancho: 1ª frase com até 8 palavras, elemento principal já na tela (`"at": 0`), `punch`/`flash` na 1ª cena. O exemplo também deixou de usar `fade` (acrescentava ~1 s de silêncio).
- Testes: 3 novos (total: 125), incluindo uma renderização que compara o 1º quadro com e sem a entrada instantânea.

## v0.8.1 — pausa entre as cenas

Achado no primeiro teste real com voz (medido no vídeo): havia **1,4 s de silêncio entre as cenas** (2,1 s com `fade`).
O edge-tts deixa ~0,87 s de silêncio depois da última palavra, e o motor o contava como fala e ainda somava 0,35 s de respiro.
- A duração da fala agora vai até o fim da última palavra + 0,15 s. O corte usa o **maior** entre o fim da última palavra marcada e o início do silêncio final medido no áudio (`voice.speech_seconds`), então a fala nunca é cortada (conferido: o fim da fala ficou no mesmo instante do vídeo original). Pausa entre cenas: 1,4 s → ~0,5 s.
- Novo campo `"pause"` no roteiro (segundos depois da fala, 0 a 3; padrão `0.2`, antes fixo em 0,35). Menu **Vídeo → Pausa entre as cenas** na interface. A cena que sai com `fade` mantém o piso de 0,55 s do próprio fade.
- Guia de roteiro para IA e validação atualizados. 15 testes novos (total: 122), incluindo uma renderização com narração em cache que prova que o silêncio final é descartado.

## v0.8.0 — roteiros escritos por IA (guia e importação)

Para comparar Claude, ChatGPT e Gemini como roteiristas **sem integrar nenhuma API de modelo de linguagem**:
- **`guia_roteiro_ia.md`**: texto para colar na IA junto com o pedido. Descreve o JSON exato (campos do roteiro e da cena, tipos de cena, gráficos, formato 16:9 e 9:16, legendas, entradas e movimentos, ritmo de Short, prompts de imagem), traz um exemplo completo e uma lista de conferência. Obriga a **separar** o que é dito (`narration`), o que é visto (`prompt`, `items`, `chart`...) e o que precisa de conferência (`revisar`), e proíbe inventar estatísticas, estudos, referências ou doses: dado sem fonte vai com `"source": "A VERIFICAR"` e é listado em `revisar`.
- **Importar roteiro** (barra lateral): cole o que a IA devolveu (aceita texto em volta e bloco ```json), veja a **prévia ao vivo** (resumo, tabela de cenas, avisos), escolha o canal e importe como **projeto novo**. Nunca sobrescreve: nome repetido vira `-2`, `-3`... e nada existente é alterado.
- Validação com o **mesmo** `validate_script()` do motor, com mensagens por cena e campo; JSON inválido mostra linha, coluna, o trecho e a causa provável (aspas curvas, vírgula sobrando, comentários).
- **`studio/script_check.py`**: avisos não bloqueantes, por cena e campo, em três níveis — *erro* (vai falhar ao renderizar: rótulos e valores de tamanhos diferentes, lista sem itens, número sem valor...), *verificar* (fonte ausente, "ilustrativo/A VERIFICAR", itens de `revisar`) e *aviso* (campo desconhecido, com sugestão "Quis dizer ...?").
- No editor: aviso no topo com a contagem de erros/itens a verificar, e caixa **Para verificar antes de publicar** em cada cena com `revisar` ("Marcar como verificado" limpa a lista).
- API: `GET /api/guide`, `POST /api/import/preview`, `POST /api/import`; `GET` do roteiro passa a devolver `warnings`.
- 22 testes novos (total: 107): importação válida, JSON inválido, erros por cena/campo, nome duplicado, preservação byte a byte de tudo que já existe, proteção de origem, e **guia sincronizado com o código** (o exemplo do guia valida; o guia cita todo campo e valor que o motor aceita).

## v0.7.0 — animações e formato vertical

Animação (sem custo por vídeo, tudo feito pelo próprio motor):
- **Gráficos animados** (`studio/chart_anim.py`, desenhados em ASS): barras (vertical e horizontal) crescem do eixo com o valor subindo junto; linhas se desenham da esquerda para a direita e cada ponto "salta" quando a linha chega nele. As barras podem entrar na palavra da narração (`"on_words"`, uma por rótulo; palavra que não é dita entra logo após a anterior). `"animate": false` volta ao gráfico estático (matplotlib), que também continua para barras agrupadas.
- **Legendas animadas**: novos estilos `"subtitles": "pop"` (blocos curtos e grandes em maiúsculas que saltam, palavra falada em destaque) e `"box"` (o mesmo sobre caixa colorida), além de `karaoke`, `simple` e `off`.
- **Entradas de cena** (`"transition"` por cena ou `"default_transition"` no roteiro): `punch` (zoom rápido que desacelera), `flash` (clarão branco), `fade` e `cut`. Funcionam em imagens, textos e vídeos.
- **Movimentos de câmera** novos: `pan_up`, `pan_down` e `shake` (câmera na mão). No vertical o automático usa subir/descer em vez de deslizar de lado.

Formato vertical (9:16) e quadrado (1:1) — `"resolution": "1080x1920"`:
- Legendas medidas com a fonte de verdade (nenhum bloco passa da largura; palavra isolada larga demais encolhe só aquele bloco) e posicionadas acima da faixa inferior ocupada pela interface do Shorts.
- Layouts conscientes do formato: lista encolhe a fonte para caber, "Fonte:" quebra em 2 linhas, número e comparação respeitam a área útil, gráfico de barras com rótulos longos vira horizontal automaticamente.
- Imagens por IA são geradas no formato do vídeo (OpenAI 1024x1536, Gemini 9:16, Pollinations 1080x1920, ComfyUI 768x1344); trocar o formato regera as imagens (cache por formato).
- Prévias (`--preview`, `--draft` e "Prévia desta cena") mantêm o formato do vídeo em 720p. Antes, a prévia de um roteiro vertical saía horizontal.

Correções encontradas ao testar:
- A contagem do número criava eventos de legenda de 0,05 s esticados para 0,2 s, que se sobrepunham; agora não há sobreposição.
- Linha: escala automática (sem forçar o zero), marcas redondas no eixo e rótulos dos pontos só quando cabem.

Interface web: menu **Vídeo** (formato, legendas, entrada padrão), **Entrada da cena** e **Movimento da câmera** por cena, "Animar o gráfico", tela e galeria na proporção do vídeo. Exemplo pronto: `exemplo_shorts.json`.
Versão única em `studio/__init__.py`. 31 testes novos (total: 85), incluindo uma renderização vertical real que confere o crescimento das barras e o flash.

## v0.6.0 — vídeo como fundo da cena

- Novo tipo de cena **vídeo**: `"video": "assets/media/clipe.mp4"` (caminho relativo à pasta do roteiro, ou absoluto). O clipe enche o quadro 16:9 (corte central, sem barras), o áudio original é descartado e a narração, a trilha, as legendas karaokê e o título opcional (`overlay_title`) continuam por cima, com o mesmo escurecimento da base usado nas imagens.
- `"video_start"` e `"video_end"` (segundos) escolhem o trecho. Se o trecho for mais curto que a narração, ele **se repete em loop**; se for mais longo, é cortado no fim da fala.
- O trecho preparado fica em cache em `temp/`: refazer uma prévia não recodifica o clipe.
- Erros claros antes de renderizar: cena de vídeo sem arquivo, arquivo não encontrado, trecho inválido.
- `layouts.detect_layout`: `video` tem prioridade sobre `image`/`prompt`. `main.py` ganhou `resolve_videos()`; `studio/video.py` ganhou `prepare_clip()`, `render_video_scene()` e `clip_window()`.
- Interface web: chip **Vídeo** (e **Vídeo IA**, desativado, "em breve"), painel de mídia da cena com miniatura, duração, início/fim e aviso de loop/corte; **biblioteca de vídeos por canal** (`assets/media`: importar, reutilizar, apagar); **Prévia desta cena** (720p, só a cena escolhida, em `output/cena_NN.mp4`); aviso quando uma cena de vídeo está sem arquivo.
- API: `GET/PUT/DELETE /api/channels/{canal}/library`. Importação em streaming (limite de 4 GB, só extensões de vídeo, nome sanitizado, nunca sobrescreve, valida com ffprobe).
- 16 testes novos (total: 53), incluindo uma renderização real com FFmpeg (loop, corte, áudio descartado, vídeo em movimento).
- Versão única em `studio/__init__.py` (`__version__`): aparece em `python main.py --version`, em `/api/meta` e no canto da barra lateral; `package.json` alinhado (0.6.0).
- Arquitetura para o futuro: um fornecedor de vídeo por IA só precisa gravar um MP4 em `assets/media` e preencher `video`; nada mais no motor muda. Ainda não implementado.

## v0.5.0 — interface web

- `web.py` + `webui/`: servidor local (FastAPI, só `127.0.0.1`) e front-end React/TypeScript. Abre no navegador pelo `abrir_studio.bat`.
- Cenas com miniatura, linha do tempo (duração estimada), editor por cena (tipo, título, destaque, narração, prompt, itens; número/gráfico/comparação/citação em JSON), reordenar/duplicar/excluir.
- Galeria de imagens com aviso de "desatualizada" quando o prompt muda e "gerar de novo" por cena.
- Player integrado para prévia e vídeo final; progresso por cena, log e cancelamento (encerra o ffmpeg junto).
- Chaves de API por canal pelo navegador (gravadas no `.env`, nunca exibidas). Aviso quando falta a chave do fornecedor escolhido.
- Salvar mantém uma cópia `.json.bak`; o roteiro é validado antes de gravar. Observação: salvar reformata o JSON (indentação padrão).
- Proteções do servidor local: só aceita `Host` local e rejeita `Origin` de outros sites; só serve arquivos de `assets/generated` e `output`.
- `main.py`: validação do roteiro extraída para `validate_script()` (comportamento igual), reaproveitada pela interface.
- A janela Tkinter da v0.4 virou `abrir_studio_simples.bat`. Novos: `requirements-dev.txt`, 10 testes da API (total: 37).
- Pendente: "Criar projeto com IA" (roteiro gerado a partir de um tema).

## v0.4.0 — interface gráfica (Windows)

- `gui.py`: interface Tkinter sem dependências pip adicionais, com seleção de canal e roteiro JSON.
- Botões de geração de imagens, prévia e vídeo final, escolha de fornecedor, regeneração de cenas e logs em tempo real.
- Criação de novo canal, abertura de roteiro e `.env`, folha de revisão e vídeo final.
- `abrir_studio.bat`: inicia a interface com o Python do ambiente virtual após `setup.bat`.
- Cancelar na interface encerra também o `ffmpeg` iniciado pelo render (árvore de processos).
- `setup.bat`: a mensagem de erro agora indica que a build "essentials" do FFmpeg basta.
- Motor de renderização v0.3.2 mantido inalterado; interface ainda não validada com as APIs reais.

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
