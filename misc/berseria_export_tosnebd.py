# Tool to export data from the binary scene files used by Tales of Berseria.
#
# Usage:  Run by itself without commandline arguments and it will search for binary scene files
# (*.TOSNEB_D) and decode them into JSON format.
#
# For command line options, run:
# /path/to/python3 berseria_export_tosnebd.py --help
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

def read_section(f, i, toc_entry):
    def read_str_array (f, offset, count):
        current_loc = f.tell()
        f.seek(offset)
        array = []
        for _ in range(count):
            array.append(read_string(f, read_offset(f)))
        f.seek(current_loc)
        return(array)
    def read_val_array (f, schema, sch_len, offset, count):
        current_loc = f.tell()
        f.seek(offset)
        array = []
        for _ in range(count):
            array.append(struct.unpack("{}{}".format(e, schema), f.read(sch_len)))
        f.seek(current_loc)
        return(array)
    def read_str_val_array (f, offset, count):
        current_loc = f.tell()
        f.seek(offset)
        array = []
        for _ in range(count):
            name_1 = read_string(f, read_offset(f))
            tell_loc = f.tell()
            offset_1 = read_offset(f)
            val_type, = struct.unpack("{}{}".format(e,{4: "I", 8: "Q"}[addr_size]), f.read(addr_size))
            val_1_1 = list(struct.unpack("{}2i".format(e), f.read(8)))
            offset_2 = read_offset(f)
            count_2, = struct.unpack("{}{}".format(e,{4: "I", 8: "Q"}[addr_size]), f.read(addr_size))
            offset_3 = read_offset(f)
            count_3, = struct.unpack("{}{}".format(e,{4: "I", 8: "Q"}[addr_size]), f.read(addr_size))
            current_loc_1 = f.tell()
            f.seek(offset_1)
            if val_type == 0:
                val_1_2, = struct.unpack("{}Q".format(e), f.read(8))
            elif val_type == 1:
                val_1_2 = struct.unpack("{}16f".format(e), f.read(64))
            elif val_type == 2:
                val_1_2 = read_string(f, read_offset(f))
            else:
                input("Unknown type at offset {}, referenced at {}!".format(hex(offset_1), hex(tell_loc)))
                #raise
            arr1, arr2 = [], []
            if count_2 > 0:
                arr1 = read_str_val_array (f, offset_2, count_2)
            if count_3 > 0:
                arr2 = read_str_val_array (f, offset_3, count_3)
            f.seek(current_loc_1)
            array.append({'name': name_1, 'values': [val_1_1, val_1_2], 'array': [arr1, arr2]})
        f.seek(current_loc)
        return(array)
    f.seek(toc_entry['offset'])
    data_list = []
    for _ in range(toc_entry['num_entries']):
        if i in [0,1,2,3,10,11,12,16]:
            name = read_string(f, read_offset(f))
        if i == 0:
            # Final 8-16 bytes seem to always be 0, so dunno why the variable length
            data = list(struct.unpack("{}4i2{}".format(e,{4: "I", 8: "Q"}[addr_size]), f.read(addr_size * 2 + 16)))
            data_list.append({'name': name, 'values': data})
        elif i == 1:
            string_1 = read_string(f, read_offset(f))
            data = list(struct.unpack("{}2I".format(e), f.read(8)))
            offset = read_offset(f)
            count, = struct.unpack("{}{}".format(e,{4: "I", 8: "Q"}[addr_size]), f.read(addr_size)) # just a guess, sample file has 1
            array = read_str_val_array(f, offset, count)
            data_list.append({'name': name, 'string_1': string_1, 'values': [data, array]})
        elif i == 2:
            val_1 = list(struct.unpack("{}3I72f3i".format(e), f.read(0x138)))
            offset = read_offset(f)
            count, = struct.unpack("{}{}".format(e,{4: "I", 8: "Q"}[addr_size]), f.read(addr_size))
            val_2 = list(struct.unpack("{}I4B2I".format(e), f.read(16)))
            val_3 = []
            if addr_size == 8:
                val_3 = list(struct.unpack("{}4I".format(e), f.read(16)))
            array = read_val_array (f, "3I", 12, offset, count)
            data_list.append({'name': name, 'values': [val_1, array, val_2, val_3]})
        elif i == 3:
            offset_1 = read_offset(f)
            count_1, = struct.unpack("{}{}".format(e,{4: "I", 8: "Q"}[addr_size]), f.read(addr_size))
            data = list(struct.unpack("{}2I".format(e), f.read(8)))
            offset_2 = read_offset(f)
            count_2, = struct.unpack("{}{}".format(e,{4: "I", 8: "Q"}[addr_size]), f.read(addr_size))
            array_1 = read_str_array (f, offset_1, count_1)
            array_2 = read_str_val_array(f, offset_2, count_2)
            data_list.append({'name': name, 'values': [data, array_1, array_2]})
        elif i == 7:
            data_list.append(list(struct.unpack("{}2H".format(e), f.read(4))))
        elif i == 8:
            data_list.append(read_string(f, read_offset(f)))
        elif i == 10:
            val1, = struct.unpack("{}{}".format(e,{4: "I", 8: "Q"}[addr_size]), f.read(addr_size))
            offset = read_offset(f)
            count, = struct.unpack("{}{}".format(e,{4: "I", 8: "Q"}[addr_size]), f.read(addr_size)) # just a guess, sample file has 1
            val2 = list(struct.unpack("{}2{}".format(e,{4: "I", 8: "Q"}[addr_size]), f.read(addr_size * 2)))
            array = read_val_array (f, "I", 4, offset, count)
            data_list.append({'name': name, 'values': [val1, array, val2]})
        elif i == 11:
            val_1 = list(struct.unpack("{}2I{}".format(e,{4: "I", 8: "Q"}[addr_size]), f.read(addr_size + 8)))
            offset = read_offset(f)
            count, = struct.unpack("{}{}".format(e,{4: "I", 8: "Q"}[addr_size]), f.read(addr_size))
            # for 64-bit, this might be u32+padding, I can't tell since 64-bit BE doesn't exist
            val_2, = struct.unpack("{}{}".format(e,{4: "I", 8: "Q"}[addr_size]), f.read(addr_size))
            array = read_str_val_array(f, offset, count)
            data_list.append({'name': name, 'values': [val_1, array, val_2]})
        elif i == 12:
            data = list(struct.unpack("{}2I".format(e), f.read(8)))
            offset = read_offset(f)
            count, = struct.unpack("{}{}".format(e,{4: "I", 8: "Q"}[addr_size]), f.read(addr_size))
            array = read_str_val_array(f, offset, count)
            data_list.append({'name': name, 'values': [data, array]})
        elif i == 13:
            data_list.append(list(struct.unpack("{}2H".format(e), f.read(4))))
        elif i == 14:
            # I've only seen count 1, so I don't know if the schema is all the offsets first then all the data,
            # or if the offsets and data are together... or if it's not possible to have more than one
            offset = read_offset(f)
            count, = struct.unpack("{}{}".format(e,{4: "I", 8: "Q"}[addr_size]), f.read(addr_size))
            array = read_val_array (f, "I", 4, offset, count)
            data_list.append({'values': array})
            # addr_size 4 has extra padding at the end
        elif i == 15:
            data_list.append(list(struct.unpack("{}Q2I".format(e), f.read(16))))
        elif i == 16:
            vals = list(struct.unpack("{}2H".format(e), f.read(4)))
            data_list.append({'name': name, 'values': vals})
            if addr_size == 8:
                f.seek(4,1) # Padding
        elif i == 17:
            data_list.extend(list(struct.unpack("{}Q".format(e), f.read(8))))
        elif i == 18:
            data_list.extend(list(struct.unpack("{}f".format(e), f.read(4))))
            # addr_size 4 has extra padding at the end - or maybe end of file is padded to 8 bytes
    return(data_list)

def read_tosnebd (scene_file):
    with open(scene_file, 'rb') as f:
        magic = f.read(4)
        if magic in [b'DPDF', b'FDPD']:
            if magic == b'FDPD':
                set_endianness('>')
            unk_int, = struct.unpack("{}I".format(e), f.read(4))
            if not unk_int == 0:
                f.seek(4,0)
                set_address_size(4) # Zestiria
            data = {}
            data['file_type'] = {'address_size': addr_size, 'endianness': e}
            data['opening_dict'] = read_opening_dict (f)
            data['unk0'] = struct.unpack("{}fI".format(e), f.read(8))
            toc = []
            for _ in range(20):
                offset = read_offset(f)
                num_entries, = struct.unpack("{}{}".format(e,{4: "I", 8: "Q"}[addr_size]), f.read(addr_size))
                toc.append({'offset': offset, 'num_entries': num_entries})
            for i in [0,1,2,3,7,8,10,11,12,13,14,15,16,17,18]:
                data['section_{0}'.format(i)] = read_section(f, i, toc[i])
            with open(scene_file + '.json', 'wb') as ff:
                ff.write(json.dumps(data, indent=4).encode('utf-8'))

if __name__ == "__main__":
    # Set current directory
    if getattr(sys, 'frozen', False):
        os.chdir(os.path.dirname(sys.executable))
    else:
        os.chdir(os.path.abspath(os.path.dirname(__file__)))

    if len(sys.argv) > 1:
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument('scene_file', help="Name of scene file to parse.")
        args = parser.parse_args()
        if os.path.exists(args.scene_file) and args.scene_file[-9:] == '.TOSNEB_D':
            read_tosnebd(args.scene_file)
    else:
        scene_files = glob.glob('*.TOSNEB_D')
        for scene_file in scene_files:
            read_tosnebd(scene_file)