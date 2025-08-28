# Tool to convert .dds textures to the .totexb_d / .totexp_p format used by Tales of Zestiria.
#
# Usage:  Run by itself without commandline arguments and it convert every .dds
# file it finds into .totexb_d / .totexp_p files.
#
# GitHub eArmada8/berseria_model_tool

import struct, glob, os, sys

if __name__ == "__main__":
    # Set current directory
    if getattr(sys, 'frozen', False):
        os.chdir(os.path.dirname(sys.executable))
    else:
        os.chdir(os.path.abspath(os.path.dirname(__file__)))

    tex_files = glob.glob('*.dds')
    for tex_file in tex_files:
        with open(tex_file, 'rb') as f:
            img_dat = f.read()
        magic = img_dat[0:4].decode("ASCII")
        if magic == 'DDS ':
            header = {}
            header['dwSize'], header['dwFlags'], header['dwHeight'], header['dwWidth'],\
                    header['dwPitchOrLinearSize'], header['dwDepth'], header['dwMipMapCount']\
                    = struct.unpack("<7I", img_dat[4:32])
            tex_type = 0x100 if img_dat[0x54:0x58] == b'\x00\x00\x00\x00' else 0x300 # 1 for uncompressed, 3 for DXT1/DXT5
            with open(tex_file.split('.dds')[0]+'.TOTEXB_D', 'wb') as f:
                f.write(b'DPDF')
                # I do not know why the header width/height is 50% of the actual dimensions
                # Maybe the game does not actually use these values?
                f.write(struct.pack("<3I4H2I", 0x18, 1, 0xC8, tex_type, header['dwWidth']//2, header['dwHeight']//2, 1, 0, 4))
                f.write((tex_file.split('.dds')[0]+'.totexp_p').encode()+b'\x00')
            with open(tex_file.split('.dds')[0]+'.TOTEXP_P', 'wb') as f:
                f.write(struct.pack("<I", len(img_dat)) + img_dat)