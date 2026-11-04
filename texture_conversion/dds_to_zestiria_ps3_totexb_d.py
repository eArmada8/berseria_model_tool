# Tool to convert .dds textures to the .totexb_d / .totexp_p format used by Tales of Zestiria PS3.
#
# Usage:  Run by itself without commandline arguments and it convert every .dds
# file it finds into .totexb_d / .totexp_p files.
#
# GitHub eArmada8/berseria_model_tool

import struct, glob, os, sys

def is_power_of_two(n):
    return n & (n - 1) == 0 # n and n-1 are bitflipped if n is power of 2, e.g. 0100 - 1 = 0011

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

def swizzle (texture_data, dwWidth, dwHeight, bpp):
    output = bytearray(dwHeight * dwWidth * bpp)
    for t in range(dwHeight * dwWidth):
        d = morton(t, dwWidth, dwHeight)
        output[t*bpp:(t+1)*bpp] = texture_data[d*bpp:(d+1)*bpp]
    return(output)

if __name__ == "__main__":
    # Set current directory
    if getattr(sys, 'frozen', False):
        os.chdir(os.path.dirname(sys.executable))
    else:
        os.chdir(os.path.abspath(os.path.dirname(__file__)))

    tex_files = glob.glob('*.dds')
    for tex_file in tex_files:
        with open(tex_file, 'rb') as f:
            magic = f.read(4)
            if magic == b'DDS ':
                header = {}
                header['dwSize'], header['dwFlags'], header['dwHeight'], header['dwWidth'],\
                        header['dwPitchOrLinearSize'], header['dwDepth'], header['dwMipMapCount']\
                        = struct.unpack("<7I", f.read(28))
                f.seek(44,1) # Skipping 'dwReserved1'
                pixel_format = {}
                pixel_format['dwSize'], pixel_format['dwFlags'] = struct.unpack("<2I", f.read(8))
                pixel_format['dwFourCC'] = f.read(4).decode("ASCII")
                pixel_format['dwRGBBitCount'], pixel_format['dwRBitMask'], pixel_format['dwGBitMask'],\
                    pixel_format['dwBBitMask'], pixel_format['dwABitMask'] = struct.unpack("<5I", f.read(20))
                header['pixel_format'] = pixel_format
                header['dwCaps'], header['dwCaps2'], header['dwCaps3'], header['dwCaps4'] = struct.unpack("<4I", f.read(16))
                f.seek(4,1) # Skipping 'dwReserved2'
                constant = 0xC8 # Not sure what this is, but it seems to be the same in all the games
                type_ = 0
                if header['dwDepth'] > 1:
                    type_ = 1
                if header['dwCaps2'] & 0x200:
                    type_ = 2
                    print("{} is a cube map, (probably) unsupported on PS3, skipping...".format(tex_file))
                    continue
                header['dwDepth'] = 0 if header['dwDepth'] == 1 else header['dwDepth'] # PS3 writes 2D as 0
                if pixel_format['dwFourCC'] == 'DX10':
                    print("{} is DX10, unsupported by this engine, skipping...".format(tex_file))
                    continue
                format_ = {'\x00\x00\x00\x00': 0x85, 'DXT1': 0x86, 'DXT3': 0x87, 'DXT5': 0x88}.get(pixel_format['dwFourCC'], 0xA5)
                remove_mipmaps = False
                if pixel_format['dwFourCC'] not in ['DXT1', 'DXT3', 'DXT5']:
                    if not (pixel_format['dwRGBBitCount'] == 32 and pixel_format['dwRBitMask'] == 0x00FF0000
                            and pixel_format['dwGBitMask'] == 0x0000FF00 and pixel_format['dwBBitMask'] == 0x000000FF):
                        print("Uncompressed texture {} is not A8R8G8B8, skipping...".format(tex_file))
                        continue
                    else:
                        bytes_per_pixel = 4
                if not (is_power_of_two(header['dwHeight']) and is_power_of_two(header['dwWidth'])):
                    format_ |= 0x20
                    remove_mipmaps = True # Remove mipmaps for linear textures (GUI elements etc)  
                    block_per_pixel = 8 if pixel_format['dwFourCC'] == 'DXT1' else 16
                pitch_mult = {'\x00\x00\x00\x00': 4, 'DXT1': 2, 'DXT3': 4, 'DXT5': 4}.get(pixel_format['dwFourCC'], 4)
                remap = 0xAAE4
                flags = (format_ << 24) + (pitch_mult << 16) + remap
                f.seek(128)
                if pixel_format['dwFourCC'] in ['DXT1', 'DXT3', 'DXT5']:
                    texdata = f.read()
                    if remove_mipmaps == True:
                        header['dwMipMapCount'] = 1
                        texdata = texdata[:max(1, (header['dwWidth'] + 3) // 4) * max(1, (header['dwHeight'] + 3) // 4)
                                          * block_per_pixel * max(header['dwDepth'], 1)]
                else: # ARGB8, need to flip endianness
                    texdata = bytearray()
                    for i in range(max(header['dwMipMapCount'], 1)):
                        w, h = max(1, header['dwWidth'] >> i), max(1, header['dwHeight'] >> i)
                        mip_data = bytearray()
                        for _ in range(w * h * max(header['dwDepth'] >> i, 1)):
                            pixel, = struct.unpack("<I", f.read(4))
                            if pixel_format['dwABitMask'] == 0:
                                pixel |= 0xFF000000 # Convert RGB to opaque ARGB
                            mip_data.extend(struct.pack(">I", pixel)) # endian swap
                        if remove_mipmaps == True:
                            header['dwMipMapCount'] = 1
                            texdata.extend(mip_data)
                            break # for loop only runs once, so there is only one mipmap
                        else:
                            texdata.extend(swizzle(mip_data, w, h, bytes_per_pixel))
                with open(tex_file.split('.dds')[0]+'.TOTEXB_D', 'wb') as ff:
                    ff.write(b'FDPD')
                    ff.write(struct.pack(">3I2B3H2I", 0x18, 1, constant, type_, max(1, header['dwMipMapCount']),
                        header['dwWidth'], header['dwHeight'], header['dwDepth'], flags, 4))
                    ff.write((tex_file.split('.dds')[0]+'.totexp_p').encode()+b'\x00')
                with open(tex_file.split('.dds')[0]+'.TOTEXP_P', 'wb') as ff:
                    ff.write(texdata)
