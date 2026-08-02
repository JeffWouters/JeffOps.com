#!/usr/bin/env python3
"""Generate the three inline SVG diagrams used in the 2026 posts.

Inline SVG rather than Mermaid, deliberately. Mermaid needs JavaScript and a
CDN, so a diagram ships to RSS subscribers as raw source and disappears
entirely if the CDN is unreachable. These render in a feed reader, with
scripting disabled, and offline.

The canvas is transparent and all text uses currentColor, so a diagram inherits
whatever it is placed on. It reads on the dark site, and it reads in a feed
reader that renders on white, without needing two versions. Meaning is carried
by shape and dash pattern as well as colour, so it survives greyscale and
colour-blindness.

Run:  python tools/make_diagrams.py    (writes tools/out/*.svg)
"""

from pathlib import Path

# currentColor inherits the surrounding text colour, so these adapt to the page.
TEXT = 'currentColor'
DIM = 'currentColor'          # differentiated by opacity, not by hue
EDGE = 'currentColor'
PANEL = 'none'                # transparent
BG = 'none'
CYAN = '#0aa5c4'              # readable on both white and near-black
WARM = '#d2593c'              # ditto

MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"

OUT = Path(__file__).parent / 'out'


def head(w, h, title, desc, uid):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
        f'width="{w}" height="{h}" role="img" aria-labelledby="{uid}t {uid}d" '
        f'style="max-width:100%;height:auto;display:block;margin:1.5rem 0">'
        f'<title id="{uid}t">{title}</title><desc id="{uid}d">{desc}</desc>'
        f'<defs><marker id="{uid}a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" '
        f'markerHeight="6" orient="auto-start-reverse">'
        f'<path d="M0,0 L10,5 L0,10 z" fill="{CYAN}"/></marker>'
        f'<marker id="{uid}aw" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" '
        f'markerHeight="6" orient="auto-start-reverse">'
        f'<path d="M0,0 L10,5 L0,10 z" fill="{WARM}"/></marker></defs>'
    )


def box(x, y, w, h, stroke=EDGE, fill=PANEL, dash=None, r=4, op=None):
    d = f' stroke-dasharray="{dash}"' if dash else ''
    if op is None:
        op = 0.28 if stroke == 'currentColor' else 1
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" '
            f'stroke="{stroke}" stroke-opacity="{op}" stroke-width="1.5"{d}/>')


def text(x, y, s, size=14, fill=TEXT, family=SANS, anchor='start', weight='400', op=None):
    if op is None:
        op = 0.62 if (fill == 'currentColor' and family == MONO) else 1
    return (f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" '
            f'fill="{fill}" fill-opacity="{op}" text-anchor="{anchor}" '
            f'font-weight="{weight}">{s}</text>')


def arrow(x1, y1, x2, y2, colour=CYAN, marker='a', dash=None, uid=''):
    d = f' stroke-dasharray="{dash}"' if dash else ''
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{colour}" '
            f'stroke-width="1.5" marker-end="url(#{uid}{marker})"{d}/>')


# ── 1. The transmission chain ─────────────────────────────────────────
def chain():
    UID = 'ch-'
    W, H = 760, 520
    s = [head(W, H, 'How a smaller resource request becomes a smaller bill',
              'A five step chain from reduced requests to a lower invoice, with four '
              'labelled points at which the chain commonly breaks.', UID)]
    stages = [
        ('1. Requests reduced', 'VPA, in-place resize'),
        ('2. Capacity freed', 'on the nodes you already run'),
        ('3. Pods consolidate', 'packing, Karpenter consolidation'),
        ('4. Node removed', 'autoscaler drains and deletes'),
        ('5. Invoice falls', 'the only step finance sees'),
    ]
    # One annotation per gap. Most failures cluster on the same step, which is
    # itself the point, so they are listed together rather than spread out.
    breaks = [
        (1, ['LeastAllocated spreads pods,', 'so no node ever empties']),
        (2, ['\u00b7 Injected anti-affinity makes', '  consolidation skip the node',
             '\u00b7 consolidateAfter resets on churn', '\u00b7 A PodDisruptionBudget blocks',
             '  the last eviction']),
    ]
    bx, bw, bh, gap = 24, 330, 62, 32
    for i, (title, sub) in enumerate(stages):
        y = 30 + i * (bh + gap)
        accent = CYAN if i in (0, 4) else EDGE
        s.append(box(bx, y, bw, bh, stroke=accent))
        s.append(text(bx + 16, y + 26, title, 15, TEXT, SANS, weight='600'))
        s.append(text(bx + 16, y + 46, sub, 12, DIM, MONO))
        if i < len(stages) - 1:
            s.append(arrow(bx + bw / 2, y + bh + 4, bx + bw / 2, y + bh + gap - 4, uid=UID))
    for after, lines in breaks:
        y = 30 + after * (bh + gap) + bh + gap / 2
        s.append(arrow(bx + bw + 78, y, bx + bw + 14, y, WARM, 'aw', dash='4 3', uid=UID))
        top = y - 6 - (len(lines) - 1) * 7
        s.append(text(bx + bw + 86, top, 'breaks here', 11, WARM, MONO, weight='600'))
        for j, line in enumerate(lines):
            s.append(text(bx + bw + 86, top + 17 + j * 14, line, 11.5, DIM, SANS))
    s.append(text(bx, H - 12,
                  'Steps 2 to 4 are where cost work quietly fails. A dashboard improves; the bill does not.',
                  12, DIM, SANS, op=0.7))
    return ''.join(s) + '</svg>'


def wrap(sentence, width):
    words, lines, cur = sentence.split(), [], ''
    for w in words:
        if len(cur) + len(w) + 1 > width and cur:
            lines.append(cur); cur = w
        else:
            cur = f'{cur} {w}'.strip()
    if cur:
        lines.append(cur)
    return lines


# ── 2. Three blast radii ──────────────────────────────────────────────
def blast():
    UID = 'bl-'
    W, H = 880, 350
    s = [head(W, H, 'Three ways to share a GPU, and the blast radius of each',
              'Time-slicing places four pods in one shared fault domain. A shared '
              'inference server places every tenant inside a single process. MIG gives '
              'each pod an isolated hardware partition.', UID)]
    panels = [
        ('Time-slicing', 'one shared fault domain', 'a crash takes all four', WARM, 'shared'),
        ('Shared server', 'one process, every tenant', 'the largest single domain', WARM, 'single'),
        ('MIG', 'hardware partitions', 'a fault stays in its slice', CYAN, 'isolated'),
    ]
    pw, gap, px, py, ph = 250, 40, 20, 62, 200
    for i, (name, sub, note, accent, kind) in enumerate(panels):
        x = px + i * (pw + gap)
        s.append(text(x, 24, name, 15, TEXT, SANS, weight='600'))
        s.append(text(x, 42, sub, 11.5, DIM, MONO))
        s.append(box(x, py, pw, ph, stroke=EDGE))
        s.append(text(x + 12, py + 22, 'GPU', 11, DIM, MONO))
        if kind == 'shared':
            s.append(box(x + 12, py + 34, pw - 24, ph - 62, stroke=WARM, fill='none', dash='5 4'))
            for j in range(4):
                s.append(box(x + 24 + (j % 2) * 106, py + 48 + (j // 2) * 52, 92, 40, stroke=EDGE, fill='none'))
                s.append(text(x + 70 + (j % 2) * 106, py + 73 + (j // 2) * 52, f'pod {j + 1}',
                              12, TEXT, MONO, anchor='middle'))
        elif kind == 'single':
            s.append(box(x + 12, py + 34, pw - 24, ph - 62, stroke=WARM, fill='none', dash='5 4'))
            s.append(box(x + 26, py + 48, pw - 52, ph - 92, stroke=EDGE, fill='none'))
            s.append(text(x + pw / 2, py + 70, 'one server process', 12, TEXT, MONO, anchor='middle'))
            s.append(text(x + pw / 2, py + 92, 'tenant A  B  C  D', 12, DIM, MONO, anchor='middle'))
        else:
            for j in range(4):
                s.append(box(x + 24 + (j % 2) * 106, py + 44 + (j // 2) * 52, 92, 40,
                             stroke=CYAN, fill='none', dash='5 4'))
                s.append(text(x + 70 + (j % 2) * 106, py + 69 + (j // 2) * 52, f'pod {j + 1}',
                              12, TEXT, MONO, anchor='middle'))
        s.append(text(x + 12, py + ph - 14, note, 12, accent, SANS, weight='600'))
    s.append(text(px, H - 14,
                  'Dashed boundary = fault domain. Density rises left to right in cost, not in safety.',
                  12, DIM, SANS, op=0.7))
    return ''.join(s) + '</svg>'


# ── 3. The evaluation deadlock ────────────────────────────────────────
def deadlock():
    UID = 'dl-'
    W, H = 720, 380
    s = [head(W, H, 'The privacy and evaluation deadlock',
              'A four step cycle: scoring quality requires message content, message '
              'content is sensitive and off by default, so spans carry no content, so '
              'the evaluator returns no score.', UID)]
    nodes = [
        (360, 44, 'You want a quality score', 'groundedness, tool-call accuracy'),
        (560, 190, 'The evaluator needs content', 'gen_ai.*.messages must be present'),
        (360, 336, 'Spans carry no content', 'nothing to evaluate against'),
        (160, 190, 'Content is sensitive', 'opt-in, and off by default'),
    ]
    bw, bh = 250, 62
    for cx, cy, title, sub in nodes:
        s.append(box(cx - bw / 2, cy - bh / 2, bw, bh, stroke=EDGE))
        s.append(text(cx, cy - 6, title, 14, TEXT, SANS, anchor='middle', weight='600'))
        s.append(text(cx, cy + 15, sub, 11, DIM, MONO, anchor='middle'))
    ring = [
        (470, 62, 545, 158),
        (545, 222, 470, 318),
        (250, 318, 175, 222),
        (175, 158, 250, 62),
    ]
    for x1, y1, x2, y2 in ring:
        s.append(arrow(x1, y1, x2, y2, WARM, 'aw', uid=UID))
    s.append(text(360, 186, 'no way out', 13, WARM, MONO, anchor='middle', weight='600'))
    s.append(text(360, 206, 'without a deliberate trade', 11, DIM, SANS, anchor='middle'))
    return ''.join(s) + '</svg>'


# ── 4. The closing gap ────────────────────────────────────────────────
def gap():
    """The arbitrage an internal platform is making, and its expiry.

    Deliberately drawn as a schematic rather than a chart. There is no dataset
    behind either curve and the axes carry no units, because the claim is about
    shape, not magnitude. Anything that looked like a measurement here would be
    a fabricated one, and this post is partly about fabricated numbers.
    """
    UID = 'gp-'
    W, H = 780, 440
    s = [head(W, H, 'Why an internal platform has an expiry date',
              'Two schematic curves. The effort of doing it yourself falls steadily as '
              'the market improves, while the effort of doing it through your platform '
              'stays roughly flat. The shaded gap between them is the value the '
              'platform provides, and it closes on its own.', UID)]

    X0, X1 = 110, 690
    n = 60
    diy, plat = [], []
    for i in range(n + 1):
        t = i / n
        x = X0 + t * (X1 - X0)
        # Higher on the page (smaller y) means more effort.
        diy.append((x, 88 + 212 * (t ** 0.75)))
        plat.append((x, 234 + 12 * t))

    # Where the market catches up. Found by scanning rather than solved for,
    # because the curves are illustrative and an exact root would imply a
    # precision the diagram does not have.
    cross = next((i for i in range(n + 1) if diy[i][1] > plat[i][1]), n)
    cx, cy = plat[cross]

    s.append(f'<line x1="{X0}" y1="46" x2="{X0}" y2="340" stroke="{EDGE}" '
             f'stroke-opacity="0.28" stroke-width="1.5"/>')
    s.append(f'<line x1="{X0}" y1="340" x2="{X1 + 24}" y2="340" stroke="{EDGE}" '
             f'stroke-opacity="0.28" stroke-width="1.5"/>')
    s.append(text(X0 - 10, 50, 'more effort', 11, DIM, MONO, anchor='end'))
    s.append(text(X0 - 10, 336, 'less', 11, DIM, MONO, anchor='end'))
    s.append(text(X1 + 24, 358, 'time', 11, DIM, MONO, anchor='end'))

    # The gap itself, as a closed region between the two curves.
    region = diy[:cross + 1] + list(reversed(plat[:cross + 1]))
    pts = ' '.join(f'{x:.1f},{y:.1f}' for x, y in region)
    s.append(f'<polygon points="{pts}" fill="{CYAN}" fill-opacity="0.14" stroke="none"/>')

    def poly(points, colour, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ''
        p = ' '.join(f'{x:.1f},{y:.1f}' for x, y in points)
        return (f'<polyline points="{p}" fill="none" stroke="{colour}" '
                f'stroke-width="2"{d}/>')

    s.append(poly(plat, CYAN))
    s.append(poly(diy, WARM, dash='6 4'))

    s.append(text(X0 + 18, 66, 'Doing it yourself', 13.5, WARM, SANS, weight='600'))
    s.append(text(X0 + 18, 84, 'falls every quarter, without anyone telling you',
                  11.5, DIM, SANS))
    s.append(text(X0 + 18, 272, 'Doing it through your platform', 13.5, CYAN, SANS,
                  weight='600'))
    s.append(text(X0 + 18, 290, 'roughly flat, and you pay to keep it there', 11.5, DIM, SANS))

    # Sits inside the wedge. The band narrows to the right as the curves
    # converge, so the label is centred left of middle where there is room for
    # two lines without either touching a curve.
    s.append(text(240, 200, 'the gap you are arbitraging', 12.5, TEXT, SANS,
                  anchor='middle', weight='600'))
    # Not "the whole business case": there are no units on either axis and no
    # cost side to the argument, so a business-case claim here would be one the
    # diagram cannot support. It shows what closing does, and nothing else.
    s.append(text(240, 216, 'when this closes, so does the platform', 10.5, DIM, MONO,
                  anchor='middle'))

    s.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="5.5" fill="none" stroke="{WARM}" '
             f'stroke-width="2"/>')
    s.append(f'<line x1="{cx:.1f}" y1="{cy - 11:.1f}" x2="{cx:.1f}" y2="132" '
             f'stroke="{WARM}" stroke-width="1.5" stroke-dasharray="3 3"/>')
    s.append(text(cx + 12, 124, 'the abstraction stops being scarce', 12.5, WARM,
                  SANS, weight='600'))
    s.append(text(cx + 12, 142, 'nothing failed; the market moved', 11, DIM, SANS))

    s.append(text(X0, H - 34,
                  'GOV.UK PaaS reached this point with 172 services, 3,200 apps and '
                  '99.95% uptime, and was retired anyway.',
                  12, DIM, SANS, op=0.75))
    s.append(text(X0, H - 14,
                  'Schematic. The shape is the argument; neither curve is measured.',
                  12, DIM, MONO, op=0.6))
    return ''.join(s) + '</svg>'


if __name__ == '__main__':
    OUT.mkdir(exist_ok=True)
    for name, fn in (('chain', chain), ('blast', blast), ('deadlock', deadlock),
                     ('gap', gap)):
        path = OUT / f'{name}.svg'
        path.write_text(fn(), encoding='utf-8')
        print(f'{path}  {len(path.read_text(encoding="utf-8")):,} bytes')
