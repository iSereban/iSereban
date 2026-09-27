"""
Реалистичные деревья (процедурный рост по ботаническим параметрам).

Дерево = скелет из сужающихся сегментов (ствол → скелетные ветви → побеги) + листья/хвоя
на концах побегов. Всё — в координатах (мм), спецификация как у остальных объектов библиотеки:
  {"t": "mesh", "v": [[x,y,z]...], "f": [[i,j,k(,l)]...], "m": материал, "draw": "skeleton"|"crown", ...}
  у ветвей дополнительно "segs": [[x0,y0,z0, x1,y1,z1, r0, r1], ...] — для чертежа.

Параметры пород (типичные городские экземпляры):
  липа мелколистная — H 14 м, ствол Ø 40 см, крона Ø 8–9 м, округлая, лист 6–8 см
  берёза повислая   — H 16 м, ствол Ø 30 см, крона Ø 6 м, яйцевидная, ветви повислые, лист 4–5 см
  ель европейская   — H 18 м, ствол Ø 35 см, крона Ø 5 м, конус, мутовки через 40–50 см
  фикус Бенджамина  — H 1,4 м (в кашпо), глянцевый лист 8–10 см
"""

import math
import random


# ---------------------------------------------------------------------------
# Геометрия: трубки и листья
# ---------------------------------------------------------------------------
def _basis(d):
    """Ортонормированные векторы, перпендикулярные d."""
    dx, dy, dz = d
    ax = (1, 0, 0) if abs(dx) < 0.9 else (0, 1, 0)
    ux = (dy * ax[2] - dz * ax[1], dz * ax[0] - dx * ax[2], dx * ax[1] - dy * ax[0])
    n = math.sqrt(sum(c * c for c in ux)) or 1
    ux = tuple(c / n for c in ux)
    uy = (dy * ux[2] - dz * ux[1], dz * ux[0] - dx * ux[2], dx * ux[1] - dy * ux[0])
    return ux, uy


def _norm(v):
    n = math.sqrt(sum(c * c for c in v)) or 1
    return tuple(c / n for c in v)


def tubes(segs, sides=6):
    """Сегменты (p0, p1, r0, r1) → вершины и грани сужающихся трубок."""
    V, F = [], []
    for p0, p1, r0, r1 in segs:
        d = _norm(tuple(b - a for a, b in zip(p0, p1)))
        ux, uy = _basis(d)
        base = len(V)
        for p, r in ((p0, r0), (p1, r1)):
            for k in range(sides):
                a = 2 * math.pi * k / sides
                V.append([p[i] + (ux[i] * math.cos(a) + uy[i] * math.sin(a)) * r for i in range(3)])
        for k in range(sides):
            k1 = (k + 1) % sides
            F.append([base + k, base + k1, base + sides + k1, base + sides + k])
    return V, F


def leaves_mesh(leaf_list):
    """Листья: (центр, нормаль, направление, длина, ширина) → ромбовидные пластинки (2 треугольника)."""
    V, F = [], []
    for c, n, t, L, W in leaf_list:
        s = _norm((n[1] * t[2] - n[2] * t[1], n[2] * t[0] - n[0] * t[2], n[0] * t[1] - n[1] * t[0]))
        b = len(V)
        V += [[c[i] - t[i] * L * 0.5 for i in range(3)], [c[i] + s[i] * W * 0.5 - t[i] * L * 0.05 for i in range(3)],
              [c[i] + t[i] * L * 0.5 for i in range(3)], [c[i] - s[i] * W * 0.5 - t[i] * L * 0.05 for i in range(3)]]
        F += [[b, b + 1, b + 2], [b, b + 2, b + 3]]
    return V, F


# ---------------------------------------------------------------------------
# Рост лиственного дерева (рекурсивное ветвление)
# ---------------------------------------------------------------------------
def grow_broadleaf(seed, H, trunk_r, crown_r, clear_h, depth=5, split=(3, 4), angle=(28, 52),
                   shrink=0.72, droop=0.0, leaf=(70, 55), leaves_per_twig=10, twig_len=0.9,
                   up_bias=0.35, gnarl=0.18, lean=0.03, first_frac=0.30, lateral_up=(25, 55), spray=150, hang=0):
    """Возвращает (сегменты ветвей, листья). Размеры — мм."""
    rng = random.Random(seed)
    segs, leaves = [], []

    def branch(p, d, length, r, level):
        n_sub = 4 if level == 0 else 3
        pos, dirv = p, d
        for i in range(n_sub):
            # изгиб + фототропизм (вверх) + свисание (вниз) у тонких ветвей
            g = gnarl * (1.0 if level else 0.35)
            dirv = _norm((dirv[0] + rng.uniform(-g, g), dirv[1] + rng.uniform(-g, g),
                          dirv[2] + up_bias * 0.25 * (1 - level / depth) - droop * (level / depth) ** 2))
            seg_len = length / n_sub
            r1 = r * (1 - 0.35 / n_sub * (i + 1))
            nxt = tuple(pos[k] + dirv[k] * seg_len for k in range(3))
            segs.append((pos, nxt, max(r * (1 - 0.35 / n_sub * i), 1.5), max(r1, 1.2)))
            pos = nxt
            if level >= depth - 1:
                # листья вдоль молодых побегов
                for _ in range(leaves_per_twig // 2):
                    t = _norm((dirv[0] + rng.uniform(-1, 1), dirv[1] + rng.uniform(-1, 1),
                               dirv[2] + rng.uniform(-0.7, 0.5) - droop * 0.4))
                    n = _norm((rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5), 1.0))
                    ball = (rng.gauss(0, spray), rng.gauss(0, spray), rng.gauss(0, spray) - abs(rng.gauss(0, hang)))
                    c = tuple(pos[k] - dirv[k] * seg_len * rng.random() + t[k] * leaf[0] * 0.55 + ball[k]
                              for k in range(3))
                    sc = rng.uniform(0.75, 1.2)
                    leaves.append((c, n, t, leaf[0] * sc, leaf[1] * sc))
        r_end = r * 0.65
        if level >= depth:
            for _ in range(leaves_per_twig):
                t = _norm((dirv[0] + rng.uniform(-0.9, 0.9), dirv[1] + rng.uniform(-0.9, 0.9),
                           dirv[2] + rng.uniform(-0.6, 0.6) - droop * 0.5))
                n = _norm((rng.uniform(-0.4, 0.4), rng.uniform(-0.4, 0.4), 1.0))
                off = rng.uniform(0.0, 1.0)
                c = tuple(pos[k] - dirv[k] * length * 0.6 * off + t[k] * leaf[0] * 0.6 for k in range(3))
                s = rng.uniform(0.75, 1.2)
                leaves.append((c, n, t, leaf[0] * s, leaf[1] * s))
            return
        k = rng.randint(*split)
        az0 = rng.uniform(0, 2 * math.pi)
        for j in range(k):
            az = az0 + 2 * math.pi * j / k + rng.uniform(-0.3, 0.3)
            el = math.radians(rng.uniform(*angle))
            ux, uy = _basis(dirv)
            nd = _norm(tuple(dirv[m] * math.cos(el) + (ux[m] * math.cos(az) + uy[m] * math.sin(az)) * math.sin(el)
                             for m in range(3)))
            # «трубочная модель»: сумма площадей сечений дочерних ≈ площадь родителя
            rr = r_end / math.sqrt(k) * rng.uniform(0.9, 1.1)
            branch(pos, nd, length * shrink * rng.uniform(0.85, 1.1), rr, level + 1)

    # ствол-лидер + скелетные ветви по спирали (крона округлая: длиннее всего в середине)
    leader_top = H * 0.80
    n_seg = max(4, int(leader_top / 600))
    pos = (0.0, 0.0, 0.0)
    for i in range(n_seg):
        z1 = leader_top * (i + 1) / n_seg
        u0, u1 = i / n_seg, (i + 1) / n_seg
        nxt = (pos[0] + rng.uniform(-lean, lean) * 600, pos[1] + rng.uniform(-lean, lean) * 600, z1)
        r0 = trunk_r * (1.35 if i == 0 else 1.0) * (1 - 0.65 * u0)
        segs.append((pos, nxt, r0, trunk_r * (1 - 0.65 * u1)))
        pos = nxt
    crown_h = H - clear_h
    n_lat = rng.randint(7, 10)
    golden = math.radians(137.5)
    az0 = rng.uniform(0, 2 * math.pi)
    for j in range(n_lat):
        rel = (j + rng.uniform(0.1, 0.9)) / n_lat
        z = clear_h + rel * (leader_top - clear_h) * 0.92
        f = 0.35 + 0.8 * math.sin(math.pi * min(1.0, (z - clear_h) / crown_h * 1.1 + 0.08))
        L = crown_r * f
        az = az0 + golden * j
        el = math.radians(rng.uniform(*lateral_up))
        d = _norm((math.cos(az) * math.cos(el), math.sin(az) * math.cos(el), math.sin(el)))
        u = z / leader_top
        start = (pos[0] * u, pos[1] * u, z)
        rr = trunk_r * (1 - 0.65 * u) * rng.uniform(0.45, 0.6)
        branch(start, d, L / 2.6, rr, 1)
    branch(pos, (0, 0, 1), (H - leader_top) * 0.45, trunk_r * 0.35, 2)
    return segs, leaves


def grow_spruce(seed, H=18000, trunk_r=175, crown_r=2600, clear_h=1200, whorl=380):
    rng = random.Random(seed)
    segs, needles = [], []
    z = 0.0
    r = trunk_r
    segs.append(((0, 0, 0), (0, 0, clear_h), trunk_r * 1.3, trunk_r))
    z = clear_h
    while z < H - 300:
        t = (z - clear_h) / (H - clear_h)
        rz = trunk_r * (1 - t) + 20
        z2 = min(z + whorl, H)
        segs.append(((0, 0, z), (0, 0, z2), rz, trunk_r * (1 - (z2 - clear_h) / (H - clear_h)) + 20))
        L = crown_r * (1 - t) ** 0.95 * rng.uniform(0.85, 1.05) + 200
        n = rng.randint(7, 9)
        az0 = rng.uniform(0, 2 * math.pi)
        for j in range(n):
            az = az0 + 2 * math.pi * j / n
            d0 = (math.cos(az), math.sin(az))
            pts = []
            for k in range(6):
                u = k / 5
                sag = -math.sin(u * math.pi) * L * 0.18 + u * u * L * 0.12      # вниз, кончик вверх
                pts.append((d0[0] * L * u, d0[1] * L * u, z + sag))
            for k in range(5):
                rr = max(rz * 0.35 * (1 - k / 5), 6)
                segs.append((pts[k], pts[k + 1], rr, rr * 0.8))
                # «лапки» хвои: плоские пучки вдоль ветви
                for m in range(7):
                    c = tuple(pts[k][i] + (pts[k + 1][i] - pts[k][i]) * (m + 0.5) / 7 for i in range(3))
                    side = (-d0[1], d0[0], 0)
                    for sgn in (-1, 1):
                        for tilt in (-0.35, 0.1):
                            tdir = _norm((d0[0] * 0.7 + side[0] * sgn + rng.uniform(-0.2, 0.2),
                                          d0[1] * 0.7 + side[1] * sgn + rng.uniform(-0.2, 0.2), tilt))
                            sz = (1 - k / 6) * (1 - t * 0.45)
                            needles.append((c, (0, 0, 1), tdir, 480 * sz + 120, 230 * sz + 60))
        z = z2
    # верхушка
    segs.append(((0, 0, H - 300), (0, 0, H), 25, 5))
    return segs, needles


# ---------------------------------------------------------------------------
# Спецификации
# ---------------------------------------------------------------------------
def _tree_spec(name, title, segs, leaves, bark, leaf_m, note, extra=None, leaf_m2=None, sides=6):
    V, F = tubes(segs, sides)
    p = [{"t": "mesh", "v": V, "f": F, "p": [0, 0, 0], "m": bark, "draw": "skeleton",
          "segs": [[*a, *b, r0, r1] for a, b, r0, r1 in segs]}]
    if leaf_m2:
        half = len(leaves) // 2
        groups = [(leaves[:half], leaf_m), (leaves[half:], leaf_m2)]
    else:
        groups = [(leaves, leaf_m)]
    for lv, m in groups:
        LV, LF = leaves_mesh(lv)
        p.append({"t": "mesh", "v": LV, "f": LF, "p": [0, 0, 0], "m": m, "draw": "crown", "smooth": False})
    p += extra or []
    return {"name": name, "title": title, "group": "Деревья", "parts": p, "note": note}


def linden(variant=1):
    segs, leaves = grow_broadleaf(100 + variant, H=14000, trunk_r=200, crown_r=5200, clear_h=2600, depth=5,
                                  split=(3, 4), angle=(28, 50), shrink=0.70, droop=0.3, leaf=(95, 80), spray=260,
                                  leaves_per_twig=30, up_bias=0.45, first_frac=0.30, lateral_up=(20, 50))
    return _tree_spec(f"tree_linden_{variant}", f"Липа мелколистная (вариант {variant})", segs, leaves,
                      "bark_linden", "leaf_linden", "H≈14 м, ствол Ø40 см, крона Ø8–9 м", leaf_m2="leaf_linden2")


def birch(variant=1):
    segs, leaves = grow_broadleaf(200 + variant, H=16000, trunk_r=150, crown_r=3200, clear_h=3500, depth=6,
                                  split=(2, 3), angle=(20, 38), shrink=0.72, droop=1.0, leaf=(60, 45), spray=120, hang=280,
                                  leaves_per_twig=46, up_bias=1.0, gnarl=0.12, first_frac=0.30, lateral_up=(35, 65))
    return _tree_spec(f"tree_birch_{variant}", f"Берёза повислая (вариант {variant})", segs, leaves,
                      "bark_birch", "leaf_birch", "H≈16 м, ствол Ø30 см, крона Ø6 м, повислые ветви",
                      leaf_m2="leaf_birch2")


def spruce(variant=1):
    segs, needles = grow_spruce(300 + variant)
    return _tree_spec(f"tree_spruce_{variant}", f"Ель европейская (вариант {variant})", segs, needles,
                      "bark_spruce", "needles", "H≈18 м, крона Ø5 м, мутовки через 45 см")


def ficus():
    """Фикус Бенджамина в кашпо (1,4 м)."""
    segs, leaves = grow_broadleaf(7, H=1050, trunk_r=18, crown_r=350, clear_h=380, depth=4, split=(2, 3),
                                  angle=(25, 50), shrink=0.72, droop=0.6, leaf=(90, 40), leaves_per_twig=16,
                                  up_bias=0.5, gnarl=0.25, first_frac=0.45)
    segs = [((a[0], a[1], a[2] + 350), (b[0], b[1], b[2] + 350), r0, r1) for a, b, r0, r1 in segs]
    leaves = [((c[0], c[1], c[2] + 350), n, t, L, W) for c, n, t, L, W in leaves]
    pot = [{"t": "cone", "r1": 170, "r2": 220, "h": 360, "p": [0, 0, 180], "m": "terracotta", "seg": 24},
           {"t": "cyl", "r": 200, "h": 10, "p": [0, 0, 345], "m": "soil", "axis": "z", "seg": 24}]
    s = _tree_spec("plant_ficus", "Фикус Бенджамина в кашпо", segs, leaves, "bark_linden", "leaf_ficus",
                   "H 1,4 м, глянцевые листья 8–10 см", extra=pot, sides=5)
    s["group"] = "Растения"
    return s


CATALOG = {
    "tree_linden_1": lambda: linden(1), "tree_linden_2": lambda: linden(2), "tree_linden_3": lambda: linden(3),
    "tree_birch_1": lambda: birch(1), "tree_birch_2": lambda: birch(2),
    "tree_spruce_1": lambda: spruce(1),
}
