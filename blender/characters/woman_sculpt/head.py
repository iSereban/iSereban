"""
Голова: объёмы по чертежу → remesh 1,8 мм → лепка лица кистями.

Лицо (Pixar-стиль, как на референсе): крупные карие глаза с веками, широкая улыбка с зубами,
округлые «яблочки» щёк, аккуратный нос, мягкие носогубные складки и гусиные лапки (50+).
"""
import math

import bpy  # noqa: I001
import numpy as np
from mathutils import Vector
from mathutils.kdtree import KDTree

import sculpt as sc
import spec as S

MM = 0.001
H = S.HEAD
E = H["eyes"]


def _v(p):
    return np.asarray(p, float) * MM


def head_blocking(col):
    parts = []
    c, r = H["cranium"]["c"], H["cranium"]["r"]
    parts.append(sc.ellipsoid("Cranium", _v(c), _v(r), 64, 48))
    c, r = H["face"]["c"], H["face"]["r"]
    parts.append(sc.ellipsoid("Face", _v(c), _v(r), 48, 32))
    parts.append(sc.ellipsoid("Muzzle", _v((0, -84, 1398)), _v((40, 26, 22)), 32, 24))
    parts.append(sc.ellipsoid("Jaw", _v((0, -24, 1394)), _v((62, 58, 42)), 48, 32))
    parts.append(sc.ellipsoid("Brow", _v((0, -78, 1516)), _v((64, 18, 12)), 32, 16))
    for sgn in (1, -1):
        parts.append(sc.ellipsoid("Ear", _v((sgn * 88, 12, 1455)), _v((9, 20, 30)), 24, 16))
        parts.append(sc.ellipsoid("NoseWing", _v((sgn * 16, -111, 1421)), _v((11, 10, 9)), 20, 12))
    n = H["nose"]
    br = np.array([(0, -88, 1484), (0, -100, 1462), (0, -112, 1442)], float)
    parts.append(sc.tube("NoseBridge", sc.catmull(br, 3.0) * MM, np.linspace(6.5, 11.5, len(sc.catmull(br, 3.0))) * MM,
                         n_pts=20))
    parts.append(sc.ellipsoid("NoseTip", _v((0, -120, 1429)), _v((14, 13, 12)), 24, 16))
    zs = np.arange(1250, 1445, 8.0)
    neck = np.stack([np.zeros_like(zs), np.full_like(zs, 18.0), zs], axis=1) * MM
    parts.append(sc.tube("Neck", neck, 55 * MM, 55 * MM, n_pts=40))
    ob = sc.join_meshes("Head", parts, col)
    sc.remesh(ob, 0.0018, smooth_iters=14)
    return ob


def eye_center(sgn):
    return np.array([sgn * E["x"], E["y_front"] + E["r"], E["z"]]) * MM


def lid_curves(u):
    """Верхнее/нижнее веко (мм) по горизонтали u ∈ [−1, 1] от внутреннего к внешнему углу."""
    w = np.clip(1 - u * u, 0, 1)
    up = E["open_up"] * w ** 0.5 + 1.2 * u            # внешний угол чуть выше
    dn = -E["open_dn"] * w ** 0.9 + 0.8 * u + 1.2 * (1 - w)
    return up, dn


def carve_eyes(s):
    """Глазницы: кожа облегает глазное яблоко, прорезается разрез глаза, края век утолщаются."""
    r = E["r"] * MM
    hidden = np.zeros(len(s.co), bool)
    for sgn in (1, -1):
        c = eye_center(sgn)
        s.push_out_of_sphere(c, r + 1.0 * MM, 0)
        rel = (s.co - c) / MM
        u = rel[:, 0] * sgn / (E["open_w"] / 2)             # −1 внутренний угол … +1 внешний
        v = rel[:, 2]
        up, dn = lid_curves(np.clip(u, -1, 1))
        front = rel[:, 1] < 0
        inside = front & (np.abs(u) < 1) & (v < up) & (v > dn) & (np.linalg.norm(rel, axis=1) < E["r"] + 6)
        # внутрь глаза строго назад (по +Y), не сжимая разрез в проекции
        dxz2 = rel[inside][:, 0] ** 2 + rel[inside][:, 2] ** 2
        depth = np.sqrt(np.clip((E["r"] - 2.5) ** 2 - dxz2, 0, None))
        s.co[inside, 1] = c[1] + (-depth + 2.0) * MM
        hidden |= inside
        # веки: ободок толщиной ~1,3 мм вокруг разреза
        gap = np.minimum(np.abs(v - up), np.abs(v - dn))
        rim = front & ~inside & (np.abs(u) < 1.15) & (gap < 3.0) & (np.linalg.norm(rel, axis=1) < E["r"] + 5)
        s.co[rim] += s.n[rim] * (1.3 * MM) * (1 - gap[rim] / 3.0)[:, None]
        s._dirty()
        # складка верхнего века
        uu = np.linspace(-0.95, 1.0, 24)
        upc, _ = lid_curves(uu)
        pts = [c + np.array([sgn * uu_ * E["open_w"] / 2 * 1.05, -E["r"] * 0.55, up_ + 3.2]) * MM for uu_, up_ in zip(uu, upc)]
        s.crease(pts, 2.2 * MM, 0.9 * MM, pinch=0.1)
        # гусиные лапки у внешнего угла
        oc = c + np.array([sgn * (E["open_w"] / 2 + 5), -8, 0.5]) * MM
        for ang in (-25, 0, 25):
            a = math.radians(ang)
            p2 = oc + np.array([sgn * math.cos(a) * 9, 3, math.sin(a) * 9]) * MM
            s.crease([oc, p2], 1.2 * MM, 0.35 * MM, pinch=0.05)
    mask = np.zeros(len(s.co))
    for sgn in (1, -1):
        d = np.linalg.norm(s.co - eye_center(sgn), axis=1) / MM
        mask = np.maximum(mask, np.clip(1 - (d - E["r"]) / 8, 0, 1))
    mask[hidden] = 0
    s.smooth(2, 0.35, mask)
    return hidden


def mouth_curves(x):
    m = H["mouth"]
    t = np.clip(2 * x / m["w"], -1, 1)
    upper = m["z"] + m["corner_up"] * t ** 2
    lower = upper - m["open"] * np.clip(1 - t ** 2, 0, 1) ** 0.8
    return upper, lower


def carve_mouth(s):
    m = H["mouth"]
    co = s.co / MM
    x, y, z = co[:, 0], co[:, 1], co[:, 2]
    up, lo = mouth_curves(x)
    front = (y < -70) & (np.abs(x) < m["w"] / 2)
    # губы: верхняя тонкая, нижняя полнее
    ul = front & (z > up) & (z < up + 5.5)
    s.co[ul] += s.n[ul] * (1.0 * MM) * np.sin(np.pi * (z[ul] - up[ul]) / 5.5)[:, None]
    ll = front & (z < lo) & (z > lo - m["lip_low"])
    s.co[ll] += s.n[ll] * (2.0 * MM) * np.sin(np.pi * (lo[ll] - z[ll]) / m["lip_low"])[:, None] \
        * np.clip(1 - (2 * x[ll] / m["w"]) ** 2, 0, 1)[:, None] ** 0.5
    s._dirty()
    # прорезь рта: внутрь на 11 мм
    hole = front & (z < up) & (z > lo)
    s.co[hole] += np.array([0, 11 * MM, 0])
    s._dirty()
    # уголки рта и ямочки
    for sgn in (1, -1):
        cx = sgn * m["w"] / 2
        s.draw((cx * MM, -0.098, (m["z"] + m["corner_up"]) * MM), 5 * MM, -1.6 * MM)
        # «яблочки» щёк от улыбки
        s.draw((sgn * 48 * MM, -0.092, 1.430), 22 * MM, 1.6 * MM)
        # носогубная складка
        pts = [(sgn * 21 * MM, -0.113, 1.421), (sgn * 33 * MM, -0.110, 1.413), (sgn * 45 * MM, -0.101, 1.401)]
        s.crease(pts, 4.5 * MM, 1.1 * MM, pinch=0.1)
    # желобок над губой, ноздри
    s.crease([(0, -0.1175, 1.4135), (0, -0.1145, 1.4035)], 3.2 * MM, 0.8 * MM, 0.1)
    for sgn in (1, -1):
        s.draw((sgn * 8.5 * MM, -0.126, 1.4165), 4.2 * MM, -3.0 * MM, normal=np.array([0, 0.3, 0.95]))
    # мягко сгладить лицо вокруг рта (кроме прорези)
    msk = sc.falloff(np.linalg.norm((s.co / MM - np.array([0, -105, 1400])) / np.array([60, 40, 30]), axis=1))
    msk[hole] = 0
    s.smooth(1, 0.3, msk)
    return hole, ul, ll


def eyebrows(head_ob, col):
    co = sc.mesh_points(head_ob)
    kd = KDTree(len(co))
    for i, p in enumerate(co):
        kd.insert(Vector(p), i)
    kd.balance()
    nrm = np.empty(len(co) * 3)
    head_ob.data.vertex_normals.foreach_get("vector", nrm)
    nrm = nrm.reshape(-1, 3)
    b = H["brow"]
    obs = []
    for sgn in (1, -1):
        u = np.linspace(0, 1, 24)
        xs = sgn * (b["x"][0] + (b["x"][1] - b["x"][0]) * u)
        zs = b["z"] + b["arch"] * np.sin(np.pi * u ** 0.8) - 5 * u ** 2 + 1.5 * (1 - u)
        pts = []
        for x, z in zip(xs, zs):
            p = np.array([x, -140.0, z]) * MM
            # луч вперёд-назад: ближайшая точка поверхности спереди
            best = None
            for yy in np.linspace(-0.13, -0.05, 60):
                q = kd.find(Vector((p[0], yy, p[2])))
                if q[2] < 0.0015:
                    best = q
                    break
            if best is None:
                best = kd.find(Vector((p[0], -0.09, p[2])))
            pts.append(np.array(best[0]) + nrm[best[1]] * 1.4 * MM)
        pts = np.array(pts)
        rx = (2.6 + 1.4 * np.sin(np.pi * np.clip(u * 1.2, 0, 1)) - 1.8 * u ** 3) * MM
        up = np.array([nrm[kd.find(Vector(p))[1]] for p in pts])
        me = sc.tube("Brow", pts, rx, rx * 0.4, n_pts=12, up=up)
        obs.append(sc.link("Brow." + ("L" if sgn > 0 else "R"), me, col))
    return obs


def eye_material():
    m = bpy.data.materials.new("Eye")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Roughness"].default_value = 0.08
    b.inputs["Coat Weight"].default_value = 1.0
    b.inputs["Coat Roughness"].default_value = 0.02
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    # d = sqrt(x² + z²) / r (спереди), сзади — белок
    sq = []
    for comp in ("X", "Z"):
        mth = nt.nodes.new("ShaderNodeMath")
        mth.operation = 'POWER'
        mth.inputs[1].default_value = 2.0
        nt.links.new(sep.outputs[comp], mth.inputs[0])
        sq.append(mth)
    add = nt.nodes.new("ShaderNodeMath")
    add.operation = 'ADD'
    nt.links.new(sq[0].outputs[0], add.inputs[0])
    nt.links.new(sq[1].outputs[0], add.inputs[1])
    sqrt = nt.nodes.new("ShaderNodeMath")
    sqrt.operation = 'SQRT'
    nt.links.new(add.outputs[0], sqrt.inputs[0])
    div = nt.nodes.new("ShaderNodeMath")
    div.operation = 'DIVIDE'
    div.inputs[1].default_value = E["r"] * MM
    nt.links.new(sqrt.outputs[0], div.inputs[0])
    back = nt.nodes.new("ShaderNodeMath")
    back.operation = 'GREATER_THAN'
    back.inputs[1].default_value = 0.0
    nt.links.new(sep.outputs["Y"], back.inputs[0])
    mx = nt.nodes.new("ShaderNodeMath")
    mx.operation = 'MAXIMUM'
    nt.links.new(div.outputs[0], mx.inputs[0])
    nt.links.new(back.outputs[0], mx.inputs[1])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    cr = ramp.color_ramp
    cr.interpolation = 'LINEAR'
    iris, sclera = sc.srgb(S.COLORS["iris"]), (0.85, 0.80, 0.76)
    stops = [(0.0, (0.005, 0.004, 0.003)), (0.26, (0.005, 0.004, 0.003)), (0.29, tuple(iris * 0.55)),
             (0.45, tuple(iris * 1.25)), (0.58, tuple(iris * 0.8)), (0.62, (0.03, 0.018, 0.01)),
             (0.66, sclera), (1.0, sclera)]
    cr.elements[0].position, cr.elements[0].color = stops[0][0], (*stops[0][1], 1)
    cr.elements[1].position, cr.elements[1].color = stops[-1][0], (*stops[-1][1], 1)
    for pos, c in stops[1:-1]:
        el = cr.elements.new(pos)
        el.color = (*c, 1)
    nt.links.new(mx.outputs[0], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    return m


def build_eyes(col):
    mat = eye_material()
    obs = []
    for sgn in (1, -1):
        me = sc.ellipsoid("Eye", (0, 0, 0), (E["r"] * MM,) * 3, 48, 32)
        ob = sc.link("Eye." + ("L" if sgn > 0 else "R"), me, col)
        ob.location = Vector(eye_center(sgn))
        # взгляд чуть к центру (в камеру)
        ob.rotation_euler = (0, 0, math.radians(-3 * sgn))
        me.materials.append(mat)
        for p in me.polygons:
            p.use_smooth = True
        obs.append(ob)
    return obs


def build_lashes(col, mat):
    """Ресницы-подводка по краю верхнего века и тонкая линия нижнего."""
    obs = []
    r = E["r"]
    for sgn in (1, -1):
        c = eye_center(sgn) / MM
        for upper in (True, False):
            u = np.linspace(-0.92, 1.08, 28)
            upc, dnc = lid_curves(np.clip(u, -1, 1))
            v = (upc + 0.4 + 1.8 * np.clip(u - 0.75, 0, None) * 4) if upper else (dnc - 0.3)
            x = u * E["open_w"] / 2
            rr = r + (1.9 if upper else 1.2)
            y = -np.sqrt(np.clip(rr ** 2 - x ** 2 - v ** 2, 1, None))
            pts = np.stack([c[0] + sgn * x, c[1] + y, c[2] + v], axis=1) * MM
            t = (u + 0.92) / 2.0
            rad = ((1.0 + 0.9 * np.sin(np.pi * np.clip(t * 1.1, 0, 1))) if upper else (0.45 + 0.2 * np.sin(np.pi * t))) * MM
            me = sc.tube("Lash", pts, rad, rad * (0.7 if upper else 1.0), n_pts=10)
            ob = sc.link("Lash", me, col)
            me.materials.append(mat)
            sc.set_color_attr(ob, np.tile(np.array([0.012, 0.007, 0.005]), (len(me.vertices), 1)))
            for p in me.polygons:
                p.use_smooth = True
            obs.append(ob)
    return obs


def build_teeth(col, mat):
    m = H["mouth"]
    zc = m["z"] - 3.5
    R = 46.0
    cy = -102 + R
    angs = np.radians(np.linspace(-42, 42, 30))
    path = np.stack([R * np.sin(angs), cy - R * np.cos(angs), np.full_like(angs, zc)], axis=1) * MM
    me = sc.tube("Teeth", path, np.full(len(path), 3.0 * MM), np.full(len(path), 6.5 * MM), n_pts=16,
                 up=np.array([0, 0, 1.0]))
    ob = sc.link("Teeth", me, col)
    me.materials.append(mat)
    for p in me.polygons:
        p.use_smooth = True
    return ob


def head_colors(ob, hidden, hole, ul, ll):
    co = sc.mesh_points(ob) / MM
    lin = {k: sc.srgb(v) for k, v in S.COLORS.items()}
    col = np.tile(lin["skin"], (len(co), 1))
    # румянец
    for sgn in (1, -1):
        d = np.linalg.norm((co - np.array([sgn * 52, -90, 1428])) / np.array([26, 30, 20]), axis=1)
        w = sc.falloff(d)[:, None] * 0.35
        col = col * (1 - w) + lin["blush"] * w
    col[ul] = lin["lips"] * 0.95
    col[ll] = lin["lips"]
    col[hole] = np.array([0.08, 0.015, 0.012])
    col[hidden] = np.array([0.05, 0.02, 0.02])
    # чуть темнее веки
    return col


def build_head(col, mat_attr):
    ob = head_blocking(col)
    s = sc.Sculpt(ob)
    # скулы и щёки — кистью Inflate, нос — сгладить в единую форму
    for sgn in (1, -1):
        s.draw((sgn * 46 * MM, -0.080, 1.428), 32 * MM, 5.0 * MM)
    s.smooth_region((0, -0.112, 1.438), 26 * MM, iters=6, lam=0.5)
    hidden = carve_eyes(s)
    hole, ul, ll = carve_mouth(s)
    # подбородок чуть вперёд-вниз, скулы
    s.grab((0, -0.098, 1.352), 20 * MM, np.array([0, -3.0, -3.0]) * MM)
    s.commit()
    sc.set_color_attr(ob, head_colors(ob, hidden, hole, ul, ll))
    ob.data.materials.append(mat_attr("Skin_Head", 0.42, sss=0.3))
    out = {"head": ob}
    brow_mat = mat_attr("Brows", 0.8)
    for b in eyebrows(ob, col):
        sc.set_color_attr(b, np.tile(sc.srgb(S.COLORS["brow"]), (len(b.data.vertices), 1)))
        b.data.materials.append(brow_mat)
        for p in b.data.polygons:
            p.use_smooth = True
        out[b.name] = b
    for e in build_eyes(col):
        out[e.name] = e
    for i, l in enumerate(build_lashes(col, mat_attr("Lashes", 0.5))):
        out[f"lash{i}"] = l
    teeth_mat = mat_attr("Teeth", 0.25)
    t = build_teeth(col, teeth_mat)
    sc.set_color_attr(t, np.tile(sc.srgb(S.COLORS["teeth"]), (len(t.data.vertices), 1)))
    out["teeth"] = t
    return out
