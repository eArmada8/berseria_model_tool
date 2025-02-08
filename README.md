# Tales of Berseria mesh export
A script to get the mesh data out of the files from Tales of Berseria.  The output is in .glb files, although there is an option for .fmt/.ib/.vb/.vgmap that are compatible with DarkStarSword Blender import plugin for 3DMigoto.  This is theoretically a work in progress since I'd like to actually mod the game, but there are quite a few hurdles to overcome and so there may never be an update for this.

## Credits:
I am as always very thankful for the dedicated reverse engineers at the Kiseki modding discord, for their brilliant work, and for sharing that work so freely.

## Requirements:
1. Python 3.10 and newer is required for use of these scripts.  It is free from the Microsoft Store, for Windows users.  For Linux users, please consult your distro.
2. The numpy module for python is needed.  Install by typing "python3 -m pip install numpy" in the command line / shell.  (The struct, json, glob, copy, os, sys, and argparse modules are also required, but these are all already included in most basic python installations.)
3. The output can be imported into Blender as .glb, or as raw buffers using DarkStarSword's amazing plugin: https://github.com/DarkStarSword/3d-fixes/blob/master/blender_3dmigoto.py (tested on commit [5fd206c](https://raw.githubusercontent.com/DarkStarSword/3d-fixes/5fd206c52fb8c510727d1d3e4caeb95dac807fb2/blender_3dmigoto.py))
4. berseria_export_model.py is dependent on lib_fmtibvb.py, which must be in the same folder.  

## Usage:
### berseria_export_model.py
Double click the python script and it will ask you for the dlb filename and export as .glb.  It will then guess the corresponding dlp filename (which is the next file in consecutive order), and search for a skeleton.  I recommending copying the files and skeleton to their own folder, because the skeleton search takes a long time when performed in the MDL folder (`/GAMEDATA/BASE/CHUNK0/GENERAL/COMMON/TLFILE/MDL`).  Textures should be placed in a `textures` folder, with the numerical suffix removed.

**Command line arguments:**
`berseria_export_model.py [-h] [-t] [-d] [-o] dlb_filename dlp_filename`

`-t, --textformat`
Output .gltf/.bin format instead of .glb format.

`-d, --dumprawbuffers`
Dump .fmt/.ib/.vb/.vgmap files in a folder with the same name as the .mdl file.  Use DarkStarSword's plugin to view.  Separate materials will be combined into a single mesh with this option.

`-h, --help`
Shows help message.

`-o, --overwrite`
Overwrite existing files without prompting.