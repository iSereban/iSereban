"""
Чертежи объектов по спецификациям (без Blender, обычный Python + matplotlib).

Для каждого объекта: вид спереди, вид слева, вид сверху (план), размеры в мм, штамп.
Запуск:  python drawings.py [--out out/drawings] [--only sofa,tv]
"""

import math
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Polygon  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from palette import PALETTE  # noqa: E402


# ---------------------------------------------------------------------------
def _rot(p, deg):
    """Эйлер XYZ (как в Blender): R = Rz·Ry·Rx."""
    rx, ry, rz = (math.radians(a) for a in deg)
    x, y, z = p
    y, z = y * math.cos(rx) - z * math.sin(rx), y * math.sin(rx) + z * math.cos(rx)
    x, z = x * math.cos(ry) + z * math.sin(ry), -x * math.sin(ry) + z * math.cos(ry)
    x, y = x * math.cos(rz) - y * math.sin(rz), x * math.sin(rz) + y * math.cos(rz)
    return (x, y, z)


def part_points(part):
    t = part["t"]
    pts = []
    if t == "box":
        w, d, h = part["s"]
        pts = [(sx * w / 2, sy * d / 2, sz * h / 2) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    elif t in ("cyl", "cone"):
        r1 = part.get("r", part.get("r1", 10))
        r2 = part.get("r", part.get("r2", 10))
        h = part["h"]
        for k in range(24):
            a = 2 * math.pi * k / 24
            pts += [(r1 * math.cos(a), r1 * math.sin(a), -h / 2), (r2 * math.cos(a), r2 * math.sin(a), h / 2)]
        ax = part.get("axis", "z")
        if ax == "x":
            pts = [_rot(q, (0, 90, 0)) for q in pts]
        elif ax == "y":
            pts = [_rot(q, (90, 0, 0)) for q in pts]
    elif t == "sph":
        rx, ry, rz = part["s"]
        for i in range(1, 12):
            th = math.pi * i / 12
            for k in range(16):
                a = 2 * math.pi * k / 16
                pts.append((rx * math.sin(th) * math.cos(a), ry * math.sin(th) * math.sin(a), rz * math.cos(th)))
        pts += [(0, 0, rz), (0, 0, -rz)]
    elif t == "mesh":
        vs = part["v"]
        step = max(1, len(vs) // 3000)
        pts = [tuple(v) for v in vs[::step]]
    elif t == "text":
        s = part.get("size", 200)
        w = 0.62 * s * len(part["text"])
        d = part.get("depth", 20)
        pts = [(sx * w / 2, sy * d / 2, sz * s / 2) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    if part.get("rot"):
        pts = [_rot(q, part["rot"]) for q in pts]
    cx, cy, cz = part["p"]
    return [(x + cx, y + cy, z + cz) for x, y, z in pts]


def hull(pts):
    pts = sorted(set((round(a, 3), round(b, 3)) for a, b in pts))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def srgb(c):
    return tuple(min(1.0, max(0.0, v)) ** (1 / 2.2) for v in c)


def nice_step(size):
    for s in (10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000):
        if size / s <= 14:
            return s
    return 20000


VIEWS = {
    # имя: (индексы осей 2D, индекс глубины, знак сортировки, подпись)
    "front": ((0, 2), 1, -1, "Вид спереди (фасад)"),
    "side": ((1, 2), 0, -1, "Вид слева"),
    "top": ((0, 1), 2, +1, "Вид сверху (план)"),
}


def _scale_mm(ax):
    """Сколько мм модели в одном мм бумаги (грубо, до установки пределов берём 1)."""
    try:
        x0, x1 = ax.get_xlim()
        w_in = ax.get_window_extent().width / ax.figure.dpi
        return (x1 - x0) / (w_in * 25.4)
    except Exception:
        return 1.0


def draw_view(ax, spec, view, dims=True):
    (ia, ib), idepth, sgn, label = VIEWS[view]
    items = []
    for part in spec["parts"]:
        pts = part_points(part)
        depth = sum(p[idepth] for p in pts) / len(pts)
        items.append((depth * sgn, part, pts))
    # дальние — раньше (перекрываются ближними): спереди дальше — большой Y,
    # слева дальше — большой X, сверху дальше — малый Z
    items.sort(key=lambda it: it[0])
    _X = [p[ia] for _d, _p, pts in items for p in pts]
    _Y = [p[ib] for _d, _p, pts in items for p in pts]
    _pad = max(max(_X) - min(_X), max(_Y) - min(_Y)) * 0.12 + 30
    ax.set_xlim(min(_X) - _pad, max(_X) + _pad)
    ax.set_ylim(min(_Y) - _pad, max(_Y) + _pad)
    ax.set_aspect("equal")
    allx, ally = [], []
    for _d, part, pts in items:
        if part.get("draw") == "skeleton":
            for sg in part["segs"]:
                a, b = sg[0:3], sg[3:6]
                lw = max(0.3, (sg[6] + sg[7]) / 2 * 2 * 72 / 25.4 / max(1.0, _scale_mm(ax)))
                ax.plot([a[ia], b[ia]], [a[ib], b[ib]], color=srgb(PALETTE[part["m"]]["c"]), lw=lw,
                        solid_capstyle="round", zorder=2)
            allx += [v[ia] for v in pts]
            ally += [v[ib] for v in pts]
            continue
        if part.get("draw") == "crown":
            col = srgb(PALETTE.get(part.get("m"), {"c": (0.2, 0.5, 0.2)})["c"])
            ax.scatter([v[ia] for v in pts], [v[ib] for v in pts], s=2.5, color=col, alpha=0.55, lw=0, zorder=3)
            allx += [v[ia] for v in pts]
            ally += [v[ib] for v in pts]
            continue
        h2 = hull([(p[ia], p[ib]) for p in pts])
        allx += [q[0] for q in h2]
        ally += [q[1] for q in h2]
        col = srgb(PALETTE.get(part.get("m"), {"c": (0.5, 0.5, 0.5)})["c"])
        ax.add_patch(Polygon(h2, closed=True, facecolor=col, edgecolor="#1b1b1b", linewidth=0.45, alpha=0.92))
        if part["t"] == "text" and view == "front":
            ax.text(part["p"][0], part["p"][2], part["text"], ha="center", va="center", fontsize=7, color="#111")
    x0, x1, y0, y1 = min(allx), max(allx), min(ally), max(ally)
    w, h = x1 - x0, y1 - y0
    pad = max(w, h) * 0.12 + 30
    ax.set_xlim(x0 - pad, x1 + pad)
    ax.set_ylim(y0 - pad, y1 + pad)
    ax.set_aspect("equal")
    step = nice_step(max(w, h))
    ax.set_xticks([k * step for k in range(math.floor((x0 - pad) / step), math.ceil((x1 + pad) / step) + 1)])
    ax.set_yticks([k * step for k in range(math.floor((y0 - pad) / step), math.ceil((y1 + pad) / step) + 1)])
    ax.tick_params(labelsize=6)
    ax.grid(True, color="#9bb", linewidth=0.3, alpha=0.6)
    ax.set_title(label, fontsize=9)
    axis_names = "XYZ"
    ax.set_xlabel(f"{axis_names[ia]}, мм", fontsize=7)
    ax.set_ylabel(f"{axis_names[ib]}, мм", fontsize=7)
    if dims:
        _dim(ax, x0, y0 - pad * 0.45, x1, y0 - pad * 0.45, f"{w:.0f}")
        _dim(ax, x0 - pad * 0.45, y0, x0 - pad * 0.45, y1, f"{h:.0f}", vertical=True)
    return w, h


def _dim(ax, xa, ya, xb, yb, text, vertical=False):
    ax.annotate("", xy=(xa, ya), xytext=(xb, yb), arrowprops=dict(arrowstyle="<->", lw=0.7, color="#b00"))
    mx, my = (xa + xb) / 2, (ya + yb) / 2
    ax.text(mx, my, text, color="#b00", fontsize=7, ha="center", va="center",
            rotation=90 if vertical else 0, bbox=dict(facecolor="white", edgecolor="none", pad=0.5))


def bbox(spec):
    P = [p for part in spec["parts"] for p in part_points(part)]
    return [min(p[i] for p in P) for i in range(3)], [max(p[i] for p in P) for i in range(3)]


def draw_object(spec, path):
    fig = plt.figure(figsize=(16, 10), dpi=90)
    gs = fig.add_gridspec(2, 2, width_ratios=[1.3, 1], height_ratios=[1, 1])
    draw_view(fig.add_subplot(gs[0, 0]), spec, "front")
    draw_view(fig.add_subplot(gs[0, 1]), spec, "side")
    draw_view(fig.add_subplot(gs[1, 0]), spec, "top")
    info = fig.add_subplot(gs[1, 1])
    info.axis("off")
    lo, hi = bbox(spec)
    W, D, H = (hi[i] - lo[i] for i in range(3))
    mats = {}
    for part in spec["parts"]:
        mats[part.get("m", "?")] = mats.get(part.get("m", "?"), 0) + 1
    lines = [
        f"ЧЕРТЁЖ ОБЪЕКТА: {spec['title']}",
        f"Код: {spec['name']}      Группа: {spec.get('group', '')}",
        "",
        f"Габариты (Ш×Г×В): {W:.0f} × {D:.0f} × {H:.0f} мм",
        f"Деталей: {len(spec['parts'])}",
        "Начало координат: центр основания, фасад в −Y, Z вверх",
        f"Координаты X: {lo[0]:.0f}…{hi[0]:.0f}   Y: {lo[1]:.0f}…{hi[1]:.0f}   Z: {lo[2]:.0f}…{hi[2]:.0f}",
    ]
    if spec.get("note"):
        lines += ["", f"Примечание: {spec['note']}"]
    lines += ["", "Материалы (деталей):"]
    for m, n in sorted(mats.items(), key=lambda kv: -kv[1])[:14]:
        lines.append(f"      {m} — {n}")
    info.text(0.02, 0.98, "\n".join(lines), va="top", ha="left", fontsize=10, family="DejaVu Sans")
    y = 0.98 - 0.043 * (len(lines) - min(len(mats), 14))
    for i, (m, _n) in enumerate(sorted(mats.items(), key=lambda kv: -kv[1])[:14]):
        col = srgb(PALETTE.get(m, {"c": (0.5, 0.5, 0.5)})["c"])
        info.add_patch(plt.Rectangle((0.015, y - 0.043 * (i + 1) + 0.008), 0.018, 0.025, color=col,
                                     transform=info.transAxes))
    info.add_patch(plt.Rectangle((0, 0), 1, 1, fill=False, lw=1.5, transform=info.transAxes))
    fig.suptitle(f"{spec['title']} — {W:.0f}×{D:.0f}×{H:.0f} мм", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(path)
    plt.close(fig)


def all_specs():
    import catalog_city
    import catalog_furniture
    import catalog_girl
    specs, seen = [], set()
    for f in list(catalog_furniture.CATALOG.values()) + list(catalog_city.CATALOG.values()) + \
            list(catalog_girl.CATALOG.values()):
        s = f()
        if s["name"] not in seen:
            seen.add(s["name"])
            specs.append(s)
    return specs


def main():
    argv = sys.argv[1:]
    out = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join(os.path.dirname(__file__), "out", "drawings")
    only = argv[argv.index("--only") + 1].split(",") if "--only" in argv else None
    os.makedirs(out, exist_ok=True)
    for s in all_specs():
        if only and s["name"] not in only:
            continue
        path = os.path.join(out, f"{s['name']}.png")
        draw_object(s, path)
        print("drawing", path)


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# План сцены: объекты, расставленные по координатам
# ---------------------------------------------------------------------------
def _xf(pt, x, y, z, rot):
    a = math.radians(rot)
    px, py, pz = pt
    return (px * math.cos(a) - py * math.sin(a) + x, px * math.sin(a) + py * math.cos(a) + y, pz + z)


def draw_plan(items, path, title, walls=(), rooms=(), openings=(), size=(16, 11), label_min=0, grid_step=None,
              dims=()):
    """items: [{"spec", "x", "y", "z", "rot", "label"}] (мм, градусы).
    walls: [(x0, y0, x1, y1)] прямоугольники стен; rooms: [(name, x0, y0, x1, y1)];
    openings: [("door"|"window", x0, y0, x1, y1)]; dims: [(xa, ya, xb, yb, text)]."""
    fig, ax = plt.subplots(figsize=size, dpi=90)
    polys = []
    for it in items:
        for part in it["spec"]["parts"]:
            pts = [_xf(p, it["x"], it["y"], it.get("z", 0), it.get("rot", 0)) for p in part_points(part)]
            top = max(p[2] for p in pts)
            polys.append((top, part, [(p[0], p[1]) for p in pts]))
    polys.sort(key=lambda t: t[0])
    for x0, y0, x1, y1 in walls:
        ax.add_patch(plt.Rectangle((min(x0, x1), min(y0, y1)), abs(x1 - x0), abs(y1 - y0), facecolor="#3a3a3a",
                                   edgecolor="#111", lw=0.5, zorder=1))
    for name, x0, y0, x1, y1 in rooms:
        ax.add_patch(plt.Rectangle((x0, y0), x1 - x0, y1 - y0, facecolor="#f4efe6", edgecolor="none", zorder=0))
        area = (x1 - x0) * (y1 - y0) / 1e6
        ax.text((x0 + x1) / 2, y1 - (y1 - y0) * 0.08, f"{name}\n{area:.1f} м²", ha="center", va="top", fontsize=9,
                color="#224", weight="bold", zorder=6)
    for _top, part, pts in polys:
        col = srgb(PALETTE.get(part.get("m"), {"c": (0.5, 0.5, 0.5)})["c"])
        ax.add_patch(Polygon(hull(pts), closed=True, facecolor=col, edgecolor="#222", lw=0.3, alpha=0.9, zorder=2))
    for kind, x0, y0, x1, y1 in openings:
        ax.add_patch(plt.Rectangle((min(x0, x1), min(y0, y1)), abs(x1 - x0), abs(y1 - y0),
                                   facecolor="#9cd3ff" if kind == "window" else "#ffffff", edgecolor="#036",
                                   lw=0.6, zorder=3))
    for it in items:
        if it.get("label"):
            ax.text(it["x"], it["y"], it["label"], ha="center", va="center", fontsize=6.5, zorder=7,
                    bbox=dict(facecolor="white", alpha=0.75, edgecolor="none", pad=0.6))
    for xa, ya, xb, yb, text in dims:
        _dim(ax, xa, ya, xb, yb, text, vertical=abs(xb - xa) < abs(yb - ya))
    ax.autoscale_view()
    ax.relim()
    xs = [p[0] for _t, _p, pts in polys for p in pts] + [w[0] for w in walls] + [w[2] for w in walls]
    ys = [p[1] for _t, _p, pts in polys for p in pts] + [w[1] for w in walls] + [w[3] for w in walls]
    pad = (max(xs) - min(xs)) * 0.05
    ax.set_xlim(min(xs) - pad, max(xs) + pad)
    ax.set_ylim(min(ys) - pad, max(ys) + pad)
    ax.set_aspect("equal")
    step = grid_step or nice_step(max(max(xs) - min(xs), max(ys) - min(ys)))
    ax.set_xticks([k * step for k in range(math.floor((min(xs) - pad) / step), math.ceil((max(xs) + pad) / step) + 1)])
    ax.set_yticks([k * step for k in range(math.floor((min(ys) - pad) / step), math.ceil((max(ys) + pad) / step) + 1)])
    ax.tick_params(labelsize=6)
    ax.grid(True, color="#9bb", lw=0.3, alpha=0.5, zorder=-1)
    ax.set_xlabel("X, мм", fontsize=8)
    ax.set_ylabel("Y, мм", fontsize=8)
    ax.set_title(title, fontsize=12)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
