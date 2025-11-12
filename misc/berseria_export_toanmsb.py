# Tool to export data from the binary animation files used by Tales of Berseria.
# Thank you to Nenkai (github.com/Nenkai) for extensive help in reverse engineering
# the binary format, and Zombie (github.com/DaZombieKiller) for RE help as well!
#
# Usage:  Run by itself without commandline arguments and it will search for binary animation files
# (*.TOANMSB/*.TOANMB) and decode them into JSON format.
#
# For command line options, run:
# /path/to/python3 berseria_export_toanmsb.py --help
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
        data['header'] = list(struct.unpack("{}I2f".format(e), f.read(12)))
        if addr_size == 8:
            data['header'].append(struct.unpack("{}I".format(e), f.read(4))[0]) # Probably 64-bit alignment
        offset1 = read_offset(f) # Offset to the first data block (tables)
        count1a, = struct.unpack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), f.read(addr_size)) # Number of data blocks
        count1b, = struct.unpack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), f.read(addr_size)) # Number of hashes
        if count1a == 0:
            print("Empty file, skipping...")
            return
        offset2 = read_offset(f) # Offset to the second data block (actual animation data)
        count2, = struct.unpack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), f.read(addr_size)) # Number of data blocks, same as count1a
        if addr_size == 8:
            data['header2'] = struct.unpack("{}2{}f".format(e, {4: "I", 8: "Q"}[addr_size]), f.read(addr_size * 2 + 4)) # Berseria only??
        try:
            assert offset1 + ((count1b + 1) * addr_size) + (count1a * 16) + (4 if addr_size == 8 else 0) == offset2
        except AssertionError:
            print("Error, {} not in the expected binary format!  Skipping...".format(animbin_file))
            return
        # Hash table
        data['hash_table'] = struct.unpack("{}{}{}".format(e, (count1b), {4: "I", 8: "Q"}[addr_size]), f.read(addr_size * (count1b)))
        offset2b = read_offset(f) # same as offset2
        if addr_size == 8:
            f.seek(4,1) # 64-bit alignment
        # Animation target data
        data['target_table'] = []
        for _ in range(count1a):
            data['target_table'].append(struct.unpack("{}Q2I".format(e), f.read(16)))
        try:
            assert f.tell() == offset2 == offset2b
        except AssertionError:
            print("Error, offsets do not match!  Will attempt to proceed.")
            pass
        # Table of contents for animation data (offset, size)
        data_toc = []
        for _ in range(count2):
            dat_offset = read_offset(f)
            dat_size, = struct.unpack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), f.read(addr_size))
            data_toc.append([dat_offset, dat_size])
        # Animation data
        data['data_stream'] = []
        for i in range(len(data_toc)):
            start_loc = f.tell()
            flag, = struct.unpack("{}I".format(e), f.read(4))
            # Not sure if val_sz should be f/e or f/h but f/e results in some NaN so will use f/h for now -> h might be SNORM (h / (2^15-1))
            type_, val_sz, header_type, vec_len = flag & 0xF, {0:('f',4),1:('h',2)}[flag >> 4 & 0x3], flag >> 8 & 0xF, flag >> 12 & 0xF
            header = []
            if header_type > 0:
                count, = struct.unpack("{}I".format(e), f.read(4))
                unk_float, = struct.unpack("{}f".format(e), f.read(4))
                if header_type in [1,2,3]: # 0 is no header, and 4 seems to be blank
                    header_val_sz = {1:('f',4), 2:('H',2), 3:('B',1)}[header_type]
                    header = list(struct.unpack("{}{}{}".format(e, count, header_val_sz[0]), f.read(header_val_sz[1] * count)))
                    while f.tell() % 4:
                        f.seek(1,1)
                else: # 4 is blank header, or "indexed"
                    header = list(range(count))
            try:
                assert ((type_ == 3 and header_type == 0) or (type_ in [0,2,8,9] and header_type > 0))
            except AssertionError:
                input("Panic!  Type {} at {} has an unexpected header!".format(hex(flag), hex(start_loc)))
                pass
            if type_ == 0: # List of vectors, read using linear interpolation (LERP) so header will have keys
                vecs = []
                for _ in range(count):
                    vecs.append(list(struct.unpack("{}{}{}".format(e, vec_len, val_sz[0]), f.read(val_sz[1] * vec_len))))
                data['data_stream'].append({'flag': flag, 'unk_float': unk_float, 'header': header, 'vecs': vecs})
            elif type_ == 2: # List of vectors, read as-is
                vecs = []
                for _ in range(count):
                    vecs.append(list(struct.unpack("{}{}{}".format(e, vec_len, val_sz[0]), f.read(val_sz[1] * vec_len))))
                data['data_stream'].append({'flag': flag, 'unk_float': unk_float, 'header': header, 'vecs': vecs})
            elif type_ == 3: # Single vector
                data['data_stream'].append({'flag': flag,
                    'vec': list(struct.unpack("{}{}{}".format(e, vec_len, val_sz[0]), f.read(val_sz[1] * vec_len)))})
            elif type_ in [8,9]: # Vectors are compressed with discrete cosine transform (DCT)
                unk_float2, = struct.unpack("{}f".format(e), f.read(4)) # iBRBaseAll
                dct_toc = [0]
                if type_ == 9: # Values are segmented as stream is too long to fit into single segment
                    segments, = struct.unpack("{}H".format(e), f.read(2))
                    # Pointers to the start of DCT segment - can be zero (reusing the first block)
                    dct_toc.extend(list(struct.unpack("{}{}H".format(e, segments - 1), f.read(2 * (segments - 1)))))
                else:
                    segments = 1
                if val_sz[1] == 4:
                    while f.tell() % 4:
                        f.seek(1,1)
                float_table = [] # vector bases
                for _ in range(segments+1):
                    float_table.extend(list(struct.unpack("{}{}{}".format(e, vec_len, val_sz[0]), f.read(val_sz[1] * vec_len))))
                # Segments can be reused - for parsing we will skip all the zero values (reusing block 1)
                # It might be possible I need to add sorted/list/set, but I haven't come across this yet
                true_dct_toc = [0] + [x for x in dct_toc if x > 0]
                true_segments = len(true_dct_toc)
                dct_real_toc = [(x*4) + f.tell() for x in true_dct_toc]
                dct_segments = []
                for _ in range(true_segments): # This will eventually need to expand to number of segments
                    dct_blocks = []
                    for _ in range(vec_len):
                        val0, val1, val2, num0, num1, num2 = struct.unpack("{}2H4B".format(e), f.read(8))
                        n_s16, n_s8, n_s4, n_0, n_b1, n_b2 = num0 >> 4, num0 & 0xF, num1 >> 4, num1 & 0xF, num2 >> 4, num2 & 0xF
                        dct_block = {'base_vals': [val0, val1, val2, num0, num1, num2], 's16': [], 's8': [], 's4': []}
                        for _ in range(n_s16):
                            dct_block['s16'].append(list(struct.unpack("{}4h".format(e), f.read(8))))
                        for _ in range(n_s8):
                            dct_block['s8'].append(list(struct.unpack("{}4b".format(e), f.read(4))))
                        for _ in range(n_s4 // 2):  # These actually need to be split into 2x vec4
                            dct_block['s4'].append(list(struct.unpack("{}4b".format(e), f.read(4))))
                        dct_blocks.append(dct_block)
                    dct_segments.append(dct_blocks)
                data['data_stream'].append({'flag': flag, 'unk_float': unk_float, 'header': header,
                    'unk_float2': unk_float2, 'float_table': float_table, 'dct_toc': dct_toc, 'dct_segments': dct_segments})
            try:
                assert data_toc[i][0] + data_toc[i][1] == f.tell()
            except AssertionError:
                if type_ in [8,9]: # It's usually DCT that fails...  Extra debug info.
                    print("dct_real_toc: {} f.tell: {}".format([hex(x) for x in dct_real_toc], hex(f.tell())))
                input("Panic!  Entry {} type {} at {} was read incorrectly!".format(i, hex(flag), hex(data_toc[i][0])))
                raise
            while f.tell() % 4:
                f.seek(1,1)
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
        if (os.path.exists(args.animbin_file)
            and (args.animbin_file[-8:].lower() == '.toanmsb'
              or args.animbin_file[-7:].lower() == '.toanmb')):
            read_tosamsb(args.animbin_file)
    else:
        animbin_files = glob.glob('*.TOANMB') + glob.glob('*.TOANMSB')
        for animbin_file in animbin_files:
            read_tosamsb(animbin_file)