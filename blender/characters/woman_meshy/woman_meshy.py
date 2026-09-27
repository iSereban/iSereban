"""
Раскраска модели женщины из Meshy (.glb без цвета) по референсу.

Как красит:
  1. Спереди — проецирует картинку-референс (reference/front.jpg) на модель:
     совмещение по силуэту (макушка, стопы, центр тела) → лицо, глаза, брови, губы, кардиган,
     блузка, брюки, носки ложатся в цвета картинки.
  2. Сзади/сбоку и там, где картинка не достаёт (за силуэтом), — по зонам высоты:
     волосы, кардиган, брюки, носки, кисти рук. Цвета взяты с той же картинки (PALETTE ниже).
  3. Переход между ними плавный — по направлению нормали поверхности.

Запуск:
  Blender → Scripting → Open → woman_meshy.py → указать GLB_PATH → Run Script
  blender -b -P woman_meshy.py -- --glb "C:\\Users\\New\\Downloads\\woman.glb" --out out
  python woman_meshy.py --glb woman.glb --out out            (bpy-модуль; + превью 480p)
Функция для других сцен: woman_meshy.load_painted(glb) → объект с материалом.
"""
import json
import math
import os
import sys

import bpy  # noqa: I001
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
_sd = getattr(bpy.context, "space_data", None)
if _sd is not None and getattr(_sd, "text", None) is not None and _sd.text.filepath:
    HERE = os.path.dirname(bpy.path.abspath(_sd.text.filepath))
sys.path.insert(0, os.path.join(HERE, "..", "..", "common"))
import autorig  # noqa: E402
import studio  # noqa: E402

GLB_PATH = r"C:\Users\New\Downloads\woman.glb"      # ← путь к модели женщины из Meshy
HEIGHT = 1.65
REF_FRONT = os.path.join(HERE, "reference", "front.jpg")

# Цвета, снятые с референса (sRGB 0–255)
PALETTE = {
    "hair": (70, 48, 32),
    "hair_grey": (150, 142, 135),
    "cardigan": (185, 118, 105),
    "blouse": (233, 207, 180),
    "pants": (214, 184, 156),
    "socks": (236, 214, 190),
    "skin": (208, 156, 128),
}
# Зоны по высоте (доля роста), измерены по front.jpg
ZONES = dict(hair_below=0.80, cardigan_hem=0.455, pants_cuff=0.105, hand_z=(0.33, 0.47), hand_dx=0.13)


def srgb_to_lin(c):
    c = np.asarray(c, dtype=np.float64) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def smoothstep(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


# ---------------------------------------------------------------------------
def load_reference(path):
    img = bpy.data.images.load(path, check_existing=True)
    img.colorspace_settings.name = 'sRGB'
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)[::-1, :, :3] * 255.0       # сверху вниз, 0..255 (sRGB)
    return img, px


def silhouette(px):
    """Маска силуэта: фон оценивается по краям каждой строки; дыры в строке заполняются."""
    h, w, _ = px.shape
    edge = np.concatenate([px[:, :30], px[:, -30:]], axis=1)
    bg = np.median(edge, axis=1)
    m = np.linalg.norm(px - bg[:, None, :], axis=2) > 40
    rows = np.where(m.sum(1) > 3)[0]
    top = rows.min()
    # низ: последняя строка, где силуэт не шире 60% кадра (отсекаем тень на полу)
    good = [y for y in rows if m[y].sum() < 0.6 * w]
    bottom = max(good)
    span = np.full((h, 2), -1)
    for y in range(top, bottom + 1):
        xs = np.where(m[y])[0]
        if len(xs):
            span[y] = (xs.min(), xs.max())
    band = [y for y in range(top + int(0.3 * (bottom - top)), top + int(0.6 * (bottom - top))) if span[y, 0] >= 0]
    cx = float(np.mean([(span[y, 0] + span[y, 1]) / 2 for y in band]))
    # шея: самая узкая строка между головой и плечами
    rng_rows = [y for y in range(top + int(0.10 * (bottom - top)), top + int(0.24 * (bottom - top))) if span[y, 0] >= 0]
    neck = min(rng_rows, key=lambda y: span[y, 1] - span[y, 0]) if rng_rows else top + int(0.16 * (bottom - top))
    head_rows = [y for y in range(top, neck) if span[y, 0] >= 0]
    head_cx = float(np.mean([(span[y, 0] + span[y, 1]) / 2 for y in head_rows])) if head_rows else cx
    return dict(top=int(top), bottom=int(bottom), cx=cx, span=span, neck=int(neck), head_cx=head_cx)


def paint(obj, ref=REF_FRONT, align=None, face_boxes=None, neck_z=None):
    """Раскрасить объект (меш, нормализован: ноги на Z=0, лицом в −Y)."""
    img, px = load_reference(ref)
    h, w, _ = px.shape
    sil = silhouette(px)
    if align:
        sil.update(align)
    me = obj.data
    n = len(me.vertices)
    co = np.empty(n * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    nr = np.empty(n * 3)
    me.vertices.foreach_get("normal", nr)
    nr = nr.reshape(-1, 3)
    H = co[:, 2].max()
    torso = co[(co[:, 2] > 0.5 * H) & (co[:, 2] < 0.75 * H)]
    cx_m = float(np.median(torso[:, 0]))
    spx = (sil["bottom"] - sil["top"]) / H                     # пикселей на метр
    if neck_z is not None:
        spx = (sil["bottom"] - sil["neck"]) / neck_z              # тело: стопы ↔ стопы, шея ↔ шея
    u_px = sil["cx"] + (co[:, 0] - cx_m) * spx
    v_px = sil["bottom"] - co[:, 2] * spx
    # голову совмещаем отдельно
    if face_boxes:
        # по прямоугольнику кожи лица: модель (x, z) ↔ картинка (пиксели)
        fx0, fx1, fz0, fz1 = face_boxes["model"]
        ix0, ix1, iy0, iy1 = face_boxes["image"]
        uh = ix0 + (co[:, 0] - fx0) / max(fx1 - fx0, 1e-6) * (ix1 - ix0)
        vh = iy1 - (co[:, 2] - fz0) / max(fz1 - fz0, 1e-6) * (iy1 - iy0)
        nz = neck_z if neck_z is not None else fz0 - 0.05 * (fz1 - fz0)
    else:
        # макушка ↔ макушка, шея ↔ шея, центр головы ↔ центр
        zs = np.linspace(0.76 * H, 0.92 * H, 40)
        widths = []
        for z in zs:
            band = co[np.abs(co[:, 2] - z) < 0.006 * H]
            band = band[np.abs(band[:, 0] - cx_m) < 0.12 * H]
            widths.append(np.ptp(band[:, 0]) if len(band) > 3 else 1e9)
        nz = float(zs[int(np.argmin(widths))])
        head = co[:, 2] > nz
        hcx = float(np.median(co[head, 0]))
        hs = (sil["neck"] - sil["top"]) / max(H - nz, 1e-6)
        uh = sil["head_cx"] + (co[:, 0] - hcx) * hs
        vh = sil["top"] + (H - co[:, 2]) * hs
    t = smoothstep((co[:, 2] - (nz - 0.02 * H)) / (0.03 * H))
    u_px = u_px * (1 - t) + uh * t
    v_px = v_px * (1 - t) + vh * t
    ui = np.clip(u_px.astype(int), 0, w - 1)
    vi = np.clip(v_px.astype(int), 0, h - 1)
    span = sil["span"][vi]
    inside = (span[:, 0] >= 0) & (ui >= span[:, 0] - 2) & (ui <= span[:, 1] + 2)
    front_w = smoothstep((-nr[:, 1] - 0.05) / 0.45) * inside

    # цвета зон (для спины, боков и мест вне силуэта)
    zf = co[:, 2] / H
    dx = np.abs(co[:, 0] - cx_m) / H
    lin = {k: srgb_to_lin(v) for k, v in PALETTE.items()}
    rule = np.tile(lin["cardigan"], (n, 1))
    rule[zf < ZONES["cardigan_hem"]] = lin["pants"]
    rule[zf < ZONES["pants_cuff"]] = lin["socks"]
    rule[zf >= ZONES["hair_below"]] = lin["hair"]
    hz0, hz1 = ZONES["hand_z"]
    hands = (zf > hz0) & (zf < hz1) & (dx > ZONES["hand_dx"])
    rule[hands] = lin["skin"]
    # седая прядь: правая (её) сторона лба/темени (x < центр), спереди-сверху
    grey = (zf > 0.88) & (co[:, 0] < cx_m - 0.02 * H) & (co[:, 1] < np.median(co[zf > 0.85][:, 1]))
    rule[grey] = rule[grey] * 0.4 + lin["hair_grey"] * 0.6

    # атрибуты: цвет по зонам + вес проекции
    for name in ("paint_rule", "front_w"):
        if name in me.attributes:
            me.attributes.remove(me.attributes[name])
    a = me.attributes.new("paint_rule", 'FLOAT_COLOR', 'POINT')
    rgba = np.concatenate([rule, np.ones((n, 1))], axis=1).astype(np.float32).ravel()
    a.data.foreach_set("color", rgba)
    fw = me.attributes.new("front_w", 'FLOAT', 'POINT')
    fw.data.foreach_set("value", front_w.astype(np.float32))

    # UV-проекция картинки спереди
    uv = me.uv_layers.get("front_proj") or me.uv_layers.new(name="front_proj")
    li = np.empty(len(me.loops), dtype=np.int64)
    me.loops.foreach_get("vertex_index", li)
    uvs = np.stack([u_px[li] / w, 1.0 - v_px[li] / h], axis=1).astype(np.float32).ravel()
    uv.data.foreach_set("uv", uvs)

    mat = bpy.data.materials.new("Woman_Painted")
    mat.use_nodes = True
    nt = mat.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Roughness"].default_value = 0.65
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.extension = 'EXTEND'
    uvn = nt.nodes.new("ShaderNodeUVMap")
    uvn.uv_map = "front_proj"
    ar = nt.nodes.new("ShaderNodeAttribute")
    ar.attribute_name = "paint_rule"
    aw = nt.nodes.new("ShaderNodeAttribute")
    aw.attribute_name = "front_w"
    mix = nt.nodes.new("ShaderNodeMixRGB")
    nt.links.new(uvn.outputs["UV"], tex.inputs["Vector"])
    nt.links.new(aw.outputs["Fac"], mix.inputs["Fac"])
    nt.links.new(ar.outputs["Color"], mix.inputs["Color1"])
    nt.links.new(tex.outputs["Color"], mix.inputs["Color2"])
    nt.links.new(mix.outputs["Color"], b.inputs["Base Color"])
    me.materials.clear()
    me.materials.append(mat)
    print(f"painted: {n} верш., спереди из картинки {float((front_w > 0.5).mean()) * 100:.0f}%")
    return mat


def load_painted(glb, height=HEIGHT, col=None, align=None):
    obj = autorig.import_character(glb, height=height, name="Woman", col=col)
    paint(obj, align=align)
    return obj


def main():
    studio.clear_scene()
    glb = studio.arg("--glb", GLB_PATH)
    align = None
    jp = os.path.join(HERE, "reference", "front_align.json")
    if os.path.exists(jp):
        with open(jp, encoding="utf-8") as f:
            align = json.load(f)
    obj = load_painted(glb, float(studio.arg("--height", HEIGHT)), align=align)
    out = studio.arg("--out")
    if out:
        out = os.path.abspath(out)
        os.makedirs(out, exist_ok=True)
        studio.studio_lights(target=(0, 0, 0.9))
        studio.floor(color=(0.45, 0.42, 0.40))
        studio.setup_render("CYCLES", studio.RES_480, int(studio.arg("--samples", 24)), exposure=-0.3)
        H = HEIGHT
        for name, loc, tgt, lens in (("front", (0, -4.2, 1.0), (0, 0, 0.85), 50),
                                     ("34", (-2.4, -3.4, 1.2), (0, 0, 0.85), 50),
                                     ("side", (4.2, 0, 1.0), (0, 0, 0.85), 50),
                                     ("back", (0.3, 4.2, 1.1), (0, 0, 0.9), 50),
                                     ("face", (0, -0.9, H * 0.92), (0, 0, H * 0.9), 60)):
            studio.render_still(os.path.join(out, f"painted_{name}.jpg"), studio.camera(name, loc, tgt, lens))
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "woman_painted.blend"), compress=True)
        print("saved", os.path.join(out, "woman_painted.blend"))


if __name__ == "__main__":
    main()
