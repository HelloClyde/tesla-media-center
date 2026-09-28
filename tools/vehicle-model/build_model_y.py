"""Blender 5.1: prepare a pre-refresh Model Y display asset with articulated parts.

Derived from the repository's CC-BY-4.0 base; see assets/model-y-2022/README.md.
Run from repository root after prepare-source.cjs. Not an engineering CAD model.
"""
from pathlib import Path
import json
import math
import bpy
import bmesh
from mathutils import Vector

ROOT = Path.cwd()
OUT = ROOT / 'assets/model-y-2022'
OUT.mkdir(parents=True, exist_ok=True)
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
bpy.ops.import_scene.gltf(filepath=str(ROOT / '.local-data/model-y/base.glb'))
bpy.ops.object.select_all(action='DESELECT')

# Recover the original disconnected pieces without cutting across door panels.
for obj in list(bpy.context.scene.objects):
    if obj.type != 'MESH':
        continue
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    # Welding UV seams for connectivity must not destroy the authored split normals.
    normals = [normal.vector.copy() for normal in obj.data.corner_normals]
    normal_layer = bm.loops.layers.float_vector.new('authored_normal')
    bm.faces.ensure_lookup_table()
    for face in bm.faces:
        for loop, index in zip(face.loops, obj.data.polygons[face.index].loop_indices):
            loop[normal_layer] = normals[index]
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=0.00006)
    bm.to_mesh(obj.data)
    bm.free()
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.separate(type='LOOSE')
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')

for obj in bpy.context.scene.objects:
    if obj.type == 'MESH' and 'authored_normal' in obj.data.attributes:
        obj.data.normals_split_custom_set([v.vector for v in obj.data.attributes['authored_normal'].data])

def material(name, color, metallic=0, roughness=.3):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (*color, 1)
    bsdf.inputs['Metallic'].default_value = metallic
    bsdf.inputs['Roughness'].default_value = roughness
    return mat

paint = material('Pearl_White_Clearcoat', (.82, .86, .9), .12, .3)
paint.node_tree.nodes['Principled BSDF'].inputs['Coat Weight'].default_value = .5
glass = material('Smoked_Panoramic_Glass', (.014, .029, .04), .36, .13)
trim = material('Satin_Black_Trim', (.018, .021, .025), .25, .32)
rubber = material('Tire_Rubber', (.022, .025, .028), 0, .78)
metal = material('Wheel_Graphite_Alloy', (.21, .24, .28), .78, .24)

def assign(obj, mat):
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    for face in obj.data.polygons:
        face.material_index = 0

def empty(name, at=(0, 0, 0)):
    obj = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(obj)
    obj.location = at
    obj.empty_display_type = 'PLAIN_AXES'
    obj.empty_display_size = .18
    return obj

root = empty('Model_Y_2022')
root['modelYear'] = 2022
root['description'] = 'Pre-refresh Model Y display model; edited and articulated in Blender'
root['license'] = 'CC-BY-4.0'
root['originalAuthor'] = 'tonielpro520'
root['source'] = 'https://sketchfab.com/3d-models/2021-tesla-model-y-59e2ead369984b1a85c800ff6cf6789d'

door_parts = {
    'FL': ['Object_2.330', 'Object_2.333', 'Object_2.379', 'Object_2.380', 'Object_2.383', 'Object_2.386', 'Object_2.006', 'Object_81.018'],
    'FR': ['Object_2.337', 'Object_2.338', 'Object_2.387', 'Object_2.388', 'Object_2.391', 'Object_2.394', 'Object_2.004', 'Object_81.013'],
    'RL': ['Object_2.334', 'Object_2.360', 'Object_2.382', 'Object_2.385', 'Object_81.017'],
    'RR': ['Object_2.339', 'Object_2.374', 'Object_2.390', 'Object_2.393', 'Object_81.023'],
}
doors = {}
for label, names in door_parts.items():
    left = label.endswith('L')
    front = label.startswith('F')
    door = empty('Door_' + label, (-.76 if left else .76, -.935 if front else .255, .89))
    door.parent = root
    door['partType'] = 'door'
    door['rotationAxis'] = 'y'  # glTF / Three.js axis (Blender Z)
    door['openAngle'] = 1.05 if left else -1.05
    doors[label] = door

wheel_groups = {}
for label, center in {'FL': (-.7735, -1.4703, .3988), 'FR': (.7735, -1.4703, .3988),
                      'RL': (-.7735, 1.4234, .3988), 'RR': (.7735, 1.4234, .3988)}.items():
    wheel = empty('Wheel_' + label, center)
    wheel.parent = root
    wheel['partType'] = 'wheel'
    wheel['rotationAxis'] = 'x'
    wheel['spinDirection'] = 1
    wheel_groups[label] = wheel

def parent_keep(obj, parent):
    world = obj.matrix_world.copy()
    obj.parent = parent
    obj.matrix_world = world

bpy.context.view_layer.update()
paint_names = {f'Object_2.{n:03}' for n in (328,329,330,331,332,334,335,336,337,339,340,341,379,387)}
trim_names = {f'Object_2.{n:03}' for n in (343,344,360,374,380,382,383,384,385,386,388,390,391,392,393,394)}
glass_names = {'Object_81.' + n for n in ('008','013','014','016','017','018','022','023')}
# Fixed calipers and brake discs stay on the chassis, not on spinning wheels.
brakes = {f'Object_2.{n:03}' for n in (44,93,142,191,203,204,205,206,267,268,276,278,279,289,300,301)}
assigned = {n: doors[label] for label, names in door_parts.items() for n in names}
for obj in list(bpy.context.scene.objects):
    if obj.type != 'MESH':
        continue
    name = obj.name
    if name in paint_names:
        assign(obj, paint)
    if name in trim_names:
        assign(obj, trim)
    if name in glass_names or name == 'Object_2.395':
        assign(obj, glass)
    if name.startswith('Object_80'):
        assign(obj, rubber)
    owner = assigned.get(name)
    if owner is None and name not in brakes:
        points = [obj.matrix_world @ Vector(v) for v in obj.bound_box]
        for label, wheel in wheel_groups.items():
            c = wheel.location
            if all(abs(v.x-c.x) < .19 and math.hypot(v.y-c.y, v.z-c.z) < .59 for v in points) and max(v.z for v in points) < .81:
                owner = wheel
                if not name.startswith('Object_80'):
                    assign(obj, metal)
                break
    parent_keep(obj, owner or root)

# Keep parts editable while reducing browser draw calls: join meshes per assembly.
for group in [root, *doors.values(), *wheel_groups.values()]:
    meshes = [o for o in group.children if o.type == 'MESH']
    if not meshes:
        raise RuntimeError('Empty assembly: ' + group.name)
    bpy.ops.object.select_all(action='DESELECT')
    for obj in meshes:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.join()
    joined = bpy.context.object
    joined.name = ('Body_Static' if group == root else group.name.replace('Door_', 'Panel_').replace('Wheel_', 'Assembly_'))

# The original is ~4.764 m long; normalize overall length to the pre-refresh 4.75 m envelope.
root.scale = (4.75 / 4.7637305,) * 3
root['dimensionsAreApproximate'] = True
bpy.context.view_layer.update()

# Reusable door-open clip. Origin/pivot lives on the group, so glass and mirror follow.
for door in doors.values():
    door.rotation_euler.z = 0
    door.keyframe_insert(data_path='rotation_euler', frame=1)
    door.rotation_euler.z = door['openAngle']
    door.keyframe_insert(data_path='rotation_euler', frame=36)
    door.animation_data.action.name = 'Open_' + door.name
bpy.context.scene.frame_set(1)

scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.samples = 48
scene.world.color = (.3, .3, .3)
scene.view_settings.view_transform = 'AgX'
bpy.ops.object.camera_add(location=(6, -8, 4.1))
camera = bpy.context.object
camera.name = 'Studio_Camera'
camera.rotation_euler = (Vector((0, 0, .8)) - camera.location).to_track_quat('-Z', 'Y').to_euler()
camera.data.type = 'ORTHO'
camera.data.ortho_scale = 6.25
scene.camera = camera
for i, (position, power, size) in enumerate([((1,-3,7),1700,6),((-4,-1,4),1000,5),((1,4,5),1800,5)]):
    bpy.ops.object.light_add(type='AREA', location=position)
    light = bpy.context.object
    light.name = 'Studio_Light_' + str(i)
    light.data.energy = power
    light.data.shape = 'DISK'
    light.data.size = size
    light.rotation_euler = (Vector((0,0,.8))-light.location).to_track_quat('-Z','Y').to_euler()
scene.render.resolution_x = 1400
scene.render.resolution_y = 950
scene.render.resolution_percentage = 100
scene.render.film_transparent = True
bpy.ops.file.pack_all()
import runpy
runpy.run_path(str(ROOT / 'tools/vehicle-model/add_plates.py'))['add_plates']()
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / 'model_y_2022.blend'))
bpy.ops.object.select_all(action='DESELECT')
root.select_set(True)
for obj in root.children_recursive:
    obj.select_set(True)
bpy.ops.export_scene.gltf(filepath=str(ROOT / 'web/public/models/2022_tesla_model_y.glb'),
    export_format='GLB', use_selection=True, export_extras=True, export_animations=True,
    export_animation_mode='ACTIONS', export_yup=True)

for name, frame in [('closed',1), ('doors-open',36)]:
    scene.frame_set(frame)
    scene.render.filepath = str(OUT / (name + '.png'))
    bpy.ops.render.render(write_still=True)
scene.frame_set(1)
summary = {'doors': [o.name for o in doors.values()], 'wheels': [o.name for o in wheel_groups.values()],
           'meshCount': len([o for o in root.children_recursive if o.type == 'MESH']),
           'triangles': sum(len(o.data.loop_triangles) for o in root.children_recursive if o.type == 'MESH')}
(OUT / 'parts.json').write_text(json.dumps(summary, indent=2), encoding='utf8')
print('MODEL_ASSEMBLY', json.dumps(summary))
