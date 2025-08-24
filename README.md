# Tales of Berseria mesh tools
A script to get the mesh data in and out of the .TOMBDLB_D/.TOMDLP_P files from Tales of Berseria.  The meshes are exported as raw buffers in the .fmt/.ib/.vb/.vgmap that are compatible with DarkStarSword Blender import plugin for 3DMigoto.  A glTF file is also exported for purposes of weight painting and texture assignment, but the glTF file is not used for modding.

*NOTE:*  There are multiple mesh types, denoted by the upper four bits of the flag byte (`0x00`: not animated e.g weapons, `0x50` skeletally animated e.g. bodies, `0x70` unsure animation e.g. faces).  While berseria_export_meshes.py is able to get mesh data out of all three, a lot of data is not interpreted for `0x70` meshes and berseria_import_meshes.py cannot rebuild them.

## Tutorials:

Please see the [wiki](https://github.com/eArmada8/berseria_model_tool/wiki), and the detailed documentation below.

## Credits:
I am as always very thankful for the dedicated reverse engineers at the Kiseki modding discord, for their brilliant work, and for sharing that work so freely.  I am also very thankful to DaZombieKiller for [TalesOfTools](https://github.com/DaZombieKiller/TalesOfTools) as well as for sharing lots of knowledge about the Tales of Berseria file structure and modding.  This toolset also utilizes the tstrip module (python file format interface) adapted for [Sega_NN_tools](https://github.com/Argx2121/Sega_NN_tools/) by Argx2121, and I am grateful for its use - it is unmodified and is distributed under its original license.

## Requirements:
1. Python 3.10 and newer is required for use of these scripts.  It is free from the Microsoft Store or python.org, for Windows users.  For Linux users, please consult your distro.
2. The numpy module for python is needed.  Install by typing "python3 -m pip install numpy" in the command line / shell.  (The struct, json, glob, copy, os, sys, and argparse modules are also required, but these are all already included in most basic python installations.)
3. The output can be imported into Blender using DarkStarSword's amazing plugin: https://github.com/DarkStarSword/3d-fixes/blob/master/blender_3dmigoto.py (tested on commit [5fd206c](https://raw.githubusercontent.com/DarkStarSword/3d-fixes/5fd206c52fb8c510727d1d3e4caeb95dac807fb2/blender_3dmigoto.py))
4. berseria_export_model.py is dependent on lib_fmtibvb.py, which must be in the same folder.  berseria_import_model.py is dependent on berseria_export_model.py, lib_fmtibvb.py and the pyffi_tstrip module, all of which must be in the same folder.

## Usage:
### berseria_export_model.py
Double click the python script and it will search the current folder for all .TOMDLB_D files that are not skeletons (`BONE` is not in the name) and with its corresponding .TOMDLP_P file.  Additionally, it will output 3 JSON files, one with metadata from the mesh section, one with the data from the materials section, and (for convenience) a list of linked files (*e.g.* textures) used by the MDL.

Additionally it will output a glTF file, by default in the binary .glb format.  Textures should be placed in a `textures` folder.

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

*NOTE:* Newer versions of the Blender plugin export .vb0 files instead of .vb files.  Do not attempt to rename .vb0 files to .vb files, just leave them as-is and the scripts will look for the correct file.

**Command line arguments:**
`berseria_import_model.py [-h] tomdlb_filename`

`-h, --help`
Shows help message.

**Adding and deleting meshes**

If meshes are missing (.fmt/.ib/.vb files that have been deleted), then the script will automatically insert an empty (invisible) mesh in its place.  Metadata does not need to be altered.

The script only looks for mesh files that are listed in the `mesh_info.json`.  If you want to add a new mesh, you will need to add metadata.  So to add another mesh, add a section to the end of `mesh_info.json` like this:
```
    {
        "id_referenceonly": 0,
        "name": "HAND0_R_VEL_HUM_000_MISHAPE",
        "mesh": 2,
        "submesh": 0,
        "node": -1,
        "flags": 83,
        "unknown": 0
    },
```
`id_referenceonly` is *NOT* used by the script, the meshes are calculated by entry order starting from zero (JSON convention) e.g. the first entry is always `0`, the third entry always `2`, etc, no matter what you put in that spot.  The import script doesn't even read `id_referenceonly`; it is only there for convenience.  When exporting new meshes from Blender, be sure to adhere to the filename convention of id number with 2 digits, underscore and name.  For example, the above entry should be `00_HAND0_R_VEL_HUM_000_MISHAPE.vb` for the import script to find it.

The combination of `mesh` and `submesh` should probably be unique in the file.  Most of the time `node` is `-1`.  Flags should match the mesh you are using, with the tens digit being `8` if the mesh has weights, and the second digit being the number of UV maps in the mesh.  When figuring out the number of UV maps, it is the presence of the buffer, not whether you use them - so even if the other UV maps are blanks or repeats, they must be accounted for in the flags.  For the models this tool supports, `unknown` is almost always `0`.

Be sure to add a comma to the } for the section prior if you are using a text editor, or better yet use a dedicated JSON editor.  I actually recommend editing JSON in a dedicated editor, because python is not forgiving if you make mistakes with the JSON structure.  (Try https://jsoneditoronline.org)  Also, be sure to point material to a real section in material_info.json.  You might want to create a new section, or use an existing one.

**Changing textures and adding materials**

First look inside the .material file for the mesh you want to edit.  For example, if you want to edit the metadata for `00_HAND0_R_VEL_HUM_000_MISHAPE.vb` then it will be inside `00_HAND0_R_VEL_HUM_000_MISHAPE.material`.  If you edit the file in a text editor, you will see the assignment.  It looks like this:

```
{
    "material": "HAND1_VEL_HUM_000_MAT"
}
```

Go to material_info.json, and go that section.  For example, if "material" in mesh_info was "HAND1_VEL_HUM_000_MAT", then go to the section of material_info.json with the tag ```"name": "HAND1_VEL_HUM_000_MAT"```.  Under textures, you can change the file names.  When changing the texture filenames, do not put the `.totexd_b` extension as the tool will automatically add the extension when making the .TOMDLB_D file.

When making mods with new textures, I highly recommend giving them unique names, instead of asking the user to overwrite textures that already exist.  That way, you do not have to worry about when two or more models use the same textures.  Because the game uses a filename hashing system, be sure to check that the new filename does not accidentally overwrite an old name.  Another option is to overwrite unused textures, as Tales of Berseria has many unused assets left over from Tales of Zesteria.

**Changing the skeleton**

It is not possible to change the skeleton as the skeleton is external.

### totexp_p_to_dds.py
Double click the python script in a folder with .TOTEXP_P files and it will convert them to .dds textures.  The corresponding .TOTEXB_D files are not necessary.

### dds_to_totexp_p.py
Double click the python script in a folder with .dds files and it will convert them to .TOTEXB_D / .TOTEXP_P textures.  Replace both files at once when modding.