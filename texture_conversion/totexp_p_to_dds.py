# Tool to extract .dds textures from the .totexp_p format used by Tales of Berseria.
#
# Usage:  Run by itself without commandline arguments and it convert every .totexp_p
# file it finds into a .dds file.  The corresponding .totexb_d files are not needed.
#
# GitHub eArmada8/berseria_model_tool

import struct, glob, os, sys

if __name__ == "__main__":
    # Set current directory
    if getattr(sys, 'frozen', False):
        os.chdir(os.path.dirname(sys.executable))
    else:
        os.chdir(os.path.abspath(os.path.dirname(__file__)))

    tex_files = glob.glob('*.TOTEXP_P')
    for tex_file in tex_files:
        with open(tex_file, 'rb') as f:
            size, = struct.unpack("<I", f.read(4))
            img_dat = f.read()
            assert size == len(img_dat)
        with open(tex_file.split('.TOTEXP_P')[0]+'.dds', 'wb') as f:
            f.write(img_dat)