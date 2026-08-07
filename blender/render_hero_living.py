from pathlib import Path
import math

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "viewer" / "public" / "assets" / "hero-living"
OUTPUT = ROOT / "output" / "previews" / "hero_living_photoreal.png"
PUBLIC_OUTPUT = ROOT / "viewer" / "public" / "hero_living_photoreal.png"


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.materials, bpy.data.curves, bpy.data.cameras, bpy.data.lights):
        for block in list(datablocks):
            datablocks.remove(block)


def pbr_material(
    name,
    base_path=None,
    rough_path=None,
    normal_path=None,
    tint=(1, 1, 1, 1),
    scale=(1, 1, 1),
    base_strength=1.0,
    normal_strength=0.34,
    roughness_range=None,
):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = tint
    bsdf.inputs["Roughness"].default_value = 0.72
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])

    texcoord = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = scale
    links.new(texcoord.outputs["Generated"], mapping.inputs["Vector"])

    if base_path:
        image = bpy.data.images.load(str(base_path), check_existing=True)
        image.colorspace_settings.name = "sRGB"
        texture = nodes.new("ShaderNodeTexImage")
        texture.image = image
        texture.projection = "BOX"
        texture.projection_blend = 0.18
        texture.extension = "REPEAT"
        links.new(mapping.outputs["Vector"], texture.inputs["Vector"])
        mix = nodes.new("ShaderNodeMixRGB")
        mix.blend_type = "MULTIPLY"
        mix.inputs[0].default_value = base_strength
        mix.inputs[1].default_value = tint
        links.new(texture.outputs["Color"], mix.inputs[2])
        links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])

    if rough_path:
        image = bpy.data.images.load(str(rough_path), check_existing=True)
        image.colorspace_settings.name = "Non-Color"
        texture = nodes.new("ShaderNodeTexImage")
        texture.image = image
        texture.projection = "BOX"
        texture.projection_blend = 0.18
        texture.extension = "REPEAT"
        links.new(mapping.outputs["Vector"], texture.inputs["Vector"])
        if roughness_range:
            ramp = nodes.new("ShaderNodeValToRGB")
            ramp.color_ramp.elements[0].color = (*([roughness_range[0]] * 3), 1)
            ramp.color_ramp.elements[1].color = (*([roughness_range[1]] * 3), 1)
            links.new(texture.outputs["Color"], ramp.inputs["Fac"])
            links.new(ramp.outputs["Color"], bsdf.inputs["Roughness"])
        else:
            links.new(texture.outputs["Color"], bsdf.inputs["Roughness"])

    if normal_path:
        image = bpy.data.images.load(str(normal_path), check_existing=True)
        image.colorspace_settings.name = "Non-Color"
        texture = nodes.new("ShaderNodeTexImage")
        texture.image = image
        texture.projection = "BOX"
        texture.projection_blend = 0.18
        texture.extension = "REPEAT"
        normal = nodes.new("ShaderNodeNormalMap")
        normal.inputs["Strength"].default_value = normal_strength
        links.new(mapping.outputs["Vector"], texture.inputs["Vector"])
        links.new(texture.outputs["Color"], normal.inputs["Color"])
        links.new(normal.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def simple_material(name, color, roughness=0.65, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    return mat


def emissive_material(name, color, strength):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = color
    emission.inputs["Strength"].default_value = strength
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return mat


def cube(name, dimensions, location, mat, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        mod = obj.modifiers.new("Edge soften", "BEVEL")
        mod.width = bevel
        mod.segments = 4
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=mod.name)
    obj.data.materials.append(mat)
    return obj


def model_bounds(objects):
    minimum = Vector((1e9, 1e9, 1e9))
    maximum = Vector((-1e9, -1e9, -1e9))
    for obj in objects:
        if obj.type != "MESH":
            continue
        for corner in obj.bound_box:
            point = obj.matrix_world @ Vector(corner)
            minimum.x = min(minimum.x, point.x)
            minimum.y = min(minimum.y, point.y)
            minimum.z = min(minimum.z, point.z)
            maximum.x = max(maximum.x, point.x)
            maximum.y = max(maximum.y, point.y)
            maximum.z = max(maximum.z, point.z)
    return minimum, maximum


def import_model(path, name, target_width, position, rotation_z=0.0):
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported = [obj for obj in bpy.context.scene.objects if obj not in before]
    roots = [obj for obj in imported if obj.parent not in imported]
    parent = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(parent)
    for obj in roots:
        obj.parent = parent
    minimum, maximum = model_bounds(imported)
    size = maximum - minimum
    parent.scale = (target_width / max(size.x, size.y),) * 3
    bpy.context.view_layer.update()
    minimum, maximum = model_bounds(imported)
    center = (minimum + maximum) / 2
    parent.location = (-center.x, -center.y, -minimum.z)
    parent.rotation_euler[2] = rotation_z
    parent.location += Vector(position)
    bpy.context.view_layer.update()
    return parent, imported


def point_camera(camera, target):
    direction = Vector(target) - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def add_area(name, location, target, energy, size, color):
    data = bpy.data.lights.new(name, "AREA")
    data.energy = energy
    data.shape = "RECTANGLE"
    data.size = size
    data.size_y = size * 0.75
    data.color = color
    light = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(light)
    light.location = location
    point_camera(light, target)
    return light


def main():
    clear_scene()
    texture_root = ASSETS / "textures"
    floor = pbr_material(
        "PBR_OAK_FLOOR",
        texture_root / "wood_floor_diff_1k.jpg",
        texture_root / "wood_floor_rough_1k.jpg",
        texture_root / "wood_floor_nor_gl_1k.jpg",
        (0.92, 0.78, 0.60, 1),
        (2.35, 2.35, 1),
    )
    plaster = pbr_material(
        "PBR_WARM_PLASTER",
        texture_root / "white_plaster_02_diff_1k.jpg",
        texture_root / "white_plaster_02_rough_1k.jpg",
        texture_root / "white_plaster_02_nor_gl_1k.jpg",
        (0.78, 0.72, 0.63, 1),
        (2.2, 1.8, 1),
        base_strength=0.10,
        normal_strength=0.045,
        roughness_range=(0.70, 0.86),
    )
    textile = pbr_material(
        "PBR_TEXTILE",
        None,
        texture_root / "fabric_pattern_05_rough_1k.jpg",
        texture_root / "fabric_pattern_05_nor_gl_1k.jpg",
        (0.30, 0.35, 0.29, 1),
        (4, 4, 1),
    )
    rug = simple_material("WOOL_RUG", (0.33, 0.29, 0.24, 1), 0.96)
    oak = simple_material("LIGHT_OAK", (0.48, 0.28, 0.12, 1), 0.44)
    walnut = simple_material("WALNUT", (0.12, 0.055, 0.025, 1), 0.38)
    brass = simple_material("BRASS", (0.32, 0.18, 0.065, 1), 0.26, 0.82)
    warm_white = simple_material("WARM_WHITE", (0.84, 0.79, 0.69, 1), 0.86)
    shadow_gap = simple_material("SHADOW_GAP", (0.055, 0.045, 0.035, 1), 1.0)
    terracotta = simple_material("TERRACOTTA", (0.45, 0.16, 0.075, 1), 0.78)

    cube("floor", (3.90, 4.40, 0.06), (2.15, 2.40, 0.0), floor)
    cube("west_wall", (0.12, 4.40, 2.80), (0.14, 2.40, 1.40), plaster)
    cube("south_wall_left", (0.42, 0.12, 2.80), (0.41, 0.14, 1.40), plaster)
    cube("south_wall_right", (0.42, 0.12, 2.80), (3.89, 0.14, 1.40), plaster)
    cube("south_wall_header", (3.06, 0.12, 0.40), (2.15, 0.14, 2.60), plaster)
    cube("ceiling", (3.90, 4.40, 0.08), (2.15, 2.40, 2.84), warm_white)
    cube("skirting_west", (0.05, 4.28, 0.10), (0.22, 2.40, 0.08), warm_white, 0.012)
    cube("skirting_south", (3.70, 0.05, 0.10), (2.15, 0.22, 0.08), warm_white, 0.012)
    cube("ceiling_shadow_gap_west", (0.012, 4.22, 0.018), (0.207, 2.40, 2.765), shadow_gap, 0.003)
    cube("ceiling_shadow_gap_south", (3.68, 0.012, 0.018), (2.15, 0.207, 2.765), shadow_gap, 0.003)

    # Window, sheers and a warm, understated art wall.
    frame = simple_material("WINDOW_FRAME", (0.12, 0.10, 0.075, 1), 0.34)
    cube("window_glow", (3.02, 0.025, 2.05), (2.15, 0.07, 1.38), emissive_material("WINDOW_GLOW", (0.42, 0.62, 0.82, 1), 1.4))
    cube("window_top", (3.08, 0.06, 0.07), (2.15, 0.20, 2.40), frame, 0.01)
    cube("window_bottom", (3.08, 0.06, 0.07), (2.15, 0.20, 0.35), frame, 0.01)
    cube("window_left", (0.07, 0.06, 2.12), (0.62, 0.20, 1.37), frame, 0.01)
    cube("window_right", (0.07, 0.06, 2.12), (3.68, 0.20, 1.37), frame, 0.01)
    for x in (0.90, 3.40):
        for index in range(8):
            strip = cube(f"curtain_{x}_{index}", (0.09, 0.055, 2.35), (x + index * 0.075, 0.29, 1.46), warm_white, 0.028)
            strip.rotation_euler[2] = math.radians((index % 2 - 0.5) * 1.2)

    cube("rug", (2.65, 2.38, 0.035), (2.18, 2.50, 0.055), rug, 0.045)
    cube("art_frame", (0.055, 1.48, 1.08), (0.225, 2.55, 1.62), walnut, 0.018)
    cube("art_canvas", (0.03, 1.36, 0.96), (0.26, 2.55, 1.62), warm_white, 0.012)
    accent = cube("art_accent", (0.02, 0.72, 0.34), (0.28, 2.43, 1.62), terracotta, 0.01)
    accent.rotation_euler[0] = math.radians(-7)

    sofa, sofa_objects = import_model(ASSETS / "hero_modern_sofa.glb", "hero_sofa", 2.68, (0.68, 2.48, 0.035), math.pi / 2)
    for obj in sofa_objects:
        if obj.type != "MESH":
            continue
        if obj.name.startswith("back_piping"):
            obj.hide_render = True
        for slot in obj.material_slots:
            if slot.material and slot.material.name.startswith("HERO_SOFA_FABRIC"):
                slot.material = textile
            elif slot.material and slot.material.name.startswith("HERO_SOFA_WOOD"):
                slot.material = walnut
            elif slot.material and slot.material.name.startswith("HERO_SOFA_BRASS"):
                slot.material = brass
            elif slot.material and slot.material.name.startswith("HERO_SOFA_ACCENT"):
                slot.material = terracotta

    import_model(ASSETS / "modern_arm_chair_01" / "modern_arm_chair_01_1k.gltf", "hero_armchair", 0.92, (2.82, 0.98, 0.035), math.radians(126))
    import_model(ASSETS / "modern_coffee_table_01" / "modern_coffee_table_01_1k.gltf", "hero_coffee_table", 1.28, (2.20, 2.48, 0.035), math.pi / 2)

    # Small styling props make scale and material response easier to read.
    cube("book_1", (0.24, 0.36, 0.035), (2.16, 2.42, 0.52), terracotta, 0.008)
    cube("book_2", (0.20, 0.31, 0.035), (2.18, 2.43, 0.56), warm_white, 0.008)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, location=(2.45, 2.48, 0.63), scale=(0.12, 0.12, 0.16))
    vase = bpy.context.object
    vase.name = "table_vase"
    vase.data.materials.append(simple_material("VASE", (0.15, 0.13, 0.11, 1), 0.22))

    # Lighting: a large cool window source plus warm bounce and HDR reflections.
    add_area("window_key", (2.15, 0.42, 1.75), (2.0, 2.3, 0.9), 430, 3.0, (0.72, 0.86, 1.0))
    add_area("warm_bounce", (3.35, 3.45, 2.35), (1.6, 2.4, 0.7), 260, 2.2, (1.0, 0.58, 0.28))
    add_area("soft_fill", (1.0, 3.9, 2.1), (2.0, 2.0, 0.8), 150, 2.5, (1.0, 0.88, 0.72))
    add_area("wall_wash", (1.26, 3.60, 2.05), (0.20, 2.75, 1.50), 85, 1.25, (1.0, 0.77, 0.53))

    world = bpy.data.worlds.new("Hero HDR World")
    bpy.context.scene.world = world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputWorld")
    background = nodes.new("ShaderNodeBackground")
    background.inputs["Strength"].default_value = 0.18
    environment = nodes.new("ShaderNodeTexEnvironment")
    environment.image = bpy.data.images.load(str(ASSETS / "cayley_interior_1k.hdr"), check_existing=True)
    links.new(environment.outputs["Color"], background.inputs["Color"])
    links.new(background.outputs["Background"], output.inputs["Surface"])

    camera_data = bpy.data.cameras.new("Hero Camera")
    camera = bpy.data.objects.new("Hero Camera", camera_data)
    bpy.context.scene.collection.objects.link(camera)
    camera.location = (5.82, 4.25, 1.52)
    camera_data.lens = 46
    camera_data.sensor_width = 36
    camera_data.dof.use_dof = True
    camera_data.dof.focus_distance = 4.15
    camera_data.dof.aperture_fstop = 6.3
    point_camera(camera, (1.82, 2.34, 0.92))
    bpy.context.scene.camera = camera

    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 64
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 960
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = False
    scene.render.filepath = str(OUTPUT)
    scene.render.image_settings.color_depth = "8"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.75
    scene.render.resolution_percentage = 100
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.render.render(write_still=True)
    PUBLIC_OUTPUT.write_bytes(OUTPUT.read_bytes())
    print(f"Rendered {OUTPUT}")


if __name__ == "__main__":
    main()
