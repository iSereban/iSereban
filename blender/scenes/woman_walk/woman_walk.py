"""
Ролик 15 с: женщина 50+ (переделанная из чиби-девочки) гуляет в парке —
идёт, приседает, идёт, разворачивается, подпрыгивает, машет рукой. Камеры как в кино.

Персонаж строится скриптом characters/woman_from_chibi, анимация и камеры — из scenes/chibi_walk.

  python woman_walk.py --glb <девочка.glb> --out out --engine CYCLES --samples 16 --render
"""
import json
import os
import sys

import bpy  # noqa: I001

_HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
for _p in (("..", "..", "common"), ("..", "..", "library"), ("..", "chibi_walk"),
           ("..", "..", "characters", "woman_from_chibi"), ("..", "..", "characters", "woman_meshy")):
    sys.path.insert(0, os.path.join(_HERE, *_p))
import autorig  # noqa: E402
import chibi_walk  # noqa: E402
import studio  # noqa: E402
import woman_from_chibi  # noqa: E402


def build():
    obj, hair, J = woman_from_chibi.build()
    H = woman_from_chibi.HEIGHT
    with open(os.path.join(_HERE, "woman.joints.json"), "w", encoding="utf-8") as f:
        json.dump(J, f, ensure_ascii=False, indent=1)
    chcol = studio.collection("Character")
    for o in [obj] + list(hair):
        for c in list(o.users_collection):
            c.objects.unlink(o)
        chcol.objects.link(o)
    lm = autorig.landmarks_from_joints(J, H)
    return chibi_walk.animate(obj, lm, H, chcol, prefix="woman_walk_", rigid_head=True, attach_head=hair)


def main():
    build()
    out = studio.arg("--out")
    if not out:
        return
    out = os.path.abspath(out)
    os.makedirs(out, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "woman_walk.blend"), compress=True)
    print("saved", os.path.join(out, "woman_walk.blend"))
    sc = bpy.context.scene
    stills = studio.arg("--stills")
    if stills:
        for f in (int(v) for v in stills.split(",")):
            sc.frame_set(f)
            for m in sorted(sc.timeline_markers, key=lambda m: m.frame):
                if m.frame <= f:
                    sc.camera = m.camera
            studio.render_still(os.path.join(out, f"frame_{f:03d}.jpg"))
    if studio.flag("--render"):
        fr = studio.arg("--frames")
        if fr:
            sc.frame_start, sc.frame_end = (int(v) for v in fr.split("-"))
        sc.render.filepath = os.path.join(out, "woman_walk_")
        bpy.ops.render.render(animation=True)


if __name__ == "__main__":
    main()
