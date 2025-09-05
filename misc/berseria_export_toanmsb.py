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

def read_tosamsb (animbin_file):
    global addr_size, e
    data = {}
    with open(animbin_file, 'rb') as f:
        print("Processing {}...".format(animbin_file))
        explore = struct.unpack("<4I", f.read(16))
        if explore[0] == 0 and explore[1] > 0:
            if explore[1] < 0x10000000:
                set_endianness('>')
            if explore[3] > 0:
                set_address_size(4) # Zestiria
        f.seek(0)
        data['file_type'] = {'address_size': addr_size, 'endianness': e}
        data['header'] = list(struct.unpack("{}If{}".format(e, {4: "I", 8: "Q"}[addr_size]), f.read(8 + addr_size)))
        offset1 = read_offset(f)
        count1a, = struct.unpack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), f.read(addr_size))
        count1b, = struct.unpack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), f.read(addr_size))
        offset2 = read_offset(f)
        count2, = struct.unpack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), f.read(addr_size))
        try:
            assert offset1 + ((count1b + 1) * addr_size) + (count1a * 16) + (4 if addr_size == 8 else 0) == offset2
        except AssertionError:
            print("Error, {} not in the expected binary format!  Skipping...".format(animbin_file))
            return
        f.seek(offset1)
        data['section_1'] = struct.unpack("{}{}{}".format(e, (count1b + 1), {4: "I", 8: "Q"}[addr_size]), f.read(addr_size * (count1b + 1)))
        if addr_size == 8:
            f.seek(4,1) # Padding
        data['section_2'] = []
        for _ in range(count1a):
            data['section_2'].append(struct.unpack("{}Q2I".format(e), f.read(16)))
        data['section_3'] = []
        for _ in range(count1a):
            data['section_3'].append(struct.unpack("{}2{}".format(e, {4: "I", 8: "Q"}[addr_size]), f.read(addr_size * 2)))
        data['section_4'] = []
        for _ in range(count2):
            flag, = struct.unpack("{}I".format(e), f.read(4))
            if not flag in [0x1003, 0x1200, 0x1300, 0x2300, 0x1402, 0x2003, 0x3003, 0x3200, 0x4003, 0x4013]:
                input("Panic!  Unknown data type {} at {}.  Press Enter to skip.".format(hex(flag), hex(f.tell()-4)))
                return
            quant = flag >> 12
            if flag & 0xF == 3:
                type_ = 'h' if flag & 0x10 else 'f'
                data['section_4'].append({'flag': flag, 'value': struct.unpack("{}{}{}".format(e, quant, type_), f.read((2 if flag & 0x10 else 4) * quant))})
            elif flag & 0xF == 2:
                arr_i = []
                for _ in range(quant):
                    count, = struct.unpack("{}I".format(e), f.read(4))
                    arr_i_i = []
                    for _ in range(count + 1):
                        arr_i_i.append(struct.unpack("{}I".format(e), f.read(4))[0])
                    arr_i.append(arr_i_i)
                data['section_4'].append({'flag': flag, 'value': arr_i})
            elif flag & 0xF == 0:
                if ((flag >> 8) & 0xF) == 3:
                    arr_i = []
                    count, = struct.unpack("{}I".format(e), f.read(4))
                    type_ = 'h' if flag & 0x10 else 'f'
                    val_1 = struct.unpack("{}f8B".format(e), f.read(12))
                    for _ in range(quant):
                        arr_i.append(struct.unpack("{}{}{}".format(e, count, type_), f.read((2 if flag & 0x10 else 4) * count)))
                elif ((flag >> 8) & 0xF) == 2:
                    arr_i = []
                    count1, = struct.unpack("{}I".format(e), f.read(4))
                    val_1 = struct.unpack("{}f{}H".format(e, count1), f.read(count1 * 2 + 4))
                    count2 = ((flag >> 12) & 0xF)
                    for _ in range(count2):
                        arr_i.append(struct.unpack("{}4f".format(e), f.read(16)))
                data['section_4'].append({'flag': flag, 'values': [val_1, arr_i]})
    with open(animbin_file + '.json', 'wb') as ff:
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
        parser.add_argument('animbin_file', help="Name of binary animation file to parse.")
        args = parser.parse_args()
        if os.path.exists(args.animbin_file) and args.animbin_file[-8:] == '.TOANMSB':
            read_tosamsb(args.animbin_file)
    else:
        animbin_files = glob.glob('*.TOANMSB')
        for animbin_file in animbin_files:
            read_tosamsb(animbin_file)