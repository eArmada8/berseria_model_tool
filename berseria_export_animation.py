# Tool to export data from the binary animation files used by Tales of Berseria.
# Thank you to Nenkai (github.com/Nenkai) for extensive help in reverse engineering
# the binary format, and Zombie (github.com/DaZombieKiller) for RE help as well!
#
# Usage:  Run by itself without commandline arguments and it will search for binary animation files
# (*.TOANMSB/*.TOANMB) and decode them into glTF format.
#
# For command line options, run:
# /path/to/python3 berseria_export_animation.py --help
#
# Requires pyquaternion, which can be installed by:
# /path/to/python3 -m pip install pyquaternion
#
# Requires berseria_export_model.py and lib_fmtibvb.py, place in the same directory
#
# GitHub eArmada8/berseria_model_tool

try:
    import math, struct, json, glob, os, sys
    from pyquaternion import Quaternion
    from berseria_export_model import *
except ModuleNotFoundError as e:
    print("Python module missing! {}".format(e.msg))
    input("Press Enter to abort.")
    raise

# Global variables, do not edit
addr_size = 8
e = '<'
file_version = 1
dct_max = 33 # This is hard-coded
ani_fps = 30

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

def set_file_version (version):
    global file_version
    if version in [0,1]:
        file_version = version
    return

def read_offset (f):
    start_offset = f.tell()
    diff_offset, = struct.unpack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), f.read(addr_size))
    return(start_offset + diff_offset)

def convert_matrix_to_trs (matrix):
    scale = [numpy.linalg.norm(matrix[0:3]), numpy.linalg.norm(matrix[4:7]),\
        numpy.linalg.norm(matrix[8:11])]
    r_mtx = numpy.array([(matrix[0:3]/scale[0]).tolist(),\
        (matrix[4:7]/scale[1]).tolist(),\
        (matrix[8:11]/scale[2]).tolist()]) # Row-major
    # Enforce orthogonality of rotation matrix, Premelani W and Bizard P "Direction Cosine Matrix IMU: Theory" Diy Drone: Usa 1 (2009).
    if (error := numpy.dot(r_mtx[0],r_mtx[1])) != 0.0:
        vectors = [r_mtx[0]-(error/2)*r_mtx[1], r_mtx[1]-(error/2)*r_mtx[0]]
        vectors.append(numpy.cross(vectors[0], vectors[1]))
        r_mtx = numpy.array([x/numpy.linalg.norm(x) for x in vectors])
    # Adapted from Day M. "Converting a Rotation Matrix to a Quaternion." Insomniac Games (13 Jan 2015)
    if (r_mtx[2][2] < 0):
        if (r_mtx[0][0] > r_mtx[1][1]):
            t = 1 + r_mtx[0][0] - r_mtx[1][1] - r_mtx[2][2]
            q = numpy.array([t, r_mtx[0][1]+r_mtx[1][0], r_mtx[2][0]+r_mtx[0][2], r_mtx[1][2]-r_mtx[2][1]])
        else:
            t = 1 - r_mtx[0][0] + r_mtx[1][1] - r_mtx[2][2]
            q = numpy.array([r_mtx[0][1]+r_mtx[1][0], t, r_mtx[1][2]+r_mtx[2][1], r_mtx[2][0]-r_mtx[0][2]])
    else:
        if (r_mtx[0][0] < -r_mtx[1][1]):
            t = 1 - r_mtx[0][0] - r_mtx[1][1] + r_mtx[2][2]
            q = numpy.array([r_mtx[2][0]+r_mtx[0][2], r_mtx[1][2]+r_mtx[2][1], t, r_mtx[0][1]-r_mtx[1][0]])
        else:
            t = 1 + r_mtx[0][0] + r_mtx[1][1] + r_mtx[2][2]
            q = numpy.array([r_mtx[1][2]-r_mtx[2][1], r_mtx[2][0]-r_mtx[0][2], r_mtx[0][1]-r_mtx[1][0], t])
    q *= 0.5 / math.sqrt(t) #xyzw
    return(matrix[12:15], q.tolist(), scale) #TRS

def decode_target_flag (flag):
    return({'type': flag & 0xFFFFFFFF, 'target': flag >> 32 & 0xFFFF, 'unknown': flag >> 48})

def read_vals (f, e, vec_len, val_sz):
    vals = list(struct.unpack("{}{}{}".format(e, vec_len, val_sz[0]), f.read(val_sz[1] * vec_len)))
    if val_sz[0] == 'h':
        norm_range = (2**15-1)
        vals = [x / norm_range for x in vals]
    return(vals)

def make_dct_table():
    dct_table = []
    for i in range(8):
        size = 4 * i + 4
        scale = math.sqrt(2 / size)
        dct_row = []
        for row in range(size):
            for col in range(size):
                dct_row.append(math.cos((row + 0.5) * (math.pi / size) * (col + 0.5)) * scale)
        dct_table.append(dct_row)
    return(dct_table)

class base_list:
    def __init__ (self, dct_header, base_all):
        self.index = 0
        self.base1 = (dct_header[0] / 0xFFFF) * base_all
        self.base2 = (dct_header[1] / 0xFFFF) * base_all
        self.base3 = (dct_header[2] / 0xFF) * self.base1 * self.base2
        self.num_base1 = dct_header[5] >> 4
        self.num_base2 = dct_header[5] & 0xF
    def get_base (self):
        if self.index < self.num_base1:
            return self.base1
        elif self.index < self.num_base2:
            return self.base2
        else:
            return self.base3
    def next_ (self):
        self.index += 1

def read_dct_segment (f, base_all, vec_len, segment_len):
    s16_max, s8_max, s4_max = (2**15-1), (2**7-1), (2**3-1)
    dct_table = make_dct_table()
    dct_data = []
    for _ in range(vec_len):
        dct_header = list(struct.unpack("{}2H4B".format(e), f.read(8)))
        n_s16, n_s8, n_s4, n_0 = dct_header[3] >> 4, dct_header[3] & 0xF, dct_header[4] >> 4, dct_header[4] & 0xF
        dct_index = n_s16 + n_s8 + n_s4 + n_0
        s16, s8, s4 = [], [], []
        for _ in range(n_s16):
            s16.append([x/s16_max for x in list(struct.unpack("{}4h".format(e), f.read(8)))])
        for _ in range(n_s8):
            s8.append([x/s8_max for x in list(struct.unpack("{}4b".format(e), f.read(4)))])
        for _ in range(n_s4 // 2):  # These are split into 2x vec4
            vals = list(struct.unpack("{}4B".format(e), f.read(4)))
            s4.append([((x >> 4) - 8) / s4_max for x in vals])
            s4.append([((x & 0xF) - 8) / s4_max for x in vals])
        dct_data.append({'header': dct_header, 'index': dct_index, 'vecs': [s16, s8, s4]})
    vectors = [[0.0 for _ in range(vec_len)]]
    for i in range(1, segment_len):
        vec = []
        for j in range(vec_len):
            baselist = base_list(dct_data[j]['header'], base_all)
            dct_sub_table = dct_table[dct_data[j]['index'] - 1]
            dct_sub_index = (4 * (i - 1) * dct_data[j]['index'])
            val = 0.0
            for k in range(len(dct_data[j]['vecs'])):
                for l in range(len(dct_data[j]['vecs'][k])):
                    val += sum([dct_data[j]['vecs'][k][l][m] * dct_sub_table[dct_sub_index + m] for m in range(4)]) * baselist.get_base()
                    baselist.next_()
                    dct_sub_index += 4
            vec.append(val)
        vectors.append(vec)
    vectors.append([0.0 for _ in range(vec_len)])
    return(vectors)

def decompress_dct (f, flag, num_indices):
    type_, val_sz, vec_len = flag & 0xF, {0:('f',4),1:('h',2)}[flag >> 4 & 0x3], flag >> 12 & 0xF
    base_all, = struct.unpack("{}f".format(e), f.read(4))
    dct_toc = [0]
    if type_ == 9: # Values are segmented as stream is too long to fit into single segment
        segments, = struct.unpack("{}H".format(e), f.read(2))
        dct_toc.extend(list(struct.unpack("{}{}H".format(e, segments - 1), f.read(2 * (segments - 1)))))
    else:
        segments = 1
    if val_sz[1] == 4:
        while f.tell() % 4:
            f.seek(1,1)
    float_table = [] # vector bases
    for _ in range(segments+1):
        float_table.extend(read_vals (f, e, vec_len, val_sz))
    dct_offsets = [(x*4) + f.tell() for x in dct_toc]
    dct_segments = []
    for i in range(segments):
        f.seek(dct_offsets[i])
        segment_len = (num_indices - (dct_max * i) - 1) if (i == segments - 1) else dct_max
        dct_segments.append(read_dct_segment(f, base_all, vec_len, segment_len))
    vecs = []
    for i in range(num_indices):
        seg_i, ii = i // dct_max, i % dct_max
        result_vec = dct_segments[seg_i][ii] if seg_i < segments else [0.0 for _ in range(vec_len)]
        static_vec = float_table[(seg_i * vec_len):((seg_i + 1) * vec_len)]
        vecs.append([result_vec[i]+static_vec[i] for i in range(vec_len)])
    return(vecs)
    
def read_vector_stream (f, num_blocks): 
    # Table of contents for animation data (offset, size)
    data_toc = []
    for _ in range(num_blocks):
        dat_offset = read_offset(f)
        dat_size, = struct.unpack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), f.read(addr_size))
        data_toc.append([dat_offset, dat_size])
    stream_data = []
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
        if type_ in [0,2]: # 0: Linear, 2: Step
            vecs = []
            for _ in range(count):
                vecs.append(read_vals (f, e, vec_len, val_sz))
            stream_data.append({'flag': flag, 'unk_float': unk_float, 'header': header, 'vecs': vecs})
        elif type_ == 3: # Single vector
            stream_data.append({'flag': flag, 'vec': read_vals (f, e, vec_len, val_sz)})
        elif type_ in [8,9]: # Vectors are compressed with discrete cosine transform (DCT)
            vecs = decompress_dct(f, flag, count)
            stream_data.append({'flag': flag, 'unk_float': unk_float, 'header': header, 'vecs': vecs})
            f.seek(data_toc[i][0] + data_toc[i][1])
        try:
            assert data_toc[i][0] + data_toc[i][1] == f.tell()
        except AssertionError:
            input("Panic!  Entry {} type {} at {} was read incorrectly!".format(i, hex(flag), hex(data_toc[i][0])))
            raise
        while f.tell() % 4:
            f.seek(1,1)
    return(stream_data)

def read_tosamsb (animbin_file):
    global addr_size, e, file_version
    data = {}
    with open(animbin_file, 'rb') as f:
        print("Processing {}...".format(animbin_file))
        explore = struct.unpack("<4I", f.read(16))
        if explore[1] > 0:
            if explore[1] < 0x10000000:
                set_endianness('>')
            if explore[3] > 0:
                set_address_size(4)
        f.seek(0)
        data['file_type'] = {'address_size': addr_size, 'endianness': e}
        data['header'] = list(struct.unpack("{}I2f".format(e), f.read(12)))
        if addr_size == 8:
            data['header'].append(struct.unpack("{}I".format(e), f.read(4))[0]) # Probably 64-bit alignment
        offset1 = read_offset(f) # Offset to the first data block (tables)
        if offset1 == 0x20:
            set_file_version(0)
        data['file_type']['version'] = file_version
        count1a, = struct.unpack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), f.read(addr_size)) # Number of data blocks
        count1b, = struct.unpack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), f.read(addr_size)) # Number of hashes
        if count1a == 0:
            print("Empty file, skipping...")
            return
        offset2 = read_offset(f) # Offset to the second data block (actual animation data)
        count2, = struct.unpack("{}{}".format(e, {4: "I", 8: "Q"}[addr_size]), f.read(addr_size)) # Number of data blocks, same as count1a
        if file_version == 1:
            data['header2'] = struct.unpack("{}2{}f".format(e, {4: "I", 8: "Q"}[addr_size]), f.read(addr_size * 2 + 4)) # Berseria only??
        try:
            assert offset1 + ((count1b + 1) * addr_size) + (count1a * 16) + (4 if file_version == 1 else 0) == offset2
        except AssertionError:
            print("Error, {} not in the expected binary format!  Skipping...".format(animbin_file))
            return
        # Hash table
        data['hash_table'] = [] # Will be rebuilt when offsets known
        temp_hash_table = [read_offset(f) for _ in range(count1b)]
        offset2b = read_offset(f) # same as offset2
        if file_version == 1:
            f.seek(4,1) # Dunno
        # Animation target data
        data['target_table'] = []
        data['decoded_target_table'] = []
        target_indices = {}
        for _ in range(count1a):
            target_indices[f.tell()] = len(target_indices)
            data['target_table'].append(struct.unpack("{}Q2I".format(e), f.read(16)))
            decode = decode_target_flag(data['target_table'][-1][0])
            decode['vec_index'] = data['target_table'][-1][1]
            data['decoded_target_table'].append(decode)
        target_indices[f.tell()] = len(target_indices)
        data['hash_table'] = [target_indices[x] for x in temp_hash_table]
        try:
            assert f.tell() == offset2 == offset2b
        except AssertionError:
            print("Error, offsets do not match!  Will attempt to proceed.")
            pass
        # Animation data
        data['data_stream'] = read_vector_stream(f, count2)
    return(data)

def write_glTF (ani_data, skel_struct, basename, write_glb = True):
    gltf_data = {}
    gltf_data['asset'] = { 'version': '2.0' }
    gltf_data['accessors'] = []
    gltf_data['animations'] = [{ 'channels': [], 'samplers': [] }]
    gltf_data['bufferViews'] = []
    gltf_data['buffers'] = []
    gltf_data['nodes'] = []
    gltf_data['scenes'] = [{}]
    gltf_data['scenes'][0]['nodes'] = [0]
    gltf_data['scene'] = 0
    gltf_data['skins'] = []
    giant_buffer = bytes()
    buffer_view = 0
    # Nodes
    for i in range(len(skel_struct)):
        t,r,s = convert_matrix_to_trs(skel_struct[i]['matrix'])
        g_node = {'children': skel_struct[i]['children'], 'name': skel_struct[i]['name']}
        if not t == [0.0, 0.0, 0.0]:
            g_node['translation'] = t
        if not r == [0.0, 0.0, 0.0, 1.0]:
            g_node['rotation'] = r
        if not s == [1.0, 1.0, 1.0]:
            g_node['scale'] = s
        gltf_data['nodes'].append(g_node)
    for i in range(len(gltf_data['nodes'])):
        if len(gltf_data['nodes'][i]['children']) == 0 and i > 0:
            del(gltf_data['nodes'][i]['children'])
    if len(gltf_data['nodes']) == 0:
        gltf_data['nodes'].append({'children': [], 'name': 'root'})
    # Animations
    node_dict = {gltf_data['nodes'][j]['name']:j for j in range(len(gltf_data['nodes']))}
    bone_id_to_name = {x['ani_id']:x['name'] for x in skel_struct}
    valid_bones = [skel_struct[i]['ani_id'] for i in range(len(skel_struct)) if skel_struct[i]['name'] in node_dict]
    ani_list = [x for x in ani_data['decoded_target_table'] if x['target'] in valid_bones and x['type'] in [0x00003, 0x10014, 0x20003]]
    for i in range(len(ani_list)):
        vec_channel = ani_data['data_stream'][ani_list[i]['vec_index']]
        outputs_raw = [vec_channel['vec']] if 'vec' in vec_channel else vec_channel['vecs']
        outputs = []
        for j in range(len(outputs_raw)):
            if ani_list[i]['type'] == 0x20003:
                if 'translation' in gltf_data['nodes'][node_dict[bone_id_to_name[ani_list[i]['target']]]]:
                    new_ = (numpy.array(outputs_raw[j])
                        + numpy.array(gltf_data['nodes'][node_dict[bone_id_to_name[ani_list[i]['target']]]]['translation']))
                    outputs.append(new_.tolist())
                else:
                    outputs.append(outputs_raw[j])
            if ani_list[i]['type'] == 0x10014:
                if 'rotation' in gltf_data['nodes'][node_dict[bone_id_to_name[ani_list[i]['target']]]]:
                    q1 = gltf_data['nodes'][node_dict[bone_id_to_name[ani_list[i]['target']]]]['rotation']
                    qp = Quaternion([q1[3]] + q1[0:3])
                    qc = Quaternion([outputs_raw[j][3]] + outputs_raw[j][0:3])
                    new_ = list(qp * qc)
                    outputs.append(new_[1:]+[new_[0]])
                else:
                    outputs.append(outputs_raw[j])
            if ani_list[i]['type'] == 0x00003:
                if 'scale' in gltf_data['nodes'][node_dict[bone_id_to_name[ani_list[i]['target']]]]:
                    new_ = (numpy.array(outputs_raw[j])
                        * numpy.array(gltf_data['nodes'][node_dict[bone_id_to_name[ani_list[i]['target']]]]['scale']))
                    outputs.append(new_.tolist())
                else:
                    outputs.append(outputs_raw[j])
        if 'header' in vec_channel:
            inputs = [x / ani_fps for x in vec_channel['header']]
        else:
            inputs = [0.0]
        sampler = { 'input': len(gltf_data['accessors']), 'interpolation': 'LINEAR', 'output':  len(gltf_data['accessors'])+1 }
        channel = { 'sampler': len(gltf_data['animations'][0]['samplers']),\
            'target': { 'node': node_dict[bone_id_to_name[ani_list[i]['target']]],
                'path': {0x20003:'translation', 0x10014:'rotation', 0x00003:'scale'}[ani_list[i]['type']] } }
        gltf_data['accessors'].append({"bufferView" : len(gltf_data['bufferViews']),\
            "componentType": 5126,\
            "count": len(inputs),\
            "type": 'SCALAR',\
            "max": [max(inputs)], "min": [min(inputs)]})
        input_buffer = numpy.array(inputs,dtype='float32').tobytes()
        gltf_data['bufferViews'].append({"buffer": 0,\
            "byteOffset": len(giant_buffer),\
            "byteLength": len(input_buffer)})                    
        giant_buffer += input_buffer
        gltf_data['accessors'].append({"bufferView" : len(gltf_data['bufferViews']),\
            "componentType": 5126,\
            "count": len(outputs),\
            "type": {0x20003:'VEC3', 0x10014:'VEC4', 0x00003:'VEC3'}[ani_list[i]['type']]})
        output_buffer = numpy.array(outputs,dtype='float32').tobytes()
        gltf_data['bufferViews'].append({"buffer": 0,\
            "byteOffset": len(giant_buffer),\
            "byteLength": len(output_buffer)})                    
        giant_buffer +=output_buffer
        gltf_data['animations'][0]['channels'].append(channel)
        gltf_data['animations'][0]['samplers'].append(sampler)
    skin = {}
    skin['skeleton'] = 0
    joints = [i for i in range(len(gltf_data['nodes'])) if i != 0]
    if len(joints) > 0:
        skin['joints'] = joints
    gltf_data['skins'].append(skin)
    gltf_data['buffers'].append({"byteLength": len(giant_buffer)})
    if write_glb == True:
        with open(basename+'.glb', 'wb') as f:
            jsondata = json.dumps(gltf_data).encode('utf-8')
            jsondata += b' ' * (4 - len(jsondata) % 4)
            f.write(struct.pack('<III', 1179937895, 2, 12 + 8 + len(jsondata) + 8 + len(giant_buffer)))
            f.write(struct.pack('<II', len(jsondata), 1313821514))
            f.write(jsondata)
            f.write(struct.pack('<II', len(giant_buffer), 5130562))
            f.write(giant_buffer)
    else:
        gltf_data['buffers'][0]["uri"] = basename+'.bin'
        with open(basename+'.bin', 'wb') as f:
            f.write(giant_buffer)
        with open(basename+'.gltf', 'wb') as f:
            f.write(json.dumps(gltf_data, indent=4).encode("utf-8"))

def process_tosamsb (animbin_file, overwrite = False, write_glb = True, dump_extra_animation_data = False):
    basename = ".".join(animbin_file.split(".")[:-1])
    ani_data = read_tosamsb (animbin_file)
    if dump_extra_animation_data == True:
        open(basename + "_ani_data.json", 'wb').write(json.dumps(ani_data, indent = 4).encode())
    try:
        full_skels = [os.path.basename(x) for x in glob.glob('*full_skeleton.json')]
        if len(full_skels) > 1:
            match = ''
            print("Multiple skeleton json files found, please choose one.")
            for i in range(len(full_skels)):
                print("{0}. {1}".format(i+1, full_skels[i]))
            while match == '':
                raw_input = input("Use which skeleton? ")
                if raw_input.isnumeric() and int(raw_input)-1 in range(len(full_skels)):
                    match = full_skels[int(raw_input)-1]
                else:
                    print("Invalid entry!")
        elif len(full_skels) == 1:
            match = full_skels[0]
        else:
            match = ''
        if not match == '':
            skel_struct = read_struct_from_json(match)
        else:
            skel_struct = combine_skeletons (find_primary_skeleton([]),[])
    except FileNotFoundError:
        input("No compatible skeleton file found!  Press Enter to quit.")
        raise
    if (os.path.exists(basename + '.gltf') or os.path.exists(basename + '.glb')) and (overwrite == False):
        if str(input(basename + ".glb/.gltf exists! Overwrite? (y/N) ")).lower()[0:1] == 'y':
            overwrite = True
    if (overwrite == True) or not (os.path.exists(basename + '.gltf') or os.path.exists(basename + '.glb')):
        write_glTF(ani_data, skel_struct, basename, write_glb = write_glb)

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
        parser.add_argument('-t', '--textformat', help="Write gltf instead of glb", action="store_false")
        parser.add_argument('-d', '--dumpanidata', help="Write extra animation data to json", action="store_true")
        parser.add_argument('animbin_file', help="Name of binary animation file to parse.")
        args = parser.parse_args()
        if (os.path.exists(args.animbin_file)
            and (args.animbin_file[-8:].lower() == '.toanmsb'
              or args.animbin_file[-7:].lower() == '.toanmb')):
            process_tosamsb(args.animbin_file, overwrite = args.overwrite, write_glb = args.textformat,\
                dump_extra_animation_data = args.dumpanidata)
    else:
        animbin_files = glob.glob('*.TOANMB') + glob.glob('*.TOANMSB')
        for animbin_file in animbin_files:
            process_tosamsb(animbin_file)