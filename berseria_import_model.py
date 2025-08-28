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
except ModuleNotFoundError as e:
    print("Python module missing! {}".format(e.msg))
    input("Press Enter to abort.")
    raise

# Global variables, do not edit
addr_size = 8

# Input is a list of bytes / bytearrays.
# Internal block is a first data block not in the table of contents, e.g. opening dict in BLDM
# Returns the block, as well as the offset of the internal block
def create_data_block (data_list, internal_block = bytearray(), endian = '<',
        address_size = 8, data_alignment = 1, block_alignment = 8):
    base_offset = address_size * len(data_list) + len(internal_block)
    data_offset = [0]
    for i in range(len(data_list)):
        if len(data_list[i]) % data_alignment:
            data_list[i] += b'\x00' * (data_alignment - (len(data_list[i]) % data_alignment))
    for i in range(len(data_list)-1):
        data_offset.append(len(data_list[i]) + data_offset[i])
    final_offset = [(base_offset + data_offset[i] - ((i)*address_size)) for i in range(len(data_list))]
    offset_block = struct.pack("{0}{1}{2}".format(endian, len(final_offset), {4:"I", 8:"Q"}[address_size]),
        *final_offset)
    data_block = b''.join(data_list)
    if len(data_block) % block_alignment:
        data_block += b'\x00' * (block_alignment - (len(data_block) % block_alignment))
    return ((offset_block + internal_block + data_block), len(offset_block))

def write_string_dict (strings_list):
    enc_strings = [bytearray(x.encode()) + b'\x00' for x in strings_list]
    return create_data_block(enc_strings, b'', '<', addr_size, 2, addr_size) # Data alignment of 2 otherwise default

def read_material_data (tomdlb_file, backup_mat_block):
    # Will read data from JSON file, or load original data from the mdl file if JSON is missing
    try:
        material_struct = read_struct_from_json(tomdlb_file[:-9] + "/material_info.json")
    except:
        print("{0}/material_info.json missing or unreadable, reading data from {0}.TOMBDLB_D instead...".format(tomdlb_file[-9:]))
        with io.BytesIO(backup_mat_block) as ff:
            material_struct = read_section_7 (ff, 0)
    return material_struct

def create_section_6 (tomdlb_file, backup_mesh_block, dlp_file, material_struct, unk0 = 0, unk1 = 0):
    # We will need some information from the original block regardless, so we will read it
    with io.BytesIO(backup_mesh_block) as ff:
        original_meshes, bone_palette_ids, orig_mesh_blocks_info = read_section_6(ff, 0, dlp_file)
    # Will read data from JSON file, or load original data from the mdl file if JSON is missing
    try:
        mesh_blocks_info = read_struct_from_json(tomdlb_file[:-9] + "/mesh_info.json")
    except:
        print("{0}/mesh_info.json missing or unreadable, using data from {0}.TOMBDLB_D instead...".format(tomdlb_file[-9:]))
        mesh_blocks_info = orig_mesh_blocks_info
    material_dict = {material_struct[i]['name']: i for i in range(len(material_struct))}
    material_list = []
    sec_0 = bytearray()
    sec_1_header = bytearray()
    sec_1_header_length = (addr_size * 3 + 0x10) * len(mesh_blocks_info)
    sec_1_data = bytearray()
    uvidx_data = bytearray()
    for i in range(len(mesh_blocks_info)):
        safe_filename = "".join([x if x not in "\/:*?<>|" else "_" for x in mesh_blocks_info[i]["name"]])
        num_uvs = (mesh_blocks_info[i]["flags"] & 0xF)
        try:
            mesh_filename = tomdlb_file[:-9] + '/{0:02d}_{1}'.format(i, safe_filename)
            fmt = read_fmt(mesh_filename + '.fmt')
            ib = stripify(read_ib(mesh_filename + '.ib', fmt), stitchstrips = True)[0]
            vb = read_vb(mesh_filename + '.vb', fmt)
            assert ([x['SemanticName'] for x in fmt['elements']]
                == ['POSITION', 'NORMAL']
                + ['TEXCOORD'] * num_uvs
                + ['BLENDWEIGHTS', 'BLENDINDICES'])
            assert (int(fmt['stride']) == 44 + (8 * (mesh_blocks_info[i]["flags"] & 0xF)))
        except (FileNotFoundError, AssertionError) as e:
            print("Submesh {0} not found or corrupt, generating an empty submesh...".format(mesh_filename))
            # Generate an empty submesh
            fmt = make_fmt(num_uvs, has_weights = True)
            ib = [0,0,0]
            vb = [{'Buffer':[[0.0, 0.0, 0.0]]}, {'Buffer':[[0.0, 0.0, 0.0]]}]
            vb.extend([{'Buffer':[[0.0, 0.0]]} for _ in range(num_uvs)])
            vb.extend([{'Buffer':[[1.0, 0.0, 0.0, 0.0]]}, {'Buffer':[[0, 0, 0, 0]]}])
        print("Processing submesh {0}...".format(mesh_filename))
        try:
            material_list.append(material_dict[mesh_blocks_info[i]["material"]])
        except KeyError: # Try legacy metadata format
            try:
                material = read_struct_from_json(tomdlb_file[:-9] + '/{0:02d}_{1}.material'.format(i, safe_filename))
                material_list.append(material_dict[material['material']])
            except:
                print("Unable to read material for {}!  The material assignment is either missing or invalid.".format(safe_filename))
                input("Press Enter to quit.")
                raise
        # I don't know what these are, in the sample models they are always 0.  Might be for non-mesh TOMDLB_D's
        sec_0.extend(struct.pack("<4I", 0, 0, 0, 0))
        # Add basic data
        sec_1_header.extend(struct.pack("<i4hi", mesh_blocks_info[i]["mesh"], mesh_blocks_info[i]["submesh"],
            mesh_blocks_info[i]["node"], mesh_blocks_info[i]["flags"], material_list[-1],
            mesh_blocks_info[i]["unknown"]))
        data_block_start = len(sec_1_data)
        # Add mesh name
        offset = sec_1_header_length - len(sec_1_header) + len(sec_1_data)
        sec_1_header.extend(struct.pack("<{}".format({4: "I", 8: "Q"}[addr_size]), offset))
        sec_1_data.extend(mesh_blocks_info[i]["name"].encode()+b'\x00')
        if len(sec_1_data) % 4:
            sec_1_data += b'\x00' * (4 - (len(sec_1_data) % 4))
        # Add mesh data
        offset = sec_1_header_length - len(sec_1_header) + len(sec_1_data)
        sec_1_header.extend(struct.pack("<{}".format({4: "I", 8: "Q"}[addr_size]), offset))
        # Standard weighted meshes
        if mesh_blocks_info[i]["flags"] & 0xF0 == 0x50:
            # Split vertices into weight types
            vgrp = [4 if not x[3]==0.0 else 3 if not x[2]==0.0 else 2 if not x[1]==0.0 else 1 for x in vb[-2]['Buffer']]
            v_by_grp = [[k for k, vgrpval in enumerate(vgrp) if vgrpval == j] for j in range(1,5)]
            new_v_assgn = {}
            counter = 0
            for j in range(len(v_by_grp)):
                for k in range(len(v_by_grp[j])):
                    new_v_assgn[v_by_grp[j][k]] = counter
                    counter += 1
            new_ib = [new_v_assgn[x] for x in ib]
            submesh_datablock = bytearray()
            submesh_datablock.extend(struct.pack("<4I", *[len(x) for x in v_by_grp]))
            uv_block = bytearray()
            for j in range(len(v_by_grp)):
                for k in range(len(v_by_grp[j])):
                    submesh_datablock.extend(struct.pack("<3f", *vb[0]['Buffer'][v_by_grp[j][k]])) # Vertices
                    submesh_datablock.extend(struct.pack("<3f", *vb[1]['Buffer'][v_by_grp[j][k]])) # Normals
                    submesh_datablock.extend(struct.pack("<4B", *vb[-1]['Buffer'][v_by_grp[j][k]])) # Blend indices
                    if j > 0:
                        submesh_datablock.extend(struct.pack("<{}f".format(j),
                            *vb[-2]['Buffer'][v_by_grp[j][k]][:j])) # Blend weights
                    uv_block.extend(struct.pack("<i", -1)) # Padding
                    for l in range(num_uvs):
                        uv_block.extend(struct.pack("<2f", *vb[2+l]['Buffer'][v_by_grp[j][k]])) # UVs
            new_ib_block = bytearray(struct.pack("<{}H".format(len(new_ib)), *new_ib)) # Triangles
            if len(new_ib_block) % 4:
                new_ib_block += b'\x00' * (4 - (len(new_ib_block) % 4))
            sec_1_data.extend(struct.pack("<2HI", len(vb[0]['Buffer']), len(new_ib), len(uvidx_data)))
            uvidx_data.extend(uv_block)
            sec_1_data.extend(struct.pack("<I", len(uvidx_data)))
            uvidx_data.extend(new_ib_block)
            sec_1_data.extend(submesh_datablock)
            sec_1_header.extend(struct.pack("<{}".format({4: "I", 8: "Q"}[addr_size]), len(submesh_datablock) + 0xC))
        # Unweighted meshes
        elif mesh_blocks_info[i]["flags"] & 0xF0 == 0x0:
            uv_block = bytearray()
            for j in range(len(vb[0]['Buffer'])):
                uv_block.extend(struct.pack("<3f", *vb[0]['Buffer'][j])) # Vertices
                uv_block.extend(struct.pack("<3f", *vb[1]['Buffer'][j])) # Normals
                uv_block.extend(struct.pack("<i", -1)) # Padding
                for l in range(num_uvs):
                    uv_block.extend(struct.pack("<2f", *vb[2+l]['Buffer'][j])) # UVs
            new_ib_block = bytearray(struct.pack("<{}H".format(len(ib)), *ib)) # Triangles
            if len(new_ib_block) % 4:
                new_ib_block += b'\x00' * (4 - (len(new_ib_block) % 4))
            sec_1_data.extend(struct.pack("<2HI", len(vb[0]['Buffer']), len(ib), len(uvidx_data)))
            uvidx_data.extend(uv_block)
            sec_1_data.extend(struct.pack("<I", len(uvidx_data)))
            uvidx_data.extend(new_ib_block)
            sec_1_data.extend(struct.pack("<5I", 0, 0, 0, 0, 0))
            sec_1_header.extend(struct.pack("<{}".format({4: "I", 8: "Q"}[addr_size]), 0x20))
        # Unsupported mesh type, e.g. 0x70 mesh
        else:
            return False, False
    sec_1 = sec_1_header + sec_1_data
    sec_2 = bytearray(struct.pack("<{}I".format(len(bone_palette_ids)), *bone_palette_ids))
    sec_3 = struct.pack("<2I", len(mesh_blocks_info), len(bone_palette_ids))
    # Build offset header
    block_lengths = [len(sec_0), len(sec_1), len(sec_2), len(sec_3)]
    block_offsets = [sum(block_lengths[:i], (addr_size * 8)-((addr_size * 2) * i)) if block_lengths[i] > 0 else 0
        for i in range(len(block_lengths))]
    block_counts = [len(mesh_blocks_info), len(mesh_blocks_info), len(bone_palette_ids), 1]
    block_header = bytearray()
    block_header.extend(struct.pack("<4I", unk0, unk1, 0, 0))
    for i in range(4):
        block_header.extend(struct.pack("<2{}".format({4: "I", 8: "Q"}[addr_size]), block_offsets[i], block_counts[i]))
    section_6 = bytearray(block_header + sec_0 + sec_1 + sec_2 + sec_3)
    if len(section_6) % addr_size:
        section_6 += b'\x00' * (addr_size - (len(section_6) % addr_size))
    return(section_6, uvidx_data)

# I have no idea what the first two integers in the block (unk0 and unk1) are.
# They do not seem to matter, the game will still load the model if they are set to 0.
def create_section_7 (material_struct, unk0 = 0, unk1 = 0):
    all_tex = sorted(list(set([x for y in [z['textures'] for z in material_struct] for x in y])))
    tex_dict = {all_tex[i]:i for i in range(len(all_tex))}
    tex_counter = 0
    set_0_base = []
    set_1 = []
    set_2_val2 = []
    for i in range(len(material_struct)):
        set_0_base.append([material_struct[i]['internal_id']] +
            material_struct[i]['unk_parameters']['set_0_base'][0] +
            [len(material_struct[i]['textures'])] +
            material_struct[i]['unk_parameters']['set_0_base'][1] +
            [tex_counter] +
            material_struct[i]['unk_parameters']['set_0_base'][2])
        tex_counter += len(material_struct[i]['textures'])
        set_1.extend([[0, tex_dict[x], 0] for x in material_struct[i]['textures']])
        val2 = material_struct[i]['unk_parameters']['set_2_unk_1'][0]
        if 'alpha' in material_struct[i]:
            val2.append(material_struct[i]['alpha'])
        if len(material_struct[i]['unk_parameters']['set_2_unk_1']) > 1:
            val2.extend(material_struct[i]['unk_parameters']['set_2_unk_1'][1])
        set_2_val2.append(val2)
    # Build section 0 (Material parameters?)
    set_0_header_len = (addr_size * 4 + 0x18)  * len(material_struct)
    set_0_header = bytearray()
    set_0_data = bytearray()
    for i in range(len(material_struct)):
        set_0_header.extend(struct.pack("<12h", *set_0_base[i]))
        offset = set_0_header_len - len(set_0_header) + len(set_0_data)
        set_0_header.extend(struct.pack("<2{}".format({4: "I", 8: "Q"}[addr_size]), offset, len(material_struct[i]['unk_parameters']['set_0_unk_0'])))
        set_0_data.extend(struct.pack("<{}I".format(len(material_struct[i]['unk_parameters']['set_0_unk_0'])),
            *material_struct[i]['unk_parameters']['set_0_unk_0']))
        offset = set_0_header_len - len(set_0_header) + len(set_0_data)
        set_0_header.extend(struct.pack("<2{}".format({4: "I", 8: "Q"}[addr_size]), offset, len(material_struct[i]['unk_parameters']['set_0_unk_1'])))
        if len(material_struct[i]['unk_parameters']['set_0_unk_1']) == 0x17:
            set_0_data.extend(struct.pack("<8I4f4If6I".format(len(material_struct[i]['unk_parameters']['set_0_unk_1'])),
                *material_struct[i]['unk_parameters']['set_0_unk_1']))
        else:
            set_0_data.extend(struct.pack("<{}I".format(len(material_struct[i]['unk_parameters']['set_0_unk_1'])),
                *material_struct[i]['unk_parameters']['set_0_unk_1']))
    set_0_block = set_0_header + set_0_data
    # Build section 1 (Texture Pointers)
    set_1_block = bytearray()
    for i in range(len(set_1)):
        set_1_block.extend(struct.pack("<3h", *set_1[i]))
    if len(set_1_block) % addr_size:
        set_1_block += b'\x00' * (addr_size - (len(set_1_block) % addr_size))
    # Build section 2 (Material name, etc)
    set_2_header_len = (addr_size * 5) * len(material_struct)
    set_2_header = bytearray()
    set_2_data = bytearray()
    for i in range(len(material_struct)):
        offset = set_2_header_len - len(set_2_header) + len(set_2_data)
        set_2_header.extend(struct.pack("<2{}".format({4: "I", 8: "Q"}[addr_size]), offset, len(material_struct[i]['unk_parameters']['set_2_unk_0'])))
        set_2_data.extend(struct.pack("<{}I".format(len(material_struct[i]['unk_parameters']['set_2_unk_0'])),
            *material_struct[i]['unk_parameters']['set_2_unk_0']))
        offset = set_2_header_len - len(set_2_header) + len(set_2_data)
        set_2_header.extend(struct.pack("<2{}".format({4: "I", 8: "Q"}[addr_size]), offset, len(set_2_val2[i])))
        set_2_data.extend(struct.pack("<{}I".format(len(set_2_val2[i])), *set_2_val2[i]))
        offset = set_2_header_len - len(set_2_header) + len(set_2_data)
        set_2_header.extend(struct.pack("<{}".format({4: "I", 8: "Q"}[addr_size]), offset))
        set_2_data.extend(material_struct[i]['name'].encode()+b'\x00')
        if len(set_2_data) % 4:
            set_2_data += b'\x00' * (4 - (len(set_2_data) % 4))
    set_2_block = set_2_header + set_2_data
    # Build section 6 (Textures)
    set_6_header_len = (addr_size + {4: 4, 8: 16}[addr_size]) * len(all_tex)
    set_6_header = bytearray()
    set_6_data = bytearray()
    for i in range(len(all_tex)):
        offset = set_6_header_len - len(set_6_header) + len(set_6_data)
        set_6_header.extend(struct.pack("<{}".format({4: "I", 8: "Q"}[addr_size]), offset))
        set_6_data.extend(all_tex[i].encode()+b'\x00')
        if len(set_6_data) % 2:
            set_6_data += b'\x00' * (2 - (len(set_6_data) % 2))
        set_6_header.extend(struct.pack("<2{}".format({4: "H", 8: "Q"}[addr_size]), 12, 0)) # SHORTS here in 32-bit format
    if len(set_6_data) % addr_size:
        set_6_data += b'\x00' * (addr_size - (len(set_6_data) % addr_size))
    set_6_block = set_6_header + set_6_data
    # Build offset header
    block_lengths = [len(set_0_block), len(set_1_block), len(set_2_block), 0, 0, 0, len(set_6_block)]
    block_offsets = [sum(block_lengths[:i], (addr_size * 14)-((addr_size * 2) * i)) if block_lengths[i] > 0 else 0
        for i in range(len(block_lengths))]
    block_counts = [len(material_struct), len(set_1), len(material_struct), 0, 0, 0, len(all_tex)]
    block_header = bytearray()
    block_header.extend(struct.pack("<6I", unk0, unk1, 0, 0, 0, 0))
    for i in range(7):
        block_header.extend(struct.pack("<2{}".format({4: "I", 8: "Q"}[addr_size]), block_offsets[i], block_counts[i]))
    # Return assembled block
    return(block_header + set_0_block + set_1_block + set_2_block + set_6_block)

def process_tomdlb (tomdlb_file):
    global addr_size
    print("Processing {}...".format(tomdlb_file))
    with open(tomdlb_file, 'rb') as f:
        magic = f.read(4)
        if magic == b'DPDF':
            unk_int, = struct.unpack("<I", f.read(4))
            set_address_size(8)
            if not unk_int == 0:
                f.seek(4,0)
                addr_size = 4 # Zesteria, might also be other 32-bit games
                set_address_size(4)
            opening_dict = read_opening_dict (f)
            dlp_file = opening_dict[0]
            anmb_file = opening_dict[1]
            magic = f.read(4)
            if magic == b'BLDM':
                unk_int2, = struct.unpack("<I", f.read(4))
                toc = [read_offset(f) for _ in range(12)]
                data_blocks = []
                for i in range(len(toc)):
                    f.seek(toc[i])
                    if i == len(toc) - 1:
                        data_blocks.append(f.read())
                    else:
                        data_blocks.append(f.read(toc[i+1] - toc[i]))
                # Read material information (needed for both building mesh and material blocks)
                material_struct = read_material_data (tomdlb_file, data_blocks[7])
                # Create new mesh block
                mesh_unk = struct.unpack("<2I", data_blocks[6][0:8])
                data_blocks[6], dlp_block = create_section_6 (tomdlb_file, data_blocks[6],
                    dlp_file, material_struct, mesh_unk[0], mesh_unk[1])
                if dlp_block == False: # Rebuild failed, due to unsupported mesh type
                    print("Unsupported mesh detected, skipping {}...".format(tomdlb_file))
                    return False
                # Create new material block
                mat_unk = struct.unpack("<2I", data_blocks[7][0:8])
                data_blocks[7] = create_section_7 (material_struct, mat_unk[0], mat_unk[1])
                # Create new opening dictionary
                all_tex = sorted(list(set([x+'.totexb_d' for y in [z['textures'] for z in material_struct] for x in y])))
                new_opening_dict_strings = [dlp_file, anmb_file] + all_tex
                new_opening_dict = write_string_dict(new_opening_dict_strings)[0]
                # Create new internal file (BLDM block)
                new_bldm_block, dict_offset = create_data_block (data_blocks, new_opening_dict, '<', addr_size, 1, addr_size)
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
                    ff.write(b'DPDF')
                    if addr_size == 8:
                        ff.write(struct.pack("<I", 0))
                    ff.write(struct.pack("<2{}".format({4: "I", 8: "Q"}[addr_size]), dict_offset + (addr_size * 2 + 8),
                        len(new_opening_dict_strings)))
                    ff.write(b'BLDM' + struct.pack("<I", unk_int2))
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
        args = parser.parse_args()
        if os.path.exists(args.tomdlb_filename) and args.tomdlb_filename[-9:].upper() == '.TOMDLB_D':
            process_tomdlb(args.tomdlb_filename)
    else:
        tomdlb_files = glob.glob('*.TOMDLB_D')
        tomdlb_files = [x for x in tomdlb_files if os.path.isdir(x[:-9])]
        for i in range(len(tomdlb_files)):
            process_tomdlb(tomdlb_files[i])
