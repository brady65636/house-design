from pathlib import Path
import math

import bpy


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "viewer" / "public" / "assets" / "hero-living" / "hero_modern_sofa.glb"


def material(name: str, color: tuple[float, float, float, float], roughness: float, metallic: float = 0.0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    mat.use_nodes = True
    principled = mat.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = color
    principled.inputs["Roughness"].default_value = roughness
    principled.inputs["Metallic"].default_value = metallic
    return mat


def rounded_cube(
    name: str,
    dimensions: tuple[float, float, float],
    location: tuple[float, float, float],
    mat,
    bevel: float,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    soft: bool = False,
):
    bpy.ops.mesh.primitive_cube_add(location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    bevel_mod = obj.modifiers.new("Soft edge", "BEVEL")
    bevel_mod.width = bevel
    bevel_mod.segments = 6 if soft else 4
    bevel_mod.limit_method = "ANGLE"
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=bevel_mod.name)

    if soft:
        texture = bpy.data.textures.new(f"{name}_micro_wrinkle", type="CLOUDS")
        texture.noise_scale = 0.16
        texture.noise_depth = 1
        displacement = obj.modifiers.new("Subtle upholstery irregularity", "DISPLACE")
        displacement.texture = texture
        displacement.strength = 0.006
        displacement.mid_level = 0.5
        displacement.texture_coords = "GLOBAL"
        bpy.ops.object.modifier_apply(modifier=displacement.name)

    for polygon in obj.data.polygons:
        polygon.use_smooth = soft
    obj.data.materials.append(mat)
    obj["asset_role"] = "hero_living_reference"
    return obj


def cylinder(name, radius, depth, location, mat, vertices=32):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    bevel_mod = obj.modifiers.new("Edge soften", "BEVEL")
    bevel_mod.width = min(radius * 0.2, 0.012)
    bevel_mod.segments = 3
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=bevel_mod.name)
    return obj


def add_piping(name: str, center_x: float, center_y: float, center_z: float, width: float, height: float, mat):
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 2
    curve.bevel_depth = 0.007
    curve.bevel_resolution = 3
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(3)
    points = [
        (center_x - width / 2, center_y, center_z - height / 2),
        (center_x + width / 2, center_y, center_z - height / 2),
        (center_x + width / 2, center_y, center_z + height / 2),
        (center_x - width / 2, center_y, center_z + height / 2),
    ]
    for point, coordinate in zip(spline.bezier_points, points):
        point.co = coordinate
        point.handle_left_type = "AUTO"
        point.handle_right_type = "AUTO"
    spline.use_cyclic_u = True
    obj = bpy.data.objects.new(name, curve)
    curve.materials.append(mat)
    bpy.context.collection.objects.link(obj)
    return obj


def main():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    fabric = material("HERO_SOFA_FABRIC", (0.45, 0.49, 0.44, 1.0), 0.88)
    piping = material("HERO_SOFA_PIPING", (0.28, 0.31, 0.28, 1.0), 0.92)
    wood = material("HERO_SOFA_WOOD", (0.14, 0.075, 0.035, 1.0), 0.40)
    brass = material("HERO_SOFA_BRASS", (0.38, 0.24, 0.10, 1.0), 0.25, 0.82)
    accent = material("HERO_SOFA_ACCENT", (0.45, 0.23, 0.13, 1.0), 0.86)

    root = bpy.data.collections.new("HERO_MODERN_SOFA")
    bpy.context.scene.collection.children.link(root)

    created = []
    created.append(rounded_cube("sofa_frame", (2.56, 0.84, 0.24), (0, 0.0, 0.29), wood, 0.055))
    created.append(rounded_cube("sofa_body", (2.50, 0.82, 0.26), (0, -0.01, 0.43), fabric, 0.105, soft=True))
    created.append(rounded_cube("sofa_back_shell", (2.35, 0.20, 0.72), (0, 0.34, 0.70), fabric, 0.09, rotation=(math.radians(-4), 0, 0), soft=True))
    created.append(rounded_cube("sofa_arm_left", (0.22, 0.83, 0.56), (-1.21, -0.01, 0.61), fabric, 0.09, soft=True))
    created.append(rounded_cube("sofa_arm_right", (0.22, 0.83, 0.56), (1.21, -0.01, 0.61), fabric, 0.09, soft=True))

    for index, x in enumerate((-0.77, 0.0, 0.77)):
        created.append(rounded_cube(f"seat_cushion_{index}", (0.70, 0.66, 0.18), (x, -0.10 + (0.006 if index == 1 else 0), 0.61), fabric, 0.085, rotation=(0, 0, math.radians((index - 1) * 0.6)), soft=True))
        created.append(rounded_cube(f"back_cushion_{index}", (0.70, 0.18, 0.53), (x, 0.22, 0.90 + (0.008 if index == 1 else 0)), fabric, 0.09, rotation=(math.radians(-7), 0, math.radians((index - 1) * 0.8)), soft=True))
        created.append(add_piping(f"back_piping_{index}", x, 0.115, 0.90, 0.62, 0.45, piping))

    created.append(rounded_cube("throw_pillow", (0.42, 0.17, 0.42), (0.78, 0.05, 0.87), accent, 0.09, rotation=(math.radians(-8), math.radians(5), math.radians(-8)), soft=True))

    for x in (-1.06, 1.06):
        for y in (-0.30, 0.30):
            created.append(cylinder(f"leg_{x}_{y}", 0.027, 0.22, (x, y, 0.11), brass, 20))

    for obj in created:
        for collection in list(obj.users_collection):
            collection.objects.unlink(obj)
        root.objects.link(obj)

    for obj in bpy.context.scene.objects:
        obj.select_set(False)
    for obj in root.objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = created[0]

    root["source_type"] = "procedural_original"
    root["license"] = "project_owned"
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=str(OUTPUT),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_extras=True,
        export_yup=True,
    )
    print(f"Exported {OUTPUT}")


if __name__ == "__main__":
    main()
