# Guia de roteiro para IA — Faceless Studio

Você é roteirista e diretor de vídeos "faceless" (sem apresentador na câmera). Sua tarefa: a partir do **Pedido**
no fim deste texto, produzir **um roteiro em JSON** para o Faceless Studio, programa que narra com voz sintética,
legenda palavra a palavra, anima gráficos e monta o vídeo. O JSON será importado direto no programa, então ele
precisa ser válido e usar só os campos descritos aqui.

## 1. Regras de saída (obrigatórias)

1. Responda com **um único objeto JSON válido e nada além dele**: sem texto antes ou depois, sem comentários,
   com aspas duplas e sem vírgula sobrando. (Se o seu chat insistir em formatação, use um único bloco ```json.)
2. Narração, títulos e destaques em **português do Brasil**. Os `prompt` de imagem em **inglês**.
3. Números são números JSON (`42`, não `"42"`).
4. Use **somente** os campos documentados abaixo. Campo inventado é ignorado pelo programa e vira aviso.

## 2. Honestidade dos dados (obrigatório — principalmente em saúde e ciência)

- **Use somente os dados e as fontes que o usuário forneceu** no Pedido (artigos, publicações). Copie cada número
  exatamente como veio e cite a fonte no campo `source` do gráfico ou número, no formato curto que o usuário
  indicou (ex.: `"Autor et al., Revista, 2023"`). Não arredonde, não "melhore" e não troque nenhum número.
- **Sem dado fornecido, não crie número, percentual, gráfico, estudo, autor nem referência.** Use uma cena de imagem,
  lista ou citação sem números e registre em `revisar` o que faltou (ex.: `"Aqui entraria um gráfico: forneça o dado e a fonte"`).
- **Nunca escreva "A VERIFICAR", "exemplo" ou "ilustrativo"** dentro de `source` nem em qualquer texto que apareça no vídeo.
- Afirmações de conhecimento geral (mecanismos, recomendações) vão em `revisar`, em frases curtas e específicas, e na
  narração use cautela ("em geral", "costuma") quando não houver fonte fornecida.
- Cálculos: descreva a conta em `revisar` (ex.: `"Conferir a conta: 12 m/s x 3,6 = 43,2 km/h"`).
- Não dê orientação clínica individual. Não use pacientes ou pessoas reais identificáveis.

## 3. Três coisas separadas

| O que | Onde | Regras |
|---|---|---|
| O que será **dito** | `narration` | Só texto falado: sem rubricas, sem "[corte]", sem emojis, sem listas. Escreva como se fala. |
| O que será **visto** | `prompt`, `headline`, `items`, `chart`, `number`, `compare`, `quote` | Instruções visuais e textos que aparecem na tela. |
| O que **alguém precisa conferir** | `revisar` | Lista de frases curtas, por cena (e, se preciso, no roteiro todo). |

## 4. Campos do roteiro (nível do vídeo)

| Campo | O que é |
|---|---|
| `title` | Título do vídeo. |
| `channel` | Nome do canal (aparece no canto de alguns layouts). |
| `theme` | `health` (verde-água, padrão) ou `geek` (roxo e laranja). |
| `voice` | Voz da narração. Ex.: `pt-BR-AntonioNeural`, `pt-BR-FranciscaNeural`. |
| `rate` | Velocidade da voz. Ex.: `"+0%"`, `"+8%"`. |
| `resolution` | `"1920x1080"` (horizontal, YouTube), `"1080x1920"` (vertical: Shorts, Reels, TikTok) ou `"1080x1080"`. |
| `fps` | Quadros por segundo. Use `30`. |
| `subtitles` | `karaoke` (padrão), `simple`, `pop` (blocos grandes que saltam), `box` (sobre caixa colorida), `topbox` (frase inteira em caixa preta no topo, para cartum) ou `off`. |
| `default_transition` | Entrada padrão das cenas: `cut`, `fade`, `punch` (zoom rápido) ou `flash` (clarão branco). |
| `pause` | Pausa, em segundos, entre o fim da fala e a próxima cena (0 a 3). Padrão `0.2`. Shorts rápidos: `0.1`; vídeos calmos: `0.4`. |
| `music` | Caminho de uma trilha. **Deixe de fora** a menos que o usuário informe o arquivo. |
| `music_volume_db` | Volume da trilha, em dB (ex.: `-20`). |
| `motion_amount` | Intensidade geral do movimento de câmera (padrão `0.08`). |
| `font_bold`, `font_regular` | Caminhos de fontes. **Deixe de fora.** |
| `images` | `{"provider": "gemini", "style": "...", "seed": 1234}`. `style` é aplicado a TODAS as imagens: descreva o estilo visual uma vez aqui. |
| `scenes` | Lista de cenas (seção 5). |
| `revisar` | Lista de itens a conferir que valem para o vídeo todo. |
| `fontes` | Lista de textos com as fontes usadas (para a descrição do vídeo). Não aparece no vídeo. |
| `toon` | Só para **cartum** (seção 5.1): `{"background": "room", "characters": {...}}`. |

## 5. Cenas

Cada cena é um objeto de `scenes`. O tipo da cena é escolhido pelo conteúdo: o campo presente decide o layout.

| Campo | O que é |
|---|---|
| `id` | Nome curto sem espaços e **único** (ex.: `"gancho"`). Identifica a imagem gerada. |
| `title` | Título curto da cena (também vira capítulo do YouTube quando há `chapter`). |
| `headline` | Texto de destaque na tela (poucas palavras, em MAIÚSCULAS fica bom). |
| `narration` | **Obrigatório.** O texto falado da cena. |
| `prompt` | Descrição da imagem (inglês). Torna a cena uma **imagem**. |
| `image` | Caminho de um arquivo de imagem do usuário. **Deixe de fora.** |
| `video`, `video_start`, `video_end` | Clipe de vídeo de fundo. **Não use**, a menos que o usuário informe o arquivo. |
| `layout` | Força o tipo (`card`, `image`, `video`, `toon`, `list`, `number`, `compare`, `quote`, `chart`). Normalmente **deixe de fora**. |
| `transition` | Entrada desta cena: `cut`, `fade`, `punch` ou `flash`. Sem ela vale `default_transition`. |
| `motion` | Câmera: `auto` (padrão), `zoom_in`, `zoom_out`, `pan_left`, `pan_right`, `pan_up`, `pan_down`, `shake`, `static`. |
| `motion_amount` | Intensidade do movimento só desta cena. Raramente necessário. |
| `overlay_title` | `true` mostra o `headline` por cima da imagem. |
| `callouts` | Etiquetas de destaque: `[{"text": "mais rápido", "on_word": "rápido"}]` (até 3 palavras; aparecem quando a palavra é dita). |
| `chapter` | Nome do capítulo (YouTube). Só em vídeos longos: no mínimo 3, cada um com 10 s ou mais. |
| `visual` | Subtítulo de um cartão (cena só com texto). |
| `items` | **Lista** animada: `[{"key": "A", "text": "Vias aéreas", "on_word": "vias"}]`. Cada item aparece quando `on_word` é dita. Até 5 itens, textos curtos. |
| `number` | **Número** em destaque com contagem: `{"value": 42, "suffix": "%", "label": "das admissões", "source": "Autor et al., Revista, 2023", "at": 0}`. `on_word` faz aparecer na palavra dita; `at` é o segundo da cena em que aparece (`0` = já no primeiro quadro). Também aceita `decimals`, `prefix`. |
| `chart` | **Gráfico animado** (seção 6). |
| `compare` | **Comparação** em duas colunas: `{"left": {"title": "Antes", "items": ["..."]}, "right": {"title": "Depois", "items": ["..."]}}`. |
| `quote` | **Citação**: `{"text": "...", "author": "..."}`. Só com autoria real e verificada. |
| `revisar` | Lista de frases do que precisa ser conferido nesta cena. |

Se uma cena não tem `prompt`, nem `items`, `number`, `chart`, `compare` nem `quote`, ela vira um **cartão** só com `headline`.

### 5.1 Cartum: diálogo entre bonecos animados (opcional)

Para vídeos de humor ou curiosidade com **dois personagens conversando** (sem imagens de IA). Os bonecos são desenhados
pelo programa: a boca abre e fecha junto com a fala, piscam, mudam de expressão e fazem gestos. Cada cena é **uma fala**.

- No roteiro, o bloco `toon` define os personagens (no máximo **2**) e o cenário:
  `"toon": {"background": "room", "characters": {"ana": {"name": "Ana", "voice": "pt-BR-FranciscaNeural"}, "leo": {"voice": "pt-BR-AntonioNeural", "hair": "spiky", "glasses": true}}}`.
  `background`: `room` (sala em preto e branco), `plain` (fundo liso) ou o caminho de uma imagem. Por personagem:
  `voice`, `side` (`left` ou `right`), `hair` (`none`, `ponytail`, `bob`, `spiky`), `hair_color`, `shirt`, `pants` (cores `[R, G, B]`) e `glasses`.
- Em cada cena de cartum use `speaker` (o `id` do personagem que fala) e `narration` (a fala). Opcionais:
  `emotion` de quem fala e `reaction` de quem escuta: `neutral`, `happy`, `angry`, `sad`, `surprised`, `thinking`, `smug`;
  `gesture`: `none`, `point`, `hip`, `open`, `shrug`; `camera`: `auto` (1ª cena em plano aberto, depois fecha em quem fala), `wide` ou `speaker`;
  `voice` troca a voz só nesta fala.
- Use `"subtitles": "topbox"`, `"resolution": "1080x1920"` e `"images": {"provider": "none"}`. Não use `prompt`, `items` nem `chart` nas cenas de cartum.
- Fale como em um diálogo: frases curtas, perguntas e respostas, 6 a 16 palavras por fala. Varie `emotion` e `gesture`.

## 6. Gráficos

```json
"chart": {"type": "bar", "labels": ["A", "B", "C"], "values": [50, 30, 20], "unit": "%",
          "highlight": 0, "source": "Autor et al., Revista, 2023", "on_words": ["primeiro", "segundo", "terceiro"]}
```

- `type`: `bar` (barras), `barh` (barras horizontais) ou `line` (linha; para várias séries use
  `"series": [{"name": "X", "values": [...]}, ...]` no lugar de `values`).
- `labels` e `values` (ou cada `series[].values`) têm **exatamente o mesmo tamanho**. No máximo 5 barras;
  rótulos curtos (até 14 letras).
- `unit` (ex.: `"%"`), `decimals`, `highlight` (índice da barra em destaque), `source` (texto da fonte).
- `on_words`: uma palavra da narração por rótulo; a barra entra quando a palavra é dita.
- Opcionais: `orient` (`horizontal` ou `vertical`), `zero` (`true` força o zero no eixo da linha), `animate`
  (`false` desliga a animação), `on_word`, `at`.

## 7. Ritmo e estrutura

- A voz fala cerca de **2,5 palavras por segundo**.
- **Short vertical** (`"resolution": "1080x1920"`, `"subtitles": "pop"`, `"default_transition": "punch"`):
  25 a 55 s no total, **7 a 12 cenas** de 2 a 5 s (6 a 14 palavras cada). A 1ª cena é o gancho (uma pergunta ou
  uma ideia surpreendente, sem inventar dado). A última fecha com uma frase curta. Alterne os tipos de cena
  (imagem, lista, número, gráfico) e evite mais de 2 imagens seguidas.
- **Vídeo horizontal** (`"resolution": "1920x1080"`, `"subtitles": "karaoke"`): cenas de 8 a 20 s
  (20 a 50 palavras); use `chapter` e `fade` entre blocos.
- **Gancho (1ª cena: decide se a pessoa fica).** A 1ª frase tem **até 8 palavras** e começa pela promessa ou pela pergunta. O elemento principal (número, pergunta no `headline`, imagem) tem de estar na tela **já no primeiro quadro**: em `number` e `chart` use `"at": 0`. Use `punch` ou `flash` na 1ª cena: ela começa sem 0,5 s de tela preta e silêncio.
- **Em Short, evite `fade`**: ele escurece a tela e acrescenta ~1 s de silêncio entre as cenas. Use `punch`, `flash` ou `cut`.
- Uma ideia por cena. Frase curta, voz ativa, sem jargão sem explicar.

## 8. Prompts de imagem

- Em inglês, descrevendo assunto, cenário, composição e clima. No vertical, peça "vertical composition,
  subject centered".
- **Cada imagem tem uma função**: o `prompt` deve ilustrar o que a narração diz *naquela* cena (o objeto, a ação ou a ideia citada). Evite imagens só decorativas ou abstratas que o espectador não consiga ligar à frase.
- **No vertical, peça que a imagem ocupe o quadro inteiro**: `tall vertical full-bleed illustration that fills the entire frame edge to edge, no empty margins or flat bands`. Sem isso o modelo às vezes devolve uma cena horizontal no meio de um fundo liso, e sobra pouco da imagem na tela.
- O **estilo visual fica em `images.style`**, uma vez só. Não repita o estilo em cada `prompt`.
- Personagem recorrente: repita a **mesma descrição física** em todos os prompts em que ele aparece
  (ex.: `"the same young nurse with short black hair and teal scrubs"`).
- Nunca peça texto, letras, números, logotipos nem marcas d'água dentro da imagem (o programa escreve o texto).
- Sem pessoas reais, celebridades, rostos identificáveis, marcas ou materiais protegidos.

## 9. Exemplo completo (vertical, formato mínimo)

No pedido deste exemplo o usuário forneceu: *"Respiratória 42%, Cardiovascular 28%, Outras 30% — Autor Fictício et al., Revista Exemplo, 2020"* (fonte fictícia, só para ilustrar este guia).

```json
{
  "title": "Por que a UTI se preocupa com a respiração",
  "channel": "Dados na Saúde",
  "theme": "health",
  "resolution": "1080x1920",
  "fps": 30,
  "voice": "pt-BR-FranciscaNeural",
  "subtitles": "pop",
  "default_transition": "punch",
  "images": {"provider": "gemini", "style": "editorial flat illustration, soft cinematic light, dark navy and teal palette, no text"},
  "scenes": [
    {
      "id": "gancho",
      "title": "Gancho",
      "headline": "ADMISSÃO NA UTI",
      "overlay_title": true,
      "narration": "Quando alguém chega à UTI, os primeiros minutos decidem muita coisa.",
      "prompt": "intensive care room at night, empty bed beside a glowing monitor, calm atmosphere, vertical composition",
      "revisar": ["Afirmação geral: confirmar a formulação com a equipe clínica"]
    },
    {
      "id": "abcd",
      "title": "O que se verifica",
      "headline": "AVALIAÇÃO INICIAL",
      "narration": "A equipe olha as vias aéreas, a respiração e a circulação.",
      "items": [
        {"key": "A", "text": "Vias aéreas", "on_word": "vias"},
        {"key": "B", "text": "Respiração", "on_word": "respiração"},
        {"key": "C", "text": "Circulação", "on_word": "circulação"}
      ]
    },
    {
      "id": "causas",
      "title": "Causas",
      "headline": "CAUSAS DE ADMISSÃO",
      "transition": "flash",
      "narration": "As causas respiratórias aparecem primeiro, depois as cardiovasculares.",
      "chart": {"type": "bar", "labels": ["Respiratória", "Cardiovascular", "Outras"], "values": [42, 28, 30], "unit": "%", "highlight": 0, "source": "Autor Fictício et al., Revista Exemplo, 2020", "on_words": ["respiratórias", "cardiovasculares", "outras"]}
    },
    {
      "id": "fecho",
      "title": "Fecho",
      "headline": "SEGUE O CANAL",
      "narration": "Siga o canal para ver mais dados que ajudam a cuidar melhor."
    }
  ]
}
```

## 10. Antes de responder, confira

- [ ] É um único JSON válido, sem texto fora dele.
- [ ] Toda cena tem `narration`, e ela contém só o que será falado.
- [ ] Nenhum número, estudo ou referência foi inventado: todo número veio do Pedido e tem a fonte em `source`.
      Onde faltou dado não há número nem gráfico, e a lacuna está em `revisar`.
- [ ] Nenhum texto do vídeo diz "A VERIFICAR", "exemplo" ou "ilustrativo".
- [ ] `labels` e `values` têm o mesmo tamanho em todos os gráficos.
- [ ] Só usei campos e valores deste guia (`transition`, `motion`, `subtitles`, `layout`).
- [ ] O `id` de cada cena é único. O estilo visual está em `images.style`, não repetido nos `prompt`.
- [ ] A duração total bate com o pedido (≈ 2,5 palavras por segundo).

---

# Pedido

- **Tema:** [escreva o tema do vídeo]
- **Canal / público / tom:** [ex.: Dados na Saúde — profissionais de saúde — didático e direto]
- **Formato:** [vertical 9:16 (Short) ou horizontal 16:9]
- **Duração desejada:** [ex.: 45 s]
- **Dados e fontes que EU forneço** (só estes podem virar número ou gráfico): [cole cada número com a sua fonte (autor, revista, ano ou link), ou escreva "nenhum"]
