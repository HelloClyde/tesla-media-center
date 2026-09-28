"""Add independently editable front/rear plate mounts to the open Blender scene."""
import math
import bpy
from mathutils import Vector

def add_plates():
    root = bpy.data.objects['Model_Y_2022']
    for obj in list(bpy.data.objects):
        if obj.name.startswith('LicensePlate_'):
            bpy.data.objects.remove(obj, do_unlink=True)
    def mat(name, color):
        m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        m.diffuse_color = (*color, 1)
        m.use_nodes = True
        m.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (*color, 1)
        m.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = .38
        return m
    frame = mat('LicensePlate_Frame', (.025, .03, .035))
    face = mat('LicensePlate_Face', (.3, .8, .38))
    bpy.context.scene.frame_set(1)
    bpy.context.view_layer.update()
    for side, direction, height in [('Front', -1, .53), ('Rear', 1, .78)]:
        hit, location, *_ = bpy.context.scene.ray_cast(
            bpy.context.evaluated_depsgraph_get(), Vector((0, direction * 4, height)), Vector((0, -direction, 0)))
        if not hit:
            raise RuntimeError('Plate mount ray missed body: ' + side)
        y = location.y + direction * .016
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0, y, height))
        mount = bpy.context.object
        mount.name = 'LicensePlate_' + side + '_Frame'
        mount.dimensions = (.465, .018, .155)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        bevel = mount.modifiers.new('Rounded mount', 'BEVEL'); bevel.width = .006; bevel.segments = 3
        mount.data.materials.append(frame)
        bpy.ops.mesh.primitive_plane_add(size=1, location=(0, y + direction * .011, height))
        surface = bpy.context.object
        surface.name = 'LicensePlate_' + side + '_Face'
        surface.scale = (.44, .14, 1)
        surface.rotation_euler = (math.pi / 2, 0, 0 if direction == -1 else math.pi)
        surface.data.materials.append(face)
        surface['partType'] = 'licensePlate'
        for obj in (mount, surface):
            obj.parent = root
            obj.matrix_parent_inverse = root.matrix_world.inverted()
    return root

if __name__ == '__main__':
    from pathlib import Path
    root_dir = Path.cwd()
    bpy.ops.wm.open_mainfile(filepath=str(root_dir / 'assets/model-y-2022/model_y_2022.blend'))
    root = add_plates()
    bpy.ops.wm.save_as_mainfile(filepath=str(root_dir / 'assets/model-y-2022/model_y_2022.blend'))
    bpy.ops.object.select_all(action='DESELECT')
    for obj in [root, *root.children_recursive]: obj.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(root_dir / 'web/public/models/2022_tesla_model_y.glb'),
        export_format='GLB', use_selection=True, export_extras=True, export_animations=True,
        export_animation_mode='ACTIONS', export_yup=True)
