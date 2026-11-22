"""Gráficos (matplotlib) no visual do canal, legíveis no celular."""
from .util import StudioError


def render_chart(spec, background, dest, w, h, accent, muted, font_path, top=0.27, bottom=0.79):
    """Desenha o gráfico sobre `background` (PIL.Image) na área entre `top` e `bottom` (fração da altura).
    spec: {"type": "bar"|"barh"|"line", "labels": [...], "values": [...] ou
           "series": [{"name": ..., "values": [...]}], "unit": "%", "highlight": índice}"""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from matplotlib import font_manager
    except ImportError:
        raise StudioError('Para gráficos instale o matplotlib: pip install -r requirements.txt')
    from PIL import Image

    kind = spec.get('type', 'bar')
    labels = [str(x) for x in spec.get('labels', [])]
    series = spec.get('series') or [{'name': '', 'values': spec.get('values', [])}]
    if not labels or any(len(s.get('values', [])) != len(labels) for s in series):
        raise StudioError('Gráfico: "labels" e "values" precisam ter o mesmo tamanho.')
    unit = spec.get('unit', '')
    hl = spec.get('highlight')

    font_manager.fontManager.addfont(str(font_path))
    family = font_manager.FontProperties(fname=str(font_path)).get_name()
    px = 1 / 100
    pad = 0.075
    area_w, area_h = w * (1 - 2 * pad), h * (bottom - top)
    fs = max(10, h * 0.022)  # tamanho em pontos com dpi=100
    fig = plt.figure(figsize=(area_w * px, area_h * px), dpi=100)
    fig.patch.set_alpha(0)
    simple_bars = kind in ('bar', 'barh') and len(series) == 1
    ax = fig.add_axes([0.02, 0.14, 0.96, 0.82] if simple_bars else [0.07, 0.14, 0.86, 0.82])
    ax.patch.set_alpha(0)
    acc = tuple(c / 255 for c in accent)
    mut = tuple(c / 255 for c in muted)
    white = (1, 1, 1)

    def fmt(v):
        txt = f'{v:,.{spec.get("decimals", 0)}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
        return f'{txt}{unit}'

    if kind in ('bar', 'barh') and len(series) == 1:
        vals = series[0]['values']
        colors = [acc if (hl is None or i == hl) else (*mut, 0.55) for i in range(len(vals))]
        if kind == 'bar':
            bars = ax.bar(labels, vals, color=colors, width=0.62)
            ax.set_ylim(0, max(vals) * 1.22 if max(vals) > 0 else 1)
            ax.tick_params(axis='x', colors=white, labelsize=fs, length=0)
            ax.set_yticks([])
            for b, v in zip(bars, vals):
                ax.text(b.get_x() + b.get_width() / 2, b.get_height() + max(vals) * 0.03, fmt(v),
                        ha='center', va='bottom', color=white, fontsize=fs * 1.15, fontweight='bold', family=family)
        else:
            order = list(range(len(vals)))[::-1]
            bars = ax.barh([labels[i] for i in order], [vals[i] for i in order],
                           color=[colors[i] for i in order], height=0.6)
            ax.set_xlim(0, max(vals) * 1.25 if max(vals) > 0 else 1)
            ax.tick_params(axis='y', colors=white, labelsize=fs, length=0)
            ax.set_xticks([])
            for b, i in zip(bars, order):
                ax.text(b.get_width() + max(vals) * 0.02, b.get_y() + b.get_height() / 2, fmt(vals[i]),
                        va='center', color=white, fontsize=fs * 1.1, fontweight='bold', family=family)
    else:
        palette_lines = [acc, (*mut, 1.0), (1, 0.75, 0.55), (0.75, 0.65, 1)]
        for n, s in enumerate(series):
            color = palette_lines[n % len(palette_lines)]
            if kind == 'line':
                ax.plot(labels, s['values'], color=color, linewidth=max(2, h / 270), marker='o',
                        markersize=h / 160, label=s.get('name') or None)
                ax.annotate(fmt(s['values'][-1]), (len(labels) - 1, s['values'][-1]), xytext=(8, 0),
                            textcoords='offset points', va='center', color=color, fontsize=fs, fontweight='bold',
                            family=family)
            else:
                width = 0.8 / len(series)
                xs = [i + (n - (len(series) - 1) / 2) * width for i in range(len(labels))]
                ax.bar(xs, s['values'], width=width * 0.92, color=color, label=s.get('name') or None)
        if kind != 'line':
            ax.set_xticks(range(len(labels)), labels)
        ax.tick_params(colors=white, labelsize=fs, length=0)
        ax.grid(axis='y', color=white, alpha=0.12)
        ax.yaxis.set_major_formatter(lambda v, _pos: fmt(v))
        if len(series) > 1 and any(s.get('name') for s in series):
            leg = ax.legend(frameon=False, fontsize=fs, loc='upper left')
            for t in leg.get_texts():
                t.set_color(white)
    for side in ('top', 'right', 'left'):
        ax.spines[side].set_visible(False)
    ax.spines['bottom'].set_color((1, 1, 1, 0.35))
    for t in ax.get_xticklabels() + ax.get_yticklabels():
        t.set_family(family)
    tmp = dest.with_suffix('.chart.png')
    fig.savefig(tmp, transparent=True, dpi=100)
    plt.close(fig)
    layer = Image.open(tmp).convert('RGBA')
    bg = background.convert('RGBA')
    bg.alpha_composite(layer, (int(w * pad), int(h * top)))
    bg.convert('RGB').save(dest)
    tmp.unlink(missing_ok=True)
