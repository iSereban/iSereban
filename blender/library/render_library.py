"""
Библиотека объектов: 3D-модели по спецификациям + превью 480p + .blend-библиотеки (ассеты).

  python render_library.py [--only sofa,tv] [--samples 16] [--no-previews]
Результат (library/out/):
  previews/<name>.jpg          — превью каждого объекта (3/4, 854×480)
  furniture_library.blend      — вся мебель, объекты помечены как ассеты
  city_library.blend           — городские объекты
"""
import math
import os
import sys

import bpy  # noqa: I001
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "common"))
import catalog_city  # noqa: E402
import catalog_furniture  # noqa: E402
import parts  # noqa: E402
import studio  # noqa: E402


def frame_camera(obj, lens=40, yaw=-35, pitch=18):
    """Камера 3/4 спереди, объект целиком в кадре."""
    bpy.context.view_layer.update()
    pts = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    center = (lo + hi) / 2
    radius = (hi - lo).length / 2
    fov = 2 * math.atan(36 * 480 / 854 / 2 / lens)      # вертикальный угол кадра 16:9
    dist = radius / math.sin(fov / 2) * 1.02
    a, b = math.radians(yaw), math.radians(pitch)
    loc = center + Vector((math.sin(a) * math.cos(b), -math.cos(a) * math.cos(b), math.sin(b))) * dist
    cam = studio.camera("Cam", loc, center, lens)
    cam.data.clip_end = dist * 10
    return cam, radius, center


def preview(spec, out, samples):
    studio.clear_scene()
    obj = parts.place(spec)
    cam, r, c = frame_camera(obj)
    s = max(r, 0.5)
    lights = studio.studio_lights(target=c, strength=(s / 1.5) ** 2)
    for L in lights:
        L.location = c + (L.location - Vector((0, 0, 1.0))) * max(s / 1.5, 1)
        studio.look_at(L, c)
    fl = studio.floor(size=max(40, r * 20), color=(0.5, 0.5, 0.52))
    fl.location.z = min((obj.matrix_world @ Vector(v)).z for v in obj.bound_box) - 0.001
    studio.setup_render("CYCLES", studio.RES_480, samples, exposure=-0.4)
    studio.render_still(os.path.join(out, f"{spec['name']}.jpg"), cam)


def build_library(specs, path, cols=6, gap=0.8):
    studio.clear_scene()
    col = studio.collection("Library")
    x = y = 0.0
    row_h = 0.0
    for i, s in enumerate(specs):
        lo_x, hi_x, lo_y, hi_y, _z0, _z1 = parts.bbox_mm(s)
        w, d = (hi_x - lo_x) / 1000, (hi_y - lo_y) / 1000
        if i and i % cols == 0:
            x = 0.0
            y += row_h + gap
            row_h = 0.0
        obj = parts.place(s, location=(x + w / 2, y + d / 2, 0), col=col)
        obj["title"] = s["title"]
        try:
            obj.asset_mark()
            obj.asset_data.description = s["title"]
            obj.asset_data.catalog_simple_name = s.get("group", "")
        except Exception:
            pass
        x += w + gap
        row_h = max(row_h, d)
    bpy.ops.wm.save_as_mainfile(filepath=path, compress=True)
    print("library", path, len(specs))


def main():
    only = studio.arg("--only")
    only = only.split(",") if only else None
    samples = int(studio.arg("--samples", 16))
    out = os.path.join(HERE, "out")
    prev = os.path.join(out, "previews")
    os.makedirs(prev, exist_ok=True)
    def uniq(cat):
        out, seen = [], set()
        for f in cat.values():
            s = f()
            if s["name"] not in seen:
                seen.add(s["name"])
                out.append(s)
        return out
    furn = uniq(catalog_furniture.CATALOG)
    city = uniq(catalog_city.CATALOG)
    if not studio.flag("--no-previews"):
        for s in furn + city:
            if only and s["name"] not in only:
                continue
            preview(s, prev, samples)
            print("preview", s["name"])
    if not only:
        build_library(furn, os.path.join(out, "furniture_library.blend"))
        build_library(city, os.path.join(out, "city_library.blend"), cols=4, gap=5.0)


if __name__ == "__main__":
    main()
