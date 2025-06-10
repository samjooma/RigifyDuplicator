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
        raise ValueError(f'String "{string}" does not start with prefix "{oldprefix}"')
    return newprefix + string

def replace_suffix(string, oldsuffix, newsuffix):
    if string.endswith(oldsuffix):
        string = string[:-len(oldsuffix)]
    else:
        raise ValueError(f'String "{string}" does not end with suffix "{oldsuffix}"')
    return string + newsuffix

def split_suffix_digits(name):
    if len(name) > 4 and name[-4] == "." and name[-3:].isdigit():
        base_name = name[:-4]
        suffix = name[-4:]
    else:
        base_name = name
        suffix = ""
    return base_name, suffix

def get_hierarchy_recursive(object):
    children = [object]
    for child in object.children:
        children = children + get_hierarchy_recursive(child)
    return children

def find_layer_collection(context, object):
    def find_layer_collections_recursive(layer_collection):
        result = []
        if any(x for x in layer_collection.collection.objects if x == object):
            result.append(layer_collection)
        for child in layer_collection.children:
            result = result + find_layer_collections_recursive(child)
        return result
    
    layer_collections = find_layer_collections_recursive(context.view_layer.layer_collection)
    if len(layer_collections) > 1:
        raise RuntimeError(f"Object {object.name} is in more than one collection.")
    if len(layer_collections) < 1:
        return None
    return layer_collections[0]