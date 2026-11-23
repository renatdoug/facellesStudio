# Biblioteca de personagens ilustrados (por recortes)

Cada personagem é uma pasta `personagens/<nome>/` ao lado dos roteiros do canal. No roteiro, a ficha usa o nome da pasta:

```json
"toon": {"characters": {"marina": {"asset": "marina", "voice": "pt-BR-FranciscaNeural"}}}
```

`"asset"` é o nome da pasta (letras, números, `_` e `-`). `"scale"` (opcional, 0,2 a 1,5) fixa a largura da imagem inteira em relação à tela; sem ele, a personagem sozinha ocupa 80% da altura.

## Formato da pasta

- `personagem.json` (manifesto): `images` (arquivo de cada expressão; `neutra` é obrigatória e é o corpo-base), `ref_size` (largura e altura das imagens), `boxes` (`face`, `mouth` e, para piscar, `eye_l` e `eye_r`, em pixels da imagem), `neck`, `tilt_fade`, `tilt_gain`, `map` (emoção do roteiro -> imagem).
- As imagens: **mesmo tamanho e mesmo enquadramento** (o Gemini manteve 0-2 px de diferença usando a 1ª imagem como referência), fundo de cor sólida (magenta, `#FF00FF`), sem sombra nem cenário. JPEG serve: o recorte é por cor.
- Expressões: `neutra` (boca fechada), `feliz`, `surpresa` e `falando` (boca aberta). Emoções sem imagem própria usam a neutra.

## Marina (`marina/`)

As 4 imagens `marina_01_neutra`, `marina_02_feliz`, `marina_03_surpresa` e `marina_04_falando` são os **recursos-base** da personagem, gerados uma única vez pelo Gemini (R$ 2,48; prompts e parâmetros em `teste_marina/manifesto.json`). Não substitua nem regere: um novo desenho seria outra personagem. As cópias da biblioteca são idênticas às originais do experimento (`teste_marina/`).

## Limitações conhecidas

Piscar e aberturas intermediárias da boca são aproximações por código (pequenas imperfeições perto dos lábios); a cabeça não se separa do corpo (inclinação suave de poucos graus); sem gestos de braço; o enquadramento termina na coxa; só 4 expressões; apenas 1 personagem testado. Veja o CHANGELOG (v0.13.0).
