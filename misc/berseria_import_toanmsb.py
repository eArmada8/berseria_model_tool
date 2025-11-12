# Tool to rebuild binary animation files used by Tales of Berseria.
# Thank you to Nenkai (github.com/Nenkai) for extensive help in reverse engineering
# the binary format, and Zombie (github.com/DaZombieKiller) for RE help as well!
#
# Usage:  Run by itself without commandline arguments and it will search for decoded animation files
# (*.TOANMB.json / *.TOANMSB.json) and rebuild them back into binary format.
#
# For command line options, run:
# /path/to/python3 berseria_import_toanmsb.py --help
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

def write_offset (header_size, header_block, data_block):
    offset = header_size - len(header_block) + len(data_block)
    header_block.extend(struct.pack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), offset))
    return

def create_toanmsb (anim_data):
    header_size = (12 + (4 if addr_size == 8 else 0) +
                   (addr_size * 5) + (20 if addr_size == 8 else 0))
    data_block = bytearray()
    header_block = bytearray(struct.pack("{}I2f".format(e), *anim_data['header'][:3]))
    if addr_size == 8:
        header_block.extend(bytearray(struct.pack("{}I".format(e), anim_data['header'][3])))
    write_offset(header_size, header_block, data_block) #offset1
    count1a, count1b, count2 = len(anim_data['target_table']), len(anim_data['hash_table']), len(anim_data['data_stream'])
    header_block.extend(bytearray(struct.pack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), count1a)))
    header_block.extend(bytearray(struct.pack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), count1b)))
    data_block.extend(struct.pack("{}{}{}".format(e, (count1b), {4: "I", 8: "Q"}[addr_size]), *anim_data['hash_table']))
    temp_block = bytearray()
    if addr_size == 8:
        temp_block.extend(struct.pack("{}I".format(e), 0)) # 64-bit alignment
    for i in range(count1a):
        temp_block.extend(struct.pack("{}Q2I".format(e), *anim_data['target_table'][i]))
    write_offset(len(data_block) + addr_size, data_block, temp_block) #offset2b
    data_block.extend(temp_block)
    write_offset(header_size, header_block, data_block) #offset2
    header_block.extend(bytearray(struct.pack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), count2)))
    if addr_size == 8:
        header_block.extend(struct.pack("{}2{}f".format(e, {4: "I", 8: "Q"}[addr_size]), *anim_data['header2']))
    header_block.extend(data_block)
    data_block = bytearray()
    header_size = len(header_block) + (count2 * addr_size * 2)
    for i in range(count2):
        data_ = anim_data['data_stream'][i]
        flag = data_['flag']
        temp_block = bytearray(struct.pack("{}I".format(e), flag))
        # Not sure if val_sz should be f/e or f/h but f/e results in some NaN so will use f/h for now -> h might be SNORM (h / (2^15-1))
        type_, val_sz, header_type, vec_len = flag & 0xF, {0:('f',4),1:('h',2)}[flag >> 4 & 0x3], flag >> 8 & 0xF, flag >> 12 & 0xF
        if header_type > 0:
            temp_block.extend(struct.pack("{}If".format(e), len(data_['header']), data_['unk_float']))
            if header_type in [1,2,3]:
                header_val_sz = {1:('f',4), 2:('H',2), 3:('B',1)}[header_type]
                temp_block.extend(struct.pack("{}{}{}".format(e, len(data_['header']), header_val_sz[0]), *data_['header']))
                while len(temp_block) % 4:
                    temp_block.extend(b'\x00')
        if type_ == 0: # List of vectors, read using linear interpolation (LERP) so header will have keys
            for j in range(len(data_['vecs'])):
                temp_block.extend(struct.pack("{}{}{}".format(e, vec_len, val_sz[0]), *data_['vecs'][j]))
        elif type_ == 2: # List of vectors, read as-is
            for j in range(len(data_['vecs'])):
                temp_block.extend(struct.pack("{}{}{}".format(e, vec_len, val_sz[0]), *data_['vecs'][j]))
        elif type_ == 3: # Single vector
            temp_block.extend(struct.pack("{}{}{}".format(e, vec_len, val_sz[0]), *data_['vec']))
        elif type_ in [8,9]: # Vectors are compressed with discrete cosine transform (DCT)
            temp_block.extend(struct.pack("{}f".format(e), data_['unk_float2']))
            if type_ == 9: # Values are segmented as stream is too long to fit into single segment
                temp_block.extend(struct.pack("{}H".format(e), len(data_['dct_toc'])))
                temp_block.extend(struct.pack("{}{}H".format(e, (len(data_['dct_toc'])-1)), *data_['dct_toc'][1:]))
            if val_sz[1] == 4:
                while len(temp_block) % 4:
                    temp_block.extend(b'\x00')
            temp_block.extend(struct.pack("{}{}{}".format(e, len(data_['float_table']), val_sz[0]), *data_['float_table']))
            for j in range(len(data_['dct_segments'])):
                for k in range(vec_len):
                    dct_ = data_['dct_segments'][j][k]
                    temp_block.extend(struct.pack("{}2H4B".format(e), *dct_['base_vals']))
                    for l in range(len(dct_['s16'])):
                        temp_block.extend(struct.pack("{}4h".format(e), *dct_['s16'][l]))
                    for l in range(len(dct_['s8'])):
                        temp_block.extend(struct.pack("{}4b".format(e), *dct_['s8'][l]))
                    for l in range(len(dct_['s4'])):
                        temp_block.extend(struct.pack("{}4b".format(e), *dct_['s4'][l]))
        write_offset(header_size, header_block, data_block)
        header_block.extend(struct.pack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), len(temp_block)))
        data_block.extend(temp_block)
        while len(data_block) % 4:
            data_block.extend(b'\x00')
    new_file = header_block + data_block
    if addr_size == 8:
        while len(new_file) % 8:
            new_file.extend(b'\x00')
    return(new_file)

def write_toanmsb (anim_json_file, overwrite = False):
    global addr_size, e
    try:
        anim_data = json.loads(open(anim_json_file,'rb').read())
        assert anim_data['file_type']['address_size'] in [4,8] and anim_data['file_type']['endianness'] in ['<','>']
        addr_size = anim_data['file_type']['address_size']
        e = anim_data['file_type']['endianness']
    except:
        input("File {} is not present or readable!  Press Enter to skip.".format(anim_json_file))
        return False
    new_toanmsb = create_toanmsb(anim_data)
    if os.path.exists(anim_json_file[:-5]) and overwrite == False:
        if str(input(anim_json_file[:-5] + " exists! Overwrite? (y/N) ")).lower()[0:1] == 'y':
            overwrite = True
    if (overwrite == True) or not os.path.exists(anim_json_file[:-5]):
        open(anim_json_file[:-5], 'wb').write(new_toanmsb)
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
        parser.add_argument('anim_json_file', help="Name of scene json file to parse.")
        args = parser.parse_args()
        if (os.path.exists(args.anim_json_file)
            and (args.anim_json_file[-13:].lower() == '.toanmsb.json'
              or args.anim_json_file[-12:].lower() == '.toanmb.json')):
            write_toanmsb(args.anim_json_file, overwrite = args.overwrite)
    else:
        anim_json_files = glob.glob('*.toanmsb.json') + glob.glob('*.toanmb.json')
        for anim_json_file in anim_json_files:
            write_toanmsb(anim_json_file)