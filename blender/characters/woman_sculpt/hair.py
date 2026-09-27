"""
Причёска: пышное кудрявое каре до скул, объём на макушке, седая прядь от лба на её правую сторону.

Скульптурный способ: основа-«шапка» из объёмов на черепе + ~90 плоских волнистых прядей-пучков с завитками
на концах → voxel remesh 2,2 мм → сглаживание. Цвет — по пряди (седая/каштановая с вариациями).
"""
import math
import random

import numpy as np

import sculpt as sc
import spec as S

MM = 0.001
CR = np.array(S.HEAD["cranium"]["c"], float)
RR = np.array(S.HEAD["cranium"]["r"], float)
HC = np.array([0.0, 20.0, 1488.0])                       # центр объёма причёски


def d(th, ph):
    return np.array([math.sin(th) * math.sin(ph), -math.sin(th) * math.cos(ph), math.cos(th)])


def skull(th, ph):
    return CR + d(th, ph) * RR


def envelope(th, ph):
    """Внешняя граница причёски (по чертежу: ширина ±178, верх 1660, перёд −132, зад +177)."""
    dd = d(th, ph)
    ry = 138.0 if dd[1] < 0 else 158.0
    rz = 172.0 if dd[2] > 0 else 150.0
    p = HC + dd * np.array([172.0, ry, rz])
    return p


def hairline(ph):
    """Граница роста волос: угол θ от макушки. Лоб — высоко, виски ниже, затылок до шеи."""
    a = abs(math.remainder(ph, 2 * math.pi))
    if a < 0.8:
        return math.radians(56)
    if a < 1.6:
        return math.radians(56 + (a - 0.8) / 0.8 * 44)
    return math.radians(100 + min(1.0, (a - 1.6) / 1.2) * 18)


def clump_path(th_ctrl, ph_ctrl, layer, rng, n=60, curl=1.0, wave=10.0):
    """Путь пряди: корень на черепе → слой объёма → вниз с волной → завиток наружу."""
    ctrl = np.array([[t, p, 0] for t, p in zip(th_ctrl, ph_ctrl)], float)
    tp = sc.catmull(ctrl, 0.02)
    idx = np.linspace(0, len(tp) - 1, n)
    th = np.interp(idx, np.arange(len(tp)), tp[:, 0])
    ph = np.interp(idx, np.arange(len(tp)), tp[:, 1])
    t = np.linspace(0, 1, n)
    pts, ups = [], []
    s0, lam = rng.uniform(0, 6.28), rng.uniform(75, 105)
    arc = 0.0
    prev = None
    for i in range(n):
        dd = d(th[i], ph[i])
        base = skull(th[i], ph[i])
        env = envelope(th[i], ph[i])
        k = min(1.0, t[i] / 0.18)
        k = k * k * (3 - 2 * k)
        lay = layer[0] + (layer[1] - layer[0]) * t[i]
        p = base + (env - base) * (k * lay)
        if prev is not None:
            arc += np.linalg.norm(p - prev)
        prev = p.copy()
        # волна поперёк пряди
        side = np.cross(dd, np.array([0, 0, 1.0]))
        if np.linalg.norm(side) < 1e-3:
            side = np.array([1.0, 0, 0])
        side /= np.linalg.norm(side)
        p = p + side * wave * math.sin(2 * math.pi * arc / lam + s0) * min(1.0, t[i] / 0.3) \
            + dd * 4.0 * math.cos(2 * math.pi * arc / lam + s0) * min(1.0, t[i] / 0.3)
        pts.append(p)
        ups.append(dd)
    pts = np.array(pts)
    # завиток на конце: последняя четверть закручивается наружу и вверх
    m = int(n * 0.75)
    if curl > 0:
        cr = rng.uniform(14, 22) * curl
        base_pt = pts[m].copy()
        down = pts[m] - pts[m - 3]
        down /= np.linalg.norm(down)
        out = ups[m]
        for i in range(m, n):
            a = (i - m) / (n - 1 - m) * math.radians(rng.uniform(100, 160))
            pts[i] = base_pt + down * cr * math.sin(a) + out * cr * (1 - math.cos(a))
            ups[i] = out
    # не ниже линии скул
    pts[:, 2] = np.maximum(pts[:, 2], 1335.0)
    return pts, np.array(ups)


def build_hair(col, mat_attr):
    rng = random.Random(11)
    meshes, labels_src = [], []
    grey_lo, grey_hi = S.HAIR["grey"]

    def add(pts, ups, r0, grey, tag):
        n = len(pts)
        t = np.linspace(0, 1, n)
        rx = r0 * (1 - 0.35 * t ** 1.6) * (0.75 + 0.25 * np.minimum(1, t / 0.1))
        me = sc.tube("Clump", pts * MM, rx * MM, rx * 0.42 * MM, n_pts=16, up=ups)
        meshes.append(me)
        labels_src.append((("grey" if grey else "hair") + tag, pts[::2] * MM))

    # 1) основа-шапка: объёмы на черепе выше линии роста
    for th in np.linspace(0.05, 1.9, 12):
        for ph in np.linspace(-math.pi, math.pi, 22, endpoint=False):
            if th > hairline(ph) - 0.12:
                continue
            p = skull(th, ph) + d(th, ph) * 18
            me = sc.ellipsoid("Blob", p * MM, (np.array([34, 34, 30]) * MM), 16, 10)
            meshes.append(me)

    # 2) передние пряди: от лба вверх-назад и в стороны (объём надо лбом)
    for k in range(14):
        ph0 = math.radians(-78 + 156 * (k + rng.random() * 0.6) / 14)
        side = 1 if ph0 > math.radians(S.HAIR["part_x"] / 3) else -1
        th0 = hairline(ph0) - 0.05
        ctrl_th = [th0, th0 - 0.45, 0.9 + rng.uniform(-0.1, 0.15), 1.75 + rng.uniform(0, 0.25)]
        ctrl_ph = [ph0, ph0 + side * 0.25, side * rng.uniform(1.0, 1.5), side * rng.uniform(1.35, 2.0)]
        pts, ups = clump_path(ctrl_th, ctrl_ph, (0.92, 1.0), rng, curl=1.0)
        grey = math.radians(grey_lo) < ph0 < math.radians(grey_hi)
        add(pts, ups, rng.uniform(24, 28), grey, "")

    # 3) средний слой: от макушки во все стороны до скул/шеи
    for k in range(38):
        ph0 = -math.pi + 2 * math.pi * (k + rng.random()) / 38
        a = abs(math.remainder(ph0, 2 * math.pi))
        if a < 0.7:
            continue
        th0 = rng.uniform(0.25, 0.7)
        side = 1 if math.sin(ph0) >= 0 else -1
        th_end = hairline(ph0) + rng.uniform(0.15, 0.35)
        ph_end = ph0 + side * rng.uniform(0.05, 0.3)
        pts, ups = clump_path([th0, (th0 + th_end) / 2, th_end], [ph0, (ph0 + ph_end) / 2, ph_end],
                              (0.85, 0.98), rng, curl=rng.uniform(0.7, 1.1))
        add(pts, ups, rng.uniform(22, 26), False, "")

    # 4) нижний внешний слой: пышные завитки по низу
    for k in range(24):
        ph0 = -math.pi + 2 * math.pi * (k + rng.random()) / 24
        a = abs(math.remainder(ph0, 2 * math.pi))
        if a < 1.1:
            continue
        th0 = rng.uniform(0.9, 1.3)
        side = 1 if math.sin(ph0) >= 0 else -1
        th_end = hairline(ph0) + rng.uniform(0.3, 0.5)
        pts, ups = clump_path([th0, th_end], [ph0, ph0 + side * rng.uniform(0.1, 0.4)], (0.92, 1.02), rng,
                              curl=rng.uniform(0.9, 1.3), wave=12)
        add(pts, ups, rng.uniform(20, 24), False, "")

    ob = sc.join_meshes("Hair", meshes, col)
    sc.remesh(ob, 0.0022, smooth_iters=6)
    labels, names = sc.label_by_nearest(ob, labels_src)
    lin_h, lin_g = sc.srgb(S.COLORS["hair"]), sc.srgb(S.COLORS["hair_grey"])
    nm = np.array(names)[labels]
    colr = np.where(np.char.startswith(nm, "grey")[:, None], lin_g, lin_h)
    # вариации тона по прядям
    var = 0.8 + 0.35 * ((labels * 7919) % 97) / 97.0
    colr = colr * var[:, None]
    # мягкие переходы цвета между прядями
    e = sc.Sculpt(ob).edges
    deg = np.bincount(e.ravel(), minlength=len(colr)).astype(float)
    deg[deg == 0] = 1
    for _ in range(12):
        acc = np.zeros_like(colr)
        np.add.at(acc, e[:, 0], colr[e[:, 1]])
        np.add.at(acc, e[:, 1], colr[e[:, 0]])
        colr = 0.5 * colr + 0.5 * acc / deg[:, None]
    sc.set_color_attr(ob, colr)
    ob.data.materials.append(mat_attr("Hair", 0.5))
    return {"hair": ob}
