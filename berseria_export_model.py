# Tool to export model data from the dlb/dlp format used by Tales of Berseria.
#
# Usage:  Run by itself without commandline arguments and it will ask for a file number and
# output a glb file.  It will do its best to find the matching dlp file and skeleton file.
#
# For command line options, run:
# /path/to/python3 berseria_export_model.py --help
#
# Requires lib_fmtibvb.py, put in the same directory
#
# GitHub eArmada8/berseria_model_tool


try:
    import struct, json, numpy, glob, copy, os, sys
    from lib_fmtibvb import *
except ModuleNotFoundError as e:
    print("Python module missing! {}".format(e.msg))
    input("Press Enter to abort.")
    raise

def read_offset (f, size = 8):
    start_offset = f.tell()
    diff_offset, = struct.unpack("<{}".format({2: "H", 4: "I", 8: "Q"}[size]), f.read(size))
    return(start_offset + diff_offset)

def read_string (f, start_offset):
    current_loc = f.tell()
    f.seek(start_offset)
    null_term_string = f.read(1)
    while null_term_string[-1] != 0:
        null_term_string += f.read(1)
    f.seek(current_loc)
    return(null_term_string[:-1].decode())

def trianglestrip_to_list(ib_list):
    triangles = []
    for i in range(len(ib_list)-2):
        if i % 2 == 0:
            triangles.append([ib_list[i], ib_list[i+1], ib_list[i+2]])
        else:
            triangles.append([ib_list[i], ib_list[i+2], ib_list[i+1]]) #DirectX implementation
            #triangles.append([ib_list[i+1], ib_list[i], ib_list[i+2]]) #OpenGL implementation
    return(triangles)

def read_opening_dict (f):
    dict_offset = read_offset(f)
    dict_size, = struct.unpack("<Q", f.read(8))
    opening_dict = []
    return_to_offset = f.tell()
    f.seek(dict_offset)
    for _ in range(dict_size):
        opening_dict.append(read_string(f, read_offset(f)))
    f.seek(return_to_offset)
    return(opening_dict)

#Node Tree, offset should be toc[0]
def read_section_0 (f, offset):
    # Jump to #0
    f.seek(offset)
    section_0_unk = struct.unpack("<4I", f.read(16))
    section_0_counts = struct.unpack("<2HI", f.read(8))
    section_0_toc = []
    for _ in range(8):
        offset = read_offset(f)
        num_entries, = struct.unpack("<Q", f.read(8))
        section_0_toc.append({'offset': offset, 'num_entries': num_entries})
    #0x38 bytes - dunno what this is
    f.seek(section_0_toc[0]['offset'])
    id = struct.unpack("<{}I".format(section_0_toc[0]['num_entries']), f.read(section_0_toc[0]['num_entries']*4))
    f.seek(section_0_toc[1]['offset'])
    true_parent = struct.unpack("<{}i".format(section_0_toc[1]['num_entries']), f.read(section_0_toc[1]['num_entries']*4))
    f.seek(section_0_toc[2]['offset'])
    tree_info = [struct.unpack("<4h", f.read(8)) for _ in range(section_0_toc[2]['num_entries'])]
    f.seek(section_0_toc[3]['offset'])
    name = [read_string(f, read_offset(f)) for _ in range(section_0_toc[3]['num_entries'])]
    f.seek(section_0_toc[4]['offset'])
    unk_matrix = [struct.unpack("<16f", f.read(64)) for _ in range(section_0_toc[4]['num_entries'])]
    f.seek(section_0_toc[5]['offset'])
    abs_matrix = [struct.unpack("<16f", f.read(64)) for _ in range(section_0_toc[5]['num_entries'])]
    f.seek(section_0_toc[6]['offset'])
    inv_matrix = [struct.unpack("<16f", f.read(64)) for _ in range(section_0_toc[6]['num_entries'])]
    f.seek(section_0_toc[7]['offset'])
    parent_list = struct.unpack("<{}h".format(section_0_toc[7]['num_entries']), f.read(section_0_toc[7]['num_entries']*2))
    #raw_data = [id, true_parent, tree_info, name, unk_matrix, abs_matrix, inv_matrix, parent_list]
    skel_struct = [{'id': id[i], 'true_parent': true_parent[i], 'tree_info': tree_info[i], 'name': name[i], 'abs_matrix': abs_matrix[i],\
    'inv_matrix': inv_matrix[i], 'parent': tree_info[i][2]} for i in range(section_0_toc[0]['num_entries'])]
    for i in range(len(skel_struct)):
        if skel_struct[i]['parent'] in range(len(skel_struct)):
            abs_mtx = [skel_struct[i]['abs_matrix'][0:4], skel_struct[i]['abs_matrix'][4:8],\
                skel_struct[i]['abs_matrix'][8:12], skel_struct[i]['abs_matrix'][12:16]]
            parent_inv_mtx = [skel_struct[skel_struct[i]['parent']]['inv_matrix'][0:4],\
                skel_struct[skel_struct[i]['parent']]['inv_matrix'][4:8],\
                skel_struct[skel_struct[i]['parent']]['inv_matrix'][8:12],\
                skel_struct[skel_struct[i]['parent']]['inv_matrix'][12:16]]
            skel_struct[i]['matrix'] = numpy.dot(abs_mtx, parent_inv_mtx).flatten('C').tolist()
        else:
            skel_struct[i]['matrix'] = skel_struct[i]['abs_matrix']
        skel_struct[i]['children'] = [j for j in range(len(skel_struct)) if skel_struct[j]['parent'] == i]
    return(skel_struct)

def read_dlb_skeleton (dlb_file):
    skel_list = []
    with open(dlb_file, 'rb') as f:
        magic = f.read(4)
        if magic == b'DPDF':
            f.seek(20,1)
            magic = f.read(4)
            if magic == b'BLDM':
                f.seek(4,1)
                offset = read_offset(f)
                f.seek(offset) # Jump to section 0
                f.seek(24,1)
                offset = read_offset(f)
                num_entries, = struct.unpack("<Q", f.read(8))
                f.seek(offset)
                skel_list.extend(list(struct.unpack("<{}I".format(num_entries), f.read(num_entries * 4))))
    return(skel_list)

def find_primary_skeleton (missing_bone_palette_ids):
    print("Searching all dlb files for primary skeleton in current folder.")
    dlb_files = glob.glob('*.TOMDLB_D')
    if len(dlb_files) > 10:
        print("This may take a long time...")
    matches = [x for x in dlb_files if all([y in read_dlb_skeleton(x) for y in missing_bone_palette_ids])]
    match = ''
    if len(matches) > 1:
        print("Multiple matches found, please choose one.")
        for i in range(len(matches)):
            print("{0}. {1}".format(i+1, matches[i]))
            if (i+1) % 25 == 0:
                input("More results, press Enter to continue...")
        while match == '':
            raw_input = input("Use which skeleton? ")
            if raw_input.isnumeric() and int(raw_input)-1 in range(len(matches)):
                match = matches[int(raw_input)-1]
            else:
                print("Invalid entry!")
    else:
        match = matches[0]
    if match == '':
        print("No matches found!")
    else:
        print("Using {} as primary skeleton.".format(match))
    return match

# skel_struct will be appended onto the skeleton_file struct, not the other way around
def combine_skeletons (skeleton_file, skel_struct):
    with open(skeleton_file, 'rb') as f:
        magic = f.read(4)
        if magic == b'DPDF':
            f.seek(20,1)
            magic = f.read(4)
            if magic == b'BLDM':
                f.seek(4,1)
                offset = read_offset(f)
                primary_skel_struct = read_section_0(f, offset)
                new_skel_struct = primary_skel_struct + skel_struct
                #Reassign parent
                new_indices = [x['id'] for x in new_skel_struct]
                for i in range(len(new_skel_struct)):
                    if new_skel_struct[i]['true_parent'] in new_indices:
                        new_skel_struct[i]['parent'] = new_indices.index(new_skel_struct[i]['true_parent'])
                    else:
                        new_skel_struct[i]['parent'] = -1
                for i in range(len(new_skel_struct)):
                    if new_skel_struct[i]['parent'] in range(len(new_skel_struct)):
                        abs_mtx = [new_skel_struct[i]['abs_matrix'][0:4], new_skel_struct[i]['abs_matrix'][4:8],\
                            new_skel_struct[i]['abs_matrix'][8:12], new_skel_struct[i]['abs_matrix'][12:16]]
                        parent_inv_mtx = [new_skel_struct[new_skel_struct[i]['parent']]['inv_matrix'][0:4],\
                            new_skel_struct[new_skel_struct[i]['parent']]['inv_matrix'][4:8],\
                            new_skel_struct[new_skel_struct[i]['parent']]['inv_matrix'][8:12],\
                            new_skel_struct[new_skel_struct[i]['parent']]['inv_matrix'][12:16]]
                        new_skel_struct[i]['matrix'] = numpy.dot(abs_mtx, parent_inv_mtx).flatten('C').tolist()
                    else:
                        new_skel_struct[i]['matrix'] = new_skel_struct[i]['abs_matrix']
                    new_skel_struct[i]['children'] = [j for j in range(len(new_skel_struct)) if new_skel_struct[j]['parent'] == i]
                return(new_skel_struct)
            else:
                print("Invalid skeleton file!")
                return skel_struct
        else:
            print("Invalid skeleton file!")
            return skel_struct

def find_and_add_external_skeleton (skel_struct, bone_palette_ids):
    #Sanity check, if the skeleton is already complete then skip the search
    if not all([y in [x['id'] for x in skel_struct] for y in bone_palette_ids]):
        missing_bone_palette_ids = [y for y in bone_palette_ids if not y in [x['id'] for x in skel_struct]]
        primary_skeleton_file = find_primary_skeleton (missing_bone_palette_ids)
        skel_struct = combine_skeletons (primary_skeleton_file, skel_struct)
    return(skel_struct)

def make_fmt(num_uvs):
    fmt = {'stride': '0', 'topology': 'trianglelist', 'format':\
        "DXGI_FORMAT_R16_UINT", 'elements': []}
    element_id, stride = 0, 0
    semantic_index = {'TEXCOORD': 0} # Counters for multiple indicies
    elements = []
    for i in range(4+num_uvs):
            # I think order matters in this dict, so we will define the entire structure with default values
            element = {'id': '{0}'.format(element_id), 'SemanticName': '', 'SemanticIndex': '0',\
                'Format': '', 'InputSlot': '0', 'AlignedByteOffset': str(stride),\
                'InputSlotClass': 'per-vertex', 'InstanceDataStepRate': '0'}
            if i == 0:
                element['SemanticName'] = 'POSITION'
                element['Format'] = 'R32G32B32_FLOAT'
                stride += 12
            elif i == 1:
                element['SemanticName'] = 'NORMAL'
                element['Format'] = 'R32G32B32_FLOAT'
                stride += 12
            elif i == 4+num_uvs-2:
                element['SemanticName'] = 'BLENDWEIGHTS'
                element['Format'] = 'R32G32B32A32_FLOAT'
                stride += 16
            elif i == 4+num_uvs-1:
                element['SemanticName'] = 'BLENDINDICES'
                element['Format'] = 'R8G8B8A8_UINT'
                stride += 4
            else:
                element['SemanticName'] = 'TEXCOORD'
                element['SemanticIndex'] = str(semantic_index['TEXCOORD'])
                element['Format'] = 'R32G32_FLOAT'
                semantic_index['TEXCOORD'] += 1
                stride += 8
            element_id += 1
            elements.append(element)
    fmt['stride'] = str(stride)
    fmt['elements'] = elements
    return(fmt)

def trianglestrip_to_list(ib_list):
    triangles = []
    for i in range(len(ib_list)-2):
        if i % 2 == 0:
            triangles.append([ib_list[i], ib_list[i+1], ib_list[i+2]])
        else:
            triangles.append([ib_list[i], ib_list[i+2], ib_list[i+1]]) #DirectX implementation
            #triangles.append([ib_list[i+1], ib_list[i], ib_list[i+2]]) #OpenGL implementation
    return(triangles)

def read_mesh (main_f, idx_f, start_offset, num_uv_maps):
    def read_floats (f, num):
        return(list(struct.unpack("<{}f".format(num), f.read(num * 4))))
    def read_bytes (f, num):
        return(list(struct.unpack("<{}B".format(num), f.read(num))))
    def read_interleaved_floats (f, num, stride, total):
        vecs = []
        padding = stride - (num * 4)
        for i in range(total):
            vecs.append(read_floats(f, num))
            f.seek(padding, 1)
        return(vecs)
    def read_interleaved_bytes (f, num, stride, total):
        vecs = []
        padding = stride - (num)
        for i in range(total):
            vecs.append(read_bytes(f, num))
            f.seek(padding, 1)
        return(vecs)
    def fix_weights (weights):
        for _ in range(3):
            weights = [x+[round(1-sum(x),6)] if len(x) < 4 else x for x in weights]
        return(weights)
    main_f.seek(start_offset)
    num_uvs, num_idx, offset_uvs, offset_idx = struct.unpack("<2H2I", main_f.read(12))
    uv_stride = (offset_idx - offset_uvs) // num_uvs
    #num_uv_maps = (uv_stride - 4) // 8 # 4 byte buffer + VEC2 per map
    num_vertices = list(struct.unpack("<4I", main_f.read(16)))
    verts = []
    norms = []
    blend_idx = []
    weights = []
    for i in range(len(num_vertices)):
        vert_offset = main_f.tell()
        norm_offset = vert_offset + 12
        blend_idx_offset = norm_offset + 12
        weights_offset = blend_idx_offset + 4
        stride = 28 + (i * 4)
        end_offset = main_f.tell() + (num_vertices[i] * stride)
        main_f.seek(vert_offset)
        verts.extend(read_interleaved_floats(main_f, 3, stride, num_vertices[i]))
        main_f.seek(norm_offset)
        norms.extend(read_interleaved_floats(main_f, 3, stride, num_vertices[i]))
        main_f.seek(blend_idx_offset)
        blend_idx.extend(read_interleaved_bytes(main_f, 4, stride, num_vertices[i]))
        if i > 0:
            main_f.seek(weights_offset)
            weights.extend(read_interleaved_floats(main_f, i, stride, num_vertices[i]))
        else:
            weights.extend([[1.0] for _ in range(num_vertices[i])])
        main_f.seek(end_offset)
    weights = fix_weights(weights)
    uv_maps = []
    for i in range(num_uv_maps):
        idx_f.seek(offset_uvs + 4 + (i * 8))
        uv_maps.append(read_interleaved_floats (idx_f, 2, uv_stride, num_uvs))
    idx_f.seek(offset_idx)
    idx_buffer = list(struct.unpack("<{}H".format(num_idx), idx_f.read(num_idx * 2)))
    fmt = make_fmt(len(uv_maps))
    vb = [{'Buffer': verts}, {'Buffer': norms}]
    for uv_map in uv_maps:
        vb.append({'Buffer': uv_map})
    vb.append({'Buffer': weights})
    vb.append({'Buffer': blend_idx})
    return({'fmt': fmt, 'vb': vb, 'ib': trianglestrip_to_list(idx_buffer)})

#Meshes, offset should be toc[6].  Requires dlp filename for uv's and index buffer.
def read_section_6 (f, offset, dlb_file, dlp_file):
    f.seek(offset)
    section_6_unk = struct.unpack("<4I", f.read(16))
    section_6_toc = []
    for _ in range(4):
        offset = read_offset(f)
        num_entries, = struct.unpack("<Q", f.read(8))
        section_6_toc.append({'offset': offset, 'num_entries': num_entries})
    #section_6_toc[0] - VEC4 (u32, f32?) - in sample is all zeroes
    #section_6_toc[1] - meshes
    #section_6_toc[2] - bone palette
    #section_6_toc[3] - u32 x 2 - # meshes, # bones
    f.seek(section_6_toc[2]['offset'])
    bone_palette_ids = struct.unpack("<{}I".format(section_6_toc[2]['num_entries']), f.read(4 * section_6_toc[2]['num_entries']))
    mesh_blocks_info = []
    meshes = []
    f.seek(section_6_toc[1]['offset'])
    with open (dlp_file, 'rb') as idx_f:
        for i in range(section_6_toc[1]['num_entries']):
            data = {'current_block_offset': f.tell(), 'name': ''}
            data["mesh"], data["submesh"], data["node"], \
                data["flags"], data["material"], data["unknown"] = struct.unpack("<i4hi", f.read(16))
            data['string_offset'] = read_offset(f)
            data['data_offset'] = read_offset(f)
            data["data_block_size"], = struct.unpack("<Q", f.read(8))
            current_offset = f.tell()
            data["name"] = read_string (f, data['string_offset'])
            meshes.append(read_mesh (f, idx_f, data['data_offset'], data["flags"] & 0xF))
            mesh_blocks_info.append(data)
            f.seek(current_offset)
    return(meshes, bone_palette_ids, mesh_blocks_info)

#Materials, offset should be toc[7]
def read_section_7 (f, offset):
    f.seek(offset)
    section_7_unk = struct.unpack("<6I", f.read(24))
    section_7_toc = []
    for _ in range(7):
        offset = read_offset(f)
        num_entries, = struct.unpack("<Q", f.read(8))
        section_7_toc.append({'offset': offset, 'num_entries': num_entries})
    set_0 = [] # Materials, including the indices that map to set_1 (textures)
    for i in range(section_7_toc[0]['num_entries']):
        f.seek(section_7_toc[0]['offset'] + (i * 56))
        values = struct.unpack("<12h", f.read(24))
        offset1 = read_offset(f)
        num_vals1, = struct.unpack("<Q", f.read(8))
        offset2 = read_offset(f)
        num_vals2, = struct.unpack("<Q", f.read(8))
        end_offset = f.tell()
        f.seek(offset1)
        vals1 = struct.unpack("<{}I".format(num_vals1), f.read(num_vals1 * 4))
        f.seek(offset2)
        assert num_vals2 == 0x17
        vals2 = struct.unpack("<8I4f4If6I", f.read(92))
        set_0.append({'base': values, 'vals1': vals1, 'vals2': vals2})
    set_1 = [] # Texture assignments, each is a tuple where the second number points to set_6
    for i in range(section_7_toc[1]['num_entries']):
        f.seek(section_7_toc[1]['offset'] + (i * 6))
        values = struct.unpack("<hi", f.read(6))
        set_1.append(values)
    set_2 = [] # Materials, including material names and alpha
    for i in range(section_7_toc[2]['num_entries']):
        f.seek(section_7_toc[2]['offset'] + (i * 40))
        offset1 = read_offset(f)
        num_vals1, = struct.unpack("<Q", f.read(8))
        offset2 = read_offset(f)
        num_vals2, = struct.unpack("<Q", f.read(8))
        str_offset = read_offset(f)
        f.seek(offset1)
        vals1 = struct.unpack("<{}I".format(num_vals1), f.read(num_vals1 * 4))
        f.seek(offset2)
        vals2 = struct.unpack("<{}I".format(num_vals2), f.read(num_vals2 * 4))
        name = read_string(f, str_offset)
        set_2.append({'name': name, 'vals1': vals1, 'vals2': vals2})
    set_6 = [] # Texture names
    for i in range(section_7_toc[6]['num_entries']):
        f.seek(section_7_toc[6]['offset'] + (i * 24))
        str_offset = read_offset(f)
        vals = struct.unpack("<2Q", f.read(16))
        tex_name = read_string(f, str_offset)
        set_6.append({'tex_name': tex_name, 'vals': vals})
    material_dict = {set_2[i]['name']:\
        {'texture':set_6[set_1[set_0[i]['base'][6]][1]]['tex_name'],\
         'alpha': set_2[i]['vals2'][3]}\
        for i in range(len(set_0))}
    return(material_dict)

def convert_format_for_gltf(dxgi_format):
    dxgi_format = dxgi_format.split('DXGI_FORMAT_')[-1]
    dxgi_format_split = dxgi_format.split('_')
    if len(dxgi_format_split) == 2:
        numtype = dxgi_format_split[1]
        vec_format = re.findall("[0-9]+",dxgi_format_split[0])
        vec_bits = int(vec_format[0])
        vec_elements = len(vec_format)
        if numtype in ['FLOAT', 'UNORM', 'SNORM']:
            componentType = 5126
            componentStride = len(re.findall('[0-9]+', dxgi_format)) * 4
            dxgi_format = "".join(['R32','G32','B32','A32','D32'][0:componentStride//4]) + "_FLOAT"
        elif numtype == 'UINT':
            if vec_bits == 32:
                componentType = 5125
                componentStride = len(re.findall('[0-9]+', dxgi_format)) * 4
            elif vec_bits == 16:
                componentType = 5123
                componentStride = len(re.findall('[0-9]+', dxgi_format)) * 2
            elif vec_bits == 8:
                componentType = 5121
                componentStride = len(re.findall('[0-9]+', dxgi_format))
        accessor_types = ["SCALAR", "VEC2", "VEC3", "VEC4"]
        accessor_type = accessor_types[len(re.findall('[0-9]+', dxgi_format))-1]
        return({'format': dxgi_format, 'componentType': componentType,\
            'componentStride': componentStride, 'accessor_type': accessor_type})
    else:
        return(False)

def convert_fmt_for_gltf(fmt):
    new_fmt = copy.deepcopy(fmt)
    stride = 0
    new_semantics = {'BLENDWEIGHTS': 'WEIGHTS', 'BLENDINDICES': 'JOINTS'}
    need_index = ['WEIGHTS', 'JOINTS', 'COLOR', 'TEXCOORD']
    for i in range(len(fmt['elements'])):
        if new_fmt['elements'][i]['SemanticName'] in new_semantics.keys():
            new_fmt['elements'][i]['SemanticName'] = new_semantics[new_fmt['elements'][i]['SemanticName']]
        new_info = convert_format_for_gltf(fmt['elements'][i]['Format'])
        new_fmt['elements'][i]['Format'] = new_info['format']
        if new_fmt['elements'][i]['SemanticName'] in need_index:
            new_fmt['elements'][i]['SemanticName'] = new_fmt['elements'][i]['SemanticName'] + '_' +\
                new_fmt['elements'][i]['SemanticIndex']
        new_fmt['elements'][i]['AlignedByteOffset'] = stride
        new_fmt['elements'][i]['componentType'] = new_info['componentType']
        new_fmt['elements'][i]['componentStride'] = new_info['componentStride']
        new_fmt['elements'][i]['accessor_type'] = new_info['accessor_type']
        stride += new_info['componentStride']
    index_fmt = convert_format_for_gltf(fmt['format'])
    new_fmt['format'] = index_fmt['format']
    new_fmt['componentType'] = index_fmt['componentType']
    new_fmt['componentStride'] = index_fmt['componentStride']
    new_fmt['accessor_type'] = index_fmt['accessor_type']
    new_fmt['stride'] = stride
    return(new_fmt)

def fix_strides(submesh):
    offset = 0
    for i in range(len(submesh['vb'])):
        submesh['vb'][i]['fmt']['AlignedByteOffset'] = str(offset)
        submesh['vb'][i]['stride'] = get_stride_from_dxgi_format(submesh['vb'][i]['fmt']['Format'])
        offset += submesh['vb'][i]['stride']
    return(submesh)

def write_gltf(dlb_file, skel_struct, vgmap, mesh_blocks_info, meshes, material_dict,\
        overwrite = False, write_raw_buffers = False, write_binary_gltf = True):
    gltf_data = {}
    gltf_data['asset'] = { 'version': '2.0' }
    gltf_data['accessors'] = []
    gltf_data['bufferViews'] = []
    gltf_data['buffers'] = []
    gltf_data['meshes'] = []
    gltf_data['materials'] = []
    gltf_data['nodes'] = []
    gltf_data['samplers'] = []
    gltf_data['scenes'] = [{}]
    gltf_data['scenes'][0]['nodes'] = [0]
    gltf_data['scene'] = 0
    gltf_data['skins'] = []
    gltf_data['textures'] = []
    giant_buffer = bytes()
    buffer_view = 0
    # Materials
    texture_list = sorted(list(set([x['texture'] for x in material_dict.values()])))
    gltf_data['images'] = [{'uri':'textures/{}.dds'.format(x)} for x in texture_list]
    for mat_name in material_dict:
        material = { 'name': mat_name }
        sampler = { 'wrapS': 10497, 'wrapT': 10497 } # I have no idea if this setting exists
        texture = { 'source': texture_list.index(material_dict[mat_name]['texture']), 'sampler': len(gltf_data['samplers']) }
        material['pbrMetallicRoughness']= { 'baseColorTexture' : { 'index' : len(gltf_data['textures']), },\
            'metallicFactor' : 0.0, 'roughnessFactor' : 1.0 }
        if material_dict[mat_name]['alpha'] & 1:
            material['alphaMode'] = 'MASK'
        gltf_data['samplers'].append(sampler)
        gltf_data['textures'].append(texture)
        gltf_data['materials'].append(material)
    material_list = [x['name'] for x in gltf_data['materials']]
    missing_textures = [x['uri'] for x in gltf_data['images'] if not os.path.exists(x['uri'])]
    if len(missing_textures) > 0:
        print("Warning:  The following textures were not found:")
        for texture in missing_textures:
            print("{}".format(texture))
    # Nodes
    for i in range(len(skel_struct)):
        g_node = {'children': skel_struct[i]['children'], 'name': skel_struct[i]['name'], 'matrix': skel_struct[i]['matrix']}
        gltf_data['nodes'].append(g_node)
    for i in range(len(gltf_data['nodes'])):
        if len(gltf_data['nodes'][i]['children']) == 0:
            del(gltf_data['nodes'][i]['children'])
    # Mesh nodes will be attached to the first node since in the original model, they don't really have a home
    node_id_list = [x['id'] for x in skel_struct]
    mesh_node_ids = {x['mesh']:x['name'] for x in mesh_blocks_info}
    for mesh_node_id in mesh_node_ids:
        if not mesh_node_id in node_id_list:
            g_node = {'name': mesh_node_ids[mesh_node_id]}
            gltf_data['nodes'][0]['children'].append(len(gltf_data['nodes']))
            gltf_data['nodes'].append(g_node)
    mesh_block_tree = {x:[i for i in range(len(mesh_blocks_info)) if mesh_blocks_info[i]['mesh'] == x] for x in mesh_node_ids}
    node_list = [x['name'] for x in gltf_data['nodes']]
    # Skin matrices
    vgmap_nodes = [node_list.index(x) for x in list(vgmap.keys())]
    ibms = [skel_struct[j]['inv_matrix'] for j in vgmap_nodes]
    inv_mtx_buffer = b''.join([struct.pack("<16f", *x) for x in ibms])
    base_name = dlb_file.split('.')[0].split('_')[0]
    # Meshes
    if write_raw_buffers == True:
        overwrite_buffers = copy.deepcopy(overwrite)
        if os.path.exists(base_name) and (os.path.isdir(base_name)) and (overwrite_buffers == False):
            if str(input(base_name + " folder exists! Overwrite? (y/N) ")).lower()[0:1] == 'y':
                overwrite_buffers = True
        if (overwrite_buffers == True) or not os.path.exists(base_name):
            if not os.path.exists(base_name):
                os.mkdir(base_name)
            overwrite_buffers = True
    for mesh in mesh_block_tree: #Mesh
        primitives = []
        for j in range(len(mesh_block_tree[mesh])): #Submesh
            i = mesh_block_tree[mesh][j]
            if mesh_blocks_info[i]["flags"] in [83, 84]:
                # Vertex Buffer
                gltf_fmt = convert_fmt_for_gltf(meshes[i]['fmt'])
                vb_stream = io.BytesIO()
                write_vb_stream(meshes[i]['vb'], vb_stream, gltf_fmt, e='<', interleave = False)
                block_offset = len(giant_buffer)
                primitive = {"attributes":{}}
                for element in range(len(gltf_fmt['elements'])):
                    primitive["attributes"][gltf_fmt['elements'][element]['SemanticName']]\
                        = len(gltf_data['accessors'])
                    gltf_data['accessors'].append({"bufferView" : len(gltf_data['bufferViews']),\
                        "componentType": gltf_fmt['elements'][element]['componentType'],\
                        "count": len(meshes[i]['vb'][element]['Buffer']),\
                        "type": gltf_fmt['elements'][element]['accessor_type']})
                    if gltf_fmt['elements'][element]['SemanticName'] == 'POSITION':
                        gltf_data['accessors'][-1]['max'] =\
                            [max([x[0] for x in meshes[i]['vb'][element]['Buffer']]),\
                             max([x[1] for x in meshes[i]['vb'][element]['Buffer']]),\
                             max([x[2] for x in meshes[i]['vb'][element]['Buffer']])]
                        gltf_data['accessors'][-1]['min'] =\
                            [min([x[0] for x in meshes[i]['vb'][element]['Buffer']]),\
                             min([x[1] for x in meshes[i]['vb'][element]['Buffer']]),\
                             min([x[2] for x in meshes[i]['vb'][element]['Buffer']])]
                    gltf_data['bufferViews'].append({"buffer": 0,\
                        "byteOffset": block_offset,\
                        "byteLength": len(meshes[i]['vb'][element]['Buffer']) *\
                        gltf_fmt['elements'][element]['componentStride'],\
                        "target" : 34962})
                    block_offset += len(meshes[i]['vb'][element]['Buffer']) *\
                        gltf_fmt['elements'][element]['componentStride']
                vb_stream.seek(0)
                giant_buffer += vb_stream.read()
                vb_stream.close()
                del(vb_stream)
                # Index Buffers
                ib_stream = io.BytesIO()
                write_ib_stream(meshes[i]['ib'], ib_stream, gltf_fmt, e='<')
                # IB is 16-bit so can be misaligned, unlike VB
                while (ib_stream.tell() % 4) > 0:
                    ib_stream.write(b'\x00')
                primitive["indices"] = len(gltf_data['accessors'])
                gltf_data['accessors'].append({"bufferView" : len(gltf_data['bufferViews']),\
                    "componentType": gltf_fmt['componentType'],\
                    "count": len([index for triangle in meshes[i]['ib'] for index in triangle]),\
                    "type": gltf_fmt['accessor_type']})
                gltf_data['bufferViews'].append({"buffer": 0,\
                    "byteOffset": len(giant_buffer),\
                    "byteLength": ib_stream.tell(),\
                    "target" : 34963})
                ib_stream.seek(0)
                giant_buffer += ib_stream.read()
                ib_stream.close()
                del(ib_stream)
                primitive["mode"] = 4 #TRIANGLES
                primitive["material"] = mesh_blocks_info[i]['material']
                if write_raw_buffers == True and overwrite_buffers == True:
                    filename = '{0:02d}_{1}'.format(i, mesh_node_ids[mesh])
                    write_fmt(meshes[i]['fmt'], '{0}/{1}.fmt'.format(base_name, filename))
                    write_ib(meshes[i]['ib'], '{0}/{1}.ib'.format(base_name, filename), meshes[i]['fmt'])
                    write_vb(meshes[i]['vb'], '{0}/{1}.vb'.format(base_name, filename), meshes[i]['fmt'])
                    with open("{0}/{1}.vgmap".format(base_name, filename), 'wb') as ff:
                        ff.write(json.dumps(vgmap, indent=4).encode('utf-8'))
                primitives.append(primitive)
        if len(primitives) > 0:
            if mesh_node_ids[mesh] in node_list: # One of the new nodes
                node_id = node_list.index(mesh_node_ids[mesh])
            else: # One of the pre-assigned nodes
                node_id = node_id_list.index(mesh_blocks_info[i]["mesh"])
            gltf_data['nodes'][node_id]['mesh'] = len(gltf_data['meshes'])
            gltf_data['meshes'].append({"primitives": primitives, "name": mesh_node_ids[mesh]})
            # Skinning
            gltf_data['nodes'][node_id]['skin'] = len(gltf_data['skins'])
            gltf_data['skins'].append({"inverseBindMatrices": len(gltf_data['accessors']),\
                "joints": [node_list.index(x) for x in vgmap]})
            gltf_data['accessors'].append({"bufferView" : len(gltf_data['bufferViews']),\
                "componentType": 5126,\
                "count": len(ibms),\
                "type": "MAT4"})
            gltf_data['bufferViews'].append({"buffer": 0,\
                "byteOffset": len(giant_buffer),\
                "byteLength": len(inv_mtx_buffer)})
            giant_buffer += inv_mtx_buffer
    # Write GLB
    gltf_data['buffers'].append({"byteLength": len(giant_buffer)})
    if (os.path.exists(base_name + '.gltf') or os.path.exists(base_name + '.glb')) and (overwrite == False):
        if str(input(base_name + ".glb/.gltf exists! Overwrite? (y/N) ")).lower()[0:1] == 'y':
            overwrite = True
    if (overwrite == True) or not (os.path.exists(base_name + '.gltf') or os.path.exists(base_name + '.glb')):
        if write_binary_gltf == True:
            with open(base_name+'.glb', 'wb') as f:
                jsondata = json.dumps(gltf_data).encode('utf-8')
                jsondata += b' ' * (4 - len(jsondata) % 4)
                f.write(struct.pack('<III', 1179937895, 2, 12 + 8 + len(jsondata) + 8 + len(giant_buffer)))
                f.write(struct.pack('<II', len(jsondata), 1313821514))
                f.write(jsondata)
                f.write(struct.pack('<II', len(giant_buffer), 5130562))
                f.write(giant_buffer)
        else:
            gltf_data['buffers'][0]["uri"] = base_name+'.bin'
            with open(base_name+'.bin', 'wb') as f:
                f.write(giant_buffer)
            with open(base_name+'.gltf', 'wb') as f:
                f.write(json.dumps(gltf_data, indent=4).encode("utf-8"))

def process_dlb (dlb_file, dlp_file, overwrite = False, write_raw_buffers = False, write_binary_gltf = True):
    with open(dlb_file, 'rb') as f:
        magic = f.read(4)
        if magic == b'DPDF':
            unk_int, = struct.unpack("<I", f.read(4))
            opening_dict = read_opening_dict (f)
            magic = f.read(4)
            if magic == b'BLDM':
                unk_int2, = struct.unpack("<I", f.read(4))
                toc = [read_offset(f) for _ in range(12)]
                #toc[0] - Nodes.  1 - (mesh) 0x16c, 0x82, mostly zeros (6x zero len sections) (skel) 0x10 header, 6 sections.  2 - 16 zero bytes, 3 - 0x16c, 0x82, mostly zeros.  
                #4 - starts with 0x16c, 0x82, lots of floats.  5 - 0x20 bytes, all zeros
                #6 - meshes.  7 - materials.  8,9,10,11 - dunno
                skel_struct = read_section_0(f, toc[0])
                meshes, bone_palette_ids, mesh_blocks_info = read_section_6(f, toc[6], dlb_file, dlp_file)
                # Attempt to incorporate an external skeleton (skipped if skeleton already complete)
                skel_struct = find_and_add_external_skeleton (skel_struct, bone_palette_ids)
                if all([y in [x['id'] for x in skel_struct] for y in bone_palette_ids]):
                    skel_index = {skel_struct[i]['id']:i for i in range(len(skel_struct))}
                    vgmap = {skel_struct[skel_index[bone_palette_ids[i]]]['name']:i for i in range(len(bone_palette_ids))}
                material_dict = read_section_7(f, toc[7])
                write_gltf(dlb_file, skel_struct, vgmap, mesh_blocks_info, meshes, material_dict,\
                    overwrite = overwrite, write_raw_buffers = write_raw_buffers, write_binary_gltf = write_binary_gltf)
    return

if __name__ == "__main__":
    # Set current directory
    if getattr(sys, 'frozen', False):
        os.chdir(os.path.dirname(sys.executable))
    else:
        os.chdir(os.path.abspath(os.path.dirname(__file__)))

    if len(sys.argv) > 1:
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument('-t', '--textformat', help="Write gltf instead of glb", action="store_false")
        parser.add_argument('-d', '--dumprawbuffers', help="Write fmt/ib/vb/vgmap files in addition to glb", action="store_true")
        parser.add_argument('-o', '--overwrite', help="Overwrite existing files", action="store_true")
        parser.add_argument('dlb_filename', help="Name of dlb file to process.")
        parser.add_argument('dlp_filename', help="Name of dlp file to process.")
        args = parser.parse_args()
        if os.path.exists(args.dlb_filename) and args.dlb_filename[-5:] == 'DLB_D'\
                and os.path.exists(args.dlp_filename) and args.dlp_filename[-5:] == 'DLP_P':
            process_mdl(args.dlb_filename, args.dlp_filename, overwrite = args.overwrite, \
                write_raw_buffers = args.dumprawbuffers, write_binary_gltf = args.textformat)
    else:
        tom_files = glob.glob('*.TOMDL*')
        tom_file = input("which DLB file?  [input number e.g. type 3975 for 00003975] ")
        if int(tom_file) > 1:
            dlb_file_match = [x for x in tom_files if '{0:08d}'.format(int(tom_file)) in x]
            dlp_file_match = [x for x in tom_files if '{0:08d}'.format(int(tom_file)+1) in x]
            if len(dlb_file_match) > 0 and len(dlp_file_match) > 0:
                process_dlb(dlb_file_match[0], dlp_file_match[0])