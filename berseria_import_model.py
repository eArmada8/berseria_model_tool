# Tool to import model data into the dlb/dlp format used by Tales of Berseria.
#
# Usage:  Run by itself without commandline arguments and it will replace
# only the mesh and material sections of every model it finds in the folder
# and replace them with fmt / ib / vb files in the same named directory.
#
# For command line options, run:
# /path/to/python3 berseria_import_model.py --help
#
# Requires pyffi_tstrip module and lib_fmtibvb.py, put in the same directory
#
# GitHub eArmada8/berseria_model_tool

try:
    import struct, json, io, shutil, glob, os, sys
    from lib_fmtibvb import *
    from berseria_export_model import *
    from pyffi_tstrip.tristrip import *
except ModuleNotFoundError as err:
    print("Python module missing! {}".format(err.msg))
    input("Press Enter to abort.")
    raise

# Global variables, do not edit
addr_size = 8
e = '<'

# Input is a list of bytes / bytearrays.
# Internal block is a first data block not in the table of contents, e.g. opening dict in BLDM
# Returns the block, as well as the offset of the internal block
def create_data_block (data_list, internal_block = bytearray(),
        address_size = 8, data_alignment = 1, block_alignment = 8):
    base_offset = address_size * len(data_list) + len(internal_block)
    data_offset = [0]
    for i in range(len(data_list)):
        if len(data_list[i]) % data_alignment:
            data_list[i] += b'\x00' * (data_alignment - (len(data_list[i]) % data_alignment))
    for i in range(len(data_list)-1):
        data_offset.append(len(data_list[i]) + data_offset[i])
    final_offset = [(base_offset + data_offset[i] - ((i)*address_size)) for i in range(len(data_list))]
    offset_block = struct.pack("{}{}{}".format(e, len(final_offset), {4:"I", 8:"Q"}[address_size]),
        *final_offset)
    data_block = b''.join(data_list)
    if len(data_block) % block_alignment:
        data_block += b'\x00' * (block_alignment - (len(data_block) % block_alignment))
    return ((offset_block + internal_block + data_block), len(offset_block))

def write_string_dict (strings_list):
    enc_strings = [bytearray(x.encode()) + b'\x00' for x in strings_list]
    return create_data_block(enc_strings, b'', addr_size, 2, addr_size) # Data alignment of 2 otherwise default

def read_skeleton_data (tomdlb_file, backup_skel_block):
    # Some values taken directly from the original block
    with io.BytesIO(backup_skel_block) as ff:
        local_skel_struct_backup, raw_skel_data_backup = read_section_0 (ff, 0)
        # Take original header and bounding sphere.  Some values on the original header will be replaced.
        raw_skel_data = raw_skel_data_backup[0:2]
    # Will read data from JSON file, or load original data from the mdl file if JSON is missing
    try:
        local_skel_struct = read_struct_from_json(tomdlb_file[:-9] + "/skeleton.json")
        raw_skel_data.append([x['id'] for x in local_skel_struct])
        raw_skel_data.append([x['true_parent'] for x in local_skel_struct])
        raw_skel_data.append([x['transform_info'] for x in local_skel_struct])
        raw_skel_data.append([x['name'] for x in local_skel_struct])
        local_mtx_idx = {local_skel_struct[i]['transform_info']['index']:i for i in range(len(local_skel_struct))
            if local_skel_struct[i]['transform_info']['flags'] & 0xF == 1}
        local_mtxs = []
        for i in sorted(list(local_mtx_idx.keys())):
            local_mtxs.append(local_skel_struct[local_mtx_idx[i]]['local_matrix'])
        raw_skel_data.append(local_mtxs)
        raw_skel_data.append([x['abs_matrix'] for x in local_skel_struct])
        raw_skel_data.append([x['inv_matrix'] for x in local_skel_struct])
        # Reconstruct visibility parent index
        counter, slot = 0, []
        for i in range(len(local_skel_struct)):
            if local_skel_struct[i]['transform_info']['flags'] & 0x100:
                slot.append(counter)
                counter += 1
            else:
                slot.append(-1 if local_skel_struct[i]['transform_info']['parent'] == -1
                    else slot[local_skel_struct[i]['transform_info']['parent']])
        raw_skel_data.append([-1 if local_skel_struct[i]['transform_info']['parent'] == -1
            else slot[local_skel_struct[i]['transform_info']['parent']]
                for i in range(len(local_skel_struct)) if local_skel_struct[i]['transform_info']['flags'] & 0x100])
        billboard_nodes = [i for i in range(len(local_skel_struct)) if 'billboard_mode' in local_skel_struct[i]]
        raw_skel_data.append([[local_skel_struct[i]['billboard_mode'],i] for i in billboard_nodes])
        po_groups = [x['process_order_group'] for x in local_skel_struct]
        try:
            assert all([po_groups[i] >= po_groups[i-1] for i in range(1, len(po_groups))])
        except AssertionError:
            print("Invalid skeleton order!  All ordinary nodes must be first, then constraint-driven nodes, then physics nodes.")
            raise
        po_header = [0]
        for i in range(3):
            po_header.append(po_header[i] + len([x for x in po_groups if x == i]))
        raw_skel_data.append(po_header)
    except (FileNotFoundError, json.JSONDecodeError):
        print("{0}/skeleton.json missing or unreadable, reading data from {0}.TOMDLB_D instead...".format(tomdlb_file[:-9]))
        raw_skel_data = raw_skel_data_backup
    return raw_skel_data

def read_physics_data (tomdlb_file, backup_phys_block, raw_skel_data):
    # Will read data from JSON file, or load original data from the mdl file if JSON is missing
    try:
        physics_params = read_struct_from_json(tomdlb_file[:-9] + "/physics_info.json")
        local_bone_dict = {raw_skel_data[5][i]:i for i in range(len(raw_skel_data[2]))}
        for i in range(len(physics_params)):
            physics_params[i]['target_node'] = local_bone_dict[physics_params[i]['target_node']]
    except (FileNotFoundError, json.JSONDecodeError):
        print("{0}/physics_info.json missing or unreadable, reading data from {0}.TOMDLB_D instead...".format(tomdlb_file[:-9]))
        with io.BytesIO(backup_phys_block) as ff:
            physics_params = read_section_4 (ff, 0)
    return physics_params

def read_collision_data (tomdlb_file, backup_coll_block, raw_skel_data):
    # Will read data from JSON file and raw buffers, or load original data from the mdl file if JSON is missing
    try:
        data1, data2 = [], []
        collision_list = read_struct_from_json(tomdlb_file[:-9] + "/collision_info.json")
        local_bone_dict = {raw_skel_data[5][i]:i for i in range(len(raw_skel_data[2]))}
        try:
            for i in range(len(collision_list)):
                collision_list[i]['target_node'] = local_bone_dict[collision_list[i]['target_node']]
        except KeyError:
            print("Bone names in collision_info.json are corrupt, possibly due to spelling error or old metadata format.")
            raise
        for i in range(len(collision_list)):
            try:
                mesh_filename = tomdlb_file[:-9] + '/COLLISION_MESH_{0:02d}'.format(i)
                fmt = read_fmt(mesh_filename + '.fmt')
                ib = read_ib(mesh_filename + '.ib', fmt)
                vb = read_vb(mesh_filename + '.vb', fmt)
                assert vb[0]['SemanticName'] == 'POSITION'
            except (FileNotFoundError, AssertionError) as err:
                print("Submesh {0} not found or corrupt, generating an empty submesh...".format(mesh_filename))
                # Generate an empty submesh
                ib = []
                vb = [{'Buffer':[[0.0, 0.0, 0.0]]}]
            print("Processing collision mesh {0}...".format(mesh_filename))
            try:
                all_indices = set(x for y in ib for x in y)
                used_tris = [vb[0]["Buffer"][j] for j in range(len(vb[0]["Buffer"])) if j in all_indices]
                bbox_min = [min(x[0] for x in used_tris),
                    min(x[1] for x in used_tris),
                    min(x[2] for x in used_tris)]
                bbox_max = [max(x[0] for x in used_tris),
                    max(x[1] for x in used_tris),
                    max(x[2] for x in used_tris)]
            except ValueError:
                bbox_min, bbox_max = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
            index = len(data2)
            num_tris = len(ib)
            data1.append([collision_list[i]['target_node']] + [collision_list[i]['group']]
                + bbox_min + bbox_max + [index] + [num_tris])
            for j in range(len(ib)):
                data2.append([x for y in [vb[0]['Buffer'][ib[j][0]], vb[0]['Buffer'][ib[j][1]],
                    vb[0]['Buffer'][ib[j][2]]] for x in y])
        raw_sec5_struct = [data1, data2]
    except (FileNotFoundError, json.JSONDecodeError):
        print("{0}/collision_information missing or corrupt, reading data from {0}.TOMDLB_D instead...".format(tomdlb_file[:-9]))
        with io.BytesIO(backup_coll_block) as ff:
            raw_sec5_struct = read_section_5 (ff, 0)
    return raw_sec5_struct

def read_material_data (tomdlb_file, backup_mat_block):
    # Will read data from JSON file, or load original data from the mdl file if JSON is missing
    try:
        material_struct = read_struct_from_json(tomdlb_file[:-9] + "/material_info.json")
    except (FileNotFoundError, json.JSONDecodeError):
        print("{0}/material_info.json missing or unreadable, reading data from {0}.TOMDLB_D instead...".format(tomdlb_file[:-9]))
        with io.BytesIO(backup_mat_block) as ff:
            material_struct = read_section_7 (ff, 0)
    return material_struct

def read_ani_default_data (tomdlb_file, backup_ani_default_block):
    def encode_target_flag (ani_struct):
        return((ani_struct['type']) + (ani_struct['target'] << 32) + (ani_struct['category'] << 56))
    # Will read data from JSON file, or load original data from the mdl file if JSON is missing
    try:
        ani_default_data = read_struct_from_json(tomdlb_file[:-9] + "/ani_default_info.json")
        data1, data2 = [], []
        for i in range(len(ani_default_data)):
            data1.append(encode_target_flag(ani_default_data[i]))
            try:
                assert len(ani_default_data[i]['vector']) == ani_default_data[i]['type'] & 0xF
                data2.extend(ani_default_data[i]['vector'])
            except AssertionError:
                print("Corrupt vector (index {}) in ani_default_info.json, defaulting to original data.".format(i))
                raise
        raw_sec_11_data = [data1, data2]
    except (FileNotFoundError, json.JSONDecodeError, AssertionError):
        print("{0}/ani_default_info.json missing or unreadable, reading data from {0}.TOMDLB_D instead...".format(tomdlb_file[:-9]))
        with io.BytesIO(backup_ani_default_block) as ff:
            raw_sec_11_data = read_section_11 (ff, 0, decode_data = False)
    return raw_sec_11_data

def make_morph_deltas (mesh, morphed_mesh):
    deltas = {'POSITION': [], 'NORMAL': [], 'TANGENT': [], 'BINORMAL': []}
    for j in range(len(mesh['vb'])):
        semantic = mesh['fmt']['elements'][j]['SemanticName']
        if semantic in deltas:
            delta_list = []
            for k in range(len(mesh['vb'][j]['Buffer'])):
                delta_list.append([morphed_mesh['vb'][j]['Buffer'][k][l] - mesh['vb'][j]['Buffer'][k][l]
                    for l in range(len(mesh['vb'][j]['Buffer'][k]))])
            deltas[semantic] = delta_list
    return(deltas)

def make_morph_run (delta):
    blank = [0.0, 0.0, 0.0]
    use_t = True if len(delta['TANGENT']) else False
    use_b = True if len(delta['BINORMAL']) else False
    full_stream = []
    skip_stream = []
    for i in range(len(delta['POSITION'])):
        full_stream.append(delta['POSITION'][i])
        skip_stream.append(1 if delta['POSITION'][i] == blank else 0)
        full_stream.append(delta['NORMAL'][i] if len(delta['NORMAL']) else blank)
        skip_stream.append(1 if (len(delta['NORMAL']) == 0) or delta['NORMAL'][i] == blank else 0)
        if use_t:
            full_stream.append(delta['TANGENT'][i])
            skip_stream.append(1 if delta['TANGENT'][i] == blank else 0)
        if use_b:
            full_stream.append(delta['BINORMAL'][i])
            skip_stream.append(1 if delta['BINORMAL'][i] == blank else 0)
    full_run = bytearray()
    counter, skips = 0, 0
    while counter < len(full_stream):
        try:
            next_val = skip_stream.index(0, counter)
            while next_val - counter > 0xFFFF: # Shorten the skip if needed to fit into u16
                full_run.extend(struct.pack("{}2H3f".format(e), 0xFFFF, 1, *blank))
                counter += 0x10000
            skips = next_val - counter
        except ValueError:
            skips = len(skip_stream) - counter
            skips = min(skips, 0xFFFF) # Remaining skips not needed
            run = 0
            break
        counter = next_val
        try:
            next_val = skip_stream.index(1, counter)
        except ValueError:
            next_val = len(skip_stream)
        next_val = min(next_val, counter + 0xFFFF) # Shorten the run if needed to fit into u16
        run = next_val - counter
        run_vals = full_stream[counter:counter+run]
        full_run.extend(struct.pack("{}2H".format(e), skips, run))
        for i in range(len(run_vals)):
            full_run.extend(struct.pack("{}3f".format(e), *run_vals[i]))
        counter = next_val
        skips = 0
    full_run.extend(struct.pack("{}2H".format(e), skips, 0))
    return(full_run)

#This function is purely for flipping endianness
def write_generic_int_section (int_list):
    return(struct.pack("{}{}I".format(e, len(int_list)), *int_list))

#Hierarchy
def create_section_0 (raw_skel_struct, ani_value_first_index = 0, ani_target_first_index = 0, start_offset = 0):
    header_block = bytearray()
    data_block = bytearray()
    header_size = (addr_size * 18)
    data_block.extend(struct.pack("{}4H".format(e), *raw_skel_struct[11]))
    data_block.extend(struct.pack("{}fi".format(e), raw_skel_struct[1]['bounding_sphere_radius'],
        raw_skel_struct[1]['bounding_sphere_node']))
    data_block.extend(struct.pack("{}3f".format(e), *raw_skel_struct[1]['bounding_sphere_center']))
    data_block.extend(struct.pack("{}3f".format(e), *raw_skel_struct[1]['bounding_sphere_relative_center']))
    for i in range(2,11):
        count = len(raw_skel_struct[i])
        if i == 2:
            data = struct.pack("{}{}I".format(e, count), *raw_skel_struct[i])
        elif i == 3:
            data = struct.pack("{}{}i".format(e, count), *raw_skel_struct[i])
        elif i == 4:
            data = b''.join([struct.pack("{}2H2h".format(e), raw_skel_struct[i][j]['flags'],
                raw_skel_struct[i][j]['index'], raw_skel_struct[i][j]['parent'],
                raw_skel_struct[i][j]['vis_index']) for j in range(count)])
        elif i == 5:
            data, _ = write_string_dict (raw_skel_struct[i])
        elif i == 6:
            flat1 = [x for y in raw_skel_struct[i] for x in y]
            flat2 = [x for y in flat1 for x in y]
            data = struct.pack("{}{}f".format(e, 32 * count), *flat2)
        elif i in [7,8]:
            data = struct.pack("{}{}f".format(e, 16 * count), *[x for y in raw_skel_struct[i] for x in y])
        elif i == 9:
            data = struct.pack("{}{}h".format(e, count), *raw_skel_struct[i])
        elif i == 10:
            data = b''.join([struct.pack("{}Hh".format(e), *list(raw_skel_struct[i][j])) for j in range(count)])
        if count > 0:
            header_block.extend(struct.pack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), len(data_block) + header_size - len(header_block)))
            header_block.extend(struct.pack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), count))
        else:
            header_block.extend(struct.pack("{}2{}".format(e, {4: "I", 8: "Q"}[addr_size]), 0, 0))
        data_block.extend(data)
        while (start_offset + 0x18 + header_size + len(data_block)) % {5:16, 10:addr_size}.get(i,1):
            data_block.extend(b'\x00')
    num_ani_nodes = len([x for x in raw_skel_struct[4] if x['flags'] & 0xF == 0])
    num_vis_nodes = len([x for x in raw_skel_struct[4] if x['flags'] & 0x100])
    section_0_header = [raw_skel_struct[0][0], ani_value_first_index, ani_target_first_index,
        num_ani_nodes * 13, num_ani_nodes * 4, num_vis_nodes, num_vis_nodes, num_ani_nodes, 0]
    return(struct.pack("{}3I6H".format(e), *section_0_header) + header_block + data_block)

#Physics
def create_section_4 (physics_params, ani_value_first_index = 0, ani_target_first_index = 0):
    raw_sec4_struct = [list(x.values()) for x in physics_params] # Remove dict keys
    data_block = bytearray()
    data_block.extend(struct.pack("{}2I2H".format(e), ani_value_first_index, ani_target_first_index,
        len(raw_sec4_struct), len(raw_sec4_struct)))
    if addr_size == 8:
        data_block.extend(struct.pack("{}I".format(e), 0)) # Padding
    if len(raw_sec4_struct) > 0:
        data_block.extend(struct.pack("{}2{}".format(e, {4: "I", 8: "Q"}[addr_size]), 2 * addr_size, len(raw_sec4_struct)))
    else:
        data_block.extend(struct.pack("{}2{}".format(e, {4: "I", 8: "Q"}[addr_size]), 0, 0))
    for i in range(len(raw_sec4_struct)):
        data_block.extend(struct.pack("{}4h25f".format(e), *raw_sec4_struct[i]))
    if len(data_block) % addr_size:
        data_block.extend(b'\x00' * (addr_size - (len(data_block) % addr_size)))
    return(data_block)

#Collision
def create_section_5 (raw_sec5_struct, symphonia_mode = False):
    header_block = bytearray()
    data_block = bytearray()
    if symphonia_mode == True:
        header_size = (addr_size * 2)
        if len(raw_sec5_struct[0]) > 0:
            tri_header_size = (28 + (addr_size * 2)) * len(raw_sec5_struct[0])
            while tri_header_size % addr_size:
                tri_header_size += 1
            tri_header_block = bytearray()
            tri_data_block = bytearray()
            for i in range(len(raw_sec5_struct[0])):
                tri_header_block.extend(struct.pack("{}hH6f".format(e), *raw_sec5_struct[0][i][:-2]))
                offset = tri_header_size - len(tri_header_block) + len(tri_data_block)
                tris = raw_sec5_struct[1][raw_sec5_struct[0][i][-2]:raw_sec5_struct[0][i][-2]+raw_sec5_struct[0][i][-1]]
                if len(tris) == 0:
                    offset = 0
                tri_header_block.extend(struct.pack("{}2{}".format(e, {4: "I", 8: "Q"}[addr_size]),
                    offset, len(tris)))
                for j in range(len(tris)):
                    tri_data_block.extend(struct.pack("{}9f".format(e), *tris[j]))
            if len(tri_header_block) % addr_size:
                tri_header_block.extend(b'\x00' * (addr_size - (len(tri_header_block) % addr_size)))
            if len(tri_data_block) % addr_size:
                tri_data_block.extend(b'\x00' * (addr_size - (len(tri_data_block) % addr_size)))
            offset = header_size - len(header_block) + len(data_block)
            header_block.extend(struct.pack("{}2{}".format(e, {4: "I", 8: "Q"}[addr_size]), offset, len(raw_sec5_struct[0])))
            data_block.extend(tri_header_block + tri_data_block)
        else:
            header_block.extend(struct.pack("{}2{}".format(e, {4: "I", 8: "Q"}[addr_size]), 0, 0))
    else:
        header_size = (addr_size * 4)
        for i in range(2):
            count = len(raw_sec5_struct[i])
            data = bytearray()
            for j in range(len(raw_sec5_struct[i])):
                if i == 0:
                    data.extend(struct.pack("{}hH6f2I".format(e), *raw_sec5_struct[i][j]))
                else:
                    data.extend(struct.pack("{}9f".format(e), *raw_sec5_struct[i][j]))
            if count > 0:
                header_block.extend(struct.pack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), len(data_block) + header_size - len(header_block)))
                header_block.extend(struct.pack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), count))
            else:
                header_block.extend(struct.pack("{}2{}".format(e, {4: "I", 8: "Q"}[addr_size]), 0, 0))
            data_block.extend(data)
            if len(data_block) % addr_size and i == 1:
                data_block.extend(b'\x00' * (addr_size - (len(data_block) % addr_size)))
    return(header_block + data_block)

#Meshes
def create_section_6 (tomdlb_file, backup_mesh_block, dlp_file, material_struct,
        ani_value_first_index = 0, ani_target_first_index = 0):
    def unorm_to_bytes (vals):
        float_max = ((2**8)-1)
        return([(int(round(min(max(x,0), 1) * float_max))) for x in vals])
    # We will need some information from the original block regardless, so we will read it
    with io.BytesIO(backup_mesh_block) as ff:
        original_meshes, bone_palette_ids, orig_mesh_blocks_info = read_section_6(ff, 0, dlp_file)
    # Will read data from JSON file, or load original data from the mdl file if JSON is missing
    try:
        mesh_blocks_info = read_struct_from_json(tomdlb_file[:-9] + "/mesh_info.json")
    except:
        print("{0}/mesh_info.json missing or unreadable, using data from {0}.TOMDLB_D instead...".format(tomdlb_file[:-9]))
        mesh_blocks_info = orig_mesh_blocks_info
        for i in range(len(mesh_blocks_info)):
            mesh_blocks_info[i]['material'] = material_struct[mesh_blocks_info[i]['material']]['name']
    material_dict = {material_struct[i]['name']: i for i in range(len(material_struct))}
    material_list = []
    sec_0 = bytearray()
    sec_1_header = bytearray()
    sec_1_header_length = (addr_size * 3 + 0x10) * len(mesh_blocks_info)
    sec_1_data = bytearray()
    uvidx_data = bytearray()
    morph_counter = 0
    assigned_morph_slots = {}
    max_ani_count = 0
    for i in range(len(mesh_blocks_info)):
        safe_filename = "".join([x if x not in "\\/:*?<>|" else "_" for x in mesh_blocks_info[i]["name"]])
        flags = mesh_blocks_info[i]["flags"]
        # Calculate strides / semantics  from flags
        semantics_present = {'NORMAL': False, 'TANGENT': False, 'BINORMAL': False,
                'COLOR': True, 'BLENDWEIGHT': False, 'BLENDINDICES': False} # Only color is always present
        cpu_stride_no_wt, gpu_stride = 0, 0 # final stride = cpu_stride_no_wt + weights, which are variable
        pos_offset, nrm_offset, tangent_offset, binormal_offset, blend_idx_offset, blend_wt_offset = 0, 0, 0, 0, 0, 0
        if flags & 0x30: # CPU skinning, vertex vector data in TOMDLB_D
            cpu_stride_no_wt += 12
            if not flags & 0x2000: # Unclear if this flag is actually used
                semantics_present['NORMAL'] = True
                nrm_offset = cpu_stride_no_wt
                cpu_stride_no_wt += 12
                if flags & 0x80:
                    semantics_present['TANGENT'] = True
                    semantics_present['BINORMAL'] = True
                    tangent_offset = cpu_stride_no_wt
                    cpu_stride_no_wt += 12
                    binormal_offset = cpu_stride_no_wt
                    cpu_stride_no_wt += 12
            elif flags & 0x20:
                nrm_offset = cpu_stride_no_wt
                cpu_stride_no_wt += 12 # If flags & 0x20, the normal slot is always there, even if unused
            if not (flags & 0x20):
                blend_idx_offset = cpu_stride_no_wt
                cpu_stride_no_wt += 4 # Blend indices
                blend_wt_offset = cpu_stride_no_wt
            if flags & 0x10:
                semantics_present['BLENDWEIGHT'] = True
                semantics_present['BLENDINDICES'] = True
        else: # No skinning, vertex vector data in TOMDLP_P (sent directly to GPU)
            gpu_stride += 12
            if not flags & 0x2000:
                semantics_present['NORMAL'] = True
                nrm_offset = gpu_stride
                gpu_stride += 12
                if flags & 0x80:
                    semantics_present['TANGENT'] = True
                    semantics_present['BINORMAL'] = True
                    tangent_offset = gpu_stride
                    gpu_stride += 12
                    binormal_offset = gpu_stride
                    gpu_stride += 12
        color_offset = gpu_stride
        gpu_stride += 4 # Vertex color
        uv_offsets = []
        num_uv_maps = flags & 0xF
        for _ in range(num_uv_maps):
            uv_offsets.append(gpu_stride)
            gpu_stride += 8 # UVs
        expected_fmt = make_fmt(num_uv_maps, semantics_present)
        semantic_i = {"{}{}".format(expected_fmt['elements'][i]['SemanticName'],
            "_" + expected_fmt['elements'][i]['SemanticIndex'] if expected_fmt['elements'][i]['SemanticName'] == 'TEXCOORD' else '')
            : i for i in range(len(expected_fmt['elements']))}
        mesh_filename = tomdlb_file[:-9] + '/{0:02d}_{1}'.format(i, safe_filename)
        print("Processing submesh {0}...".format(mesh_filename))
        try:
            fmt = read_fmt(mesh_filename + '.fmt')
            ib = read_ib(mesh_filename + '.ib', fmt)
            if not (flags & 0xF00 == 0x100):
                ib = stripify(ib, stitchstrips = True)[0]
            else:
                ib = [x for y in ib for x in y]
            vb = read_vb(mesh_filename + '.vb', fmt)
            assert ([x['SemanticName'] for x in fmt['elements']]
                == [x['SemanticName'] for x in expected_fmt['elements']])
            stride_semantic = 'vb0 stride' if 'vb0 stride' in fmt else 'stride'
            assert (int(fmt[stride_semantic]) == int(expected_fmt['stride']))
            assert len(ib) > 2
        except (FileNotFoundError, AssertionError) as err:
            print("Submesh {0} not found or corrupt, generating an empty submesh...".format(mesh_filename))
            # Generate an empty submesh
            fmt = expected_fmt
            ib = [0,0,0]
            vb = [{'Buffer':[[0.0, 0.0, 0.0]]}]
            if not flags & 0x2000:
                vb.append({'Buffer': [[0.0, 0.0, 0.0]]})
            if flags & 0x80:
                vb.append({'Buffer': [[0.0, 0.0, 0.0]]})
                vb.append({'Buffer': [[0.0, 0.0, 0.0]]})
            vb.append({'Buffer': [[1.0, 1.0, 1.0, 1.0]]})
            for _ in range(num_uv_maps):
                vb.append({'Buffer': [[0.0, 0.0]]})
            if flags & 0x10:
                vb.append({'Buffer': [[1.0, 0.0, 0.0, 0.0]]})
                vb.append({'Buffer': [[0, 0, 0, 0]]})
        if flags & 0x20: # Read in morph targets
            morphed_meshes = []
            for j in range(mesh_blocks_info[i]["morph_count"]):
                morphed_mesh_filename = "{0}_morphed_{1:02d}".format(mesh_filename, j)
                try:
                    mfmt = read_fmt(morphed_mesh_filename + '.fmt')
                    mvb = read_vb(morphed_mesh_filename + '.vb', mfmt)
                    assert ([x['SemanticName'] for x in mfmt['elements']]
                        == [x['SemanticName'] for x in expected_fmt['elements']])
                    stride_semantic = 'vb0 stride' if 'vb0 stride' in mfmt else 'stride'
                    assert (int(mfmt[stride_semantic]) == int(expected_fmt['stride']))
                    assert len(mvb[0]['Buffer']) == len(vb[0]['Buffer'])
                except (FileNotFoundError, AssertionError) as err:
                    print("Morphed submesh {0} not found or corrupt, generating an empty morph...".format(morphed_mesh_filename))
                    # Generate an cloned submesh (for empty deltas)
                    mfmt = fmt
                    mvb = vb
                morphed_meshes.append({'fmt': mfmt, 'ib': ib, 'vb': mvb})
            deltas = [make_morph_deltas({'fmt': fmt, 'ib': ib, 'vb': vb}, morphed_mesh) for morphed_mesh in morphed_meshes]
            runs = [make_morph_run(delta) for delta in deltas]
        try:
            material_list.append(material_dict[mesh_blocks_info[i]["material"]])
        except:
            print("Unable to read material for {}!  The material assignment is either missing or invalid.".format(safe_filename))
            input("Press Enter to quit.")
            raise
        sec_0.extend(struct.pack("{}i3f".format(e), mesh_blocks_info[i]["sort_priority"], *mesh_blocks_info[i]["sort_center"]))
        # Add basic data
        if not flags & 0x20:
            first_morph_wt_slot = 0
        else:
            morph_slot_code = '{}_{}'.format(mesh_blocks_info[i]["name"], len(runs)) 
            if morph_slot_code in assigned_morph_slots:
                first_morph_wt_slot = assigned_morph_slots[morph_slot_code]
            else:
                first_morph_wt_slot = morph_counter
        sec_1_header.extend(struct.pack("{}i6h".format(e), mesh_blocks_info[i]["mesh"], mesh_blocks_info[i]["submesh"],
            mesh_blocks_info[i]["node"], mesh_blocks_info[i]["flags"], material_list[-1],
            first_morph_wt_slot, mesh_blocks_info[i]["padding"]))
        data_block_start = len(sec_1_data)
        # Add mesh name
        offset = sec_1_header_length - len(sec_1_header) + len(sec_1_data)
        sec_1_header.extend(struct.pack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), offset))
        sec_1_data.extend(mesh_blocks_info[i]["name"].encode()+b'\x00')
        if len(sec_1_data) % 4:
            sec_1_data += b'\x00' * (4 - (len(sec_1_data) % 4))
        # Add mesh data
        offset = sec_1_header_length - len(sec_1_header) + len(sec_1_data)
        sec_1_header.extend(struct.pack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), offset))
        # Standard weighted meshes
        if flags & 0x30 and not flags & 0x20:
            submesh_datablock = bytearray()
            submesh_datablock_header = bytearray()
            uv_block = bytearray()
            vertices_to_process = []
            ps3_mode = False
            if e == '>' and addr_size == 4: # PS3 mode, split vertices into groups
                ps3_mode = True
                vcount = 0
                while vcount < len(vb[0]['Buffer']):
                    vertices_to_process.append((vcount, min(vcount+0x200, len(vb[0]['Buffer']))))
                    vcount += 512
                submesh_datablock_header.extend(struct.pack("{}I".format(e), len(vertices_to_process)))
            else:
                vertices_to_process.append((0, len(vb[0]['Buffer'])))
            vgrp = [4 if not x[3]==0.0 else 3 if not x[2]==0.0 else 2 if not x[1]==0.0 else 1 for x in
                vb[semantic_i['BLENDWEIGHT']]['Buffer']]
            new_v_assgn = {}
            for slice_i in range(len(vertices_to_process)):
                # Split vertices into weight types
                v_by_grp = [[k + vertices_to_process[slice_i][0] for k, vgrpval
                    in enumerate(vgrp[vertices_to_process[slice_i][0]
                    :vertices_to_process[slice_i][1]]) if vgrpval == j] for j in range(1,5)]
                counter = vertices_to_process[slice_i][0]
                for j in range(len(v_by_grp)):
                    for k in range(len(v_by_grp[j])):
                        new_v_assgn[v_by_grp[j][k]] = counter
                        counter += 1
                if ps3_mode == True:
                    submesh_datablock_header.extend(struct.pack("{}4H".format(e), *[len(x) for x in v_by_grp]))
                else:
                    submesh_datablock_header.extend(struct.pack("{}4I".format(e), *[len(x) for x in v_by_grp]))
                for j in range(len(v_by_grp)):
                    for k in range(len(v_by_grp[j])):
                        submesh_datablock.extend(struct.pack("{}3f".format(e),
                            *vb[semantic_i['POSITION']]['Buffer'][v_by_grp[j][k]]))
                        if not flags & 0x2000:
                            submesh_datablock.extend(struct.pack("{}3f".format(e),
                                *vb[semantic_i['NORMAL']]['Buffer'][v_by_grp[j][k]]))
                        if flags & 0x80:
                            submesh_datablock.extend(struct.pack("{}3f".format(e),
                                *vb[semantic_i['TANGENT']]['Buffer'][v_by_grp[j][k]]))
                            submesh_datablock.extend(struct.pack("{}3f".format(e),
                                *vb[semantic_i['BINORMAL']]['Buffer'][v_by_grp[j][k]]))
                        submesh_datablock.extend(struct.pack("{}4B".format(e),
                            *vb[semantic_i['BLENDINDICES']]['Buffer'][v_by_grp[j][k]]))
                        if j > 0:
                            submesh_datablock.extend(struct.pack("{}{}f".format(e, j),
                                *vb[semantic_i['BLENDWEIGHT']]['Buffer'][v_by_grp[j][k]][:j]))
                        uv_block.extend(struct.pack("{}4B".format(e),
                            *unorm_to_bytes(vb[semantic_i['COLOR']]['Buffer'][v_by_grp[j][k]])))
                        for l in range(num_uv_maps):
                            uv_block.extend(struct.pack("{}2f".format(e),
                                *vb[semantic_i['TEXCOORD_'+str(l)]]['Buffer'][v_by_grp[j][k]]))
            new_ib = [new_v_assgn[x] for x in ib]
            new_ib_block = bytearray(struct.pack("{}{}H".format(e, len(new_ib)), *new_ib))
            if len(new_ib_block) % 4:
                new_ib_block += b'\x00' * (4 - (len(new_ib_block) % 4))
            sec_1_data.extend(struct.pack("{}2HI".format(e), len(vb[semantic_i['POSITION']]['Buffer']),
                len(new_ib), len(uvidx_data)))
            uvidx_data.extend(uv_block)
            sec_1_data.extend(struct.pack("{}I".format(e), len(uvidx_data)))
            uvidx_data.extend(new_ib_block)
            sec_1_data.extend(submesh_datablock_header + submesh_datablock)
            sec_1_header.extend(struct.pack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]),
                len(submesh_datablock_header + submesh_datablock) + 0xC))
        # Morph target meshes
        elif flags & 0x20:
            if flags & 0x10:
                bone_slot = vb[semantic_i['BLENDINDICES']]['Buffer'][0][0]
            else:
                bone_slot = 0
            num_verts = len(vb[semantic_i['POSITION']]['Buffer'])
            submesh_datablock = bytearray()
            uv_block = bytearray()
            for j in range(num_verts):
                submesh_datablock.extend(struct.pack("{}3f".format(e), *vb[semantic_i['POSITION']]['Buffer'][j]))
                if not flags & 0x2000:
                    submesh_datablock.extend(struct.pack("{}3f".format(e), *vb[semantic_i['NORMAL']]['Buffer'][j]))
                else:
                    submesh_datablock.extend(struct.pack("{}3f".format(e), 0.0, 0.0, 0.0)) # Ignored by game engine
                if flags & 0x80:
                    submesh_datablock.extend(struct.pack("{}3f".format(e), *vb[semantic_i['TANGENT']]['Buffer'][j]))
                    submesh_datablock.extend(struct.pack("{}3f".format(e), *vb[semantic_i['BINORMAL']]['Buffer'][j]))
                uv_block.extend(struct.pack("{}4B".format(e), *unorm_to_bytes(vb[semantic_i['COLOR']]['Buffer'][j])))
                for l in range(num_uv_maps):
                    uv_block.extend(struct.pack("{}2f".format(e), *vb[semantic_i['TEXCOORD_'+str(l)]]['Buffer'][j]))
            new_ib_block = bytearray(struct.pack("{}{}H".format(e, len(ib)), *ib)) # Triangles
            if len(new_ib_block) % 4:
                new_ib_block += b'\x00' * (4 - (len(new_ib_block) % 4))
            sec_1_data.extend(struct.pack("{}2HI".format(e), len(vb[semantic_i['POSITION']]['Buffer']),
                len(ib), len(uvidx_data)))
            uvidx_data.extend(uv_block)
            sec_1_data.extend(struct.pack("{}I".format(e), len(uvidx_data)))
            uvidx_data.extend(new_ib_block)
            sec_1_data.extend(struct.pack("{}2H".format(e), len(runs), bone_slot))
            morph_offsets = []
            morph_block = bytearray()
            for j in range(len(runs)):
                morph_offsets.append(len(morph_block))
                morph_block.extend(runs[j])
            sec_1_data.extend(struct.pack("{}{}I".format(e, len(morph_offsets)), *morph_offsets))
            sec_1_data.extend(submesh_datablock + morph_block)
            sec_1_header.extend(struct.pack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]),
                0xC + 4 + 4 * len(runs) + len(submesh_datablock) + len(morph_block)))
            if not morph_slot_code in assigned_morph_slots:
                assigned_morph_slots[morph_slot_code] = morph_counter
                morph_counter += len(runs)
            max_ani_count = max(max_ani_count, assigned_morph_slots[morph_slot_code] + len(runs))
        # Unweighted meshes
        else:
            uv_block = bytearray()
            for j in range(len(vb[semantic_i['POSITION']]['Buffer'])):
                uv_block.extend(struct.pack("{}3f".format(e), *vb[semantic_i['POSITION']]['Buffer'][j]))
                if not flags & 0x2000:
                    uv_block.extend(struct.pack("{}3f".format(e), *vb[semantic_i['NORMAL']]['Buffer'][j]))
                if flags & 0x80:
                    uv_block.extend(struct.pack("{}3f".format(e), *vb[semantic_i['TANGENT']]['Buffer'][j]))
                    uv_block.extend(struct.pack("{}3f".format(e), *vb[semantic_i['BINORMAL']]['Buffer'][j]))
                uv_block.extend(struct.pack("{}4B".format(e), *unorm_to_bytes(vb[semantic_i['COLOR']]['Buffer'][j])))
                for l in range(num_uv_maps):
                    uv_block.extend(struct.pack("{}2f".format(e), *vb[semantic_i['TEXCOORD_'+str(l)]]['Buffer'][j]))
            new_ib_block = bytearray(struct.pack("{}{}H".format(e, len(ib)), *ib)) # Triangles
            if len(new_ib_block) % 4:
                new_ib_block += b'\x00' * (4 - (len(new_ib_block) % 4))
            sec_1_data.extend(struct.pack("{}2HI".format(e), len(vb[semantic_i['POSITION']]['Buffer']),
                len(ib), len(uvidx_data)))
            uvidx_data.extend(uv_block)
            sec_1_data.extend(struct.pack("{}I".format(e), len(uvidx_data)))
            uvidx_data.extend(new_ib_block)
            sec_1_data.extend(struct.pack("{}5I".format(e), 0, 0, 0, 0, 0))
            sec_1_header.extend(struct.pack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), 0x20))
    sec_1 = sec_1_header + sec_1_data
    sec_2 = bytearray(struct.pack("{}{}I".format(e, len(bone_palette_ids)), *bone_palette_ids))
    sec_3 = struct.pack("{}2I".format(e), len(mesh_blocks_info), len(bone_palette_ids))
    # Build offset header
    block_lengths = [len(sec_0), len(sec_1), len(sec_2), len(sec_3)]
    block_offsets = [sum(block_lengths[:i], (addr_size * 8)-((addr_size * 2) * i)) if block_lengths[i] > 0 else 0
        for i in range(len(block_lengths))]
    block_counts = [len(mesh_blocks_info), len(mesh_blocks_info), len(bone_palette_ids), 1]
    block_header = bytearray()
    #ani_value_first_index, ani_target_first_index, total_ani_value, total_ani_target, total_morph_weights, padding
    block_header.extend(struct.pack("{}2I4H".format(e), ani_value_first_index, ani_target_first_index,
        max_ani_count, max_ani_count, max_ani_count, 0))
    for i in range(4):
        block_header.extend(struct.pack("{}2{}".format(e, {4: "I", 8: "Q"}[addr_size]), block_offsets[i], block_counts[i]))
    section_6 = bytearray(block_header + sec_0 + sec_1 + sec_2 + sec_3)
    if len(section_6) % addr_size:
        section_6 += b'\x00' * (addr_size - (len(section_6) % addr_size))
    return(section_6, uvidx_data)

#Materials
def create_section_7 (material_struct, ani_value_first_index = 0, ani_target_first_index = 0):
    all_tex_groups = []
    for i in range(len(material_struct)):
        for j in range(len(material_struct[i]['textures'])):
            if 'frames' in material_struct[i]['textures'][j]:
                tex_group = []
                for k in range(len(material_struct[i]['textures'][j]['frames'])):
                    tex_group.append(material_struct[i]['textures'][j]['frames'][k])
            else:
                tex_group = [material_struct[i]['textures'][j]]
            all_tex_groups.append(tex_group)
    # Deduplicate groups
    dedup_tex_groups = []
    for i in range(len(all_tex_groups)):
        if len(all_tex_groups[i]) > 1: # Process frames first
            if not [x['texture_name'] for x in all_tex_groups[i]] in [[t['texture_name'] for t in g] for g in dedup_tex_groups]:
                dedup_tex_groups.append(all_tex_groups[i])
    for i in range(len(all_tex_groups)):
        if len(all_tex_groups[i]) == 1: # Single textures can exist inside other frames
            if not all_tex_groups[i][0]['texture_name'] in [x for y in [[t['texture_name'] for t in g] for g in dedup_tex_groups] for x in y]:
                dedup_tex_groups.append(all_tex_groups[i])
    sorted_tex_groups = sorted(dedup_tex_groups, key=lambda g: [t['texture_name'] for t in g])
    all_tex = [x for y in sorted_tex_groups for x in y]
    tex_dict = {}
    for i in range(len(all_tex)):
        if not all_tex[i]['texture_name'] in tex_dict:
            tex_dict[all_tex[i]['texture_name']] = i
    all_tex_name_list = [x['texture_name'] for x in all_tex]
    all_tex_names = [x + '.totexb_d' for x in tex_dict.keys()]
    frame_dict = {} # Frames need consecutive textures, so find the exact group in the final list
    for i in range(len(all_tex_groups)):
        if len(all_tex_groups[i]) > 1: # Process frames only
            frame_names = [x['texture_name'] for x in all_tex_groups[i]]
            counter = 0
            while all_tex_name_list[counter:counter+len(frame_names)] != frame_names:
                counter += 1
            frame_dict[tuple(frame_names)] = counter
    tex_counter = 0
    set_0_base = []
    set_1 = []
    for i in range(len(material_struct)):
        s0vals = list(material_struct[i]['parameters']['mat_info'].values())
        s0vals[3], s0vals[5] = len(material_struct[i]['textures']), tex_counter
        set_0_base.append(s0vals)
        tex_counter += len(material_struct[i]['textures'])
        set_1.extend([[material_struct[i]['textures'][j]['layer_options']['blend_type'],
            material_struct[i]['textures'][j]['layer_options']['unk'],
            frame_dict[tuple(x['texture_name'] for x in material_struct[i]['textures'][j]['frames'])]
            if 'frames' in material_struct[i]['textures'][j]
            else tex_dict[material_struct[i]['textures'][j]['texture_name']],
            material_struct[i]['textures'][j]['layer_options']['frame_count']]
            for j in range(len(material_struct[i]['textures']))])
    mat_info_blocks = [x['parameters']['mat_info'] for x in material_struct]
    set_3 = sorted(range(len(mat_info_blocks)), key=lambda i: mat_info_blocks[i]['ani_color_slot'])
    set_3 = [i for i in set_3 if mat_info_blocks[i]['ani_color_slot'] != -1]
    count_3 = len(set_3)
    set_4 = [i for i, m in enumerate(mat_info_blocks) if m['ani_uv_scroll_slot'] != -1]
    count_4 = sum([len(material_struct[i]['textures']) for i in set_4])
    set_5 = [i for i, m in enumerate(mat_info_blocks) if m['ani_sprite_sheet_slot'] != -1]
    count_5 = sum([len(material_struct[i]['textures']) for i in set_5])
    # Build section 0 (Material parameters?)
    set_0_header_len = (addr_size * 4 + 0x18)  * len(material_struct)
    set_0_header = bytearray()
    set_0_data = bytearray()
    for i in range(len(material_struct)):
        set_0_header.extend(struct.pack("{}I3H4h3H".format(e), *set_0_base[i]))
        offset = set_0_header_len - len(set_0_header) + len(set_0_data)
        set_0_header.extend(struct.pack("{}2{}".format(e, {4: "I", 8: "Q"}[addr_size]), offset, len(material_struct[i]['parameters']['mat_params'])))
        set_0_data.extend(struct.pack("{}{}I".format(e, len(material_struct[i]['parameters']['mat_params'])),
            *list(material_struct[i]['parameters']['mat_params'].values())))
        offset = set_0_header_len - len(set_0_header) + len(set_0_data)
        set_0_header.extend(struct.pack("{}2{}".format(e, {4: "I", 8: "Q"}[addr_size]), offset, len(material_struct[i]['parameters']['shader_params'])))
        if len(material_struct[i]['parameters']['shader_params']) == 0x17:
            set_0_data.extend(struct.pack("{}8I4f4If6I".format(e, len(material_struct[i]['parameters']['shader_params'])),
                *list(material_struct[i]['parameters']['shader_params'].values())))
        elif len(material_struct[i]['parameters']['shader_params']) == 0x11:
            set_0_data.extend(struct.pack("{}8I4f4If".format(e, len(material_struct[i]['parameters']['shader_params'])),
                *list(material_struct[i]['parameters']['shader_params'].values())))
        else:
            set_0_data.extend(struct.pack("{}{}I".format(e, len(material_struct[i]['parameters']['shader_params'])),
                *list(material_struct[i]['parameters']['shader_params'].values())))
    set_0_block = set_0_header + set_0_data
    if len(set_0_block) % addr_size:
        set_0_block += b'\x00' * (addr_size - (len(set_0_block) % addr_size))
    # Build section 1 (Texture Pointers)
    set_1_block = bytearray()
    for i in range(len(set_1)):
        set_1_block.extend(struct.pack("{}2B2H".format(e), *set_1[i]))
    if len(set_1_block) % addr_size:
        set_1_block += b'\x00' * (addr_size - (len(set_1_block) % addr_size))
    # Build section 2 (Material name, etc)
    set_2_header_len = (addr_size * 5) * len(material_struct)
    set_2_header = bytearray()
    set_2_data = bytearray()
    for i in range(len(material_struct)):
        offset = set_2_header_len - len(set_2_header) + len(set_2_data)
        set_2_header.extend(struct.pack("{}2{}".format(e, {4: "I", 8: "Q"}[addr_size]), offset, len(material_struct[i]['parameters']['vshader_keys'])))
        set_2_data.extend(struct.pack("{}{}I".format(e, len(material_struct[i]['parameters']['vshader_keys'])),
            *material_struct[i]['parameters']['vshader_keys']))
        offset = set_2_header_len - len(set_2_header) + len(set_2_data)
        set_2_header.extend(struct.pack("{}2{}".format(e, {4: "I", 8: "Q"}[addr_size]), offset,
            len(material_struct[i]['parameters']['pshader_keys'])))
        set_2_data.extend(struct.pack("{}{}I".format(e, len(material_struct[i]['parameters']['pshader_keys'])),
            *material_struct[i]['parameters']['pshader_keys']))
        offset = set_2_header_len - len(set_2_header) + len(set_2_data)
        set_2_header.extend(struct.pack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), offset))
        set_2_data.extend(material_struct[i]['name'].encode()+b'\x00')
        if len(set_2_data) % 4:
            set_2_data += b'\x00' * (4 - (len(set_2_data) % 4))
    set_2_block = set_2_header + set_2_data
    if len(set_2_block) % addr_size:
        set_2_block += b'\x00' * (addr_size - (len(set_2_block) % addr_size))
    # Build section 3
    set_3_block = bytearray()
    set_3_block.extend(struct.pack("{}{}h".format(e, len(set_3)), *set_3))
    while len(set_3_block) % addr_size > 0:
        set_3_block.extend(struct.pack("{}h".format(e), 0))
    # Build section 4
    set_4_block = bytearray()
    set_4_block.extend(struct.pack("{}{}h".format(e, len(set_4)), *set_4))
    while len(set_4_block) % addr_size > 0:
        set_4_block.extend(struct.pack("{}h".format(e), 0))
    # Build section 5
    set_5_block = bytearray()
    set_5_block.extend(struct.pack("{}{}h".format(e, len(set_5)), *set_5))
    while len(set_5_block) % addr_size > 0:
        set_5_block.extend(struct.pack("{}h".format(e), 0))
    # Build section 6 (Textures)
    set_6_header_len = (addr_size + {4: 4, 8: 16}[addr_size]) * len(all_tex)
    set_6_header = bytearray()
    set_6_data = bytearray()
    for i in range(len(all_tex)):
        wrap_flag = ({'MIRROR':1,'REPEAT':4,'CLAMP':0}[all_tex[i]['wrapS']] +
                     {'MIRROR':2,'REPEAT':8,'CLAMP':0}[all_tex[i]['wrapT']])
        offset = set_6_header_len - len(set_6_header) + len(set_6_data)
        set_6_header.extend(struct.pack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), offset))
        set_6_data.extend(all_tex[i]['texture_name'].encode()+b'\x00')
        if len(set_6_data) % 2:
            set_6_data += b'\x00' * (2 - (len(set_6_data) % 2))
        if addr_size == 8:
            set_6_header.extend(struct.pack("{}IfI4x".format(e), wrap_flag,
                all_tex[i]['lod_bias'] if 'lod_bias' in all_tex[i] else 0.0, 0))
        else:
            set_6_header.extend(struct.pack("{}I".format(e), wrap_flag))
    if len(set_6_data) % addr_size:
        set_6_data += b'\x00' * (addr_size - (len(set_6_data) % addr_size))
    set_6_block = set_6_header + set_6_data
    # Build offset header
    header_counts = [count_3*4, count_3,  # Color animation counts (# RGBA floats, # animation targets)
                    count_4*5, count_4*3, # UV scroll animation counts (# 5x floats, # animation targets)
                    count_5, count_5,     # Sprite sheet animation counts (# 1x floats, # animation targets)
                    count_4, count_5]     # count_4 and count_5 again
    block_lengths = [len(set_0_block), len(set_1_block), len(set_2_block),
        len(set_3_block), len(set_4_block), len(set_5_block), len(set_6_block)]
    block_offsets = [sum(block_lengths[:i], (addr_size * 14)-((addr_size * 2) * i)) if block_lengths[i] > 0 else 0
        for i in range(len(block_lengths))]
    block_counts = [len(material_struct), len(set_1), len(material_struct), len(set_3), len(set_4), len(set_5), len(all_tex)]
    block_header = bytearray()
    block_header.extend(struct.pack("{}2I8H".format(e), ani_value_first_index, ani_target_first_index, *header_counts))
    for i in range(7):
        block_header.extend(struct.pack("{}2{}".format(e, {4: "I", 8: "Q"}[addr_size]), block_offsets[i], block_counts[i]))
    # Return assembled block
    return(block_header + set_0_block + set_1_block + set_2_block + set_3_block
        + set_4_block + set_5_block + set_6_block, all_tex_names)

#Animation defaults?
def create_section_11 (raw_sec11_struct, start_offset = 0):
    header_block = bytearray()
    data_block = bytearray()
    header_size = (addr_size * 4)
    # Add the blank third vector, offset + (0,0) as addr_size, per-flag exclusivity data.
    data_block.extend(struct.pack("{}2{}".format(e, {4: "I", 8: "Q"}[addr_size]), 0, 0))
    while (start_offset + header_size + len(data_block)) % 8: # Alignment
        data_block.extend(b'\x00')
    for i in range(2):
        count = len(raw_sec11_struct[i])
        if i == 0:
            data = struct.pack("{}{}Q".format(e, len(raw_sec11_struct[i])), *raw_sec11_struct[i])
        else:
            data = struct.pack("{}{}f".format(e, len(raw_sec11_struct[i])), *raw_sec11_struct[i])
        if count > 0:
            header_block.extend(struct.pack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), len(data_block) + header_size - len(header_block)))
            header_block.extend(struct.pack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), count))
        else:
            header_block.extend(struct.pack("{}2{}".format(e, {4: "I", 8: "Q"}[addr_size]), 0, 0))
        data_block.extend(data)
        if len(data_block) % addr_size:
            data_block.extend(b'\x00' * (addr_size - (len(data_block) % addr_size)))
    return(header_block + data_block)

def process_tomdlb (tomdlb_file, swap_endian = False):
    global addr_size, e
    print("Processing {}...".format(tomdlb_file))
    with open(tomdlb_file, 'rb') as f:
        magic = f.read(4)
        if magic in [b'DPDF', b'FDPD']:
            e, addr_size = '<', 8
            set_endianness('<')
            if magic == b'FDPD':
                e = '>' # Write mode
                set_endianness('>') # Read mode
            unk_int, = struct.unpack("{}I".format(e), f.read(4))
            set_address_size(8)
            if not unk_int == 0:
                f.seek(4,0)
                addr_size = 4 # Write mode
                set_address_size(4) # Read mode
            opening_dict = read_opening_dict (f)
            dlp_file = opening_dict[0]
            anmb_file = opening_dict[1]
            magic = f.read(4)
            if magic in [b'BLDM', b'MDLB']:
                unk_int2, = struct.unpack("{}I".format(e), f.read(4))
                toc = [read_offset(f) for _ in range(12)]
                data_blocks = []
                for i in range(len(toc)):
                    f.seek(toc[i])
                    if i == len(toc) - 1:
                        data_blocks.append(f.read())
                    else:
                        data_blocks.append(f.read(toc[i+1] - toc[i]))
                # Read data from .json files (or rebuild from original .TOMDLB_D file)
                raw_skel_data = read_skeleton_data (tomdlb_file, data_blocks[0])
                physics_params = read_physics_data (tomdlb_file, data_blocks[4], raw_skel_data)
                collision_struct = read_collision_data (tomdlb_file, data_blocks[5], raw_skel_data)
                material_struct = read_material_data (tomdlb_file, data_blocks[7]) # Needed for meshes as well
                raw_ani_default_data = read_ani_default_data (tomdlb_file, data_blocks[11])
                skel_unk = struct.unpack("{}2I".format(e), data_blocks[0][4:12]) # Indices in data_blocks[11]
                phys_unk = struct.unpack("{}2I".format(e), data_blocks[4][0:8]) # Indices in data_blocks[11]
                mesh_unk = struct.unpack("{}2I".format(e), data_blocks[6][0:8]) # Indices in data_blocks[11]
                mat_unk = struct.unpack("{}2I8H".format(e), data_blocks[7][0:24]) # Indices in data_blocks[11]
                # Until we find a better way... This will default to Z/B if there are no materials
                symphonia_mode = len(material_struct[0]['parameters']['mat_params']) == 1 if material_struct else False
                if swap_endian == True:
                    # Changing e will change endianness for this script *only*; do not call set_endianness()!
                    e = {'>': '<', '<': '>'}[e] # Write mode
                    for i in [1,2,3,8,9,10]:
                        data_blocks[i] = write_generic_int_section(read_generic_int_section(f, toc[i], (toc[i+1]-toc[i])))
                # Create new physics block
                data_blocks[4] = create_section_4(physics_params, phys_unk[0], phys_unk[1])
                # Create new collision block
                data_blocks[5] = create_section_5(collision_struct, symphonia_mode)
                # Create new mesh block
                data_blocks[6], dlp_block = create_section_6(tomdlb_file, data_blocks[6],
                    dlp_file, material_struct, mesh_unk[0], mesh_unk[1])
                if dlp_block == False: # Rebuild failed, due to unsupported mesh type
                    print("Unsupported mesh detected, skipping {}...".format(tomdlb_file))
                    return False
                # Create new material block
                data_blocks[7], all_tex_names = create_section_7(material_struct, mat_unk[0], mat_unk[1])
                # Create new opening dictionary
                new_opening_dict_strings = [dlp_file, anmb_file] + all_tex_names
                new_opening_dict = write_string_dict(new_opening_dict_strings)[0]
                # Create new skeleton block
                file_header_size = 4 + (4 if addr_size == 8 else 0) + (2 * addr_size) + 8
                new_s0_start_offset = file_header_size + (12 * addr_size) + len(new_opening_dict)
                data_blocks[0] = create_section_0(raw_skel_data, skel_unk[0], skel_unk[1], new_s0_start_offset)
                # Create new animation default data block
                new_s11_start_offset = (file_header_size + (12 * addr_size) + len(new_opening_dict)
                    + sum([len(data_blocks[i]) for i in range(11)]))
                data_blocks[11] = create_section_11(raw_ani_default_data, new_s11_start_offset)
                # Create new internal file (BLDM block)
                new_bldm_block, dict_offset = create_data_block (data_blocks, new_opening_dict, addr_size, 1, 1)
                if (file_header_size + len(new_bldm_block)) % 8:
                    new_bldm_block += b'\x00' * (8 - ((file_header_size + len(new_bldm_block)) % 8))
                # Instead of overwriting backups, it will just tag a number onto the end
                backup_suffix = ''
                if os.path.exists(tomdlb_file + '.bak' + backup_suffix):
                    backup_suffix = '1'
                    if os.path.exists(tomdlb_file + '.bak' + backup_suffix):
                        while os.path.exists(tomdlb_file + '.bak' + backup_suffix):
                            backup_suffix = str(int(backup_suffix) + 1)
                    shutil.copy2(tomdlb_file, tomdlb_file + '.bak' + backup_suffix)
                else:
                    shutil.copy2(tomdlb_file, tomdlb_file + '.bak')
                with open(tomdlb_file, 'wb') as ff:
                    ff.write({'<': b'DPDF', '>': b'FDPD'}[e])
                    if addr_size == 8:
                        ff.write(struct.pack("{}I".format(e), 0))
                    ff.write(struct.pack("{}2{}".format(e, {4: "I", 8: "Q"}[addr_size]), dict_offset + (addr_size * 2 + 8),
                        len(new_opening_dict_strings)))
                    ff.write({'<': b'BLDM', '>': b'MDLB'}[e] + struct.pack("{}I".format(e), unk_int2))
                    ff.write(new_bldm_block)
                # Next write TOMDLP_P file
                backup_suffix = ''
                if os.path.exists(dlp_file + '.bak' + backup_suffix):
                    backup_suffix = '1'
                    if os.path.exists(dlp_file + '.bak' + backup_suffix):
                        while os.path.exists(dlp_file + '.bak' + backup_suffix):
                            backup_suffix = str(int(backup_suffix) + 1)
                    shutil.copy2(dlp_file, dlp_file + '.bak' + backup_suffix)
                else:
                    shutil.copy2(dlp_file, dlp_file + '.bak')
                with open(dlp_file, 'wb') as ff:
                    ff.write(dlp_block)
    return True

if __name__ == "__main__":
    # Set current directory
    if getattr(sys, 'frozen', False):
        os.chdir(os.path.dirname(sys.executable))
    else:
        os.chdir(os.path.abspath(os.path.dirname(__file__)))

    # If argument given, attempt to import into file in argument
    if len(sys.argv) > 1:
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument('tomdlb_filename', help="Name of tomdlb_d file to import into (required).")
        parser.add_argument('-s', '--swap_endian', help="Change endianness", action="store_true")
        args = parser.parse_args()
        if os.path.exists(args.tomdlb_filename) and args.tomdlb_filename[-9:].upper() == '.TOMDLB_D':
            process_tomdlb(args.tomdlb_filename, swap_endian = args.swap_endian)
    else:
        tomdlb_files = glob.glob('*.TOMDLB_D')
        tomdlb_files = [x for x in tomdlb_files if os.path.isdir(x[:-9])]
        for i in range(len(tomdlb_files)):
            process_tomdlb(tomdlb_files[i])
