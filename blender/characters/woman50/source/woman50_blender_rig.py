"""
Woman 50 — Disney-stylized 3D starter rig for Blender 3.x / 4.x
===============================================================
What this script creates:
  1. Official Rigify Human Meta-Rig (full body + face bones)
  2. Scale for a ~168 cm woman (~50 years)
  3. Extra face animation helpers: jaw, eyes, eyelids, mouth corners, teeth
  4. Placeholder upper/lower teeth meshes parented to the face / jaw
  5. A JSON dump of every bone head/tail after scale

HOW TO USE
----------
1. Open Blender (empty scene recommended).
2. Edit > Preferences > Add-ons > enable "Rigify".
3. Scripting workspace > Open this file > Run Script.
4. Select the metarig > Object Data Properties > Rigify > Generate Rig.
5. Model or import the woman mesh, then parent With Automatic Weights.
6. For smile / lips / eyes use:
     - Rigify face controls after Generate Rig
     - plus Shape Keys on the head mesh (recommended for Disney smile)

Units: 1 Blender unit = 1 meter. Character stands on Z=0, facing -Y.
"""

import bpy
import json
import addon_utils
from mathutils import Vector

SCALE = 0.85  # Rigify default human ~1.98 m  ->  ~1.68 m woman
COLLECTION_NAME = "Woman50_Disney"
ARMATURE_NAME = "Woman50_Metarig"


def enable_rigify():
    loaded, enabled = addon_utils.check("rigify")
    if not enabled:
        addon_utils.enable("rigify")


def clear_scene_objects():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def ensure_collection(name):
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col


def add_metarig():
    bpy.ops.object.armature_human_metarig_add()
    metarig = bpy.context.active_object
    metarig.name = ARMATURE_NAME
    metarig.data.name = ARMATURE_NAME
    metarig.scale = (SCALE, SCALE, SCALE)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return metarig


def add_extra_face_bones(arm_obj):
    """Jaw / eyes / lids / mouth helpers on top of Rigify face bones."""
    bpy.context.view_layer.objects.active = arm_obj
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm_obj.data.edit_bones

    # Approximate face landmarks after SCALE=0.85
    # Head sits around z=1.51, face front y negative
    extras = [
        # name, head, tail, parent
        ("ctrl_jaw",        (0.000, -0.020, 1.470), (0.000, -0.075, 1.430), "spine.006"),
        ("ctrl_eye.L",      (0.032, -0.068, 1.545), (0.032, -0.090, 1.545), "spine.006"),
        ("ctrl_eye.R",      (-0.032, -0.068, 1.545), (-0.032, -0.090, 1.545), "spine.006"),
        ("ctrl_lid_top.L",  (0.032, -0.080, 1.558), (0.032, -0.092, 1.558), "ctrl_eye.L"),
        ("ctrl_lid_bot.L",  (0.032, -0.080, 1.532), (0.032, -0.092, 1.532), "ctrl_eye.L"),
        ("ctrl_lid_top.R",  (-0.032, -0.080, 1.558), (-0.032, -0.092, 1.558), "ctrl_eye.R"),
        ("ctrl_lid_bot.R",  (-0.032, -0.080, 1.532), (-0.032, -0.092, 1.532), "ctrl_eye.R"),
        ("ctrl_mouth_C",    (0.000, -0.090, 1.488), (0.000, -0.110, 1.488), "ctrl_jaw"),
        ("ctrl_mouth_L",    (0.028, -0.082, 1.490), (0.040, -0.090, 1.490), "ctrl_jaw"),
        ("ctrl_mouth_R",    (-0.028, -0.082, 1.490), (-0.040, -0.090, 1.490), "ctrl_jaw"),
        ("ctrl_smile.L",    (0.038, -0.070, 1.498), (0.052, -0.078, 1.500), "ctrl_jaw"),
        ("ctrl_smile.R",    (-0.038, -0.070, 1.498), (-0.052, -0.078, 1.500), "ctrl_jaw"),
        ("ctrl_teeth_up",   (0.000, -0.078, 1.502), (0.000, -0.098, 1.502), "spine.006"),
        ("ctrl_teeth_lo",   (0.000, -0.078, 1.478), (0.000, -0.098, 1.478), "ctrl_jaw"),
        ("ctrl_tongue",     (0.000, -0.055, 1.485), (0.000, -0.090, 1.478), "ctrl_jaw"),
    ]

    created = []
    for name, head, tail, parent in extras:
        if name in eb:
            continue
        bone = eb.new(name)
        bone.head = Vector(head)
        bone.tail = Vector(tail)
        bone.use_deform = True
        if parent in eb:
            bone.parent = eb[parent]
            bone.use_connect = False
        created.append(name)

    bpy.ops.object.mode_set(mode="OBJECT")
    return created


def add_teeth_meshes(arm_obj, col):
    """Simple placeholder teeth so they can be weighted / parented."""
    def make_teeth(name, location, scale, parent_bone):
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
        obj = bpy.context.active_object
        obj.name = name
        obj.scale = scale
        bpy.ops.object.transform_apply(scale=True)
        # parent to armature bone
        obj.parent = arm_obj
        obj.parent_type = "BONE"
        obj.parent_bone = parent_bone
        # keep world location after parenting
        obj.matrix_parent_inverse = arm_obj.matrix_world.inverted()
        if obj.name not in col.objects:
            # already in scene collection; move
            for c in obj.users_collection:
                c.objects.unlink(obj)
            col.objects.link(obj)
        return obj

    upper = make_teeth(
        "Teeth_Upper",
        location=(0.0, -0.088, 1.502),
        scale=(0.045, 0.018, 0.012),
        parent_bone="ctrl_teeth_up",
    )
    lower = make_teeth(
        "Teeth_Lower",
        location=(0.0, -0.086, 1.476),
        scale=(0.042, 0.016, 0.011),
        parent_bone="ctrl_teeth_lo",
    )
    return upper, lower


def dump_bone_coordinates(arm_obj, path):
    bpy.context.view_layer.objects.active = arm_obj
    bpy.ops.object.mode_set(mode="EDIT")
    data = []
    for bone in arm_obj.data.edit_bones:
        data.append({
            "name": bone.name,
            "head": [round(bone.head.x, 4), round(bone.head.y, 4), round(bone.head.z, 4)],
            "tail": [round(bone.tail.x, 4), round(bone.tail.y, 4), round(bone.tail.z, 4)],
            "roll": round(bone.roll, 4),
            "parent": bone.parent.name if bone.parent else None,
            "connected": bool(bone.use_connect),
            "length": round(bone.length, 4),
        })
    bpy.ops.object.mode_set(mode="OBJECT")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data


def add_reference_empties(arm_obj, col):
    """Named empties at key landmarks — useful while modeling clothes / face."""
    landmarks = {
        "LM_ground": (0.0, 0.0, 0.0),
        "LM_hip": (0.0, 0.047, 0.858),
        "LM_chest": (0.0, 0.005, 1.245),
        "LM_neck": (0.0, -0.011, 1.462),
        "LM_head_top": (0.0, -0.021, 1.683),
        "LM_eye.L": (0.032, -0.079, 1.545),
        "LM_eye.R": (-0.032, -0.079, 1.545),
        "LM_mouth": (0.0, -0.090, 1.488),
        "LM_hand.L": (0.560, 0.042, 1.110),
        "LM_hand.R": (-0.560, 0.042, 1.110),
    }
    for name, loc in landmarks.items():
        empty = bpy.data.objects.new(name, None)
        empty.empty_display_type = "PLAIN_AXES"
        empty.empty_display_size = 0.03
        empty.location = loc
        col.objects.link(empty)


def main():
    enable_rigify()
    # Do not wipe user's scene silently if they already have work —
    # only delete default cube if it is the only mesh.
    cube = bpy.data.objects.get("Cube")
    if cube and cube.type == "MESH":
        bpy.data.objects.remove(cube, do_unlink=True)

    col = ensure_collection(COLLECTION_NAME)
    metarig = add_metarig()

    # Move metarig into our collection
    for c in metarig.users_collection:
        c.objects.unlink(metarig)
    col.objects.link(metarig)

    extras = add_extra_face_bones(metarig)
    add_teeth_meshes(metarig, col)
    add_reference_empties(metarig, col)

    json_path = bpy.path.abspath("//woman50_bone_coordinates.json")
    # If blend not saved yet, write next to a predictable fallback
    if json_path.endswith("//woman50_bone_coordinates.json") or json_path.startswith("//"):
        json_path = "/tmp/woman50_bone_coordinates.json"
    bones = dump_bone_coordinates(metarig, json_path)

    metarig.show_in_front = True
    metarig.data.display_type = "OCTAHEDRAL"

    print("=" * 60)
    print("Woman50 metarig ready.")
    print(f"Bones in armature: {len(metarig.data.bones)}")
    print(f"Extra face bones added: {extras}")
    print(f"Coordinates dumped to: {json_path}")
    print("Next: select metarig -> Rigify panel -> Generate Rig")
    print("=" * 60)


if __name__ == "__main__":
    main()
