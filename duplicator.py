from collections import defaultdict
import bpy
from . import misc

def convert_rigify_rig(context, original_armature, name_suffix, convert_to_twist_bones, twist_bone_suffix):
    if original_armature.data.get("rig_id") is None:
        raise TypeError(f"Object {original_armature} is not a Rigify rig.")
    
    if not context.mode == "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    
    #
    # Duplicate armature.
    #

    bpy.ops.object.select_all(action="DESELECT")

    def duplicate(object):
        bpy.ops.object.select_all(action="DESELECT")
        layer_collection = misc.find_layer_collection(context, object)
        if layer_collection.exclude == False:
            object.select_set(True)
        context.view_layer.objects.active = object
        bpy.ops.object.duplicate(linked=True)
        return context.active_object
    
    original_objects = misc.get_hierarchy_recursive(original_armature)
    created_objects_map = {}
    for object in original_objects:
        created_objects_map[object] = duplicate(object)
    bpy.ops.object.select_all(action="DESELECT")

    created_armature = created_objects_map[original_armature]
    created_meshes = [created_objects_map[x] for x in created_objects_map if x.type == "MESH"]
    
    for object in original_objects:
        object.select_set(False)
    context.view_layer.objects.active = None

    created_objects = created_meshes + [created_armature]

    # Move objects to the scene collection.
    for created_object in created_objects:
        layer_collection = misc.find_layer_collection(context, created_object)
        layer_collection.collection.objects.unlink(created_object)
        context.scene.collection.objects.link(created_object)

    # Duplicate data too.
    for created_object in created_objects:
        created_object.data = created_object.data.copy()

    # Make linked data local.
    context_override = context.copy()
    context_override["selected_objects"] = created_objects
    with context.temp_override(**context_override):
        bpy.ops.object.make_local(type="SELECT_OBDATA")
    
    # Fix parents.
    for created_mesh in created_meshes:
        if created_mesh.parent == original_armature:
            created_mesh.parent = created_armature

    # Add suffix to names.
    for object in created_meshes + [created_armature]:
        original_object = next(x for x in created_objects_map if created_objects_map[x] == object)
        object.name = f"{original_object.name}{name_suffix}"
        object.data.name = f"{original_object.data.name}{name_suffix}"

    #
    # Apply all modifiers except armature modifier.
    #

    for created_object in created_objects:
        context_override = context.copy()
        context_override["selected_objects"] = created_object
        context_override["active_object"] = created_object
        with context.temp_override(**context_override):
            modifier_names = [x.name for x in created_object.modifiers if x.type != "ARMATURE"]
            for x in modifier_names:
                try:
                    bpy.ops.object.modifier_apply(modifier=x)
                except RuntimeError:
                    pass
    
    #
    # Remove drivers
    #

    try:
        drivers = created_armature.animation_data.drivers
        while len(drivers) > 0:
            drivers.remove(drivers[0])
    except AttributeError:
        pass
    try:
        drivers = created_armature.data.animation_data.drivers
        while len(drivers) > 0:
            drivers.remove(drivers[0])
    except AttributeError:
        pass

    for created_mesh in created_meshes:
        try:
            drivers = created_mesh.animation_data.drivers
            while len(drivers) > 0:
                drivers.remove(drivers[0])
        except AttributeError:
            pass
        try:
            drivers = created_mesh.data.animation_data.drivers
            while len(drivers) > 0:
                drivers.remove(drivers[0])
        except AttributeError:
            pass

    #
    # Remove all modifiers except armature modifiers.
    #

    for modifier in [x for x in created_armature.modifiers]:
        created_armature.modifiers.remove(modifier)
    
    for created_mesh in created_meshes:
        for modifier in [x for x in created_mesh.modifiers]:
            if isinstance(modifier, bpy.types.ArmatureModifier):
                if modifier.object == original_armature:
                    modifier.object = created_armature
            else:
                created_mesh.modifiers.remove(modifier)

    #
    # Remove bone contraints.
    #

    bpy.ops.object.select_all(action="DESELECT")
    created_armature.select_set(True)
    context.view_layer.objects.active = created_armature

    bpy.ops.object.mode_set(mode="POSE")
    for bone in created_armature.pose.bones:
        while len(bone.constraints) > 0:
            bone.constraints.remove(bone.constraints[0])
    bpy.ops.object.mode_set(mode="OBJECT")

    bpy.ops.object.select_all(action="DESELECT")

    #
    # Modify rigify deform bones.
    #

    bpy.ops.object.select_all(action="DESELECT")
    created_armature.select_set(True)
    context.view_layer.objects.active = created_armature

    bpy.ops.object.mode_set(mode="EDIT")

    # Make all bones visible.
    for bone_collection in created_armature.data.collections_all:
        bone_collection.is_visible = True
        bpy.ops.armature.reveal()

    deform_bones = [x for x in created_armature.data.edit_bones if x.name.startswith("DEF-")]
    base_bone_names = [x.name[4:] for x in created_armature.data.edit_bones if x.name.startswith("ORG-")]
    base_deform_bones = [x for x in deform_bones if x.name[4:] in base_bone_names]

    # Find deform bones and replace their parents with a deform version of the parent bone.
    for edit_bone in (x for x in deform_bones if x.parent is not None):
        def get_new_parent(edit_bone):
            if edit_bone.parent.name.startswith("DEF-"):
                return edit_bone.parent
            if edit_bone.parent.name.startswith("ORG-"):
                return created_armature.data.edit_bones[misc.replace_prefix(edit_bone.parent.name, "ORG", "DEF")]
            return None
        new_parent = get_new_parent(edit_bone)
        if new_parent is not None and new_parent.name == edit_bone.name:
            new_parent = get_new_parent(edit_bone.parent)
        edit_bone.parent = new_parent

    # Find root bone.
    root_bone_candidates = [
        x for x in original_armature.data.bones if
        (x.parent is None or x.parent == "") and not x.name.startswith("DEF-") and not x.name.startswith("ORG-") and not x.name.startswith("MCH-")
    ]
    if len(root_bone_candidates) != 1:
        raise RuntimeError(f"Couldn't find root bone in armature \"{original_armature.name}\".")
    original_root_bone = root_bone_candidates[0]

    # Remove non-deform bones (but keep root).
    root_bone = created_armature.data.edit_bones[original_root_bone.name]
    for edit_bone in created_armature.data.edit_bones:
        if edit_bone != root_bone and not edit_bone.name.startswith("DEF-"):
            created_armature.data.edit_bones.remove(edit_bone)

    # Set the parent of parentless bones to the root bone.
    for edit_bone in created_armature.data.edit_bones:
        if edit_bone.parent is None:
            edit_bone.parent = root_bone

    #
    # Replace limb segments with twist bones.
    #

    # Store the names that the bones had before being renamed.
    old_bone_names = {}

    def find_namesake_children(bone, bone_name):
        bone_segments = []
        for child_bone in bone.children:
            if child_bone.name.startswith(bone_name):
                bone_segments.append(child_bone)
                bone_segments = bone_segments + find_namesake_children(child_bone, bone_name)
        return bone_segments

    if convert_to_twist_bones:
        for edit_bone in base_deform_bones:
            # Limb segments have the same name as the parent.
            # For example bone "DEF-upperarm_l" would have a segment named "DEF-upperarm_l.001".
            bone_segments = find_namesake_children(edit_bone, edit_bone.name)

            # Rename bone segments to twist bones.
            for i, bone_segment in enumerate(bone_segments):
                # Find the left/right part of the bone name. There is no built-in function that does it,
                # so we flip the name of the bone, then compare the difference of the new name to the original name.

                original_name = bone_segment.name

                bpy.ops.armature.select_all(action="DESELECT")
                bone_segment.select = True
                bpy.ops.armature.flip_names()
                flipped_name = context.selected_bones[0].name
                bpy.ops.armature.select_all(action="DESELECT")

                bone_segment.name = original_name

                first_different_index = len(bone_segment.name)
                try:
                    first_different_index = next(i for i, x in enumerate(bone_segment.name) if x != flipped_name[i])
                except StopIteration:
                    pass

                first_side_index = len(bone_segment.name)
                try:
                    first_side_index = next(i for i, x in enumerate(bone_segment.name) if i >= first_different_index and x in ["l", "L", "r", "R"])
                except StopIteration:
                    pass

                # Rename bone.
                if (
                    first_different_index < len(bone_segment.name) and
                    first_side_index < len(bone_segment.name)
                ):
                    base_name, _ = misc.split_suffix_digits(bone_segment.name)
                    
                    common_part = base_name[0:first_different_index]
                    side_name = base_name[first_side_index:]
                    new_bone_name = f"{common_part}{twist_bone_suffix}_{i+1:02}_{side_name}"

                    old_bone_names[new_bone_name] = bone_segment.name
                    bone_segment.name = new_bone_name

            # Reparent twist bones.
            for bone_segment in bone_segments:
                bone_segment.use_connect = False
                bone_segment.parent = edit_bone
                # Reparent children of twist bones.
                for child_bone in bone_segment.children:
                    child_bone.use_connect = False
                    child_bone.parent = edit_bone

            if len(bone_segments) > 0:
                # Move bone's tail to the end of the twist bone chain.
                last_chain_bone = bone_segments[len(bone_segments) - 1]
                edit_bone.tail = last_chain_bone.head

    #
    # Add constraints to copy transforms from the original rig.
    #

    bpy.ops.object.mode_set(mode = "OBJECT")

    bpy.ops.object.select_all(action="DESELECT")
    created_armature.hide_set(False)
    created_armature.hide_viewport = False
    created_armature.select_set(True)
    context.view_layer.objects.active = created_armature

    bpy.ops.object.mode_set(mode = "POSE")

    for pose_bone in created_armature.pose.bones:
        # Remove old constraints.
        while len(pose_bone.constraints) > 0:
            pose_bone.constraints.remove(pose_bone.constraints[0])
        # Add copy constraint.
        new_constraint = pose_bone.constraints.new("COPY_TRANSFORMS")
        new_constraint.target = original_armature

        try:
            new_constraint.subtarget = old_bone_names[pose_bone.name]
        except KeyError:
            new_constraint.subtarget = pose_bone.name

    bpy.ops.object.mode_set(mode="EDIT")

    #
    # Rename bones.
    #

    # Rename root.
    root_bone = created_armature.data.edit_bones[original_root_bone.name]
    root_bone.name = "root"

    # Remove DEF prefix from bone names.
    for bone in created_armature.data.edit_bones:
        if bone != root_bone:
            bone.name = misc.replace_prefix(bone.name, "DEF-", "")

    bpy.ops.object.mode_set(mode="OBJECT")

    return created_armature
