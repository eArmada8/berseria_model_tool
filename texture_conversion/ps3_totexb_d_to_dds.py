# Tool to extract .dds textures from the .totexb_d format used by Tales of Symphonia PS3
# and Tales of Zestiria PS3.
#
# Usage:  Run by itself without commandline arguments and it convert every .totexb_d
# file it finds into a .dds file, using the data from .totexp_p files.
#
# GitHub eArmada8/berseria_model_tool

try:
    import struct, glob, os, sys
except ModuleNotFoundError as e:
    print("Python module missing! {}".format(e.msg))
    input("Press Enter to abort.")
    raise

# Global variable, do not edit
addr_size = 4
e = '>'

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

def morton (t, sx, sy):
    num = [1,1,t,sx,sy,0,0]
    while num[3] > 1 or num[4] > 1:
        if num[3] > 1:
            num[5] += num[1] * (num[2] & 1)
            num[2] >>= 1
            num[1] *= 2
            num[3] >>= 1
        if num[4] > 1:
            num[6] += num[0] * (num[2] & 1)
            num[2] >>= 1
            num[0] *= 2
            num[4] >>= 1
    return(num[6] * sx + num[5])

def unswizzle (texture_data, dwWidth, dwHeight, bpp):
    output = bytearray(dwHeight * dwWidth * bpp)
    data_index = 0
    for t in range(dwHeight * dwWidth):
        d = morton(t, dwWidth, dwHeight)
        output[d*bpp:(d+1)*bpp] = texture_data[t*bpp:(t+1)*bpp]
    return(output)

def write_dds_header (type_, dwMipMapCount, dwWidth, dwHeight, dwDepth, format_):
    try:
        dds_format = {0x85: 'ARGB8', 0x86: 'DXT1', 0x87: 'DXT3', 0x88: 'DXT5'}[format_ & 0x9F]
    except KeyError:
        print("Unsupported texture format: {}!".format(hex(format_)))
        return False
    block_compressed = True if dds_format in ['DXT1', 'DXT3', 'DXT5'] else False
    dwFlags, dwCaps, dwCaps2 = 0x1007, 0x1000, 0
    if block_compressed:
        dwPitchOrLinearSize = max(1,(dwWidth+3)//4) * max(1,(dwHeight+3)//4) * (8 if dds_format == 'DXT1' else 16)
        dwFlags |= 0x80000
        px_header = struct.pack("<2I", 32, 0x4) + dds_format.encode() + struct.pack("<5I", *[0]*5)
    else:
        dwPitchOrLinearSize = dwWidth * 4
        dwFlags |= 0x8
        px_header = struct.pack("<2I4s5I", 32, 0x41, b'\x00' * 4, 32,
            0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000) # Mask is little endian
    if type_ == 1 or dwDepth > 1:
        dwCaps |= 0x8
        dwCaps2 = 0x200000
        dwFlags |= 0x800000
    elif type_ == 2:
        dwCaps |= 0x8
        dwCaps2 = 0x200 | 0xFE00
    if dwMipMapCount > 1:
        dwCaps |= 0x400000 | 0x8
        dwFlags |= 0x20000
    dds_header = bytearray(b'DDS ' + struct.pack("<7I", 124, dwFlags, dwHeight, dwWidth,
        dwPitchOrLinearSize, max(dwDepth, 1), dwMipMapCount))
    dds_header.extend(struct.pack("<11I", *[0]*11))
    dds_header.extend(px_header)
    dds_header.extend(struct.pack("<5I", dwCaps, dwCaps2, 0, 0, 0))
    return(dds_header)

def process_texb (texb_file):
    print("Processing {}...".format(texb_file))
    base_name = texb_file.split('.TOTEXB_D')[0]
    with open(texb_file, 'rb') as f:
        magic = f.read(4)
        if magic == b'FDPD':
            string_ptr_offset, count = read_offset_and_count (f)
            constant, type_, mipmaps, width, height, depth, flags = struct.unpack("{}I2B3HI".format(e), f.read(16))
            format_, pitch_mult, remap = (flags >> 24) & 0xFF, (flags >> 16) & 0xFF, flags & 0xFFFF
            if not remap == 0xAAE4:
                input("{} not supported due to channel remapping.  Press Enter to skip.".format(texb_file))
                return
            f.seek(string_ptr_offset)
            tex_resource = read_string (f, read_offset (f))
            if not os.path.exists(tex_resource) and os.path.exists(tex_resource.upper()):
                tex_resource = tex_resource.upper()
            dds_header = write_dds_header(type_, mipmaps, width, height, depth, format_)
            if dds_header is False:
                return
            if os.path.exists(tex_resource):
                with open(tex_resource, 'rb') as ff:
                    if format_ & 0x9F == 0x85:
                        tex_data = bytearray()
                        bpp = 4
                        for i in range(max(mipmaps, 1)):
                            w, h = max(1, width >> i), max(1, height >> i)
                            mip_data = bytearray()
                            for _ in range(w * h):
                                mip_data.extend(struct.pack("<I", struct.unpack(">I", ff.read(4))[0]))
                            if not (format_ & 0x20):
                                mip_data = unswizzle(mip_data, w, h, bpp)
                            tex_data.extend(mip_data)
                    else:
                        tex_data = ff.read()
                    with open(base_name + '.dds', 'wb') as fff:
                        fff.write(dds_header + tex_data)
            else:
                input("{} is missing!  Press Enter to skip.".format(tex_resource))
                return

if __name__ == "__main__":
    # Set current directory
    if getattr(sys, 'frozen', False):
        os.chdir(os.path.dirname(sys.executable))
    else:
        os.chdir(os.path.abspath(os.path.dirname(__file__)))

    texb_files = glob.glob('*.TOTEXB_D')
    for texb_file in texb_files:
        process_texb (texb_file)