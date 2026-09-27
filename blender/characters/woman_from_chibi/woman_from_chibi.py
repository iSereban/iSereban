"""
Переделка чиби-девочки (Meshy) во взрослую женщину 50+ по референсу.

Шаги:
  1. Цвета вершин берутся из текстуры модели. Меш Meshy состоит из сотен кусков:
     куски, где больше половины «волосяного» цвета, удаляются целиком, кепка — по красному цвету,
     кусок лица (кожа) сохраняется вместе с глазами
  2. Взрослые пропорции: кости ног/корпуса/рук растягиваются, голова (жёстко) уменьшается;
     сдвиги сглаживаются по объёму, чтобы куски одежды не рвались; рост 1,65 м
  3. Под лицом — гладкий череп (у девочки затылка не было, его закрывали волосы)
  4. Раскраска по референсу (characters/woman_meshy): лицо совмещается по зоне кожи лица,
     одежда — по силуэту и зонам
  5. Причёска: пряди от пробора по голове, косая чёлка, волнистое каре до плеч, седая прядь

  python woman_from_chibi.py --glb <девочка.glb> --out out
"""
import json
import math
import os
import random
import sys

import bpy  # noqa: I001
import bmesh
import numpy as np
from mathutils.bvhtree import BVHTree
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
_sd = getattr(bpy.context, "space_data", None)
if _sd is not None and getattr(_sd, "text", None) is not None and _sd.text.filepath:
    HERE = os.path.dirname(bpy.path.abspath(_sd.text.filepath))
sys.path.insert(0, os.path.join(HERE, "..", "..", "common"))
sys.path.insert(0, os.path.join(HERE, "..", "woman_meshy"))
import autorig  # noqa: E402
import studio  # noqa: E402
import woman_meshy  # noqa: E402

GLB_PATH = r"C:\Users\New\Downloads\Meshy_AI_Chibi_Figure_0926172701_texture.glb"
JOINTS = os.path.join(HERE, "..", "..", "scenes", "chibi_walk", "Meshy_AI_Chibi_Figure_0926172701_texture.joints.json")
HEIGHT = 1.65

# масштаб костей (x, y — вдоль кости, z): чиби → взрослая
BONE_SCALE = {
    "head": (0.68, 0.68, 0.68), "neck": (1.0, 1.7, 1.0),
    "hips": (1.1, 1.25, 1.1), "spine": (1.05, 1.5, 1.05), "chest": (1.05, 1.45, 1.05),
    "thigh": (1.05, 2.3, 1.05), "shin": (1.0, 2.45, 1.0), "foot": (1.0, 1.2, 1.0),
    "shoulder": (1.0, 1.35, 1.0), "upper_arm": (1.0, 1.9, 1.0), "forearm": (1.0, 1.9, 1.0), "hand": (1.0, 1.05, 1.0),
}


# ---------------------------------------------------------------------------
# Цвет вершин из текстуры
# ---------------------------------------------------------------------------
def base_color_pixels(obj):
    mat = obj.data.materials[0]
    b = mat.node_tree.nodes.get("Principled BSDF")
    img = None
    if b and b.inputs["Base Color"].is_linked:
        img = getattr(b.inputs["Base Color"].links[0].from_node, "image", None)
    if img is None:
        img = max((n.image for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image), key=lambda i: i.size[0])
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    return px.reshape(h, w, 4)[:, :, :3], w, h


def vertex_colors(obj):
    px, w, h = base_color_pixels(obj)
    me = obj.data
    uv = np.empty(len(me.loops) * 2, dtype=np.float32)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    li = np.empty(len(me.loops), dtype=np.int64)
    me.loops.foreach_get("vertex_index", li)
    x = np.clip((uv[:, 0] % 1.0) * (w - 1), 0, w - 1).astype(int)
    y = np.clip((uv[:, 1] % 1.0) * (h - 1), 0, h - 1).astype(int)
    col = np.zeros((len(me.vertices), 3), dtype=np.float32)
    col[li] = px[y, x]
    return col


def coords(obj):
    co = np.empty(len(obj.data.vertices) * 3)
    obj.data.vertices.foreach_get("co", co)
    return co.reshape(-1, 3)


# ---------------------------------------------------------------------------
# 1–2. Удалить волосы и кепку
# ---------------------------------------------------------------------------
def islands(obj):
    """Номер связного куска для каждой вершины (union-find по рёбрам)."""
    me = obj.data
    e = np.zeros(len(me.edges) * 2, np.int64)
    me.edges.foreach_get("vertices", e)
    e = e.reshape(-1, 2)
    p = np.arange(len(me.vertices))
    while True:
        m = np.minimum(p[e[:, 0]], p[e[:, 1]])
        np.minimum.at(p, e[:, 0], m)
        np.minimum.at(p, e[:, 1], m)
        q = p[p]
        if np.array_equal(q, p) and np.array_equal(p[e[:, 0]], p[e[:, 1]]):
            return p
        p = q


def remove_hair_and_cap(obj, lm):
    cols = vertex_colors(obj)
    co = coords(obj)
    H = co[:, 2].max()
    r, g, b = cols[:, 0], cols[:, 1], cols[:, 2]
    cap = (r > 0.55) & (g < 0.28) & (r > 2.2 * g) & (co[:, 2] > lm["neck"] - 0.02)
    ratio = r / np.maximum(g, 1e-3)
    skin = (r > 0.75) & (g > 0.52)
    hair = (r > 0.06) & (r < 0.80) & (ratio > 1.18) & (ratio < 3.0) & (b < 0.5) & (r >= b) & ~skin
    # меш Meshy состоит из сотен отдельных кусков: решаем по куску целиком
    isl = islands(obj)
    _, inv, cnt = np.unique(isl, return_inverse=True, return_counts=True)
    hair_frac = np.bincount(inv, hair) / cnt
    skin_frac = np.bincount(inv, skin) / cnt
    zc = np.bincount(inv, co[:, 2]) / cnt
    face = (skin_frac > 0.3) & (zc > lm["neck"])          # лицо — вместе с глазами не трогаем
    body = co[:, 2] > lm["crotch"] + 0.08
    kill = cap | (body & (hair_frac[inv] > 0.45)) | (body & hair & ~face[inv])
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[bm.verts[i] for i in np.where(kill)[0]], context='VERTS')
    # мелкие обрывки (острова) — удалить
    bm.verts.ensure_lookup_table()
    seen, parts = set(), []
    for v in bm.verts:
        if v.index in seen:
            continue
        stack, isl = [v], []
        seen.add(v.index)
        while stack:
            a = stack.pop()
            isl.append(a)
            for e in a.link_edges:
                o = e.other_vert(a)
                if o.index not in seen:
                    seen.add(o.index)
                    stack.append(o)
        parts.append(isl)
    biggest = max(len(i) for i in parts)
    small = [v for isl in parts if len(isl) < biggest * 0.02 for v in isl]
    bmesh.ops.delete(bm, geom=small, context='VERTS')
    bm.to_mesh(obj.data)
    bm.free()
    print(f"удалено: кепка {int(cap.sum())}, волосы {int((kill & ~cap).sum())} вершин; обрывков {len(small)}")


# ---------------------------------------------------------------------------
# 3. Взрослые пропорции
# ---------------------------------------------------------------------------
def adultify(obj, lm):
    arm = autorig.build_rig(obj, lm, name="Tmp_Rig", weights="distance")
    # голова — жёстко (иначе она «размажется» при уменьшении)
    co = coords(obj)
    neck = lm["neck"]
    hv = [i for i in range(len(co)) if co[i, 2] > neck + 0.005]
    for gname in [g.name for g in obj.vertex_groups]:
        if gname != "head":
            obj.vertex_groups[gname].remove(hv)
    obj.vertex_groups["head"].add(hv, 1.0, 'REPLACE')
    old_co = coords(obj)
    for b in arm.data.bones:
        b.inherit_scale = 'NONE'
    for pb in arm.pose.bones:
        key = pb.name.split(".")[0]
        if key in BONE_SCALE:
            pb.scale = BONE_SCALE[key]
    bpy.context.view_layer.update()
    head_base = (arm.matrix_world @ arm.pose.bones["head"].head).copy()
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(obj.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    me.transform(obj.matrix_world)
    old = obj.data
    obj.modifiers.clear()
    obj.parent = None
    obj.matrix_world = Matrix.Identity(4)
    obj.data = me
    bpy.data.meshes.remove(old)
    bpy.data.objects.remove(arm, do_unlink=True)
    for g in list(obj.vertex_groups):
        obj.vertex_groups.remove(g)
    keep = old_co[:, 2] > neck - 0.01
    new = smooth_displacement(old_co, coords(obj), keep)
    obj.data.vertices.foreach_set("co", new.ravel())
    obj.data.update()
    return head_base


def normalize(obj, height):
    co = coords(obj)
    mn, mx = co.min(0), co.max(0)
    s = height / (mx[2] - mn[2])
    M = Matrix.Diagonal((s, s, s, 1)) @ Matrix.Translation((-(mn[0] + mx[0]) / 2, -(mn[1] + mx[1]) / 2, -mn[2]))
    obj.data.transform(M)
    return M


# ---------------------------------------------------------------------------
# 4. Причёска по форме головы
# ---------------------------------------------------------------------------
class HeadShape:
    """Гладкая форма головы — эллипсоид по вершинам головы (с запасом, чтобы волосы не проваливались)."""

    def __init__(self, obj, neck_z, face_top):
        # от головы девочки после удаления волос остаётся только «маска» лица с ушами —
        # ширину и перед берём из неё, глубину и высоту черепа — по взрослым пропорциям
        co = coords(obj)
        hv = co[co[:, 2] > neck_z]
        lo, hi = np.percentile(hv, 1, axis=0), np.percentile(hv, 99, axis=0)
        w = (hi[0] - lo[0]) / 2
        self.chin = float(neck_z)
        self.rx = w * 1.02
        self.ry = w * 1.18
        self.top = face_top + 0.65 * (face_top - neck_z)
        self.rz = (self.top - neck_z) / 1.86
        self.c = Vector(((lo[0] + hi[0]) / 2, lo[1] + self.ry * 0.93, neck_z + self.rz * 0.86))
        # линия роста волос надо лбом (угол от макушки)
        self.front_th = math.acos(max(-1.0, min(1.0, (face_top + 0.01 - self.c.z) / self.rz)))
        self.hh = self.top - neck_z

    def outer(self, th, ph, lift, bvh):
        """Точка на внешней поверхности головы (эллипсоид или реальный меш — что дальше от центра)."""
        p, n = self.surface(th, ph)
        if bvh is not None:
            d = (p - self.c).normalized()
            hit = bvh.ray_cast(self.c + d * 3 * max(self.rx, self.ry, self.rz), -d)
            if hit[0] is not None and (hit[0] - self.c).length > (p - self.c).length:
                p = hit[0]
        return p + n * lift

    def surface(self, th, ph):
        d = Vector((math.sin(th) * math.sin(ph), -math.sin(th) * math.cos(ph), math.cos(th)))
        p = self.c + Vector((d.x * self.rx, d.y * self.ry, d.z * self.rz))
        n = Vector((d.x / self.rx, d.y / self.ry, d.z / self.rz)).normalized()
        return p, n

    def radius(self, z, ph):
        u = max(-1.0, min(1.0, (z - self.c.z) / self.rz))
        k = math.sqrt(max(1 - u * u, 0.05))
        a, b = self.rx * k, self.ry * k
        return 1.0 / math.sqrt((math.sin(ph) / a) ** 2 + (math.cos(ph) / b) ** 2)


def add_skull(obj, head):
    """Гладкий череп под лицом: закрывает дыры и пустой затылок (волосы девочки были «крышкой»)."""
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=32, radius=1.0, location=head.c)
    sk = bpy.context.active_object
    sk.scale = (head.rx * 0.97, head.ry * 0.97, head.rz * 0.97)
    bpy.ops.object.transform_apply(scale=True)
    bm = bmesh.new()
    bm.from_mesh(sk.data)
    cut = head.chin + 0.12 * head.hh
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if (sk.matrix_world @ v.co).z < cut], context='VERTS')
    bm.to_mesh(sk.data)
    bm.free()
    bpy.ops.object.shade_smooth()
    for o in bpy.context.selected_objects:
        o.select_set(False)
    sk.select_set(True)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.join()


def smooth_displacement(old, new, keep, cell=0.03):
    """Сдвиги вершин усредняются по соседним вокселям и плавно интерполируются:
    куски одежды двигаются вместе, без разрывов и лоскутов."""
    d = new - old
    f = old / cell
    k = np.floor(f).astype(np.int64)
    k0 = k.min(0) - 2
    dims = k.max(0) - k0 + 3

    def enc(kk):
        kk = kk - k0
        return (kk[:, 0] * dims[1] + kk[:, 1]) * dims[2] + kk[:, 2]

    uk, inv = np.unique(enc(k), return_inverse=True)
    sums = np.zeros((len(uk), 3))
    np.add.at(sums, inv, d)
    cnt = np.bincount(inv, minlength=len(uk)).astype(float)
    ucell = np.zeros((len(uk), 3), np.int64)
    ucell[inv] = k

    def lookup(kk):
        key = enc(kk)
        j = np.clip(np.searchsorted(uk, key), 0, len(uk) - 1)
        return j, uk[j] == key

    # среднее по 3×3×3 соседям — значение в центре каждого вокселя
    acc, num = np.zeros_like(sums), np.zeros(len(uk))
    for o in np.array(np.meshgrid([-1, 0, 1], [-1, 0, 1], [-1, 0, 1])).T.reshape(-1, 3):
        j, ok = lookup(ucell + o)
        acc[ok] += sums[j[ok]]
        num[ok] += cnt[j[ok]]
    grid = acc / num[:, None]
    # трилинейная интерполяция между центрами вокселей
    g = f - 0.5
    base = np.floor(g).astype(np.int64)
    w = g - base
    out_d, wsum = np.zeros_like(d), np.zeros(len(d))
    for o in np.array(np.meshgrid([0, 1], [0, 1], [0, 1])).T.reshape(-1, 3):
        j, ok = lookup(base + o)
        wt = np.prod(np.where(o == 1, w, 1 - w), axis=1) * ok
        out_d += grid[j] * wt[:, None]
        wsum += wt
    out = old + out_d / np.maximum(wsum, 1e-9)[:, None]
    out[keep] = new[keep]
    return out


def hairline_theta(head, ph):
    """Граница волос: лоб высоко, виски ниже, затылок до шеи (угол θ от макушки)."""
    a = abs(math.remainder(ph, 2 * math.pi))
    f = head.front_th
    if a < 0.9:
        return f
    if a < 1.5:
        return f + (math.radians(102) - f) * (a - 0.9) / 0.6
    return math.radians(102 + min(1.0, (a - 1.5) / 1.3) * 28)


def build_hair(head, mats, part_ph=-0.45, seed=5, bvh=None):
    rng = random.Random(seed)
    hh = head.hh
    # плотная основа
    bm = bmesh.new()
    nph, nt = 72, 18
    grid = []
    for j in range(nph):
        ph = -math.pi + 2 * math.pi * j / nph
        tl = hairline_theta(head, ph)
        row = []
        for i in range(nt + 1):
            th = tl * (i / nt) ** 0.9 + 1e-3
            p, n = head.surface(th, ph)
            row.append(bm.verts.new(p + n * hh * (0.006 + 0.02 * math.cos(th) ** 2)))
        grid.append(row)
    for j in range(nph):
        k = (j + 1) % nph
        for i in range(nt):
            bm.faces.new((grid[j][i], grid[k][i], grid[k][i + 1], grid[j][i + 1]))
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new("HairCap")
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(mats["hair"])
    cap = bpy.data.objects.new("HairCap", me)
    bpy.context.scene.collection.objects.link(cap)

    # волнистые пряди до плеч
    z_end0 = head.chin - hh * 0.25
    lists = {"hair": [], "grey": []}
    for th_r, n in ((0.86, 30), (1.10, 36), (1.34, 32), (1.58, 26)):
        for k in range(n):
            ph0 = -math.pi + 2 * math.pi * (k + rng.random()) / n
            if th_r > hairline_theta(head, ph0) - 0.05 or (abs(ph0) < 0.95 and th_r > 0.3):
                continue
            p0, _ = head.surface(th_r, ph0)
            side = 1 if math.remainder(ph0 - part_ph, 2 * math.pi) > 0 else -1
            a0 = abs(ph0)
            if a0 < 1.3:
                ph_end = side * max(a0 if (ph0 > 0) == (side > 0) else 0, 1.25) + side * rng.uniform(0.05, 0.4)
            else:
                ph_end = ph0 + side * rng.uniform(0.05, 0.25)
            z_end = z_end0 + rng.uniform(-0.05, 0.12) * hh + (0.08 * hh if a0 < 1.6 else 0)
            s1, s2 = rng.uniform(0, 6.28), rng.uniform(0, 6.28)
            curl = rng.choice((-1, 1)) * rng.uniform(0.02, 0.05) * hh
            lift = hh * rng.uniform(0.015, 0.04)
            pts, core_prev = [], 0.0
            for i in range(27):
                t = i / 26
                ph = ph0 + (ph_end - ph0) * (3 * min(t / 0.18, 1) ** 2 - 2 * min(t / 0.18, 1) ** 3)
                z = p0.z + (z_end - p0.z) * (t ** 1.3 if abs(ph0) < 1.3 else t)
                base = head.radius(max(z, head.chin + 0.02 * hh), ph)
                core = max(base + lift, core_prev - 0.01 * hh)
                core_prev = core
                bob = hh * 0.16 * max(0.0, min(1.0, (t - 0.3) / 0.6)) * (1.0 if abs(ph) > 1.0 else 0.6)
                r = core + bob
                amp = hh * 0.05 * max(0.0, min(1.0, (t - 0.22) / 0.3))
                r += amp * math.sin(2 * math.pi * z / (hh * 0.55) + s1)
                phw = ph + amp / hh * 4.0 * math.cos(2 * math.pi * z / (hh * 0.6) + s2)
                r += curl * max(0.0, min(1.0, (t - 0.82) / 0.18))
                if i == 0:
                    r = math.hypot(p0.x - head.c.x, p0.y - head.c.y) + 0.01 * hh
                rad = hh * (0.028 + 0.016 * math.sin(math.pi * min(t * 1.4, 1))) * (1 - 0.75 * t ** 3)
                pts.append((Vector((head.c.x + r * math.sin(phw), head.c.y - r * math.cos(phw), z)), rad))
            grey = rng.random() < 0.01
            lists["grey" if grey else "hair"].append(pts)
    for pts, grey in top_locks(head, rng, part_ph, bvh):
        lists["grey" if grey else "hair"].append(pts)
    objs = [cap]
    for key, lst in lists.items():
        cu = bpy.data.curves.new(f"Hair_{key}", 'CURVE')
        cu.dimensions = '3D'
        cu.bevel_depth = 1.0
        cu.bevel_resolution = 2
        cu.use_fill_caps = True
        for pts in lst:
            sp = cu.splines.new('POLY')
            sp.points.add(len(pts) - 1)
            for i, (p, rad) in enumerate(pts):
                sp.points[i].co = (p.x, p.y, p.z, 1.0)
                sp.points[i].radius = rad
            sp.use_smooth = True
        cu.materials.append(mats["hair"] if key == "hair" else mats["grey"])
        o = bpy.data.objects.new(f"Hair_{key}", cu)
        bpy.context.scene.collection.objects.link(o)
        objs.append(o)
    return objs


def top_locks(head, rng, part_ph, bvh=None, n=220):
    """Пряди от пробора по голове: макушка закрыта, спереди косая чёлка набок, дальше волна до плеч."""
    hh = head.hh
    out = []
    sweep = 1                      # чёлка уходит в сторону +φ (её левая сторона)
    for k in range(n):
        ph_end = -math.pi + 2 * math.pi * (k + rng.random()) / n
        rel = math.remainder(ph_end - part_ph, 2 * math.pi)
        side = 1 if rel > 0 else -1
        front = abs(ph_end) < 0.95
        th0, ph0 = rng.uniform(0.04, 0.14), part_ph + side * 0.04
        if front and side == sweep:
            # косая чёлка: от пробора через лоб, опускаясь к виску
            f = (rel / max(math.remainder(0.95 - part_ph, 2 * math.pi), 0.1))
            ctrl = [(th0, ph0), (head.front_th * (0.72 + 0.3 * f + 0.05 * rng.random()), ph_end),
                    (head.front_th + 0.35, sweep * rng.uniform(1.3, 1.65))]
        elif front:
            # со стороны пробора — зачёсаны назад за ухо, лоб частично открыт
            ctrl = [(th0, ph0), (head.front_th * (0.7 + 0.08 * rng.random()), ph_end),
                    (head.front_th + 0.3, -sweep * rng.uniform(1.35, 1.7))]
        else:
            ctrl = [(th0, ph0), (hairline_theta(head, ph_end) * rng.uniform(0.7, 0.9), ph_end)]
        lift = hh * rng.uniform(0.02, 0.035)
        pts = []
        # 1) по поверхности головы
        m = 14
        for i in range(m):
            t = i / (m - 1) * (len(ctrl) - 1)
            j = min(int(t), len(ctrl) - 2)
            f = t - j
            f = f * f * (3 - 2 * f)
            th = ctrl[j][0] + (ctrl[j + 1][0] - ctrl[j][0]) * f
            dph = math.remainder(ctrl[j + 1][1] - ctrl[j][1], 2 * math.pi)
            ph = ctrl[j][1] + dph * f
            rad = hh * (0.03 + 0.016 * math.sin(math.pi * i / (m - 1)))
            pts.append((head.outer(th, ph, lift, bvh), rad))
        # 2) свободно вниз, волной, до плеч
        ph_f = ctrl[-1][1]
        p_last = pts[-1][0]
        z0 = p_last.z
        z_end = head.chin - hh * rng.uniform(0.18, 0.32)
        s1 = rng.uniform(0, 6.28)
        r0 = math.hypot(p_last.x - head.c.x, p_last.y - head.c.y)
        for i in range(1, 15):
            t = i / 14
            z = z0 + (z_end - z0) * t
            base = head.radius(max(z, head.chin + 0.02 * hh), ph_f) + lift
            r = max(base, r0 - 0.02 * hh) + hh * 0.14 * t ** 1.5
            amp = hh * 0.045 * min(1.0, t / 0.3)
            r += amp * math.sin(2 * math.pi * z / (hh * 0.55) + s1)
            ph = ph_f + side * 0.12 * t
            rad = hh * 0.04 * (1 - 0.75 * t ** 3)
            pts.append((Vector((head.c.x + r * math.sin(ph), head.c.y - r * math.cos(ph), z)), rad))
        grey = (-0.55 < rel < -0.2 and front) or (0 < rel < 0.12 and front)
        out.append((pts, grey))
    return out


def hair_material(name, color, light):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Roughness"].default_value = 0.5
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (240, 240, 20)
    nz = nt.nodes.new("ShaderNodeTexNoise")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (*color, 1)
    ramp.color_ramp.elements[1].position = 0.75
    ramp.color_ramp.elements[1].color = (*light, 1)
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.25
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], nz.inputs["Vector"])
    nt.links.new(nz.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    nt.links.new(nz.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return mat


# ---------------------------------------------------------------------------
# 5. Совмещение лица с картинкой по зоне кожи
# ---------------------------------------------------------------------------
def face_boxes(obj, cols, neck_z):
    """Прямоугольник кожи лица на модели (x, z) и на картинке (пиксели)."""
    co = coords(obj)
    H = co[:, 2].max()
    skin = (cols[:, 0] > 0.80) & (cols[:, 1] > 0.62) & (cols[:, 2] > 0.55) & (cols[:, 0] - cols[:, 2] > 0.08)
    head = (co[:, 2] > neck_z + 0.01 * H)
    front = co[:, 1] < np.median(co[head, 1])
    m = skin & head & front
    fx0, fx1 = np.percentile(co[m, 0], [3, 97])
    fz0, fz1 = np.percentile(co[m, 2], [3, 97])
    _img, px = woman_meshy.load_reference(woman_meshy.REF_FRONT)
    sil = woman_meshy.silhouette(px)
    top, neck = sil["top"], sil["neck"]
    y0 = top + int(0.25 * (neck - top))
    reg = px[y0:neck]
    skin_c = np.array(woman_meshy.PALETTE["skin"], dtype=float)
    d = np.linalg.norm(reg - skin_c, axis=2)
    hc = sil["head_cx"]
    ys, xs = np.where(d < 32)
    keep = np.abs(xs - hc) < 0.33 * (neck - top)
    ys, xs = ys[keep], xs[keep]
    ix0, ix1 = np.percentile(xs, [6, 94])
    iy0, iy1 = np.percentile(ys + y0, [6, 97])
    return dict(model=(fx0, fx1, fz0, fz1), image=(ix0, ix1, iy0, iy1))


def build(glb=None):
    studio.clear_scene()
    glb = glb or studio.arg("--glb", GLB_PATH)
    obj = autorig.import_character(glb, height=1.0, name="Woman")
    with open(JOINTS, encoding="utf-8") as f:
        lm = autorig.landmarks_from_joints(json.load(f), 1.0)
    remove_hair_and_cap(obj, lm)
    head_base = adultify(obj, lm)
    M = normalize(obj, HEIGHT)
    neck_z = (M @ head_base).z
    cols = vertex_colors(obj)
    fb = face_boxes(obj, cols, neck_z)
    print("лицо: модель", [round(v, 3) for v in fb["model"]], "картинка", [round(v) for v in fb["image"]])
    head = HeadShape(obj, neck_z, fb["model"][3])
    add_skull(obj, head)
    woman_meshy.paint(obj, face_boxes=fb, neck_z=neck_z)
    mats = {"hair": hair_material("Hair", (0.030, 0.014, 0.006), (0.075, 0.040, 0.020)),
            "grey": hair_material("Hair_Grey", (0.16, 0.15, 0.145), (0.40, 0.39, 0.38))}
    dg = bpy.context.evaluated_depsgraph_get()
    hair = build_hair(head, mats, bvh=BVHTree.FromObject(obj, dg))
    return obj, hair


def main():
    build()
    out = studio.arg("--out")
    if not out:
        return
    out = os.path.abspath(out)
    os.makedirs(out, exist_ok=True)
    studio.studio_lights(target=(0, 0, 0.9))
    studio.floor(color=(0.45, 0.42, 0.40))
    studio.setup_render("CYCLES", studio.RES_480, int(studio.arg("--samples", 16)), exposure=-0.3)
    H = HEIGHT
    for name, loc, tgt, lens in (("front", (0, -4.8, 1.0), (0, 0, 0.92), 50), ("34", (-2.7, -3.9, 1.2), (0, 0, 0.92), 50),
                                 ("side", (4.8, 0, 1.0), (0, 0, 0.92), 50), ("back", (0.3, 4.8, 1.1), (0, 0, 0.92), 50),
                                 ("face", (-0.25, -1.2, H * 0.98), (0, 0, H * 0.965), 60)):
        studio.render_still(os.path.join(out, f"woman_{name}.jpg"), studio.camera(name, loc, tgt, lens))
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "woman_from_chibi.blend"), compress=True)


if __name__ == "__main__":
    main()
