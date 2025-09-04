# Tool to rebuild binary scene files used by Tales of Berseria.
#
# Usage:  Run by itself without commandline arguments and it will search for decoded scene files
# (*.TOSNEB_D.json) and rebuild them back into binary format.
#
# For command line options, run:
# /path/to/python3 berseria_import_tosnebd.py --help
#
# GitHub eArmada8/berseria_model_tool

try:
    import struct, json, glob, os, sys
except ModuleNotFoundError as e:
    print("Python module missing! {}".format(e.msg))
    input("Press Enter to abort.")
    raise

# Global variable, do not edit
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

def write_offset (header_size, header_block, data_block):
    offset = header_size - len(header_block) + len(data_block)
    header_block.extend(struct.pack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), offset))
    return

def create_section (data, i, starting_offset):
    # For all internal functions, data_block should be a bytearray so a pointer to data_block is passed
    def write_string (string, data_block, full_padding = True):
        data_block.extend(string.encode('utf-8')+b'\x00')
        if full_padding == True:
            if len(data_block) % addr_size:
                data_block.extend(b'\x00' * (addr_size - (len(data_block) % addr_size)))
        else:
            if len(data_block) % 2:
                data_block.extend(b'\x00' * (2 - (len(data_block) % 2)))
        return
    def write_str_array (array, data_block):
        int_header_block = bytearray()
        int_data_block = bytearray()
        int_header_size = (addr_size) * len(array)
        for k in range(len(array)):
            write_offset (int_header_size, int_header_block, int_data_block)
            write_string(array[k], int_data_block)
        if len(int_data_block) % addr_size: # I'm not sure if this is after each value or only at the end
            int_data_block.extend(b'\x00' * (addr_size - (len(int_data_block) % addr_size)))
        data_block.extend(int_header_block + int_data_block)
    def write_val_array (array, data_block, schema, sch_len):
        int_data_block = bytearray()
        for k in range(len(array)):
            int_data_block.extend(struct.pack("{}{}".format(e, schema), *array[k]))
        if len(int_data_block) % addr_size: # I'm not sure if this is after each value or only at the end
            int_data_block.extend(b'\x00' * (addr_size - (len(int_data_block) % addr_size)))
        data_block.extend(int_data_block)
    def write_str_val_array (array, data_block, starting_offset):
        int_header_block = bytearray()
        int_data_block = bytearray()
        int_header_size = (addr_size * 7 + 8) * len(array)
        for k in range(len(array)):
            write_offset (int_header_size, int_header_block, int_data_block)
            write_string(array[k]['name'], int_data_block)
            if isinstance(array[k]['values'][1], int):
                offset = starting_offset + ((addr_size * 7) * len(array)) + 8 + len(int_data_block)
                if offset % 8: # Global 8-byte alignment before u64
                    int_data_block.extend(b'\x00' * (8 - (offset % 8)))
                write_offset (int_header_size, int_header_block, int_data_block)
                int_data_block.extend(struct.pack("{}Q".format(e), array[k]['values'][1]))
                val_type = 0
            elif isinstance(array[k]['values'][1], list) and len(array[k]['values'][1]) == 16:
                write_offset (int_header_size, int_header_block, int_data_block)
                int_data_block.extend(struct.pack("{}16f".format(e), *array[k]['values'][1]))
                val_type = 1
            elif isinstance(array[k]['values'][1], str):
                write_offset (int_header_size, int_header_block, int_data_block)
                int_data_block.extend(struct.pack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), addr_size))
                write_string(array[k]['values'][1], int_data_block)
                val_type = 2
            int_header_block.extend(struct.pack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), val_type))
            int_header_block.extend(struct.pack("{}2i".format(e), *array[k]['values'][0][:2]))
            if len(array[k]['array'][0]) > 0:
                write_offset(int_header_size, int_header_block, int_data_block)
                int_header_block.extend(struct.pack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), len(array[k]['array'][0])))
                write_str_val_array(array[k]['array'][0], int_data_block, starting_offset + int_header_size + len(int_data_block))
            else:
                int_header_block.extend(struct.pack("{}2{}".format(e, {4: "I", 8: "Q"}[addr_size]), 0, 0))
            if len(array[k]['array'][1]) > 0:
                write_offset(int_header_size, int_header_block, int_data_block)
                int_header_block.extend(struct.pack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), len(array[k]['array'][1])))
                write_str_val_array(array[k]['array'][1], int_data_block, starting_offset + int_header_size + len(int_data_block))
            else:
                int_header_block.extend(struct.pack("{}2{}".format(e, {4: "I", 8: "Q"}[addr_size]), 0, 0))
        data_block.extend(int_header_block + int_data_block)
        return
    header_block = bytearray()
    data_block = bytearray()
    header_size = ((addr_size * 3 + 16) * len(data) if i == 0 else
                   (addr_size * 4 + 8)  * len(data) if i == 1 else
                   (addr_size * 3 + 328 + (16 if addr_size == 8 else 0)) * len(data) if i == 2 else
                   (addr_size * 5 + 8)  * len(data) if i == 3 else
                   4 * len(data) if i == 7 else
                   addr_size  * len(data) if i == 8 else
                   (addr_size * 6)  * len(data) if i == 10 else
                   (addr_size * 5 + 8)  * len(data) if i == 11 else
                   (addr_size * 3 + 8)  * len(data) if i == 12 else
                   4 * len(data) if i == 13 else
                   (addr_size * 2)  * len(data) if i == 14 else
                   16 * len(data) if i == 15 else
                   (addr_size + 4 + (4 if addr_size == 8 else 0)) * len(data) if i == 16 else
                   8 * len(data) if i == 17 else
                   4 * len(data) if i == 18 else
                   0)
    for j in range(len(data)):
        if i in [0,1,2,3,10,11,12,16]:
            write_offset(header_size, header_block, data_block)
            full_padding = False if i in [1,16] else True
            write_string(data[j]['name'], data_block, full_padding = full_padding)
        if i == 0:
            header_block.extend(struct.pack("{}4i2{}".format(e,{4: "I", 8: "Q"}[addr_size]), *data[j]['values']))
        elif i == 1:
            write_offset(header_size, header_block, data_block)
            write_string(data[j]['string_1'], data_block)
            header_block.extend(struct.pack("{}2I".format(e), *data[j]['values'][0]))
            write_offset(header_size, header_block, data_block)
            header_block.extend(struct.pack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), len(data[j]['values'][1])))
            write_str_val_array(data[j]['values'][1], data_block, starting_offset + header_size + len(data_block))
        elif i == 2:
            header_block.extend(struct.pack("{}3I72f3i".format(e), *data[j]['values'][0]))
            if len(data[j]['values'][1]) > 0:
                write_offset(header_size, header_block, data_block)
                header_block.extend(struct.pack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), len(data[j]['values'][1])))
                write_val_array (data[j]['values'][1], data_block, "3I", 12)
            else:
                header_block.extend(struct.pack("{}2{}".format(e, {4: "I", 8: "Q"}[addr_size]), 0, 0))
            header_block.extend(struct.pack("{}I4B2I".format(e), *data[j]['values'][2]))
            if addr_size == 8:
                header_block.extend(struct.pack("{}4I".format(e), *data[j]['values'][3]))
        elif i == 3:
            write_offset(header_size, header_block, data_block)
            header_block.extend(struct.pack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), len(data[j]['values'][1])))
            write_str_array (data[j]['values'][1], data_block)
            header_block.extend(struct.pack("{}2I".format(e), *data[j]['values'][0]))
            write_offset(header_size, header_block, data_block)
            header_block.extend(struct.pack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), len(data[j]['values'][2])))
            write_str_val_array (data[j]['values'][2], data_block, starting_offset + header_size + len(data_block))
        elif i == 7:
            header_block.extend(struct.pack("{}2H".format(e), *data[j]))
        elif i == 8:
            write_offset(header_size, header_block, data_block)
            if j < (len(data) - 1):
                write_string(data[j], data_block, full_padding = False)
            else:
                write_string(data[j], data_block, full_padding = True)
        elif i == 10:
            header_block.extend(struct.pack("{}{}".format(e,{4: "I", 8: "Q"}[addr_size]), data[j]['values'][0]))
            write_offset(header_size, header_block, data_block)
            header_block.extend(struct.pack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), len(data[j]['values'][1])))
            write_val_array(data[j]['values'][1], data_block, "I", 4)
            header_block.extend(struct.pack("{}2{}".format(e,{4: "I", 8: "Q"}[addr_size]), *data[j]['values'][2]))
        elif i == 11:
            header_block.extend(struct.pack("{}2I{}".format(e,{4: "I", 8: "Q"}[addr_size]), *data[j]['values'][0]))
            write_offset(header_size, header_block, data_block)
            header_block.extend(struct.pack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), len(data[j]['values'][1])))
            write_str_val_array(data[j]['values'][1], data_block, starting_offset + header_size + len(data_block))
            header_block.extend(struct.pack("{}{}".format(e,{4: "I", 8: "Q"}[addr_size]), data[j]['values'][2]))
        elif i == 12:
            header_block.extend(struct.pack("{}2I".format(e,), *data[j]['values'][0]))
            write_offset(header_size, header_block, data_block)
            header_block.extend(struct.pack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), len(data[j]['values'][1])))
            write_str_val_array(data[j]['values'][1], data_block, starting_offset + header_size + len(data_block))
        elif i == 13:
            header_block.extend(struct.pack("{}2H".format(e), *data[j]))
        elif i == 14:
            if len(data[j]['values']) > 0:
                write_offset(header_size, header_block, data_block)
                header_block.extend(struct.pack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), len(data[j]['values'])))
            else:
                header_block.extend(struct.pack("{}2{}".format(e, {4: "I", 8: "Q"}[addr_size]), 0, 0))
            write_val_array(data[j]['values'], data_block, "I", 4)
        elif i == 15:
            header_block.extend(struct.pack("{}Q2I".format(e), *data[j]))
        elif i == 16:
            header_block.extend(struct.pack("{}2H".format(e), *data[j]['values']))
            if addr_size == 8:
                header_block.extend(struct.pack("{}I".format(e), 0))
        elif i == 17:
            header_block.extend(struct.pack("{}Q".format(e), data[j]))
        elif i == 18:
            header_block.extend(struct.pack("{}f".format(e), data[j]))
    return(header_block + data_block)

def create_tosnebd (scene_data):
    header_size = addr_size * 44 + (4 if addr_size == 4 else 0)
    data_block = bytearray()
    header_block = bytearray()
    header_block.extend({'<': b'DPDF', '>': b'FDPD'}[e])
    if addr_size == 8:
        header_block.extend(struct.pack("{}I".format(e), 0))
    write_offset (header_size, header_block, data_block)
    header_block.extend(struct.pack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), len(scene_data['opening_dict'])))
    header_block.extend(struct.pack("{}fI".format(e), *scene_data['unk0']))
    data_block.extend(write_string_dict(scene_data['opening_dict'])[0])
    to_align = [14] if addr_size == 4 else [7,13,14]
    for i in range(20):
        if 'section_{}'.format(i) in scene_data and len(scene_data['section_{}'.format(i)]) > 0:
            write_offset (header_size, header_block, data_block)
            header_block.extend(struct.pack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), len(scene_data['section_{}'.format(i)])))
            data_block.extend(create_section(scene_data['section_{}'.format(i)], i, header_size + len(data_block)))
            if (i in to_align) and ((header_size + len(data_block)) % 8): # Block alignment
                data_block.extend(b'\x00' * (8 - ((header_size + len(data_block)) % 8)))
        else:
            header_block.extend(struct.pack("{}2{}".format(e, {4: "I", 8: "Q"}[addr_size]), 0, 0))
    if (len(header_block + data_block) % 8): # Block alignment
        data_block.extend(b'\x00' * (8 - (len(header_block + data_block) % 8)))
    return(header_block + data_block)

def write_tosnebd (scene_json_file, overwrite = True):
    global addr_size, e
    try:
        scene_data = json.loads(open(scene_json_file,'rb').read())
        assert scene_data['file_type']['address_size'] in [4,8] and scene_data['file_type']['endianness'] in ['<','>']
        addr_size = scene_data['file_type']['address_size']
        e = scene_data['file_type']['endianness']
    except:
        input("File {} is not present or readable!  Press Enter to skip.".format(scene_json_file))
        return False
    new_tosnebd = create_tosnebd(scene_data)
    if os.path.exists(scene_json_file[:-5]) and overwrite == False:
        if str(input(scene_json_file[:-5] + " exists! Overwrite? (y/N) ")).lower()[0:1] == 'y':
            overwrite = True
    if (overwrite == True) or not os.path.exists(scene_json_file[:-5]):
        open(scene_json_file[:-5], 'wb').write(new_tosnebd)
    return True

if __name__ == "__main__":
    # Set current directory
    if getattr(sys, 'frozen', False):
        os.chdir(os.path.dirname(sys.executable))
    else:
        os.chdir(os.path.abspath(os.path.dirname(__file__)))

    if len(sys.argv) > 1:
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument('-o', '--overwrite', help="Overwrite existing files", action="store_true")
        parser.add_argument('scene_json_file', help="Name of scene json file to parse.")
        args = parser.parse_args()
        if os.path.exists(args.scene_json_file) and args.scene_json_file[-14:].lower() == '.tosneb_d.json':
            write_tosnebd(args.scene_json_file, overwrite = args.overwrite)
    else:
        scene_json_files = glob.glob('*.tosneb_d.json')
        for scene_json_file in scene_json_files:
            write_tosnebd(scene_json_file)