import bpy

def is_valid_rig(context, rigObject):
    if (rigObject.type == "ARMATURE" and
        (rigObject.library is None or rigObject.library == "") and
        rigObject in context.scene.objects.values()):
        return True
    return False

def replace_prefix(string, oldprefix, newprefix):
    if string.startswith(oldprefix):
        string = string[len(oldprefix):]
    else:
        raise RuntimeError(f'String "{string}" does not start with prefix "{oldprefix}"')
    return newprefix + string

def replace_suffix(string, oldsuffix, newsuffix):
    if string.endswith(oldsuffix):
        string = string[:-len(oldsuffix)]
    else:
        raise RuntimeError(f'String "{string}" does not end with suffix "{oldsuffix}"')
    return string + newsuffix

def split_name(name):
    if len(name) > 4 and name[-4] == "." and name[-3:].isdigit():
        base_name = name[:-4]
        suffix = name[-4:]
    else:
        base_name = name
        suffix = ""
    return base_name, suffix

def find_layer_collections(context, object):
    def find_layer_collections_recursive(layer_collection):
        result = set([])
        if any(x for x in layer_collection.collection.objects if x == object):
            result.add(layer_collection)
        for child in layer_collection.children:
            for x in find_layer_collections_recursive(child):
                result.add(x)
        return result
    return find_layer_collections_recursive(context.view_layer.layer_collection)

def make_object_and_collection_visible(context, object):
    layer_collections = find_layer_collections(context, object)
    for layer_collection in layer_collections:
        layer_collection.exclude = False
        layer_collection.hide_viewport = False
        layer_collection.collection.hide_viewport = False
    object.hide_set(False)
    object.hide_viewport = False