"""
Авто-риг для сгенерированных персонажей (Meshy / Tripo / Rodin / Hunyuan3D .glb).

Что делает:
  1. import_character(path)  — импорт .glb/.fbx/.obj, склейка в один меш, нормализация:
                               стоит на Z=0, по центру, лицом в −Y, заданный рост.
  2. find_landmarks(obj)     — по срезам сетки находит таз, пах, шею, голову, плечи,
                               кисти, колени, стопы (работает и для чиби-пропорций).
  3. build_rig(obj, lm)      — строит скелет и веса (bone heat, при сбое — по расстоянию).
  4. aim(...)                — поза «направить кость в мировом направлении» (удобно для
                               процедурной анимации, не зависит от ролла костей).

Кости: root, hips, spine, chest, neck, head, shoulder/upper_arm/forearm/hand.L/R,
       thigh/shin/foot.L/R.  L — сторона +X (левая рука персонажа, смотрящего в −Y).
"""

import math

import bpy  # noqa: I001
from mathutils import Matrix, Vector

try:
    import numpy as np
except ImportError:  # в Blender numpy есть всегда
    np = None


# ---------------------------------------------------------------------------
# Импорт
# ---------------------------------------------------------------------------
def import_character(path, height=1.0, turn_deg=0.0, name="Character", col=None):
    """Импорт модели, один меш, рост height, ноги на Z=0, центр по X/Y, поворот turn_deg вокруг Z."""
    before = set(bpy.data.objects)
    ext = path.lower().rsplit(".", 1)[-1]
    if ext in ("glb", "gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == "fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext == "obj":
        if hasattr(bpy.ops.wm, "obj_import"):
            bpy.ops.wm.obj_import(filepath=path)
        else:
            bpy.ops.import_scene.obj(filepath=path)
    else:
        raise ValueError(f"Неизвестный формат: {path}")
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == 'MESH']
    if not meshes:
        raise RuntimeError("В файле нет мешей")

    # снять чужие арматуры/родителей, запечь трансформации в вершины
    dg = bpy.context.evaluated_depsgraph_get()
    baked = []
    for o in meshes:
        me = bpy.data.meshes.new_from_object(o.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
        me.transform(o.matrix_world)
        baked.append(me)
    for o in new:
        bpy.data.objects.remove(o, do_unlink=True)

    obj = bpy.data.objects.new(name, baked[0])
    (col or bpy.context.scene.collection).objects.link(obj)
    if len(baked) > 1:
        others = []
        for me in baked[1:]:
            o = bpy.data.objects.new("tmp", me)
            (col or bpy.context.scene.collection).objects.link(o)
            others.append(o)
        with bpy.context.temp_override(active_object=obj, selected_editable_objects=[obj, *others],
                                       selected_objects=[obj, *others]):
            bpy.ops.object.join()

    # нормализация
    me = obj.data
    if turn_deg:
        me.transform(Matrix.Rotation(math.radians(turn_deg), 4, 'Z'))
    co = _coords(me)
    mn, mx = co.min(axis=0), co.max(axis=0)
    s = height / max(mx[2] - mn[2], 1e-6)
    me.transform(Matrix.Translation((0, 0, 0)) @ Matrix.Diagonal((s, s, s, 1)) @
                 Matrix.Translation((-(mn[0] + mx[0]) / 2, -(mn[1] + mx[1]) / 2, -mn[2])))
    for p in me.polygons:
        p.use_smooth = True
    return obj


def _coords(me):
    co = np.empty(len(me.vertices) * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    return co.reshape(-1, 3)


# ---------------------------------------------------------------------------
# Поиск ориентиров по срезам
# ---------------------------------------------------------------------------
def _tris(me):
    me.calc_loop_triangles()
    idx = np.empty(len(me.loop_triangles) * 3, dtype=np.int64)
    me.loop_triangles.foreach_get("vertices", idx)
    return _coords(me)[idx.reshape(-1, 3)]          # (T, 3, 3)


def _section(tris, z):
    """Сечение плоскостью Z=z: интервалы по X (объединение) и точки пересечения."""
    zz = tris[:, :, 2]
    m = (zz.min(axis=1) < z) & (zz.max(axis=1) > z)
    T = tris[m]
    if len(T) == 0:
        return [], np.zeros((0, 3))
    xs_min = np.full(len(T), np.inf)
    xs_max = np.full(len(T), -np.inf)
    pts = []
    for i, j in ((0, 1), (1, 2), (2, 0)):
        p, q = T[:, i], T[:, j]
        cross = (p[:, 2] - z) * (q[:, 2] - z) < 0
        t = np.where(cross, (z - p[:, 2]) / np.where(cross, q[:, 2] - p[:, 2], 1), 0)
        x = p + (q - p) * t[:, None]
        xs_min = np.where(cross, np.minimum(xs_min, x[:, 0]), xs_min)
        xs_max = np.where(cross, np.maximum(xs_max, x[:, 0]), xs_max)
        pts.append(x[cross])
    ok = np.isfinite(xs_min)
    iv = sorted(zip(xs_min[ok], xs_max[ok]))
    merged = []
    for a, b in iv:
        if merged and a <= merged[-1][1] + 1e-4:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [tuple(v) for v in merged], np.concatenate(pts)


def find_landmarks(obj):
    co = _coords(obj.data)
    tris = _tris(obj.data)
    H = co[:, 2].max()
    W = co[:, 0].max() - co[:, 0].min()
    n = 160
    zs = np.linspace(0, H, n + 1)[1:-1]

    def central(z):
        cl, pts = _section(tris, z)
        for a, b in cl:
            if a <= 0.0 <= b:
                return a, b, pts
        return None, None, pts

    # пах: самая верхняя высота (ниже 60% роста), где по X=0 есть разрыв между ногами
    # (свободные штанины могут соприкасаться ниже — поэтому берём максимум, а не первый разрыв)
    crotch = None
    for z in zs[1:int(n * 0.6)]:
        a, b, s = central(z)
        if a is None and len(s):
            crotch = z
    if crotch is None:
        crotch = 0.30 * H

    # шея: минимальная ширина центрального кластера в верхней части
    best, neck = 1e9, 0.8 * H
    for z in zs[int(n * 0.45):int(n * 0.92)]:
        a, b, s = central(z)
        if a is None:
            continue
        w = b - a
        if w < best:
            best, neck = w, z
    if neck < crotch + 0.1 * H:
        neck = crotch + 0.5 * (H - crotch)

    # торс
    z_chest = crotch + 0.55 * (neck - crotch)
    a, b, s = central(z_chest)
    if a is None:
        a, b = -0.15 * W, 0.15 * W
    torso_hw = (b - a) / 2
    ymid = float(s[:, 1].mean()) if len(s) else 0.0
    shoulder_z = neck - 0.18 * (neck - crotch)

    # кисти: крайние точки по X между пахом и шеей
    band = co[(co[:, 2] > crotch - 0.05 * H) & (co[:, 2] < neck)]
    hands = {}
    for side, sgn in (("L", 1), ("R", -1)):
        xs = band[:, 0] * sgn
        mx = xs.max()
        tip = band[xs > mx - 0.03 * H].mean(axis=0)
        hands[side] = Vector(tip)

    # ноги
    legs = {}
    for side, sgn in (("L", 1), ("R", -1)):
        low = co[(co[:, 2] < crotch * 0.7) & (co[:, 0] * sgn > 0)]
        if len(low) == 0:
            low = co[co[:, 2] < crotch]
        lx = float(np.median(low[:, 0]))
        foot = co[(co[:, 2] < max(0.08 * H, crotch * 0.25)) & (co[:, 0] * sgn > 0)]
        if len(foot) == 0:
            foot = low
        toe_y = float(foot[:, 1].min())
        heel_y = float(foot[:, 1].max())
        ankle_z = max(0.035 * H, crotch * 0.16)
        legs[side] = dict(x=lx, toe_y=toe_y, heel_y=heel_y, ankle_z=ankle_z,
                          ankle_y=heel_y - 0.30 * (heel_y - toe_y))

    return dict(H=H, W=W, crotch=crotch, neck=neck, shoulder_z=shoulder_z, torso_hw=torso_hw,
                ymid=ymid, hands=hands, legs=legs)


# ---------------------------------------------------------------------------
# Скелет и веса
# ---------------------------------------------------------------------------
def bone_layout(lm):
    H, cr, nk, y = lm["H"], lm["crotch"], lm["neck"], lm["ymid"]
    B = {}
    B["root"] = ((0, y, 0), (0, y - 0.15 * H, 0), None)
    hip_z = cr + 0.05 * (nk - cr)
    B["hips"] = ((0, y, hip_z), (0, y, hip_z + 0.30 * (nk - cr)), "root")
    B["spine"] = (B["hips"][1], (0, y, hip_z + 0.60 * (nk - cr)), "hips")
    B["chest"] = (B["spine"][1], (0, y, nk - 0.02 * H), "spine")
    B["neck"] = (B["chest"][1], (0, y, nk + 0.04 * H), "chest")
    B["head"] = (B["neck"][1], (0, y, H), "neck")
    for s, sg in (("L", 1), ("R", -1)):
        sh = Vector((sg * lm["torso_hw"] * 0.80, y, lm["shoulder_z"]))
        tip = lm["hands"][s]
        wrist = sh + (tip - sh) * 0.82
        elbow = (sh + wrist) / 2 + Vector((0, 0.02 * H, 0))
        B[f"shoulder.{s}"] = ((sg * 0.02 * H, y, lm["shoulder_z"]), tuple(sh), "chest")
        B[f"upper_arm.{s}"] = (tuple(sh), tuple(elbow), f"shoulder.{s}")
        B[f"forearm.{s}"] = (tuple(elbow), tuple(wrist), f"upper_arm.{s}")
        B[f"hand.{s}"] = (tuple(wrist), tuple(tip), f"forearm.{s}")
        L = lm["legs"][s]
        hip = Vector((L["x"], y, cr - 0.02 * H))
        ankle = Vector((L["x"], L["ankle_y"], L["ankle_z"]))
        knee = (hip + ankle) / 2 + Vector((0, -0.015 * H, 0))
        B[f"thigh.{s}"] = (tuple(hip), tuple(knee), "hips")
        B[f"shin.{s}"] = (tuple(knee), tuple(ankle), f"thigh.{s}")
        B[f"foot.{s}"] = (tuple(ankle), (L["x"], L["toe_y"] + 0.01 * H, 0.012 * H), f"shin.{s}")
    return B


def landmarks_from_joints(J, H=1.0):
    """Ориентиры/суставы, заданные вручную (JSON, рост 1.0) → масштаб H."""
    k = H
    lm = dict(H=H, W=H, cx=J.get("cx", 0.0) * k, crotch=J["crotch"] * k, neck=J["neck"] * k,
              shoulder_z=J["L"]["shoulder"][2] * k, torso_hw=J["torso_hw"] * k, ymid=0.0,
              hands={s: Vector(J[s]["hand"]) * k for s in "LR"}, legs={}, joints={})
    for s in "LR":
        lm["joints"][s] = {n: Vector(v) * k for n, v in J[s].items()}
    lm["head_top"] = J.get("head_top", 1.0) * k
    lm["chest"] = J.get("chest", (J["crotch"] + J["neck"]) / 2) * k
    return lm


def joint_layout(lm):
    """Кости по явно заданным суставам."""
    cx, cr, nk, H = lm["cx"], lm["crotch"], lm["neck"], lm["H"]
    ch, top = lm["chest"], lm["head_top"]
    B = {}
    B["root"] = ((cx, 0, 0), (cx, -0.15 * H, 0), None)
    B["hips"] = ((cx, 0, cr), (cx, 0, cr + 0.45 * (ch - cr)), "root")
    B["spine"] = (B["hips"][1], (cx, 0, ch), "hips")
    B["chest"] = (B["spine"][1], (cx, 0, nk - 0.03 * H), "spine")
    B["neck"] = (B["chest"][1], (cx, 0, nk + 0.02 * H), "chest")
    B["head"] = (B["neck"][1], (cx, 0, top), "neck")
    for s in "LR":
        j = lm["joints"][s]
        B[f"shoulder.{s}"] = ((cx, 0, j["shoulder"].z), tuple(j["shoulder"]), "chest")
        B[f"upper_arm.{s}"] = (tuple(j["shoulder"]), tuple(j["elbow"]), f"shoulder.{s}")
        B[f"forearm.{s}"] = (tuple(j["elbow"]), tuple(j["wrist"]), f"upper_arm.{s}")
        B[f"hand.{s}"] = (tuple(j["wrist"]), tuple(j["hand"]), f"forearm.{s}")
        B[f"thigh.{s}"] = (tuple(j["hip"]), tuple(j["knee"]), "hips")
        B[f"shin.{s}"] = (tuple(j["knee"]), tuple(j["ankle"]), f"thigh.{s}")
        B[f"foot.{s}"] = (tuple(j["ankle"]), tuple(j["toe"]), f"shin.{s}")
    return B


def build_rig(obj, lm, name="Rig", col=None, weights="auto"):  # weights: "auto" | "distance"
    arm_data = bpy.data.armatures.new(name)
    arm = bpy.data.objects.new(name, arm_data)
    (col or bpy.context.scene.collection).objects.link(arm)
    arm.show_in_front = True
    B = joint_layout(lm) if "joints" in lm else bone_layout(lm)
    with bpy.context.temp_override(active_object=arm, object=arm):
        bpy.context.view_layer.objects.active = arm
        bpy.ops.object.mode_set(mode='EDIT')
        eb = arm_data.edit_bones
        for bn, (h, t, _p) in B.items():
            b = eb.new(bn)
            b.head, b.tail = Vector(h), Vector(t)
            b.use_deform = bn not in ("root",)
        for bn, (_h, _t, p) in B.items():
            if p:
                eb[bn].parent = eb[p]
                eb[bn].use_connect = (eb[bn].head - eb[p].tail).length < 1e-5
        bpy.ops.object.mode_set(mode='OBJECT')
    for pb in arm.pose.bones:
        pb.rotation_mode = 'XYZ'

    ok = False
    if weights == "auto":
        try:
            with bpy.context.temp_override(active_object=arm, object=arm,
                                           selected_objects=[obj, arm], selected_editable_objects=[obj, arm]):
                bpy.ops.object.parent_set(type='ARMATURE_AUTO')
            ok = _weight_coverage(obj) > 0.97
        except RuntimeError:
            ok = False
    if not ok:
        for g in list(obj.vertex_groups):
            obj.vertex_groups.remove(g)
        for m in list(obj.modifiers):
            if m.type == 'ARMATURE':
                obj.modifiers.remove(m)
        distance_weights(obj, arm, lm)
        obj.parent = arm
        mod = obj.modifiers.new("Armature", 'ARMATURE')
        mod.object = arm
    return arm


def _weight_coverage(obj):
    if not obj.vertex_groups:
        return 0.0
    n = sum(1 for v in obj.data.vertices if any(g.weight > 1e-3 for g in v.groups))
    return n / max(len(obj.data.vertices), 1)


def distance_weights(obj, arm, lm):
    """Веса по расстоянию до костей с зонами (руки не тянут торс, голова жёсткая)."""
    co = _coords(obj.data)
    H = lm["H"]
    segs = []
    for b in arm.data.bones:
        if b.use_deform:
            segs.append((b.name, np.array(b.head_local), np.array(b.tail_local)))
    D = np.empty((len(co), len(segs)))
    for j, (_n, a, b) in enumerate(segs):
        ab = b - a
        t = np.clip(((co - a) @ ab) / max(ab @ ab, 1e-12), 0, 1)
        D[:, j] = np.linalg.norm(co - (a + np.outer(t, ab)), axis=1)
    names = [s[0] for s in segs]
    big = 1e3
    cx = lm.get("cx", 0.0)
    ax = np.abs(co[:, 0] - cx)
    behind = co[:, 1] > lm.get("ymid", 0.0) + 0.07 * H          # волосы/капюшон за спиной
    for j, n in enumerate(names):
        if n.startswith(("shoulder", "upper_arm", "forearm", "hand")):
            D[ax < lm["torso_hw"] * 0.75, j] += big            # руки — только снаружи торса
            D[D[:, j] > 0.075 * H, j] += big                   # и только в «капсуле» вокруг кости
            D[behind, j] += big
        if n.startswith(("thigh", "shin", "foot")):
            D[co[:, 2] > lm["crotch"] + 0.06 * H, j] += big     # ноги — только ниже пояса
            side = 1 if n.endswith(".L") else -1
            D[(co[:, 0] - cx) * side < -0.01 * H, j] += big     # и только своей стороны
            D[D[:, j] > 0.12 * H, j] += big
        if n == "head":
            D[co[:, 2] > lm["neck"] + 0.03 * H, j] = 0.0        # вся голова (с волосами) — на кость head
    # рука влияет только на вершины, связанные рёбрами с плечом (рукав+кисть),
    # а не на касающиеся её штаны/ремни
    ev = np.empty(len(obj.data.edges) * 2, dtype=np.int64)
    obj.data.edges.foreach_get("vertices", ev)
    ev = ev.reshape(-1, 2)
    for side in ("L", "R"):
        cols = [j for j, n in enumerate(names) if n.endswith("." + side) and
                n.startswith(("shoulder", "upper_arm", "forearm", "hand"))]
        if not cols:
            continue
        cand = D[:, cols].min(axis=1) < 0.075 * H
        ua = names.index(f"upper_arm.{side}")
        reached = cand & (D[:, ua] < 0.035 * H)
        for _ in range(2000):
            a, b = reached[ev[:, 0]], reached[ev[:, 1]]
            grow = np.zeros_like(reached)
            grow[ev[a & ~b, 1]] = True
            grow[ev[b & ~a, 0]] = True
            grow &= cand & ~reached
            if not grow.any():
                break
            reached |= grow
        for j in cols:
            D[~reached, j] += big
    D = np.maximum(D, 1e-4)
    order = np.argsort(D, axis=1)[:, :3]
    groups = {n: obj.vertex_groups.new(name=n) for n in names}
    for i in range(len(co)):
        d = D[i, order[i]]
        w = (d[0] / d) ** 6
        w /= w.sum()
        for k, j in enumerate(order[i]):
            if w[k] > 0.02:
                groups[names[j]].add([i], float(w[k]), 'REPLACE')


# ---------------------------------------------------------------------------
# Позирование
# ---------------------------------------------------------------------------
def aim(arm, bone, direction, roll_ref=None):
    """Повернуть кость так, чтобы в мировых координатах она смотрела в direction."""
    pb = arm.pose.bones[bone]
    mw = arm.matrix_world
    cur = (mw.to_3x3() @ (pb.tail - pb.head)).normalized()
    want = Vector(direction).normalized()
    q = cur.rotation_difference(want)
    m = pb.matrix.copy()
    h = m.translation.copy()
    r = (mw.to_3x3().inverted() @ q.to_matrix() @ mw.to_3x3()).to_4x4()
    pb.matrix = Matrix.Translation(h) @ r @ Matrix.Translation(-h) @ m
    bpy.context.view_layer.update()


def reset_pose(arm):
    for pb in arm.pose.bones:
        pb.location = (0, 0, 0)
        pb.rotation_euler = (0, 0, 0)
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.scale = (1, 1, 1)
    bpy.context.view_layer.update()


def bone_length(arm, bone):
    return arm.data.bones[bone].length
