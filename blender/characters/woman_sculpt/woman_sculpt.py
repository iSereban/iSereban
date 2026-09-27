"""
Женщина 50+, вылепленная по чертежу (spec.py / blueprint.py).

Порядок как у скульптора:
  1. Блокинг: корпус, ноги, стопы, рукава — лофтом по сечениям чертежа; голова — из объёмов
     (череп, лицевая часть, скулы, подбородок, нос)
  2. Voxel remesh — всё сливается в одну поверхность (как Remesh в режиме Sculpt)
  3. Кисти: Draw / Crease / Grab / Smooth — складки, веки, улыбка, носогубки, резинки
  4. Кардиган — отдельный слой одежды (полотно + борт с шалевым воротником + резинка низа)
  5. Волосы — объёмные пряди-«пучки», слитые remesh'ем в скульптурную причёску
  6. Цвет — по зонам чертежа, вязка/рубчик — рельефом в материале
В итоговом .blend на теле и голове стоит Multires — можно продолжать лепить руками в режиме Sculpt.

  python woman_sculpt.py --out out
"""
import os
import sys

import bpy  # noqa: I001
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "common"))
import body  # noqa: E402
import sculpt as sc  # noqa: E402
import spec as S  # noqa: E402
import studio  # noqa: E402

MM = 0.001
LIN = {k: sc.srgb(v) for k, v in S.COLORS.items()}


# ------------------------------------------------------------------ материалы
def mat_attr(name, rough=0.6, sss=0.0, bump=None, sheen=0.0):
    """Материал: цвет из атрибута Col; bump: 'knit' | 'cloth' | 'socks' | None."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    at = nt.nodes.new("ShaderNodeAttribute")
    at.attribute_name = "Col"
    nt.links.new(at.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = rough
    if sss:
        b.inputs["Subsurface Weight"].default_value = sss
        b.inputs["Subsurface Radius"].default_value = (1.0, 0.45, 0.3)
        b.inputs["Subsurface Scale"].default_value = 0.004
    if sheen:
        b.inputs["Sheen Weight"].default_value = sheen
    if bump:
        tc = nt.nodes.new("ShaderNodeTexCoord")
        bp = nt.nodes.new("ShaderNodeBump")
        if bump == "knit":
            # вязка: косички-петли (волна по X + шум) и рубчик на борту/резинках (атрибут rib)
            wv = nt.nodes.new("ShaderNodeTexWave")
            wv.wave_type = 'BANDS'
            wv.bands_direction = 'X'
            wv.inputs["Scale"].default_value = 60.0
            wv.inputs["Distortion"].default_value = 6.0
            wv.inputs["Detail"].default_value = 3.0
            nz = nt.nodes.new("ShaderNodeTexNoise")
            nz.inputs["Scale"].default_value = 300.0
            rb = nt.nodes.new("ShaderNodeTexWave")
            rb.wave_type = 'BANDS'
            rb.bands_direction = 'X'
            rb.inputs["Scale"].default_value = 110.0
            ra = nt.nodes.new("ShaderNodeAttribute")
            ra.attribute_name = "rib"
            mx = nt.nodes.new("ShaderNodeMix")
            mx.data_type = 'FLOAT'
            cl = nt.nodes.new("ShaderNodeMath")
            cl.operation = 'MINIMUM'
            cl.inputs[1].default_value = 1.0
            add = nt.nodes.new("ShaderNodeMath")
            add.operation = 'ADD'
            for tex in (wv, nz, rb):
                nt.links.new(tc.outputs["Object"], tex.inputs["Vector"])
            nt.links.new(wv.outputs["Fac"], add.inputs[0])
            nt.links.new(nz.outputs["Fac"], add.inputs[1])
            nt.links.new(ra.outputs["Fac"], cl.inputs[0])
            nt.links.new(cl.outputs[0], mx.inputs["Factor"])
            nt.links.new(add.outputs[0], mx.inputs["A"])
            nt.links.new(rb.outputs["Fac"], mx.inputs["B"])
            nt.links.new(mx.outputs["Result"], bp.inputs["Height"])
            bp.inputs["Strength"].default_value = 0.55
            bp.inputs["Distance"].default_value = 0.003
        else:
            nz = nt.nodes.new("ShaderNodeTexNoise")
            nz.inputs["Scale"].default_value = 900.0 if bump == "cloth" else 350.0
            nz.inputs["Detail"].default_value = 6.0
            nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
            nt.links.new(nz.outputs["Fac"], bp.inputs["Height"])
            bp.inputs["Strength"].default_value = 0.25 if bump == "cloth" else 0.5
            bp.inputs["Distance"].default_value = 0.001
        nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    return m


def color_body(ob, labels, names):
    co = sc.mesh_points(ob) / MM
    z, x, y = co[:, 2], co[:, 0], co[:, 1]
    lab = np.array(names)[labels]
    col = np.tile(LIN["pants"], (len(co), 1))
    tor = lab == "torso"
    col[tor & (z >= S.BLOUSE_HEM)] = LIN["blouse"]
    # вырез хенли: кожа выше линии выреза
    nl = S.NECKLINE
    neckline = nl["front"] + (nl["side"] - nl["front"]) * np.clip(np.abs(x) / 70, 0, 1) ** 1.5
    skin = (lab == "neck") | (tor & (y < 0) & (z > neckline)) | (tor & (z > nl["side"] + 5))
    col[skin] = LIN["skin"]
    arm = np.char.startswith(lab, "arm")
    col[arm] = LIN["cardigan"]
    sock = np.char.startswith(lab, "foot") | np.char.startswith(lab, "ankle") | (np.char.startswith(lab, "leg") & (z < 150))
    col[sock] = LIN["socks"]
    sc.set_color_attr(ob, col)
    rib = np.zeros(len(co))
    rib[arm & (z < S.ARM[-2][2] + S.CARDIGAN["cuff_rib"])] = 1.0
    sc.set_float_attr(ob, rib, "rib")
    # материалы по граням: рукава — вязка, остальное — ткань
    ob.data.materials.append(mat_attr("Body_Cloth", 0.75, bump="cloth", sheen=0.3))
    ob.data.materials.append(mat_attr("Body_Knit", 0.85, bump="knit", sheen=0.5))
    ob.data.materials.append(mat_attr("Body_Skin", 0.45, sss=0.25))
    ob.data.materials.append(mat_attr("Body_Socks", 0.9, bump="socks", sheen=0.5))
    vid = np.zeros(len(co), np.int64)
    vid[arm] = 1
    vid[skin] = 2
    vid[sock] = 3
    pv = np.empty(len(ob.data.loops), np.int64)
    ob.data.loops.foreach_get("vertex_index", pv)
    fi = np.empty(len(ob.data.polygons), np.int64)
    ob.data.polygons.foreach_get("loop_start", fi)
    ob.data.polygons.foreach_set("material_index", vid[pv[fi]])


def color_flat(ob, key, mat):
    sc.set_color_attr(ob, np.tile(LIN[key], (len(ob.data.vertices), 1)))
    ob.data.materials.append(mat)


def build(parts=("body", "cardigan", "hands", "head", "hair")):
    studio.clear_scene()
    col = studio.collection("Woman")
    out = {}
    if "body" in parts:
        ob, labels, names = body.build_body(col)
        color_body(ob, labels, names)
        out["body"] = ob
    if "cardigan" in parts:
        cg, _ = body.build_cardigan(col)
        color_flat(cg, "cardigan", mat_attr("Cardigan", 0.85, bump="knit", sheen=0.5))
        out["cardigan"] = cg
    if "hands" in parts:
        skin = mat_attr("Skin_Hands", 0.45, sss=0.25)
        for sgn in (1, -1):
            h = body.build_hand(sgn, col)
            color_flat(h, "skin", skin)
            out[h.name] = h
    if "head" in parts:
        import head
        out.update(head.build_head(col, mat_attr))
    if "hair" in parts:
        import hair
        out.update(hair.build_hair(col, mat_attr))
    return out


def render_views(out_dir, views=("front", "34", "side", "back", "face")):
    studio.studio_lights(target=(0, 0, 0.9))
    studio.floor(color=(0.45, 0.42, 0.40))
    studio.setup_render("CYCLES", studio.RES_480, int(studio.arg("--samples", 24)), exposure=-0.2)
    cams = {"front": ((0, -4.6, 0.95), (0, 0, 0.84), 50), "34": ((-2.6, -3.7, 1.15), (0, 0, 0.86), 50),
            "side": ((4.6, 0, 0.95), (0, 0, 0.84), 50), "back": ((0.3, 4.6, 1.05), (0, 0, 0.86), 50),
            "face": ((-0.3, -1.3, 1.53), (0, 0, 1.49), 60), "head_side": ((1.3, -0.25, 1.52), (0, 0, 1.49), 60)}
    for v in views:
        loc, tgt, lens = cams[v]
        studio.render_still(os.path.join(out_dir, f"woman_{v}.jpg"), studio.camera("Cam_" + v, loc, tgt, lens))


def main():
    parts = tuple(studio.arg("--parts", "body,cardigan,hands,head,hair").split(","))
    build(parts)
    out = studio.arg("--out")
    if not out:
        return
    out = os.path.abspath(out)
    os.makedirs(out, exist_ok=True)
    render_views(out, tuple(studio.arg("--views", "front,34,side,back,face").split(",")))
    if studio.flag("--save"):
        # Multires на теле и голове — чтобы продолжать лепить руками в режиме Sculpt
        for key in ("body", "head", "hair", "cardigan"):
            ob = bpy.data.objects.get({"body": "Body", "head": "Head", "hair": "Hair", "cardigan": "Cardigan"}[key])
            if ob:
                ob.modifiers.new("Multires", 'MULTIRES')
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "woman_sculpt.blend"), compress=True)


if __name__ == "__main__":
    main()
