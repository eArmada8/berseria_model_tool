# Tool to export model data from the dlb/dlp format used by Tales of Berseria.
#
# Usage:  Run by itself without commandline arguments and it will search for non-skeletal
# TOMDLB_D/TOMDLP_P files and export raw meshes for modding as well as a .gib file for
# weight-painting and texture preview.  It will do its best to find the matching skeleton file.
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

# Configuration variable
# True to enable combining models (requires a compatible skeleton, no commandline arguments)
combine_models_into_single_gltf = True

# Global variable, do not edit
addr_size = 8
e = '<'

def set_address_size (size):
    global addr_size
    if size in [4,8]:
        addr_size = size
    return

def set_endianness (endianness):
    global e
    if endianness in ['<', '>']:
        e = endianness
    return

def read_offset (f):
    start_offset = f.tell()
    diff_offset, = struct.unpack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), f.read(addr_size))
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
    split_lists = [[]]
    # Split ib_list by primitive restart command, some models have this
    for i in range(len(ib_list)):
        if not ib_list[i] == -1:
            split_lists[-1].append(ib_list[i])
        else:
            split_lists.append([])
    for i in range(len(split_lists)):
        for j in range(len(split_lists[i])-2):
            if j % 2 == 0:
                triangles.append([split_lists[i][j], split_lists[i][j+1], split_lists[i][j+2]])
            else:
                triangles.append([split_lists[i][j], split_lists[i][j+2], split_lists[i][j+1]]) #DirectX implementation
                #triangles.append([split_lists[i][j+1], split_lists[i][j], split_lists[i][j+2]]) #OpenGL implementation
    # Remove degenerate triangles
    triangles = [x for x in triangles if len(set(x)) == 3]
    return(triangles)

def read_opening_dict (f):
    dict_offset = read_offset(f)
    dict_size, = struct.unpack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), f.read(addr_size))
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
    section_0_header = struct.unpack("{}3I6H".format(e), f.read(24))
    section_0_toc = []
    for _ in range(8):
        offset = read_offset(f)
        num_entries, = struct.unpack("{}{}".format(e,{4: "I", 8: "Q"}[addr_size]), f.read(addr_size))
        section_0_toc.append({'offset': offset, 'num_entries': num_entries})
    unk_block = list(struct.unpack("{}2{}".format(e,{4: "I", 8: "Q"}[addr_size]), f.read(addr_size * 2)))
    unk_block.extend(struct.unpack("{}4Hf2i5f".format(e), f.read(40)))
    f.seek(section_0_toc[0]['offset'])
    id = struct.unpack("{}{}I".format(e, section_0_toc[0]['num_entries']), f.read(section_0_toc[0]['num_entries']*4))
    f.seek(section_0_toc[1]['offset'])
    true_parent = struct.unpack("{}{}i".format(e, section_0_toc[1]['num_entries']), f.read(section_0_toc[1]['num_entries']*4))
    f.seek(section_0_toc[2]['offset'])
    tree_info = [struct.unpack("{}4h".format(e), f.read(8)) for _ in range(section_0_toc[2]['num_entries'])]
    f.seek(section_0_toc[3]['offset'])
    name = [read_string(f, read_offset(f)) for _ in range(section_0_toc[3]['num_entries'])]
    f.seek(section_0_toc[4]['offset'])
    unk_matrix = [[struct.unpack("{}16f".format(e), f.read(64)) for _ in range(2)] for _ in range(section_0_toc[4]['num_entries'])]
    f.seek(section_0_toc[5]['offset'])
    abs_matrix = [struct.unpack("{}16f".format(e), f.read(64)) for _ in range(section_0_toc[5]['num_entries'])]
    f.seek(section_0_toc[6]['offset'])
    inv_matrix = [struct.unpack("{}16f".format(e), f.read(64)) for _ in range(section_0_toc[6]['num_entries'])]
    f.seek(section_0_toc[7]['offset'])
    parent_list = struct.unpack("{}{}h".format(e, section_0_toc[7]['num_entries']), f.read(section_0_toc[7]['num_entries']*2))
    raw_data = [section_0_header, unk_block, id, true_parent, tree_info, name, unk_matrix, abs_matrix, inv_matrix, parent_list]
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
    return(skel_struct, raw_data)

def read_dlb_skeleton (dlb_file):
    current_addr_size = addr_size # Store original size so we can restore it at the end
    current_endian = e
    skel_list = []
    with open(dlb_file, 'rb') as f:
        magic = f.read(4)
        if magic in [b'DPDF', b'FDPD']:
            set_endianness({b'DPDF': '<', b'FDPD': '>'}[magic])
            unk_int, = struct.unpack("{}I".format(e), f.read(4))
            set_address_size(8)
            if not unk_int == 0:
                set_address_size(4) # Cannot assume that the skeleton is the same!
            f.seek({4: 4, 8: 16}[addr_size],1)
            magic = f.read(4)
            if magic in [b'BLDM', b'MDLB']:
                f.seek(4,1)
                offset = read_offset(f)
                f.seek(offset) # Jump to section 0
                f.seek(0x18,1)
                offset = read_offset(f)
                num_entries, = struct.unpack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), f.read(addr_size))
                f.seek(offset)
                skel_list.extend(list(struct.unpack("{}{}I".format(e, num_entries), f.read(num_entries * 4))))
    set_address_size(current_addr_size) # Restore original address size
    set_endianness(current_endian) # Restore original endianness
    return(skel_list)

def find_primary_skeleton (missing_bone_palette_ids):
    print("Searching all dlb files for primary skeleton in current folder.")
    dlb_files = glob.glob('*.TOMDLB_D')
    if len(dlb_files) > 10:
        print("This may take a long time...")
    palettes = {}
    for i in range(len(dlb_files)):
        palettes[dlb_files[i]] = read_dlb_skeleton(dlb_files[i])
    matches = [x for x in dlb_files if all([y in palettes[x] for y in missing_bone_palette_ids])]
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
    elif len(matches) == 1:
        match = matches[0]
    if match == '':
        print("No matches found!")
    else:
        print("Using {} as primary skeleton.".format(match))
    return match

# skel_struct will be appended onto the skeleton_file struct, not the other way around
def combine_skeletons (skeleton_file, skel_struct):
    current_addr_size = addr_size # Store original size so we can restore it at the end
    current_endian = e
    with open(skeleton_file, 'rb') as f:
        magic = f.read(4)
        if magic in [b'DPDF', b'FDPD']:
            set_endianness({b'DPDF': '<', b'FDPD': '>'}[magic])
            unk_int, = struct.unpack("{}I".format(e), f.read(4))
            set_address_size(8)
            if not unk_int == 0:
                set_address_size(4) # Cannot assume that the skeleton is the same!
            f.seek({4: 4, 8: 16}[addr_size],1)
            magic = f.read(4)
            if magic in [b'BLDM', b'MDLB']:
                f.seek(4,1)
                offset = read_offset(f)
                primary_skel_struct, _ = read_section_0(f, offset)
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
                set_address_size(current_addr_size) # Restore original address size
                set_endianness(current_endian) # Restore original endianness
                return(new_skel_struct)
            else:
                print("Invalid skeleton file!")
                set_address_size(current_addr_size) # Restore original address size
                set_endianness(current_endian) # Restore original endianness
                return skel_struct
        else:
            print("Invalid skeleton file!")
            set_address_size(current_addr_size) # Restore original address size
            set_endianness(current_endian) # Restore original endianness
            return skel_struct

def find_and_add_external_skeleton (skel_struct, bone_palette_ids):
    #Sanity check, if the skeleton is already complete then skip the search
    if not all([y in [x['id'] for x in skel_struct] for y in bone_palette_ids]):
        missing_bone_palette_ids = [y for y in bone_palette_ids if not y in [x['id'] for x in skel_struct]]
        primary_skeleton_file = find_primary_skeleton (missing_bone_palette_ids)
        if os.path.exists(primary_skeleton_file):
            return(combine_skeletons (primary_skeleton_file, skel_struct))
        else:
            return([])
    else:
        return(skel_struct)

def make_fmt(num_uvs, semantics_present = {'NORMAL': True, 'TANGENT': False, 'BINORMAL': False,
        'COLOR': False, 'BLENDWEIGHTS': True, 'BLENDINDICES': True}):
    fmt = {'stride': '0', 'topology': 'trianglelist', 'format':\
        "DXGI_FORMAT_R16_UINT", 'elements': []}
    element_id, stride = 0, 0
    semantic_index = {'TEXCOORD': 0} # Counters for multiple indicies
    elements = []
    for i in range(7 + num_uvs):
            # I think order matters in this dict, so we will define the entire structure with default values
            element = {'id': '{0}'.format(element_id), 'SemanticName': '', 'SemanticIndex': '0',\
                'Format': '', 'InputSlot': '0', 'AlignedByteOffset': str(stride),\
                'InputSlotClass': 'per-vertex', 'InstanceDataStepRate': '0'}
            semantic_present = False
            if i == 0:
                element['SemanticName'] = 'POSITION'
                element['Format'] = 'R32G32B32_FLOAT'
                element_id += 1
                stride += 12
                semantic_present = True
            elif i == 1 and semantics_present['NORMAL']:
                element['SemanticName'] = 'NORMAL'
                element['Format'] = 'R32G32B32_FLOAT'
                element_id += 1
                stride += 12
                semantic_present = True
            elif i == 2 and semantics_present['TANGENT']:
                element['SemanticName'] = 'TANGENT'
                element['Format'] = 'R32G32B32_FLOAT'
                element_id += 1
                stride += 12
                semantic_present = True
            elif i == 3 and semantics_present['BINORMAL']:
                element['SemanticName'] = 'BINORMAL'
                element['Format'] = 'R32G32B32_FLOAT'
                element_id += 1
                stride += 12
                semantic_present = True
            elif i == 4 and semantics_present['COLOR']:
                element['SemanticName'] = 'COLOR'
                element['Format'] = 'R8G8B8A8_UNORM'
                element_id += 1
                stride += 4
                semantic_present = True
            elif i == 7+num_uvs-2 and semantics_present['BLENDWEIGHTS']:
                element['SemanticName'] = 'BLENDWEIGHTS'
                element['Format'] = 'R32G32B32A32_FLOAT'
                element_id += 1
                stride += 16
                semantic_present = True
            elif i == 7+num_uvs-1 and semantics_present['BLENDINDICES']:
                element['SemanticName'] = 'BLENDINDICES'
                element['Format'] = 'R8G8B8A8_UINT'
                element_id += 1
                stride += 4
                semantic_present = True
            elif i > 4 and i < (5 + num_uvs):
                element['SemanticName'] = 'TEXCOORD'
                element['SemanticIndex'] = str(semantic_index['TEXCOORD'])
                element['Format'] = 'R32G32_FLOAT'
                semantic_index['TEXCOORD'] += 1
                element_id += 1
                stride += 8
                semantic_present = True
            if semantic_present == True:
                elements.append(element)
    fmt['stride'] = str(stride)
    fmt['elements'] = elements
    return(fmt)

def read_mesh (main_f, idx_f, start_offset, flags):
    def read_floats (f, num):
        return(list(struct.unpack("{}{}f".format(e, num), f.read(num * 4))))
    def read_bytes (f, num):
        return(list(struct.unpack("{}{}B".format(e, num), f.read(num))))
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
    def read_interleaved_ufloats (f, num, stride, total): # Unsigned normalized byte floats
        vecs = []
        padding = stride - (num)
        float_max = ((2**8)-1)
        for i in range(total):
            vals = read_bytes(f, num)
            vecs.append([x / float_max for x in vals])
            f.seek(padding, 1)
        return(vecs)
    def fix_weights (weights):
        for _ in range(3):
            weights = [x+[round(1-sum(x),6)] if len(x) < 4 else x for x in weights]
        return(weights)
    main_f.seek(start_offset)
    num_verts, num_idx, offset_uvs, offset_idx = struct.unpack("{}2H2I".format(e), main_f.read(12))
    uv_stride = (offset_idx - offset_uvs) // num_verts
    num_uv_maps = flags & 0xF
    #num_uv_maps = (uv_stride - 4) // 8 # 4 byte buffer + VEC2 per map
    verts = []
    norms = []
    if flags & 0xF0 == 0x50:
        blend_idx = []
        weights = []
        num_v_per_wt_grp = list(struct.unpack("{}4I".format(e), main_f.read(16)))
        if sum(num_v_per_wt_grp) == num_verts:
            num_vertices_array = [num_v_per_wt_grp]
        else: # Some builds have arrays of arrays, might be a PS3 thing
            main_f.seek(-16,1)
            num_vertices_array = [[]]
            count, = struct.unpack("{}I".format(e), main_f.read(4))
            for i in range(count):
                num_vertices_array.append(list(struct.unpack("{}4H".format(e), main_f.read(8))))
        for i in range(len(num_vertices_array)):
            for j in range(len(num_vertices_array[i])):
                vert_offset = main_f.tell()
                norm_offset = vert_offset + 12
                blend_idx_offset = norm_offset + 12
                weights_offset = blend_idx_offset + 4
                stride = 28 + (j * 4)
                end_offset = main_f.tell() + (num_vertices_array[i][j] * stride)
                main_f.seek(vert_offset)
                verts.extend(read_interleaved_floats(main_f, 3, stride, num_vertices_array[i][j]))
                main_f.seek(norm_offset)
                norms.extend(read_interleaved_floats(main_f, 3, stride, num_vertices_array[i][j]))
                main_f.seek(blend_idx_offset)
                blend_idx.extend(read_interleaved_bytes(main_f, 4, stride, num_vertices_array[i][j]))
                if j > 0:
                    main_f.seek(weights_offset)
                    weights.extend(read_interleaved_floats(main_f, j, stride, num_vertices_array[i][j]))
                else:
                    weights.extend([[1.0] for _ in range(num_vertices_array[i][j])])
                main_f.seek(end_offset)
        weights = fix_weights(weights)
    elif flags & 0xF0 == 0x70:
        num_unk = struct.unpack("{}2H".format(e), main_f.read(4)) # Dunno what this is, maybe shape morphs?
        unk_list = list(struct.unpack("{}{}I".format(e, num_unk[0]), main_f.read(4 * num_unk[0])))
        vert_offset = main_f.tell()
        norm_offset = vert_offset + 12
        stride = 24
        end_offset = main_f.tell() + (num_verts * stride)
        main_f.seek(vert_offset)
        verts.extend(read_interleaved_floats(main_f, 3, stride, num_verts))
        main_f.seek(norm_offset)
        norms.extend(read_interleaved_floats(main_f, 3, stride, num_verts))
        main_f.seek(end_offset) # More data after this
    elif flags & 0xF0 in [0x0, 0x40]:
        vert_offset = idx_f.seek(offset_uvs)
        norm_offset = vert_offset + 12
        stride = 28 + ((flags & 0xF) * 8) # 12 + 12 + 4 extra for UV padding
        idx_f.seek(vert_offset)
        verts.extend(read_interleaved_floats(idx_f, 3, stride, num_verts))
        idx_f.seek(norm_offset)
        norms.extend(read_interleaved_floats(idx_f, 3, stride, num_verts))
    elif flags & 0xF0 == 0xC0:
        tangents = []
        binormals = []
        colors = []
        vert_offset = idx_f.seek(offset_uvs)
        norm_offset = vert_offset + 12
        tan_offset = norm_offset + 12
        binorm_offset = tan_offset + 12
        color_offset = binorm_offset + 12
        stride = 52 + ((flags & 0xF) * 8) # 12 + 12 + 4 extra for UV padding
        idx_f.seek(vert_offset)
        verts.extend(read_interleaved_floats(idx_f, 3, stride, num_verts))
        idx_f.seek(norm_offset)
        norms.extend(read_interleaved_floats(idx_f, 3, stride, num_verts))
        idx_f.seek(tan_offset)
        tangents.extend(read_interleaved_floats(idx_f, 3, stride, num_verts))
        idx_f.seek(binorm_offset)
        binormals.extend(read_interleaved_floats(idx_f, 3, stride, num_verts))
        idx_f.seek(color_offset)
        colors.extend(read_interleaved_ufloats(idx_f, 4, stride, num_verts))
    uv_maps = []
    if flags & 0xF0 in [0x50, 0x70]:
        for i in range(num_uv_maps):
            idx_f.seek(offset_uvs + 4 + (i * 8))
            uv_maps.append(read_interleaved_floats (idx_f, 2, uv_stride, num_verts))
    elif flags & 0xF0 in [0x0, 0x40]:
        for i in range(num_uv_maps):
            idx_f.seek(offset_uvs + 28 + (i * 8))
            uv_maps.append(read_interleaved_floats (idx_f, 2, stride, num_verts))
    idx_f.seek(offset_idx)
    idx_buffer = list(struct.unpack("{}{}h".format(e, num_idx), idx_f.read(num_idx * 2)))
    if not flags & 0xF0 in [0xC0]:
        fmt = make_fmt(len(uv_maps))
    elif flags & 0xF0 == 0xC0:
        fmt = make_fmt(len(uv_maps), semantics_present = {'NORMAL': True, 'TANGENT': True, 'BINORMAL': True,
            'COLOR': True, 'BLENDWEIGHTS': True, 'BLENDINDICES': True})
    vb = [{'Buffer': verts}, {'Buffer': norms}]
    if flags & 0xF0 == 0xC0:
        vb.append({'Buffer': tangents})
        vb.append({'Buffer': binormals})
        vb.append({'Buffer': colors})
    for uv_map in uv_maps:
        vb.append({'Buffer': uv_map})
    if flags & 0xF0 == 0x50:
        vb.append({'Buffer': weights})
        vb.append({'Buffer': blend_idx})
    elif flags & 0xF0 in [0x0, 0x40, 0x70, 0xC0]:
        vb.append({'Buffer': [[1.0, 0.0, 0.0, 0.0] for _ in range(len(verts))]})
        vb.append({'Buffer': [[0, 0, 0, 0] for _ in range(len(verts))]})
    return({'fmt': fmt, 'vb': vb, 'ib': trianglestrip_to_list(idx_buffer)})

#This function is purely for flipping endianness
def read_generic_int_section (f, offset, length):
    f.seek(offset)
    return(list(struct.unpack("{}{}I".format(e, length // 4), f.read(length))))

#Dunno, offset should be toc[4].
def read_section_4 (f, offset):
    f.seek(offset)
    section_4_unk = struct.unpack("{}2I".format(e), f.read(8))
    counts = struct.unpack("{}2H".format(e), f.read(4))
    if addr_size == 8:
        f.seek(4,1) # Padding
    offset = read_offset(f)
    count, = struct.unpack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), f.read(addr_size))
    data = [list(struct.unpack("{}4h25f".format(e), f.read(0x6c))) for _ in range(count)]
    return(data)

#Dunno, offset should be toc[5].
def read_section_5 (f, offset):
    f.seek(offset)
    offset1 = read_offset(f)
    count1, = struct.unpack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), f.read(addr_size))
    offset2 = read_offset(f)
    count2, = struct.unpack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), f.read(addr_size))
    data1 = [list(struct.unpack("{}I6f2I".format(e), f.read(36))) for _ in range(count1)]
    data2 = [list(struct.unpack("{}9f".format(e), f.read(36))) for _ in range(count2)]
    return([data1, data2])

#Meshes, offset should be toc[6].  Requires dlp filename for uv's and index buffer.
def read_section_6 (f, offset, dlp_file):
    f.seek(offset)
    section_6_unk = struct.unpack("{}4I".format(e), f.read(16))
    section_6_toc = []
    for _ in range(4):
        offset = read_offset(f)
        num_entries, = struct.unpack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), f.read(addr_size))
        section_6_toc.append({'offset': offset, 'num_entries': num_entries})
    #section_6_toc[0] - VEC4 (u32, f32?) - in sample is all zeroes
    #section_6_toc[1] - meshes
    #section_6_toc[2] - bone palette
    #section_6_toc[3] - u32 x 2 - # meshes, # bones
    f.seek(section_6_toc[2]['offset'])
    bone_palette_ids = struct.unpack("{}{}I".format(e, section_6_toc[2]['num_entries']), f.read(4 * section_6_toc[2]['num_entries']))
    mesh_blocks_info = []
    meshes = []
    f.seek(section_6_toc[1]['offset'])
    with open (dlp_file, 'rb') as idx_f:
        for i in range(section_6_toc[1]['num_entries']):
            data = {'current_block_offset': f.tell(), 'name': ''}
            data["mesh"], data["submesh"], data["node"], \
                data["flags"], data["material"], data["unknown"] = struct.unpack("{}i4hi".format(e), f.read(16))
            data['string_offset'] = read_offset(f)
            data['data_offset'] = read_offset(f)
            data["data_block_size"], = struct.unpack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), f.read(addr_size))
            current_offset = f.tell()
            data["name"] = read_string (f, data['string_offset'])
            meshes.append(read_mesh (f, idx_f, data['data_offset'], data["flags"]))
            mesh_blocks_info.append(data)
            f.seek(current_offset)
    return(meshes, bone_palette_ids, mesh_blocks_info)

#Materials, offset should be toc[7]
def read_section_7 (f, offset):
    f.seek(offset)
    section_7_unk = struct.unpack("{}6I".format(e), f.read(24))
    section_7_toc = []
    for _ in range(7):
        offset = read_offset(f)
        num_entries, = struct.unpack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), f.read(addr_size))
        section_7_toc.append({'offset': offset, 'num_entries': num_entries})
    set_0 = [] # Materials, including the indices that map to set_1 (textures)
    for i in range(section_7_toc[0]['num_entries']):
        f.seek(section_7_toc[0]['offset'] + (i * (4 * addr_size + 0x18)))
        values = struct.unpack("{}12h".format(e), f.read(24))
        offset1 = read_offset(f)
        num_vals1, = struct.unpack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), f.read(addr_size))
        offset2 = read_offset(f)
        num_vals2, = struct.unpack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), f.read(addr_size))
        end_offset = f.tell()
        f.seek(offset1)
        vals1 = struct.unpack("{}{}I".format(e, num_vals1), f.read(num_vals1 * 4))
        f.seek(offset2)
        if num_vals2 == 0x17:
            vals2 = struct.unpack("{}8I4f4If6I".format(e), f.read(92))
        else:
            vals2 = struct.unpack("{}{}I".format(e, num_vals2), f.read(num_vals2 * 4))
        set_0.append({'base': values, 'vals1': vals1, 'vals2': vals2})
    set_1 = [] # Texture assignments, each is a tuple where the second number points to set_6
    for i in range(section_7_toc[1]['num_entries']):
        f.seek(section_7_toc[1]['offset'] + (i * 6))
        values = struct.unpack("{}3h".format(e), f.read(6))
        set_1.append(values)
    set_2 = [] # Materials, including material names and alpha
    for i in range(section_7_toc[2]['num_entries']):
        f.seek(section_7_toc[2]['offset'] + (i * (5 * addr_size)))
        offset1 = read_offset(f)
        num_vals1, = struct.unpack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), f.read(addr_size))
        offset2 = read_offset(f)
        num_vals2, = struct.unpack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), f.read(addr_size))
        str_offset = read_offset(f)
        f.seek(offset1)
        vals1 = struct.unpack("{}{}I".format(e, num_vals1), f.read(num_vals1 * 4))
        f.seek(offset2)
        vals2 = struct.unpack("{}{}I".format(e, num_vals2), f.read(num_vals2 * 4))
        name = read_string(f, str_offset)
        set_2.append({'name': name, 'vals1': vals1, 'vals2': vals2})
    set_6 = [] # Texture names
    for i in range(section_7_toc[6]['num_entries']):
        if addr_size == 8:
            f.seek(section_7_toc[6]['offset'] + (i * 24))
            str_offset = read_offset(f)
            vals = struct.unpack("{}2Q".format(e), f.read(16))
        else:
            f.seek(section_7_toc[6]['offset'] + (i * 8))
            str_offset = read_offset(f)
            vals = struct.unpack("{}2H".format(e), f.read(4))
        tex_name = read_string(f, str_offset)
        set_6.append({'tex_name': tex_name, 'vals': vals})
    material_struct = []
    if len(set_0) == len(set_2):
        for i in range(len(set_0)):
            material = {'name': set_2[i]['name']}
            material['textures'] = [set_6[set_1[set_0[i]['base'][6]+j][1]]['tex_name'] for j in range(set_0[i]['base'][4])]
            material['alpha'] = set_2[i]['vals2'][3] if len(set_2[i]['vals2']) > 3 else -1 # Unsigned so never -1
            material['internal_id'] = set_0[i]['base'][0]
            material['unk_parameters'] = {'set_0_base': [set_0[i]['base'][1:4], [set_0[i]['base'][5]], set_0[i]['base'][7:]],
                'set_0_unk_0': set_0[i]['vals1'], 'set_0_unk_1': set_0[i]['vals2'], 'set_2_unk_0': set_2[i]['vals1'],
                'set_2_unk_1': [set_2[i]['vals2'][0:3], set_2[i]['vals2'][4:]]}
            # Some materials have very short set_2, remove extraneous empty values so import script will not add extra values
            if material['alpha'] == -1:
                del(material['alpha'])
            if len(material['unk_parameters']['set_2_unk_1'][1]) == 0:
                material['unk_parameters']['set_2_unk_1'].pop(1)
            material_struct.append(material)
    return(material_struct)

#Something to do with animation, offset should be toc[11]. By default the data is not decoded (unneeded).
def read_section_11 (f, offset, decode_data = False):
    def decode_target_flag (flag):
        return({'type': flag & 0xFFFFFFFF, 'target': flag >> 32 & 0xFFFF, 'unknown': flag >> 48})
    def decode_block_11 (data1, data2):
        decoded = [decode_target_flag(x) for x in data1]
        count = 0
        for i in range(len(decoded)):
            vec_len = decoded[i]['type'] & 0x7
            decoded[i]['vector'] = []
            for _ in range(vec_len):
                decoded[i]['vector'].append(data2[count])
                count += 1
            decoded[i]
        return(decoded)
    f.seek(offset)
    offset1 = read_offset(f)
    count1, = struct.unpack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), f.read(addr_size))
    offset2 = read_offset(f)
    count2, = struct.unpack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), f.read(addr_size))
    f.seek(offset1) # Skip 0x10 zero bytes for 8-byte addressing, 0x0c zero bytes for 4-byte - maybe a blank address?
    # data1 does not look like u64, except when looking at endianness, dunno why
    data1 = [struct.unpack("{}Q".format(e), f.read(8))[0] for _ in range(count1)]
    data2 = [struct.unpack("{}f".format(e), f.read(4))[0] for _ in range(count2)]
    if decode_data == True:
        return(decode_block_11(data1, data2))
    else:
        return([data1, data2])

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

def write_gltf(base_name, skel_struct, vgmaps, mesh_blocks_info, meshes, material_struct,\
        overwrite = False, write_binary_gltf = True):
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
    material_dict = [{'name': material_struct[i]['name'],
        'texture': material_struct[i]['textures'][0] if len(material_struct[i]['textures']) > 0 else '',
        'alpha': material_struct[i]['alpha'] if 'alpha' in material_struct[i] else 0}
        for i in range(len(material_struct))]
    texture_list = sorted(list(set([x['texture'] for x in material_dict if not x['texture'] == ''])))
    gltf_data['images'] = [{'uri':'textures/{}.dds'.format(x)} for x in texture_list]
    for mat in material_dict:
        material = { 'name': mat['name'] }
        material['pbrMetallicRoughness'] = { 'metallicFactor' : 0.0, 'roughnessFactor' : 1.0 }
        if not mat['texture'] == '':
            sampler = { 'wrapS': 10497, 'wrapT': 10497 } # I have no idea if this setting exists
            texture = { 'source': texture_list.index(mat['texture']), 'sampler': len(gltf_data['samplers']) }
            material['pbrMetallicRoughness']['baseColorTexture'] = { 'index' : len(gltf_data['textures']), }
            gltf_data['samplers'].append(sampler)
            gltf_data['textures'].append(texture)
        if mat['alpha'] & 1:
            material['alphaMode'] = 'MASK'
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
        if len(gltf_data['nodes'][i]['children']) == 0 and i > 0:
            del(gltf_data['nodes'][i]['children'])
    if len(gltf_data['nodes']) == 0:
        gltf_data['nodes'].append({'children': [], 'name': 'root'})
    # Mesh nodes will be attached to the first node since in the original model, they don't really have a home
    node_id_list = [x['id'] for x in skel_struct]
    for i in range(len(mesh_blocks_info)):
        mesh_blocks_info[i]['mesh_v'] = '{0}_{1:02d}'.format(mesh_blocks_info[i]['mesh'], mesh_blocks_info[i]['vgmap'])
    mesh_node_ids = {x['mesh_v']:x['name'] for x in mesh_blocks_info}
    if not 'children' in gltf_data['nodes'][0]:
        gltf_data['nodes'][0]['children'] = []
    for mesh_node_id in mesh_node_ids:
        if not mesh_node_id in node_id_list:
            g_node = {'name': mesh_node_ids[mesh_node_id]}
            gltf_data['nodes'][0]['children'].append(len(gltf_data['nodes']))
            gltf_data['nodes'].append(g_node)
    mesh_block_tree = {x:[i for i in range(len(mesh_blocks_info)) if mesh_blocks_info[i]['mesh_v'] == x] for x in mesh_node_ids}
    node_list = [x['name'] for x in gltf_data['nodes']]
    # Skin matrices
    skinning_possible = True
    try:
        ibms_struct = []
        inv_mtx_buffers = []
        for vgmap in vgmaps:
            vgmap_nodes = [node_list.index(x) for x in list(vgmap.keys())]
            ibms = [skel_struct[j]['inv_matrix'] for j in vgmap_nodes]
            inv_mtx_buffer = b''.join([struct.pack("<16f", *x) for x in ibms])
            ibms_struct.append(ibms)
            inv_mtx_buffers.append(inv_mtx_buffer)
    except ValueError:
        skinning_possible = False
    # Meshes
    for mesh in mesh_block_tree: #Mesh
        primitives = []
        for j in range(len(mesh_block_tree[mesh])): #Submesh
            i = mesh_block_tree[mesh][j]
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
            primitives.append(primitive)
        if len(primitives) > 0:
            if mesh_node_ids[mesh] in node_list: # One of the new nodes
                node_id = node_list.index(mesh_node_ids[mesh])
            else: # One of the pre-assigned nodes
                node_id = node_id_list.index(mesh_blocks_info[i]["mesh_v"])
            gltf_data['nodes'][node_id]['mesh'] = len(gltf_data['meshes'])
            gltf_data['meshes'].append({"primitives": primitives, "name": mesh_node_ids[mesh]})
            # Skinning
            if len(vgmaps[mesh_blocks_info[i]["vgmap"]]) > 0 and skinning_possible == True:
                gltf_data['nodes'][node_id]['skin'] = len(gltf_data['skins'])
                gltf_data['skins'].append({"inverseBindMatrices": len(gltf_data['accessors']),\
                    "joints": [node_list.index(x) for x in vgmaps[mesh_blocks_info[i]["vgmap"]]]})
                gltf_data['accessors'].append({"bufferView" : len(gltf_data['bufferViews']),\
                    "componentType": 5126,\
                    "count": len(ibms_struct[mesh_blocks_info[i]["vgmap"]]),\
                    "type": "MAT4"})
                gltf_data['bufferViews'].append({"buffer": 0,\
                    "byteOffset": len(giant_buffer),\
                    "byteLength": len(inv_mtx_buffers[mesh_blocks_info[i]["vgmap"]])})
                giant_buffer += inv_mtx_buffers[mesh_blocks_info[i]["vgmap"]]
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

def process_dlb (dlb_file, overwrite = False, write_raw_buffers = True, write_binary_gltf = True):
    print("Processing {}...".format(dlb_file))
    base_name = dlb_file.split('.TOMDLB_D')[0]
    with open(dlb_file, 'rb') as f:
        magic = f.read(4)
        if magic in [b'DPDF', b'FDPD']:
            if magic == b'FDPD':
                set_endianness('>')
            unk_int, = struct.unpack("{}I".format(e), f.read(4))
            if not unk_int == 0:
                f.seek(4,0)
                set_address_size(4) # Zestiria
            opening_dict = read_opening_dict (f)
            dlp_file = opening_dict[0]
            magic = f.read(4)
            if magic in [b'BLDM', b'MDLB']:
                unk_int2, = struct.unpack("{}I".format(e), f.read(4))
                toc = [read_offset(f) for _ in range(12)]
                #toc[0] - Nodes.  1 - (mesh) 0x16c, 0x82, mostly zeros (6x zero len sections) (skel) 0x10 header, 6 sections.  2 - 16 zero bytes, 3 - 0x16c, 0x82, mostly zeros.  
                #4 - starts with 0x16c, 0x82, lots of floats.
                #5 - offset1, count1, offset2, count2, 0x24 * count1 (u32, f32 *6, u32 *2), 0x24 * count2 (all f)
                #6 - meshes.  7 - materials.  8,9,10,11 - dunno
                if os.path.exists(dlp_file) or os.path.exists(dlp_file.upper()): # TLTool uses uppercase extension
                    skel_struct, _ = read_section_0(f, toc[0])
                    meshes, bone_palette_ids, mesh_blocks_info = read_section_6(f, toc[6], dlp_file)
                    # Attempt to incorporate an external skeleton (skipped if skeleton already complete)
                    skel_struct = find_and_add_external_skeleton (skel_struct, bone_palette_ids)
                    vgmap = {'bone_{}'.format(bone_palette_ids[i]):i for i in range(len(bone_palette_ids))}
                    if all([y in [x['id'] for x in skel_struct] for y in bone_palette_ids]):
                        skel_index = {skel_struct[i]['id']:i for i in range(len(skel_struct))}
                        vgmap = {skel_struct[skel_index[bone_palette_ids[i]]]['name']:i for i in range(len(bone_palette_ids))}
                    for i in range(len(mesh_blocks_info)):
                        mesh_blocks_info[i]['vgmap'] = 0
                    material_struct = read_section_7(f, toc[7])
                    gltf_overwrite = copy.deepcopy(overwrite)
                    if write_raw_buffers == True:
                        if os.path.exists(base_name) and (os.path.isdir(base_name)) and (overwrite == False):
                            if str(input(base_name + " folder exists! Overwrite? (y/N) ")).lower()[0:1] == 'y':
                                overwrite = True
                        if (overwrite == True) or not os.path.exists(base_name):
                            if not os.path.exists(base_name):
                                os.mkdir(base_name)
                            for i in range(len(meshes)):
                                filename = '{0:02d}_{1}'.format(i, mesh_blocks_info[i]['name'])
                                write_fmt(meshes[i]['fmt'], '{0}/{1}.fmt'.format(base_name, filename))
                                write_ib(meshes[i]['ib'], '{0}/{1}.ib'.format(base_name, filename), meshes[i]['fmt'], '<')
                                write_vb(meshes[i]['vb'], '{0}/{1}.vb'.format(base_name, filename), meshes[i]['fmt'], '<')
                                open('{0}/{1}.vgmap'.format(base_name, filename), 'wb').write(json.dumps(vgmap,indent=4).encode())
                            mesh_struct = [{y:x[y] for y in x if not any(
                                ['offset' in y, 'num' in y])} for x in mesh_blocks_info]
                            for i in range(len(mesh_struct)):
                                mesh_struct[i]['material'] = material_struct[mesh_struct[i]['material']]['name']
                            mesh_struct = [{'id_referenceonly': i, **mesh_struct[i]} for i in range(len(mesh_struct))]
                            write_struct_to_json(mesh_struct, base_name + '/mesh_info')
                            write_struct_to_json(material_struct, base_name + '/material_info')
                            write_struct_to_json(opening_dict, base_name + '/linked_files')
                            #write_struct_to_json(skel_struct, base_name + '/skeleton_info')
                    if combine_models_into_single_gltf == False:
                        write_gltf(base_name, skel_struct, [vgmap], mesh_blocks_info, meshes, material_struct,\
                            overwrite = gltf_overwrite, write_binary_gltf = write_binary_gltf)
                else:
                    print("Skipping {0} as {1} not present...".format(dlb_file, dlp_file))
    return

def process_dlbs_combined (dlb_files, overwrite = False, write_binary_gltf = True):
    skel_struct, meshes, bone_palettes, vgmaps, mesh_blocks_info, material_struct, tex_data = [], [], [], [], [], [], []
    gltf_overwrite = copy.deepcopy(overwrite)
    base_name_dict = {}
    for i in range(len(dlb_files)):
        with open(dlb_files[i], 'rb') as f:
            magic = f.read(4)
            if magic in [b'DPDF', b'FDPD']:
                if magic == b'FDPD':
                    set_endianness('>')
                unk_int, = struct.unpack("{}I".format(e), f.read(4))
                if not unk_int == 0:
                    f.seek(4,0)
                    set_address_size(4) # Zestiria
                opening_dict = read_opening_dict (f)
                dlp_file = opening_dict[0]
                magic = f.read(4)
                if magic in [b'BLDM', b'MDLB']:
                    unk_int2, = struct.unpack("{}I".format(e), f.read(4))
                    toc = [read_offset(f) for _ in range(12)]
                    new_skel_struct, _ = read_section_0(f, toc[0])
                    # Prevent addition of repeated bones - although in my experiments probably not necessary
                    unique_skel = [x for x in new_skel_struct if not x['id'] in [y['id'] for y in skel_struct]]
                    skel_struct.extend(unique_skel) # At this point the children lists are garbage
    for i in range(len(dlb_files)):
        base_name = dlb_files[i].split('.TOMDLB_D')[0]
        with open(dlb_files[i], 'rb') as f:
            print("Processing {} for combined glTF...".format(dlb_files[i]))
            magic = f.read(4)
            if magic in [b'DPDF', b'FDPD']:
                if magic == b'FDPD':
                    set_endianness('>')
                unk_int, = struct.unpack("{}I".format(e), f.read(4))
                if not unk_int == 0:
                    f.seek(4,0)
                    set_address_size(4) # Zestiria
                opening_dict = read_opening_dict (f)
                dlp_file = opening_dict[0]
                magic = f.read(4)
                if magic in [b'BLDM', b'MDLB']:
                    unk_int2, = struct.unpack("{}I".format(e), f.read(4))
                    toc = [read_offset(f) for _ in range(12)]
                    if os.path.exists(dlp_file) or os.path.exists(dlp_file.upper()): # TLTool uses uppercase extension
                        meshes_i, bone_palette_ids_i, mesh_blocks_info_i = read_section_6(f, toc[6], dlp_file)
                        material_struct_i = read_section_7(f, toc[7])
                        base_name_dict[len(bone_palettes)] = base_name 
                        for i in range(len(mesh_blocks_info_i)):
                            mesh_blocks_info_i[i]['material'] = mesh_blocks_info_i[i]['material'] + len(material_struct)
                            mesh_blocks_info_i[i]['vgmap'] = len(bone_palettes)
                        bone_palettes.append(bone_palette_ids_i)
                        meshes.extend(meshes_i)
                        mesh_blocks_info.extend(mesh_blocks_info_i)
                        material_struct.extend(material_struct_i)
                    else:
                        print("Skipping {0} as {1} not present...".format(dlb_files[i], dlp_file))
    bone_palette_ids = list(set([x for y in bone_palettes for x in y]))
    skel_struct = find_and_add_external_skeleton (skel_struct, bone_palette_ids)
    for i in range(len(bone_palettes)):
        vgmap = {'bone_{}'.format(bone_palettes[i][j]):j for j in range(len(bone_palettes[i]))}
        if all([y in [x['id'] for x in skel_struct] for y in bone_palettes[i]]):
            skel_index = {skel_struct[j]['id']:j for j in range(len(skel_struct))}
            vgmap = {skel_struct[skel_index[bone_palettes[i][j]]]['name']:j for j in range(len(bone_palettes[i]))}
        vgmaps.append(vgmap)
    common_name = []
    for i in range(len(os.path.basename(dlb_files[0]))):
        if all([os.path.basename(x)[:i] == os.path.basename(dlb_files[0])[:i] for x in dlb_files]):
            common_name = os.path.basename(dlb_files[0])[:i]
        else:
            break
    if len(common_name) > 1:
        base_name = common_name[:-1] if common_name[-1] == '_' else common_name
    else:
        base_name = base_name + '_combined'
    write_gltf(base_name, skel_struct, vgmaps, mesh_blocks_info, meshes, material_struct,\
        overwrite = gltf_overwrite, write_binary_gltf = write_binary_gltf)
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
        parser.add_argument('-s', '--skiprawbuffers', help="Skip writing fmt/ib/vb/vgmap files in addition to glb", action="store_false")
        parser.add_argument('-o', '--overwrite', help="Overwrite existing files", action="store_true")
        parser.add_argument('dlb_filename', help="Name of dlb file to process.")
        args = parser.parse_args()
        if os.path.exists(args.dlb_filename) and args.dlb_filename[-5:] == 'DLB_D':
            process_dlb(args.dlb_filename, overwrite = args.overwrite, \
                write_raw_buffers = args.skiprawbuffers, write_binary_gltf = args.textformat)
    else:
        dlb_files = glob.glob('*.TOMDLB_D')
        # Remove external skeletons
        dlb_files = [x for x in dlb_files if not 'BONE' in x]
        for dlb_file in dlb_files:
            process_dlb(dlb_file)
        if combine_models_into_single_gltf == True:
            process_dlbs_combined (dlb_files)
