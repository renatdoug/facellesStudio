"""Pequenos construtores de linhas ASS compartilhados pelos layouts e pelos gráficos animados."""
from .subtitles import ass_color, ass_time

ASS_SCALE = 1.16  # no ASS o tamanho inclui ascendente+descendente; isto iguala ao tamanho do Pillow


def style(name, font, size, color, bold=False, box=None, align=7, outline=0, shadow=0):
    """Linha de estilo ASS. box=(cor, padding) desenha caixa opaca atrás do texto.
    `size` é o tamanho no Pillow (o mesmo usado para medir e quebrar as linhas)."""
    prim = ass_color(color)
    size = round(size * ASS_SCALE)
    if box:
        return (f'Style: {name},{font},{size},{prim},{prim},{ass_color(box[0])},&H80000000,'
                f'{-1 if bold else 0},0,0,0,100,100,0,0,3,{box[1]},0,{align},0,0,0,1')
    return (f'Style: {name},{font},{size},{prim},{prim},&H00101418,&H90000000,'
            f'{-1 if bold else 0},0,0,0,100,100,0,0,1,{outline},{shadow},{align},0,0,0,1')


def ev(start, end, style_name, text, layer=2, min_dur=0.2):
    """Evento ASS. `min_dur` impede eventos curtíssimos; passe um valor menor para animações
    quadro a quadro (contagens), em que eventos consecutivos NÃO podem se sobrepor."""
    return f'Dialogue: {layer},{ass_time(start)},{ass_time(max(end, start + min_dur))},{style_name},,0,0,0,,{text}'
