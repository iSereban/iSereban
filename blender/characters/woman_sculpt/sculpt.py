"""
Инструменты «скульптинга кодом»: блокинг из сечений/трубок → voxel remesh → кисти.

Кисти повторяют кисти режима Sculpt в Blender:
  draw (выдавить/вдавить по нормали), inflate, grab (сдвиг), crease (борозда по кривой),
  smooth (сглаживание), flatten; спад (falloff) — гладкий (1 − t²)².
"""
import math

import bpy  # noqa: I001
import bmesh
import numpy as np
from mathutils import Vector
from mathutils.kdtree import KDTree

MM = 0.001


# ---------------------------------------------------------------- построение мешей
def link(name, me, col=None):
    ob = bpy.data.objects.new(name, me)
    (col or bpy.context.scene.collection).objects.link(ob)
    return ob


def mesh_from_rings(name, rings, cap_start=True, cap_end=True, closed=True):
    """rings: список массивов (N,3) одинаковой длины. closed — кольца замкнуты."""
    bm = bmesh.new()
    vs = [[bm.verts.new(tuple(p)) for p in r] for r in rings]
    n = len(rings[0])
    m = n if closed else n - 1
    for i in range(len(rings) - 1):
        for j in range(m):
            k = (j + 1) % n
            bm.faces.new((vs[i][j], vs[i][k], vs[i + 1][k], vs[i + 1][j]))
    for flag, ring in ((cap_start, 0), (cap_end, -1)):
        if flag and closed:
            c = bm.verts.new(tuple(np.mean(rings[ring], axis=0)))
            for j in range(n):
                k = (j + 1) % n
                bm.faces.new((vs[ring][j], vs[ring][k], c))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return me


def superellipse(n_pts, a, b_front, b_back, cx=0.0, cy=0.0, z=0.0, p=2.4):
    """Кольцо сечения корпуса: полуширина a, перёд −b_front, спина +b_back."""
    t = np.linspace(0, 2 * math.pi, n_pts, endpoint=False)
    c, s = np.cos(t), np.sin(t)
    x = a * np.sign(c) * np.abs(c) ** (2 / p)
    yy = np.abs(s) ** (2 / p)
    y = np.where(s < 0, -b_front * yy, b_back * yy)
    return np.stack([cx + x, cy + y, np.full_like(x, z)], axis=1)


def interp_table(rows, zs):
    """rows: [(z, v1, v2, ...)] → значения при zs (сглаженная интерполяция)."""
    rows = sorted(rows, key=lambda r: r[0])
    arr = np.array(rows, float)
    out = np.stack([np.interp(zs, arr[:, 0], arr[:, k]) for k in range(1, arr.shape[1])], axis=1)
    # лёгкое сглаживание, чтобы не было изломов в узлах
    for _ in range(3):
        out[1:-1] = 0.25 * out[:-2] + 0.5 * out[1:-1] + 0.25 * out[2:]
    return out


def catmull(points, step):
    """Гладкая кривая через точки (Catmull–Rom) с шагом ≈ step. points: (N,k) — первые 3 = координаты."""
    P = np.asarray(points, float)
    P = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        n = max(2, int(np.linalg.norm(p2[:3] - p1[:3]) / step))
        for t in np.linspace(0, 1, n, endpoint=False):
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(P[-2])
    return np.array(out)


def frames(path):
    """Параллельный перенос: касательная, нормаль, бинормаль по пути (N,3)."""
    T = np.gradient(path, axis=0)
    T /= np.linalg.norm(T, axis=1, keepdims=True)
    ref = np.array([0, 0, 1.0]) if abs(T[0][2]) < 0.9 else np.array([1.0, 0, 0])
    N = [np.cross(T[0], ref)]
    N[0] /= np.linalg.norm(N[0])
    for i in range(1, len(T)):
        v = N[-1] - T[i] * np.dot(N[-1], T[i])
        N.append(v / np.linalg.norm(v))
    N = np.array(N)
    B = np.cross(T, N)
    return T, N, B


def tube(name, path, rx, ry=None, n_pts=32, up=None, cap=True):
    """Трубка по пути (N,3) с радиусами rx/ry (массивы N). up — вектор, задающий ориентацию ry."""
    path = np.asarray(path, float)
    rx = np.broadcast_to(np.asarray(rx, float), (len(path),))
    ry = rx if ry is None else np.broadcast_to(np.asarray(ry, float), (len(path),))
    T, N, B = frames(path)
    if up is not None:
        up = np.asarray(up, float)
        U = np.broadcast_to(up, path.shape) if up.ndim == 1 else up
        N = U - T * np.sum(U * T, axis=1, keepdims=True)
        N /= np.linalg.norm(N, axis=1, keepdims=True)
        B = np.cross(T, N)
    t = np.linspace(0, 2 * math.pi, n_pts, endpoint=False)
    rings = [path[i] + np.outer(np.cos(t), B[i]) * rx[i] + np.outer(np.sin(t), N[i]) * ry[i] for i in range(len(path))]
    return mesh_from_rings(name, rings, cap, cap)


def ellipsoid(name, c, r, segs=48, rings=32):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=rings, radius=1.0)
    for v in bm.verts:
        v.co = Vector((c[0] + v.co.x * r[0], c[1] + v.co.y * r[1], c[2] + v.co.z * r[2]))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return me


def join_meshes(name, meshes, col=None):
    """Объединить несколько bpy mesh в один объект (без булевых — для последующего remesh)."""
    bm = bmesh.new()
    for me in meshes:
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return link(name, me, col)


def apply_modifiers(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    old = ob.data
    ob.modifiers.clear()
    ob.data = me
    bpy.data.meshes.remove(old)


def remesh(ob, voxel, smooth_iters=0):
    """Voxel remesh — как кнопка Remesh в режиме Sculpt: всё пересекающееся сливается в одну поверхность."""
    m = ob.modifiers.new("Remesh", 'REMESH')
    m.mode = 'VOXEL'
    m.voxel_size = voxel
    m.adaptivity = 0.0
    m.use_smooth_shade = True
    apply_modifiers(ob)
    if smooth_iters:
        Sculpt(ob).smooth(smooth_iters).commit()
    for p in ob.data.polygons:
        p.use_smooth = True


def solidify(ob, thick, offset=-1.0):
    m = ob.modifiers.new("Solidify", 'SOLIDIFY')
    m.thickness = thick
    m.offset = offset
    m.use_even_offset = True
    apply_modifiers(ob)


# ---------------------------------------------------------------- кисти
def falloff(t):
    t = np.clip(t, 0.0, 1.0)
    return (1 - t * t) ** 2


class Sculpt:
    """Сеанс лепки над мешем: координаты в numpy, кисти, commit() записывает обратно."""

    def __init__(self, ob):
        self.ob = ob
        me = ob.data
        n = len(me.vertices)
        self.co = np.empty(n * 3)
        me.vertices.foreach_get("co", self.co)
        self.co = self.co.reshape(-1, 3)
        e = np.empty(len(me.edges) * 2, np.int64)
        me.edges.foreach_get("vertices", e)
        self.edges = e.reshape(-1, 2)
        self._normals = None

    # --- служебное
    @property
    def n(self):
        if self._normals is None:
            self.commit()
            me = self.ob.data
            nv = np.empty(len(me.vertices) * 3)
            me.vertex_normals.foreach_get("vector", nv)
            self._normals = nv.reshape(-1, 3)
        return self._normals

    def commit(self):
        me = self.ob.data
        me.vertices.foreach_set("co", self.co.ravel())
        me.update()
        self._normals = None
        return self

    def _dirty(self):
        self._normals = None

    def dist(self, c, scale=(1, 1, 1)):
        d = (self.co - np.asarray(c)) / np.asarray(scale)
        return np.linalg.norm(d, axis=1)

    # --- кисти
    def draw(self, c, radius, strength, scale=(1, 1, 1), normal=None):
        """Выдавить (+) / вдавить (−) по нормали поверхности (или по заданному направлению)."""
        w = falloff(self.dist(c, scale) / radius) * strength
        nrm = self.n if normal is None else np.asarray(normal)
        self.co += nrm * w[:, None]
        self._dirty()
        return self

    def grab(self, c, radius, vec, scale=(1, 1, 1)):
        w = falloff(self.dist(c, scale) / radius)
        self.co += np.outer(w, vec)
        self._dirty()
        return self

    def inflate(self, c, radius, strength, scale=(1, 1, 1)):
        return self.draw(c, radius, strength, scale)

    def crease(self, pts, radius, depth, pinch=0.3):
        """Борозда вдоль полилинии pts (N,3): вдавливание + стягивание к линии."""
        pts = np.asarray(pts, float)
        seg_a, seg_b = pts[:-1], pts[1:]
        best_d = np.full(len(self.co), 1e9)
        best_p = np.zeros_like(self.co)
        for a, b in zip(seg_a, seg_b):
            ab = b - a
            t = np.clip(((self.co - a) @ ab) / max(ab @ ab, 1e-12), 0, 1)
            p = a + np.outer(t, ab)
            d = np.linalg.norm(self.co - p, axis=1)
            m = d < best_d
            best_d[m], best_p[m] = d[m], p[m]
        w = falloff(best_d / radius)
        nrm = self.n
        self.co += -nrm * (w * depth)[:, None] + (best_p - self.co) * (w * pinch)[:, None]
        self._dirty()
        return self

    def smooth(self, iters=1, lam=0.5, mask=None):
        e = self.edges
        n = len(self.co)
        deg = np.bincount(e.ravel(), minlength=n).astype(float)
        deg[deg == 0] = 1
        for _ in range(iters):
            acc = np.zeros_like(self.co)
            np.add.at(acc, e[:, 0], self.co[e[:, 1]])
            np.add.at(acc, e[:, 1], self.co[e[:, 0]])
            lap = acc / deg[:, None] - self.co
            k = lam if mask is None else lam * mask[:, None]
            self.co += lap * k
        self._dirty()
        return self

    def smooth_region(self, c, radius, iters=2, lam=0.5, scale=(1, 1, 1)):
        return self.smooth(iters, lam, falloff(self.dist(c, scale) / radius))

    def push_out_of_sphere(self, c, r, band):
        """Всё, что внутри сферы (c, r) и ближе band к ней — вытолкнуть на поверхность r (кожа облегает глаз)."""
        d = self.co - np.asarray(c)
        L = np.linalg.norm(d, axis=1)
        m = L < r
        self.co[m] = np.asarray(c) + d[m] / L[m, None] * r
        self._dirty()
        return m


# ---------------------------------------------------------------- метки частей после remesh
def label_by_nearest(ob, sources):
    """sources: список (метка, массив точек (N,3)). Возвращает метку каждой вершины ob по ближайшей точке."""
    pts = np.concatenate([p for _, p in sources])
    labels = np.concatenate([np.full(len(p), i) for i, (_, p) in enumerate(sources)])
    kd = KDTree(len(pts))
    for i, p in enumerate(pts):
        kd.insert(Vector(p), i)
    kd.balance()
    me = ob.data
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    out = np.empty(len(co), np.int64)
    for i, p in enumerate(co):
        out[i] = labels[kd.find(Vector(p))[1]]
    return out, [name for name, _ in sources]


def mesh_points(me_or_ob):
    me = me_or_ob.data if hasattr(me_or_ob, "data") else me_or_ob
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    return co.reshape(-1, 3)


def set_color_attr(ob, rgb_lin, name="Col"):
    me = ob.data
    if name in me.attributes:
        me.attributes.remove(me.attributes[name])
    a = me.attributes.new(name, 'FLOAT_COLOR', 'POINT')
    rgba = np.concatenate([rgb_lin, np.ones((len(rgb_lin), 1))], axis=1).astype(np.float32)
    a.data.foreach_set("color", rgba.ravel())
    return a


def set_float_attr(ob, vals, name):
    me = ob.data
    if name in me.attributes:
        me.attributes.remove(me.attributes[name])
    a = me.attributes.new(name, 'FLOAT', 'POINT')
    a.data.foreach_set("value", np.asarray(vals, np.float32))
    return a


def srgb(c):
    c = np.asarray(c, float) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
