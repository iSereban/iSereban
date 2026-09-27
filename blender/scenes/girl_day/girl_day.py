"""
Ролик «День девочки» — 1 минута, 480p, 25 к/с.

  Часть 1 (room):   кадры 1–900  — уроки, расчёска, телефон, рюкзак, выход из комнаты
  Часть 2 (street): кадры 1–600  — выходит из подъезда и гуляет по городу

  python girl_day.py --part room --glb <девочка.glb> --out out --check            проверка камер (перекрытия)
  python girl_day.py --part room --glb ... --out out --stills 50,150,300           контрольные кадры
  python girl_day.py --part room --glb ... --out out --render [--frames 1-900]     рендер кадров (jpg)
  python girl_day.py --join --out out                                               склейка в girl_day.mp4
"""
import os
import subprocess
import sys

import bpy  # noqa: I001

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (("..", "..", "common"), ("..", "..", "library"), ()):
    sys.path.insert(0, os.path.join(HERE, *_p))
import cinema  # noqa: E402
import performer  # noqa: E402
import studio  # noqa: E402

JOINTS = os.path.join(HERE, "..", "chibi_walk", "Meshy_AI_Chibi_Figure_0926172701_texture.joints.json")
H = 1.3


def build(part):
    studio.clear_scene()
    glb = studio.arg("--glb", performer.glb_default())
    if part == "room":
        import room as mod
        col = studio.collection("Room")
        walls, hinge, chair = mod.build_room(col)
        mod.lights(col)
    else:
        import street as mod
        walls = mod.build_street()
        hinge = chair = None
    chcol = studio.collection("Girl")
    g = performer.Girl(glb, JOINTS, H=H, col=chcol)
    props_col = studio.collection("Props")
    mod.choreograph(g, props_col)
    if part == "room":
        mod.animate_set(hinge, chair)
    g.bake(1, mod.FRAMES)
    shots = mod.shots(walls)
    if hasattr(mod, "resolve_camera_paths"):
        mod.resolve_camera_paths(g, shots)
    cinema.build_shots(g, shots, studio.collection("Cameras"))
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, mod.FRAMES
    studio.setup_render("CYCLES", studio.RES_480, int(studio.arg("--samples", 16)), fps=25, exposure=float(studio.arg("--exposure", -0.3)))
    sc.cycles.max_bounces = 4
    sc.cycles.diffuse_bounces = 2
    sc.cycles.glossy_bounces = 2
    sc.cycles.transparent_max_bounces = 6
    sc.cycles.caustics_reflective = False
    sc.cycles.caustics_refractive = False
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = 0.05
    sc.render.use_persistent_data = True
    sc.render.image_settings.file_format = 'JPEG'
    sc.render.image_settings.quality = 92
    return g, shots, mod


def camera_at(shots, f):
    cur = shots[0]
    for s in shots:
        if s.f0 <= f:
            cur = s
    return cur.obj


def main():
    out = os.path.abspath(studio.arg("--out", os.path.join(HERE, "out")))
    os.makedirs(out, exist_ok=True)
    if studio.flag("--join"):
        join(out)
        return
    part = studio.arg("--part", "room")
    g, shots, mod = build(part)
    sc = bpy.context.scene
    if studio.flag("--check"):
        cinema.check(g, shots)
    if studio.flag("--save"):
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, f"girl_day_{part}.blend"), compress=True)
    stills = studio.arg("--stills")
    if stills:
        for f in (int(v) for v in stills.split(",")):
            sc.frame_set(f)
            sc.camera = camera_at(shots, f)
            studio.render_still(os.path.join(out, f"{part}_{f:04d}.jpg"))
    if studio.flag("--render"):
        fr = studio.arg("--frames", f"1-{mod.FRAMES}")
        a, b = (int(v) for v in fr.split("-"))
        d = os.path.join(out, f"frames_{part}")
        os.makedirs(d, exist_ok=True)
        for f in range(a, b + 1):
            path = os.path.join(d, f"{f:04d}.jpg")
            if os.path.exists(path):
                continue                       # продолжение после остановки
            sc.frame_set(f)
            sc.camera = camera_at(shots, f)
            sc.render.filepath = path
            bpy.ops.render.render(write_still=True)
            print("frame", part, f, flush=True)


def join(out):
    """Склейка: комната + улица → girl_day.mp4 (fade in/out)."""
    lst = []
    for part in ("room", "street"):
        d = os.path.join(out, f"frames_{part}")
        mp4 = os.path.join(out, f"{part}.mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "25", "-i", os.path.join(d, "%04d.jpg"),
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", mp4], check=True)
        lst.append(mp4)
    listfile = os.path.join(out, "list.txt")
    with open(listfile, "w") as fh:
        fh.writelines(f"file '{p}'\n" for p in lst)
    final = os.path.join(out, "girl_day.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", listfile,
                    "-vf", "fade=t=in:st=0:d=0.8,fade=t=out:st=59.2:d=0.8", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-crf", "18", final], check=True)
    print("saved", final)


if __name__ == "__main__":
    main()
