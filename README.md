# Tales of Berseria mesh tools
A script to get the mesh data in and out of the .TOMBDLB_D/.TOMDLP_P files from Tales of Berseria.  The meshes are exported as raw buffers in the .fmt/.ib/.vb/.vgmap that are compatible with DarkStarSword Blender import plugin for 3DMigoto.  A glTF file is also exported for purposes of weight painting and texture assignment, but the glTF file is not used for modding.

## Credits:
I am as always very thankful for the dedicated reverse engineers at the Kiseki modding discord, for their brilliant work, and for sharing that work so freely.  I am also very thankful to DaZombieKiller for [TalesOfTools](https://github.com/DaZombieKiller/TalesOfTools) as well as for sharing lots of knowledge about the Tales of Berseria file structure and modding.  This toolset also utilizes the tstrip module (python file format interface) adapted for [Sega_NN_tools](https://github.com/Argx2121/Sega_NN_tools/) by Argx2121, and I am grateful for its use - it is unmodified and is distributed under its original license.

## Requirements:
1. Python 3.10 and newer is required for use of these scripts.  It is free from the Microsoft Store or python.org, for Windows users.  For Linux users, please consult your distro.
2. The numpy module for python is needed.  Install by typing "python3 -m pip install numpy" in the command line / shell.  (The struct, json, glob, copy, os, sys, and argparse modules are also required, but these are all already included in most basic python installations.)
3. The output can be imported into Blender using DarkStarSword's amazing plugin: https://github.com/DarkStarSword/3d-fixes/blob/master/blender_3dmigoto.py (tested on commit [5fd206c](https://raw.githubusercontent.com/DarkStarSword/3d-fixes/5fd206c52fb8c510727d1d3e4caeb95dac807fb2/blender_3dmigoto.py))
4. berseria_export_model.py is dependent on lib_fmtibvb.py, which must be in the same folder.  berseria_import_model.py is dependent on berseria_export_model.py, lib_fmtibvb.py and the pyffi_tstrip module, all of which must be in the same folder.

## Usage:
### berseria_export_model.py
Double click the python script and it will search the current folder for all .TOMDLB_D files that are not skeletons (`BONE` is not in the name) and with its corresponding .TOMDLP_P file.  Textures should be placed in a `textures` folder.

**Command line arguments:**
`berseria_export_model.py [-h] [-t] [-s] [-o] dlb_filename dlp_filename`

`-t, --textformat`
Output the glTF model in .gltf/.bin format instead of the binary .glb format.

`-s, --skiprawbuffers`
Do not dump .fmt/.ib/.vb/.vgmap files in a folder with the same name as the .TOMDLB_D file.  These files are used for modding; this switch can be used to output only a .glb file if desired.

`-h, --help`
Shows help message.

`-o, --overwrite`
Overwrite existing files without prompting.

### berseria_import_model.py
Double click the python script and it will search the current folder for all .TOMDLB_D / .TOMDLP_P files with exported folders, and import the meshes in the folder back into the .TOMDLB_D / .TOMDLP_P files.  Additionally, it will parse the 2 JSON files (mesh metadata, materials) if available and use that information to rebuild the mesh and materials sections.  This script requires a working .TOMDLB_D file already be present as it does not reconstruct the entire file; only the known relevant sections.  The remaining parts of the file (including the skeleton) are copied unaltered from the intact .TOMDLB_D file.

It will make a backup of the originals, then overwrite the originals.  It will not overwrite backups; for example if "model.TOMDLB_D.bak" already exists, then it will write the backup to "model.TOMDLB_D.bak1", then to "model.TOMDLB_D.bak2", and so on.

**Command line arguments:**
`berseria_import_model.py [-h] tomdlb_filename`

`-h, --help`
Shows help message.
