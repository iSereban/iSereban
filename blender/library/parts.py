"""
Конструктор объектов из описаний в координатах (спецификаций).

Спецификация объекта (чистый Python, без bpy — её же читает генератор чертежей):
    {
      "name": "sofa", "title": "Диван", "group": "Гостиная",
      "parts": [ {деталь}, ... ]
    }
Деталь (все размеры и координаты — в миллиметрах, от центра основания объекта:
X — вправо, Y — вглубь (фасад смотрит в −Y), Z — вверх от пола):
    {"t": "box",  "s": [ширина, глубина, высота], "p": [x, y, z_центр], "m": "материал", "b": фаска, "rot": [rx, ry, rz]°}
    {"t": "cyl",  "r": радиус, "h": высота, "p": [x, y, z_центр], "axis": "z|x|y", "m": ...}
    {"t": "cone", "r1": радиус низа, "r2": радиус верха, "h": высота, "p": [...], "m": ...}
    {"t": "sph",  "s": [rx, ry, rz], "p": [...], "m": ...}
    {"t": "text", "text": "АПТЕКА", "size": высота букв, "depth": толщина, "p": [...], "m": ...}
"""

import math

import bpy  # noqa: I001
import bmesh
from mathutils import Euler, Matrix, Vector

MM = 0.001

from palette import PALETTE  # noqa: E402


def material(name):
    mat = bpy.data.materials.get("M_" + name)
    if mat:
        return mat
    spec = PALETTE.get(name, dict(c=(0.5, 0.5, 0.5), r=0.5))
    mat = bpy.data.materials.new("M_" + name)
    mat.use_nodes = True
    nt = mat.node_tree
    b = nt.nodes["Principled BSDF"]
    c = spec["c"]
    mat.diffuse_color = (*c, 1)
    b.inputs["Roughness"].default_value = spec.get("r", 0.5)
    b.inputs["Metallic"].default_value = spec.get("metal", 0.0)
    color_out = None
    tc = nt.nodes.new("ShaderNodeTexCoord")

    def ramp_between(fac_socket, c1, c2, p0=0.4, p1=0.6):
        rp = nt.nodes.new("ShaderNodeValToRGB")
        rp.color_ramp.elements[0].position = p0
        rp.color_ramp.elements[0].color = (*c1, 1)
        rp.color_ramp.elements[1].position = p1
        rp.color_ramp.elements[1].color = (*c2, 1)
        nt.links.new(fac_socket, rp.inputs["Fac"])
        return rp.outputs["Color"]

    dark = tuple(v * 0.6 for v in c)
    light = tuple(min(v * 1.35, 1) for v in c)
    if spec.get("wood"):
        w = nt.nodes.new("ShaderNodeTexWave")
        w.wave_type = 'RINGS'
        w.inputs["Scale"].default_value = 12.0
        w.inputs["Distortion"].default_value = 3.0
        w.inputs["Detail"].default_value = 2.0
        nt.links.new(tc.outputs["Object"], w.inputs["Vector"])
        color_out = ramp_between(w.outputs["Fac"], tuple(v * 0.8 for v in c), c, 0.2, 0.8)
        if spec.get("planks"):
            br = nt.nodes.new("ShaderNodeTexBrick")
            br.inputs["Scale"].default_value = 1.0
            br.inputs["Brick Width"].default_value = 1.2
            br.inputs["Row Height"].default_value = 0.15
            br.inputs["Mortar Size"].default_value = 0.003
            br.inputs["Color1"].default_value = (*c, 1)
            br.inputs["Color2"].default_value = (*dark, 1)
            br.inputs["Mortar"].default_value = (*tuple(v * 0.3 for v in c), 1)
            nt.links.new(tc.outputs["Object"], br.inputs["Vector"])
            mix = nt.nodes.new("ShaderNodeMixRGB")
            mix.blend_type = 'MULTIPLY'
            mix.inputs["Fac"].default_value = 0.7
            nt.links.new(color_out, mix.inputs["Color1"])
            nt.links.new(br.outputs["Color"], mix.inputs["Color2"])
            color_out = mix.outputs["Color"]
    elif spec.get("bricks") or spec.get("tiles") or spec.get("panels"):
        br = nt.nodes.new("ShaderNodeTexBrick")
        if spec.get("bricks"):
            br.inputs["Scale"].default_value = 1.0
            br.inputs["Brick Width"].default_value = 0.25
            br.inputs["Row Height"].default_value = 0.075
            br.inputs["Mortar Size"].default_value = 0.008
        elif spec.get("panels"):
            br.inputs["Scale"].default_value = 1.0
            br.inputs["Brick Width"].default_value = 3.0
            br.inputs["Row Height"].default_value = 2.8
            br.inputs["Mortar Size"].default_value = 0.02
            br.offset = 0.0
        else:
            br.inputs["Scale"].default_value = 1.0
            br.inputs["Brick Width"].default_value = 0.3
            br.inputs["Row Height"].default_value = 0.3
            br.inputs["Mortar Size"].default_value = 0.004
            br.offset = 0.0
        br.inputs["Color1"].default_value = (*c, 1)
        br.inputs["Color2"].default_value = (*tuple(v * 0.85 for v in c), 1)
        br.inputs["Mortar"].default_value = (*tuple(min(v * 1.2 + 0.05, 1) for v in c), 1)
        nt.links.new(tc.outputs["Object"], br.inputs["Vector"])
        color_out = br.outputs["Color"]
    elif spec.get("carpet"):
        mg = nt.nodes.new("ShaderNodeTexMagic")
        mg.inputs["Scale"].default_value = 3.0
        mg.turbulence_depth = 3
        nt.links.new(tc.outputs["Generated"], mg.inputs["Vector"])
        gold = tuple(min(v * 1.8 + 0.08, 1) for v in c)
        color_out = ramp_between(mg.outputs["Fac"], tuple(v * 0.7 for v in c), gold, 0.5, 0.8)
    elif spec.get("floral"):
        vo = nt.nodes.new("ShaderNodeTexVoronoi")
        vo.inputs["Scale"].default_value = 25.0
        nt.links.new(tc.outputs["Object"], vo.inputs["Vector"])
        color_out = ramp_between(vo.outputs["Distance"], light, c, 0.08, 0.2)
    elif spec.get("stripes"):
        wv = nt.nodes.new("ShaderNodeTexWave")
        wv.inputs["Scale"].default_value = 6.0
        nt.links.new(tc.outputs["Object"], wv.inputs["Vector"])
        color_out = ramp_between(wv.outputs["Fac"], c, (0.8, 0.78, 0.74), 0.49, 0.51)
    elif spec.get("noise") or spec.get("fabric"):
        nz = nt.nodes.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = 40.0 if spec.get("fabric") else 3.0
        nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
        color_out = ramp_between(nz.outputs["Fac"], dark, light, 0.3, 0.7)
    if color_out is not None:
        nt.links.new(color_out, b.inputs["Base Color"])
    else:
        b.inputs["Base Color"].default_value = (*c, 1)
    if spec.get("glass"):
        key = "Transmission Weight" if "Transmission Weight" in b.inputs else "Transmission"
        b.inputs[key].default_value = 1.0
        b.inputs["IOR"].default_value = 1.45
    if spec.get("coat") and "Coat Weight" in b.inputs:
        b.inputs["Coat Weight"].default_value = 1.0
    if "alpha" in spec:
        b.inputs["Alpha"].default_value = spec["alpha"]
        if hasattr(mat, "blend_method"):
            mat.blend_method = 'BLEND'
    if "glow" in spec:
        key = "Emission Color" if "Emission Color" in b.inputs else "Emission"
        b.inputs[key].default_value = (*spec["glow"], 1)
        b.inputs["Emission Strength"].default_value = spec.get("glow_s", 1.0)
    return mat


# ---------------------------------------------------------------------------
# Геометрия деталей
# ---------------------------------------------------------------------------
def _part_bmesh(part):
    bm = bmesh.new()
    t = part["t"]
    if t == "box":
        w, d, h = (v * MM for v in part["s"])
        bmesh.ops.create_cube(bm, size=1.0)
        for v in bm.verts:
            v.co = Vector((v.co.x * w, v.co.y * d, v.co.z * h))
        bev = part.get("b", 0) * MM
        if bev > 0:
            bev = min(bev, w * 0.45, d * 0.45, h * 0.45)
            bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bev, segments=3, affect='EDGES', profile=0.5)
    elif t in ("cyl", "cone"):
        r1 = part.get("r", part.get("r1", 10)) * MM
        r2 = part.get("r", part.get("r2", 10)) * MM
        h = part["h"] * MM
        bmesh.ops.create_cone(bm, cap_ends=True, segments=part.get("seg", 24), radius1=r1, radius2=r2, depth=h)
        ax = part.get("axis", "z")
        if ax == "x":
            bmesh.ops.rotate(bm, verts=bm.verts, matrix=Matrix.Rotation(math.pi / 2, 3, 'Y'))
        elif ax == "y":
            bmesh.ops.rotate(bm, verts=bm.verts, matrix=Matrix.Rotation(math.pi / 2, 3, 'X'))
    elif t == "sph":
        rx, ry, rz = (v * MM for v in part["s"])
        bmesh.ops.create_uvsphere(bm, u_segments=part.get("seg", 20), v_segments=max(part.get("seg", 20) // 2, 6),
                                  radius=1.0)
        for v in bm.verts:
            v.co = Vector((v.co.x * rx, v.co.y * ry, v.co.z * rz))
    elif t == "text":
        cu = bpy.data.curves.new("txt", 'FONT')
        cu.body = part["text"]
        cu.size = part.get("size", 200) * MM
        cu.extrude = part.get("depth", 20) * MM / 2
        cu.align_x = 'CENTER'
        cu.align_y = 'CENTER'
        tmp = bpy.data.objects.new("txt", cu)
        bpy.context.scene.collection.objects.link(tmp)
        dg = bpy.context.evaluated_depsgraph_get()
        me = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg))
        bpy.data.objects.remove(tmp)
        bpy.data.curves.remove(cu)
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
        # текст лежит в XY → ставим вертикально лицом в −Y
        bmesh.ops.rotate(bm, verts=bm.verts, matrix=Matrix.Rotation(math.pi / 2, 3, 'X'))
    else:
        raise ValueError(f"Неизвестный тип детали: {t}")
    rot = part.get("rot")
    if rot:
        bmesh.ops.rotate(bm, verts=bm.verts, matrix=Euler([math.radians(a) for a in rot]).to_matrix())
    bmesh.ops.translate(bm, verts=bm.verts, vec=Vector(part["p"]) * MM)
    return bm


def build_mesh(spec, name=None):
    """Спецификация → меш с материалами (одна сетка на объект)."""
    name = name or spec["name"]
    mats, index = [], {}
    bm = bmesh.new()
    for part in spec["parts"]:
        pb = _part_bmesh(part)
        m = part.get("m", "white")
        if m not in index:
            index[m] = len(mats)
            mats.append(m)
        for f in pb.faces:
            f.material_index = index[m]
            f.smooth = part["t"] in ("cyl", "cone", "sph") or part.get("b", 0) > 0
        tmp = bpy.data.meshes.new("tmp")
        pb.to_mesh(tmp)
        pb.free()
        bm.from_mesh(tmp)
        bpy.data.meshes.remove(tmp)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(material(m))
    return me


def place(spec, location=(0, 0, 0), rot_deg=0.0, col=None, name=None, mesh_cache=None):
    """Поставить объект: location — метры, rot_deg — поворот вокруг Z (0 — фасад в −Y)."""
    key = spec["name"]
    me = None
    if mesh_cache is not None:
        me = mesh_cache.get(key)
    if me is None:
        me = build_mesh(spec)
        if mesh_cache is not None:
            mesh_cache[key] = me
    obj = bpy.data.objects.new(name or spec["name"], me)
    (col or bpy.context.scene.collection).objects.link(obj)
    obj.location = location
    obj.rotation_euler = (0, 0, math.radians(rot_deg))
    obj["spec"] = spec["name"]
    return obj


def bbox_mm(spec):
    """Габарит объекта по деталям (мм): (xmin, xmax, ymin, ymax, zmin, zmax)."""
    xs, ys, zs = [], [], []
    for p in spec["parts"]:
        x, y, z = p["p"]
        if p["t"] == "box":
            w, d, h = p["s"]
            r = p.get("rot")
            if r and abs(r[2]) % 180 == 90:
                w, d = d, w
        elif p["t"] in ("cyl", "cone"):
            rr = max(p.get("r", 0), p.get("r1", 0), p.get("r2", 0))
            ax = p.get("axis", "z")
            w = d = h = 2 * rr
            if ax == "z":
                h = p["h"]
            elif ax == "x":
                w = p["h"]
            else:
                d = p["h"]
        elif p["t"] == "sph":
            w, d, h = (2 * v for v in p["s"])
        else:  # text
            w, d, h = p.get("size", 200) * 0.7 * len(p["text"]), p.get("depth", 20), p.get("size", 200)
        xs += [x - w / 2, x + w / 2]
        ys += [y - d / 2, y + d / 2]
        zs += [z - h / 2, z + h / 2]
    return min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)
