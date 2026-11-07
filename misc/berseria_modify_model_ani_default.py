# Tool to scale animation root node data in a tomdlb_d format used by Tales of Berseria.
#
# Usage:  Run by itself without commandline arguments and it will replace the vectors in
# the animation default data section of the model file with values provided by JSON.
#
# The format of data is a JSON list of structures in an identical format to ani_default_info.json
# outputted by berseria_export_model.py, but should be truncated to changed values only.  The
# filename should be {.TOMDLB_D filename}_new_ani_default_data.json, for example
# CHR_BONE_LAI_ALL_000_MI.TOMDLB_D_new_ani_default_data.json if the TOMDLB_D file is
# CHR_BONE_LAI_ALL_000_MI.TOMDLB_D.
#
# For command line options, run:
# /path/to/python3 berseria_modify_model_ani_default.py --help
#
# GitHub eArmada8/berseria_model_tool

try:
    import struct, io, json, shutil, glob, os, sys
except ModuleNotFoundError as err:
    print("Python module missing! {}".format(err.msg))
    input("Press Enter to abort.")
    raise

# Global variables, do not edit
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

def read_offset_and_count (f):
    offset = read_offset (f)
    offset_count, = struct.unpack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), f.read(addr_size))
    return(offset, offset_count)

def read_string (f, start_offset):
    current_loc = f.tell()
    f.seek(start_offset)
    null_term_string = f.read(1)
    while null_term_string[-1] != 0:
        null_term_string += f.read(1)
    f.seek(current_loc)
    return(null_term_string[:-1].decode())

def read_opening_dict (f):
    dict_offset, dict_size = read_offset_and_count(f)
    opening_dict = []
    return_to_offset = f.tell()
    f.seek(dict_offset)
    for _ in range(dict_size):
        opening_dict.append(read_string(f, read_offset(f)))
    f.seek(return_to_offset)
    return(opening_dict)

# Animation target defaults, including the true bind pose and true default states for physics, animated materials, etc
def read_section_11 (f, offset, decode_data = False):
    def decode_target_flag (flag):
        return({'type': flag & 0xFFFFFFFF, 'target': flag >> 32 & 0xFFFFFF, 'category': flag >> 56})
    def decode_block_11 (data1, data2):
        decoded = [decode_target_flag(x) for x in data1]
        count = 0
        for i in range(len(decoded)):
            vec_len = decoded[i]['type'] & 0xF
            decoded[i]['vector'] = []
            for _ in range(vec_len):
                decoded[i]['vector'].append(data2[count])
                count += 1
        return(decoded)
    f.seek(offset)
    offset1, count1 = read_offset_and_count(f)
    offset2, count2 = read_offset_and_count(f)
    offset3, count3 = read_offset_and_count(f)
    f.seek(offset1)
    # data1 does not look like u64, except when looking at endianness, dunno why
    data1 = [struct.unpack("{}Q".format(e), f.read(8))[0] for _ in range(count1)]
    data2 = [struct.unpack("{}f".format(e), f.read(4))[0] for _ in range(count2)]
    if (count3 > 0):
        print("Warning! Alternate flag data found, this file will not fully decode or re-import correctly, please report.")
    if decode_data == True:
        return(decode_block_11(data1, data2))
    else:
        return([data1, data2])

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

def rebuild_ani_default_data (ani_default_data, backup_ani_default_block):
    def encode_target_flag (ani_struct):
        return((ani_struct['type']) + (ani_struct['target'] << 32) + (ani_struct['category'] << 56))
    try:
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
    except (AssertionError):
        print("Rebuild failed, using original data instead...")
        with io.BytesIO(backup_ani_default_block) as ff:
            raw_sec_11_data = read_section_11 (ff, 0, decode_data = False)
    return raw_sec_11_data

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

def read_tomdlb_to_dump_ani_default_data (tomdlb_file):
    global addr_size, e
    ani_default_data = []
    with open(tomdlb_file, 'rb') as f:
        magic = f.read(4)
        if magic in [b'DPDF', b'FDPD']:
            e, addr_size = '<', 8
            set_endianness('<')
            if magic == b'FDPD':
                set_endianness('>')
            unk_int, = struct.unpack("{}I".format(e), f.read(4))
            set_address_size(8)
            if not unk_int == 0:
                f.seek(4,0)
                set_address_size(4)
            opening_dict = read_opening_dict (f)
            magic = f.read(4)
            if magic in [b'BLDM', b'MDLB']:
                unk_int2, = struct.unpack("{}I".format(e), f.read(4))
                toc = [read_offset(f) for _ in range(12)]
                ani_default_data = read_section_11 (f, toc[11], decode_data = True)
    return(ani_default_data)

# new_default_data should look like {'type': 3, 'target': 10514, 'category': 0, 'vector': [1.0, 1.0, 1.0]}
def process_tomdlb_to_replace_ani_vector (tomdlb_file, new_default_data = []):
    global addr_size, e
    print("Processing {}...".format(tomdlb_file))
    with open(tomdlb_file, 'rb') as f:
        magic = f.read(4)
        if magic in [b'DPDF', b'FDPD']:
            e, addr_size = '<', 8
            set_endianness('<')
            if magic == b'FDPD':
                set_endianness('>')
            unk_int, = struct.unpack("{}I".format(e), f.read(4))
            set_address_size(8)
            if not unk_int == 0:
                f.seek(4,0)
                set_address_size(4)
            opening_dict = read_opening_dict (f)
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
                ani_default_data = read_section_11 (f, toc[11], decode_data = True)
                for i in range(len(new_default_data)):
                    if list(new_default_data[i].keys()) == ['type', 'target', 'category', 'vector']:
                        ani_entry_find = [j for j in range(len(ani_default_data))
                            if ani_default_data[j]['type'] == new_default_data[i]['type']
                            and ani_default_data[j]['target'] == new_default_data[i]['target']
                            and ani_default_data[j]['category'] == new_default_data[i]['category']]
                        if len(ani_entry_find) > 0:
                            ani_entry = ani_entry_find[0]
                            if len(ani_default_data[ani_entry]['vector']) == len(new_default_data[i]['vector']):
                                print("Animation default entry found, replacing vector.")
                                ani_default_data[ani_entry]['vector'] = new_default_data[i]['vector']
                            else:
                                print("Error: New vector length incorrect, aborting.")
                                return False
                        else:
                            print("Error: Matching node not found, aborting.")
                            return False
                    else:
                        print("Error: Data to insert is not in the correct format, aborting.")
                        return False
                raw_ani_default_data = rebuild_ani_default_data (ani_default_data, data_blocks[11])
                # Create new opening dictionary
                new_opening_dict = write_string_dict(opening_dict)[0]
                # Create new animation default data block
                new_s11_start_offset = (4 + (4 if addr_size == 8 else 0) + (2 * addr_size)
                    + 8 + (12 * addr_size) + len(new_opening_dict)
                    + sum([len(data_blocks[i]) for i in range(11)]))
                data_blocks[11] = create_section_11(raw_ani_default_data, new_s11_start_offset)
                # Create new internal file (BLDM block)
                new_bldm_block, dict_offset = create_data_block (data_blocks, new_opening_dict, addr_size, 1, 1)
                file_header_size = 4 + (4 if addr_size == 8 else 0) + (2 * addr_size) + 8
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
                        len(opening_dict)))
                    ff.write({'<': b'BLDM', '>': b'MDLB'}[e] + struct.pack("{}I".format(e), unk_int2))
                    ff.write(new_bldm_block)
    return

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
        parser.add_argument('tomdlb_filename', help="Name of tomdlb_d file to import values into (required).")
        args = parser.parse_args()
        if os.path.exists(args.tomdlb_filename) and args.tomdlb_filename[-9:].upper() == '.TOMDLB_D':
            json_file = args.tomdlb_filename+'_new_ani_default_data.json'
            try:
                new_default_data = json.loads(open(json_file, 'rb').read())
                process_tomdlb_to_replace_ani_vector (args.tomdlb_filename, new_default_data)
            except (FileNotFoundError):
                raw_input = input("{} missing or unreadable, dump out a full list? [y/N] ".format(os.path.basename(json_file)))
                if raw_input.strip().upper().startswith('Y'):
                    ani_default_data = read_tomdlb_to_dump_ani_default_data(args.tomdlb_filename)
                    if len(ani_default_data) > 0:
                        open(json_file, 'wb').write(json.dumps(ani_default_data, indent = 4).encode())
                    else:
                        print("Error, no animation default data found in {}.  Aborting.".format(
                            os.path.basename(args.tomdlb_filename)))
            except json.JSONDecodeError as err:
                print("Error: {}".format(err))
                print("{} unreadable, skipping...".format(json_file))
    else:
        tomdlb_files = glob.glob('*.TOMDLB_D')
        tomdlb_files = [x for x in tomdlb_files if os.path.exists(x+'_new_ani_default_data.json')]
        for tomdlb_file in tomdlb_files:
            json_file = tomdlb_file+'_new_ani_default_data.json'
            try:
                new_default_data = json.loads(open(json_file, 'rb').read())
                process_tomdlb_to_replace_ani_vector (tomdlb_file, new_default_data)
            except (json.JSONDecodeError):
                print("{} unreadable, skipping...".format(json_file))