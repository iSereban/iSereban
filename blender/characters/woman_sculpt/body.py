"""Тело: блокинг по чертежу (spec.py) → voxel remesh → кисти. Кардиган и кисти рук — отдельные «скульпты»."""
import math

import numpy as np

import sculpt as sc
import spec as S

MM = 0.001


def _torso_rings():
    zs = np.arange(S.TORSO[0][0], S.TORSO[-1][0] + 1, 8.0)
    tab = sc.interp_table(S.TORSO, zs)
    return [sc.superellipse(56, a * MM, -yf * MM, yb * MM, z=z * MM, p=2.3) for z, (a, yf, yb) in zip(zs, tab)]


def _leg(sign):
    zs = np.arange(S.LEG[-1][0], S.LEG[0][0] + 1, 8.0)[::-1]
    tab = sc.interp_table(S.LEG, zs)
    rings = []
    for z, (cx, rx, ry, cy) in zip(zs, tab):
        t = np.linspace(0, 2 * math.pi, 40, endpoint=False)
        rings.append(np.stack([sign * cx * MM + rx * MM * np.cos(t), cy * MM + ry * MM * np.sin(t),
                               np.full_like(t, z * MM)], axis=1))
    return sc.mesh_from_rings("Leg", rings)


def _foot(sign):
    """Стопа в носке: лофт вдоль стопы (пятка → носок), подошва плоская."""
    sk = S.SOCK
    L = sk["foot_len"]
    ys = np.linspace(sk["heel_y"], sk["heel_y"] - L, 30)
    u = (sk["heel_y"] - ys) / L                                        # 0 пятка … 1 носок
    half_w = sk["foot_w"] / 2 * (0.78 + 0.22 * np.sin(np.pi * np.clip(u * 1.25, 0, 1)) ** 0.7)
    half_w *= np.where(u > 0.82, np.sqrt(np.clip(1 - (u - 0.82) / 0.18, 0.05, 1)) * 0.6 + 0.4, 1.0)
    h = sk["foot_h"] * (1.0 - 0.55 * np.clip((u - 0.35) / 0.65, 0, 1) ** 1.3)
    h *= np.where(u > 0.85, np.sqrt(np.clip(1 - (u - 0.85) / 0.15, 0.05, 1)) * 0.5 + 0.5, 1.0)
    h *= np.where(u < 0.08, np.sqrt(np.clip(u / 0.08, 0.1, 1)) * 0.4 + 0.6, 1.0)
    ang = math.radians(sk["toe_out_deg"]) * sign
    cx = S.LEG[-1][1] * sign
    rings = []
    t = np.linspace(0, 2 * math.pi, 36, endpoint=False)
    for y, hw, hh in zip(ys, half_w, h):
        x = hw * np.sign(np.cos(t)) * np.abs(np.cos(t)) ** (2 / 2.6)
        zz = hh / 2 * (1 + np.sign(np.sin(t)) * np.abs(np.sin(t)) ** (2 / 3.2))
        yy = np.full_like(t, y)
        # поворот носком наружу
        xr = x * math.cos(ang) - yy * math.sin(ang)
        yr = x * math.sin(ang) + yy * math.cos(ang)
        rings.append(np.stack([(cx + xr) * MM, yr * MM, zz * MM], axis=1))
    return sc.mesh_from_rings("Foot", rings)


def _ankle(sign):
    sk = S.SOCK
    cx, cy = S.LEG[-1][1] * sign, 8
    zs = np.arange(20, sk["top"] + 1, 8.0)
    r = sk["ankle_r"] * (1 + 0.12 * (zs > sk["top"] - 45))            # верх носка чуть толще (резинка)
    path = np.stack([np.full_like(zs, cx), np.full_like(zs, cy), zs], axis=1) * MM
    return sc.tube("Ankle", path, r * MM, n_pts=32)


def arm_path(sign):
    pts = np.array([(sign * x, y, z, r) for x, y, z, r in S.ARM], float)
    return sc.catmull(pts, 8.0)


def _arm(sign):
    P = arm_path(sign)
    path, r = P[:, :3] * MM, P[:, 3] * MM
    return sc.tube("Arm", path, r, r * 0.93, n_pts=36)


def _neck():
    zs = np.arange(1230, 1335, 8.0)
    path = np.stack([np.zeros_like(zs), np.full_like(zs, 22.0), zs], axis=1) * MM
    return sc.tube("NeckBase", path, 55 * MM, 52 * MM, n_pts=32)


def build_body(col=None):
    parts = {"torso": sc.mesh_from_rings("Torso", _torso_rings()), "neck": _neck()}
    for sgn, s in ((1, "L"), (-1, "R")):
        parts[f"leg.{s}"] = _leg(sgn)
        parts[f"foot.{s}"] = _foot(sgn)
        parts[f"ankle.{s}"] = _ankle(sgn)
        parts[f"arm.{s}"] = _arm(sgn)
    sources = [(k, sc.mesh_points(me)) for k, me in parts.items()]
    ob = sc.join_meshes("Body", list(parts.values()), col)
    sc.remesh(ob, 0.0045, smooth_iters=4)
    labels, names = sc.label_by_nearest(ob, sources)
    body_details(ob, labels, names)
    return ob, labels, names


def body_details(ob, labels, names):
    s = sc.Sculpt(ob)
    co = s.co
    z = co[:, 2] / MM
    # низ блузки: лёгкая ступенька-борозда по кругу
    tor = np.isin(labels, [names.index("torso")])
    # борозда по низу блузки — через draw по полосе
    band = tor & (np.abs(z - S.BLOUSE_HEM) < 6)
    s.co[band] -= s.n[band] * 2.0 * MM
    below = tor & (z < S.BLOUSE_HEM) & (z > S.BLOUSE_HEM - 60)
    s.co[below] -= s.n[below] * (1.5 * MM) * np.clip((S.BLOUSE_HEM - z[below]) / 20, 0, 1)[:, None]
    s._dirty()
    # планка хенли и вырез
    pl = S.NECKLINE["placket"]
    for zz in np.arange(pl[0], pl[1], 6):
        s.draw((0, -0.105 if zz < 1200 else -0.09, zz * MM), 14 * MM, 0.9 * MM, scale=(1.0, 3.0, 0.6))
    # складки брюк: у отворота и под коленом
    for sgn in (1, -1):
        cx = S.LEG[3][1] * sgn * MM
        for zz, depth in ((205, 2.5), (228, 2.0), (395, 1.8), (430, 1.5), (560, 1.6)):
            pts = [(cx + 0.09 * math.cos(a), 0.008 + 0.09 * math.sin(a), (zz + 6 * math.sin(3 * a)) * MM)
                   for a in np.linspace(-math.pi, math.pi, 40)]
            s.crease(pts, 7 * MM, depth * MM, pinch=0.15)
        # края отворота
        for zz in (150, 190):
            pts = [(cx + 0.09 * math.cos(a), 0.008 + 0.09 * math.sin(a), zz * MM) for a in np.linspace(-math.pi, math.pi, 40)]
            s.crease(pts, 5 * MM, 2.2 * MM, pinch=0.2)
        # складки на рукаве у локтя и над манжетой
        P = arm_path(sgn)
        for frac, depth in ((0.52, 2.2), (0.6, 1.8), (0.8, 1.6), (0.87, 2.4)):
            i = int(frac * (len(P) - 1))
            c, r = P[i, :3] * MM, P[i, 3] * MM
            t = P[min(i + 1, len(P) - 1), :3] - P[max(i - 1, 0), :3]
            t /= np.linalg.norm(t)
            a = np.cross(t, (0, 1, 0))
            a /= np.linalg.norm(a)
            b = np.cross(t, a)
            pts = [c + (a * math.cos(q) + b * math.sin(q)) * r * 1.05 + t * 0.006 * math.sin(2 * q)
                   for q in np.linspace(-math.pi, math.pi, 30)]
            s.crease(pts, 6 * MM, depth * MM, pinch=0.15)
        # верх носка: резинка-валик
        pts = [(S.LEG[-1][1] * sgn * MM + 0.058 * math.cos(a), 0.008 + 0.058 * math.sin(a), (S.SOCK["top"] - 45) * MM)
               for a in np.linspace(-math.pi, math.pi, 40)]
        s.crease(pts, 5 * MM, 2.0 * MM, pinch=0.2)
    s.smooth(1, 0.3).commit()


# ------------------------------------------------------------------ кардиган
def _cardigan_ring(z, a, yf, yb, op, m=110, p=2.3):
    """Дуга сечения кардигана от правого края проёма через спину к левому (открыта спереди)."""
    t = np.linspace(-math.pi / 2, 3 * math.pi / 2, 2000)
    c, s = np.cos(t), np.sin(t)
    x = a * np.sign(c) * np.abs(c) ** (2 / p)
    yy = np.abs(s) ** (2 / p)
    y = np.where(s < 0, -yf * yy, yb * yy)
    keep = ~((y < 0) & (np.abs(x) < op))
    # непрерывная дуга: с левого-переднего края (x=+op) через спину к правому (x=−op)
    idx = np.where(keep)[0]
    xs, ys = x[idx], y[idx]
    # параметр по длине дуги и равномерная выборка m точек
    d = np.r_[0, np.cumsum(np.hypot(np.diff(xs), np.diff(ys)))]
    u = np.linspace(0, d[-1], m)
    return np.stack([np.interp(u, d, xs), np.interp(u, d, ys), np.full(m, z)], axis=1)


def cardigan_front_edge(z):
    """Точки кромки проёма (правая, левая) и направление «наружу» на высоте z (мм)."""
    tab = sc.interp_table(S.CARDIGAN["rings"], np.array([z]))[0]
    op = np.interp(z, *zip(*S.CARDIGAN["opening"]))
    r = _cardigan_ring(z, tab[0], -tab[1], tab[2], op)
    return r[0], r[-1]


def build_cardigan(col=None):
    C = S.CARDIGAN
    zs = np.arange(C["hem"], C["top"] + 1, 8.0)
    tab = sc.interp_table(C["rings"], zs)
    opz = np.interp(zs, *zip(*C["opening"]))
    rings = [_cardigan_ring(z, a, -yf, yb, op) * MM for z, (a, yf, yb), op in zip(zs, tab, opz)]
    me = sc.mesh_from_rings("CardiganShell", rings, False, False, closed=False)
    shell = sc.link("CardiganShell", me, col)
    sc.solidify(shell, C["thick"] * MM, offset=-1.0)
    shell_pts = sc.mesh_points(shell)

    # борт + шалевый воротник: одна полоса вдоль кромки проёма и вокруг шеи
    left = [r[0] / MM for r in rings]            # x>0
    right = [r[-1] / MM for r in rings]
    bw, bt = C["band_w"], C["band_t"]
    path_l = [p + np.array([bw / 2 - 6, -bt / 2 + 4, 0]) for p in left]
    path_r = [p + np.array([-(bw / 2 - 6), -bt / 2 + 4, 0]) for p in right]
    collar = []
    for a in np.linspace(math.radians(-150), math.radians(150), 40):       # 0 = спина
        z = C["top"] + 18 + 45 * math.cos(a / 2) ** 2
        collar.append(np.array([95 * math.sin(a), 22 + 88 * math.cos(a), z]))
    path = np.array(path_r[::6] + [path_r[-1]] + collar + [path_l[-1]] + path_l[::-1][::6])
    # сглаженный путь
    P = sc.catmull(path, 8.0)
    n = len(P)
    # ориентация сечения: у борта ширина — по X, у воротника — вверх/наружу
    up = []
    for p in P:
        tcol = np.clip((p[2] - (C["top"] - 60)) / 60, 0, 1)
        radial = np.array([p[0], p[1] - 22, 0.0])
        radial /= max(np.linalg.norm(radial), 1e-6)
        up.append((1 - tcol) * np.array([0, -1.0, 0]) + tcol * (radial * 0.7 + np.array([0, 0, 0.7])))
    up = np.array(up)
    band = sc.tube("Band", P * MM, np.full(n, bw / 2 * MM), np.full(n, bt / 2 * MM), n_pts=24, up=up)
    # резинка низа
    hem_rings = [r for r, z in zip(rings, zs) if z < C["hem"] + C["hem_rib"]]
    hem_me = sc.mesh_from_rings("Hem", hem_rings, False, False, closed=False)
    hem = sc.link("Hem", hem_me, col)
    sc.solidify(hem, (C["thick"] + 6) * MM, offset=0.2)
    parts = [shell.data.copy(), band, hem.data.copy()]
    import bpy
    for o in (shell, hem):
        bpy.data.objects.remove(o, do_unlink=True)
    ob = sc.join_meshes("Cardigan", parts, col)
    sc.remesh(ob, 0.004, smooth_iters=3)
    # метки: борт/резинки (для рубчика в материале)
    co = sc.mesh_points(ob) / MM
    rib = np.zeros(len(co))
    rib[co[:, 2] < C["hem"] + C["hem_rib"]] = 1.0
    bandp = P
    from mathutils.kdtree import KDTree
    from mathutils import Vector
    kd = KDTree(len(bandp))
    for i, p in enumerate(bandp):
        kd.insert(Vector(p), i)
    kd.balance()
    for i, p in enumerate(co):
        if kd.find(Vector(p))[2] < bw / 2 + 2:
            rib[i] = 2.0
    sc.set_float_attr(ob, rib, "rib")
    # карманы-накладки угадываются лёгкими бороздами (как на картинке)
    s = sc.Sculpt(ob)
    for sgn in (1, -1):
        x0 = sgn * 0.105
        s.crease([(x0 - 0.045, -0.135, 0.845), (x0 + 0.045, -0.135, 0.845)], 4 * MM, 1.8 * MM, 0.2)
    s.commit()
    return ob, shell_pts


# ------------------------------------------------------------------ кисти рук
def build_hand(sign, col=None):
    """Кисть висит вдоль тела, ладонь к бедру, пальцы слегка согнуты. Лепка из частей + remesh 1.6 мм."""
    Hd = S.HAND
    wx, wy, wz = Hd["wrist"]
    parts = []
    # ладонь (локально: длина по −Z, ширина по Y, толщина по X; +X — к бедру)
    palm_c = np.array([0, 0, -44.0])
    parts.append(sc.ellipsoid("Palm", palm_c, (13, 36, 48), 32, 24))
    parts.append(sc.ellipsoid("PalmBase", (0, 2, -12), (15, 30, 22), 24, 16))
    fingers = [(-25, 70, 8.6), (-8.5, 78, 9.0), (8.0, 74, 8.6), (23, 60, 7.8)]
    for fy, ln, r in fingers:
        pts, p, d = [], np.array([0, fy * 0.95, -84.0]), np.array([0, fy * 0.05, -1.0])
        d /= np.linalg.norm(d)
        segs = (0.42, 0.33, 0.25)
        bends = (0.20, 0.30, 0.25)
        pts.append(p.copy())
        B = 0.0
        for sl, bd in zip(segs, bends):
            B += bd                                    # сгиб к ладони (локальный +X — к бедру)
            d = np.array([math.sin(B), fy * 0.004, -math.cos(B)])
            d /= np.linalg.norm(d)
            for k in range(1, 5):
                pts.append(p + d * ln * sl * k / 4)
            p = pts[-1].copy()
        pts = np.array(pts)
        rr = r * (1 - 0.18 * np.linspace(0, 1, len(pts)))
        parts.append(sc.tube("Finger", pts, rr, n_pts=16))
        parts.append(sc.ellipsoid("Tip", pts[-1], (r * 0.8, r * 0.8, r * 0.8), 12, 8))
    # большой палец: вперёд-вниз, к ладони
    tp = np.array([[4, -30, -22], [10, -44, -42], [16, -48, -62], [21, -46, -78]], float)
    parts.append(sc.tube("Thumb", sc.catmull(tp, 3.0), np.linspace(12, 8.5, len(sc.catmull(tp, 3.0))), n_pts=16))
    parts.append(sc.ellipsoid("ThumbTip", tp[-1], (8, 8, 8), 12, 8))
    # запястье — уходит в манжету
    parts.append(sc.tube("Wrist", np.array([[0, 0, 30.0], [0, 0, 0], [0, 0, -14]]), np.array([22, 21, 20.0]), np.array([17, 16, 16.0]), n_pts=20))
    # в мировые: масштаб мм→м, зеркало по X для правой руки, ладонь к бедру
    for me in parts:
        for v in me.vertices:
            x, y, z = v.co
            v.co = ((wx - x) * sign * MM, (wy + y) * MM, (wz + z) * MM)
    ob = sc.join_meshes(f"Hand.{'L' if sign > 0 else 'R'}", parts, col)
    sc.remesh(ob, 0.0016, smooth_iters=4)
    s = sc.Sculpt(ob)
    # костяшки и складки на пальцах — лёгкими бороздами
    s.smooth(2, 0.4).commit()
    return ob
