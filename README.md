# Tales of Berseria mesh toolset
Scripts to get the mesh data in and out of the .TOMBDLB_D/.TOMDLP_P files from Tales of Berseria, Tales of Zestiria and Tales of Symphonia Chronicles.  The meshes are exported as raw buffers in the .fmt/.ib/.vb/.vgmap that are compatible with DarkStarSword Blender import plugin for 3DMigoto.  A glTF file is also exported for purposes of weight painting and texture assignment, but the glTF file is not used for modding.

*NOTE:*  While my tool supports exporting models from both the PS3 and PC platforms, I have only testing modding (importing) on the PC games.  I have tested importing models to the PS3 format via synthetic tests, but I have not done any in-game testing.  YMMV.

## Tutorials:

Please see the [wiki](https://github.com/eArmada8/berseria_model_tool/wiki), and the detailed documentation below.

## Credits:
I am as always very thankful for the dedicated reverse engineers at the Tales of ABCDE modding discord and the Kiseki modding discord, for their brilliant work, and for sharing that work so freely.  I am also very thankful to DaZombieKiller for [TalesOfTools](https://github.com/DaZombieKiller/TalesOfTools/) as well as for sharing lots of knowledge about the Tales of Berseria / Zestiria file structure and modding.  I am also thankful to Nenkai for sharing [extensive research](https://github.com/Nenkai/TLAnimDCT/) about the animation format.  This toolset also utilizes the tstrip module (python file format interface) adapted for [Sega_NN_tools](https://github.com/Argx2121/Sega_NN_tools/) by Argx2121, and I am grateful for its use - it is unmodified and is distributed under its original license.

## AI Disclosure

I used AI (Claude, attached to ghidra) as a debugger / decompiler to help me debug persistent errors, and I wrote the code to fix those errors.

## Requirements:
1. Python 3.10 and newer is required for use of these scripts.  It is free from the Microsoft Store or python.org, for Windows users.  For Linux users, please consult your distro.
2. The numpy and pyquaternion modules for python are needed.  Install by typing "python3 -m pip install numpy pyquaternion" in the command line / shell.  (The struct, json, math, glob, copy, os, sys, and argparse modules are also required, but these are all already included in most basic python installations.)
3. The output can be imported into Blender using DarkStarSword's amazing plugin: https://github.com/DarkStarSword/3d-fixes/blob/master/blender_3dmigoto.py (tested on commit [5fd206c](https://raw.githubusercontent.com/DarkStarSword/3d-fixes/5fd206c52fb8c510727d1d3e4caeb95dac807fb2/blender_3dmigoto.py))
4. berseria_export_model.py is dependent on lib_fmtibvb.py, which must be in the same folder.  berseria_import_model.py is dependent on berseria_export_model.py, lib_fmtibvb.py and the pyffi_tstrip module, all of which must be in the same folder.

## Usage:
### berseria_export_model.py
Double click the python script and it will search the current folder for all .TOMDLB_D files that are not skeletons (`BONE` is not in the name) and with its corresponding .TOMDLP_P file.  Additionally, it will output 7 JSON files per .TOMDLB_D file that are used to reconstruct the .TOMDLB_D file:

- ani_default_info.json - Values used throughout the .TOMDLB_D file via pointer
- collision_info.json - Tracks the collision meshes
- linked_files.json - A list of all the textures used by the model
- material_info.json - All the materials information
- mesh_info.json - Mesh flags and node / materials assignments
- physics_info.json - All the physics information
- skeleton.json - All the node information

*Note:* When used without command line arguments, the script will attempt to combine all models into a single .glb - editing the configuration variable `combine_models_into_single_gltf` at the top of the script will revert the script to processing models sequentially and outputting one .glb per model.  Raw buffers are still separated by model for game modding.  The script will also output a `{MODEL NAME}_full_skeleton.json` file when used in combined model format, to be used with berseria_export_animation.py.

Additionally it will output a glTF file, by default in the binary .glb format.  Textures should be placed in a `textures` folder in .dds format (use totexp_p_to_dds.py or ps3_totexb_d_to_dds.py to convert textures).

*NOTE: The export script supports both 64-bit and 32-bit addressing, as well as little endian (PC) and big endian (PS3) encoded assets.  The import script supports both 64-bit and 32-bit addressing, and both endian formats, but only little endian (PC) encoding has been extensively tested.*

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

### berseria_export_animation.py
Double click the python script to run and it will attempt to convert the TOANMB animation into glTF (in .glb format).  The glb files can be directly imported into Blender, but Bone Dir must be set to "Blender (best for re-importing)" upon import or the skeleton will be altered irreversibly, preventing the animation from being linked to a model.  (The model should also use the same Bone Dir setting.)  This tool only supports translation, rotation and scale animation channels.  *If you run this tool on an animation that exclusively utilizes the shader varying or uv scrolling channels, you will end up with an empty .glb.  You can examine the unsupported channels in json format using the --dumpanidata command.*

*NOTE:* A compatible skeleton file must be in the folder, either in the form of a dumped skeleton (the `{MODEL NAME}_full_skeleton.json` file outputted by berseria_export_model.py) or the same binary skeleton file (.TOMDLB_D) used by berseria_export_model.py; dumped skeleton files are prioritized over binary skeleton files.  The script will only export animation channels targeted to the skeletal nodes; therefore utilizing dumped skeletons will produce a more complete animation as the model-specific physics bones will also be incorporated.  You can still use the --dumpanidata command without a skeleton to obtain all animation data in JSON format.

It will search the current folder for TOANMB/TOANMSB files and convert them all, unless you use command line options.

**Command line arguments:**
`berseria_export_animation.py [-h] [-o] [-t] [-d] animbin_file`

`-h, --help`
Shows help message.

`-o, --overwrite`
Overwrite existing files without prompting.

`-t, --textformat`
Output .gltf/.bin format instead of .glb format.

`-d, --dumpanidata`
Dump all animation data (including unused channels and unknown channel types) and the skeleton into .json files.

### berseria_import_model.py
Double click the python script and it will search the current folder for all .TOMDLB_D / .TOMDLP_P files with exported folders, and import the meshes in the folder back into the .TOMDLB_D / .TOMDLP_P files.  Additionally, it will parse the 6 JSON files (all except linked files) if available and use that information to rebuild the .TOMDLB_D file.  This script requires a working .TOMDLB_D file already be present as it does not reconstruct the entire file; only the known relevant sections.  The remaining parts of the file (including the skeleton) are copied unaltered from the intact .TOMDLB_D file.

It will make a backup of the originals, then overwrite the originals.  It will not overwrite backups; for example if "model.TOMDLB_D.bak" already exists, then it will write the backup to "model.TOMDLB_D.bak1", then to "model.TOMDLB_D.bak2", and so on.

*NOTE:* Newer versions of the Blender plugin export .vb0 files instead of .vb files.  Do not attempt to rename .vb0 files to .vb files, just leave them as-is and the scripts will look for the correct file.

**Command line arguments:**
`berseria_import_model.py [-h] tomdlb_filename`

`-s, --swap_endian`
This flag will instruct the script to rebuild a PS3 file as a PC file by changing big endian encoding to little endian.  This is tested for PS3->PC only.  (It is possible that PC->PS3 will work, but this is unverified except via synthetic tests.)

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
        "material": "HAND1_VEL_HUM_000_MAT",
        "first_morph_wt_slot": 0,
        "padding": 0,
        "sort_priority": 0,
        "sort_center": [
            0.0,
            0.0,
            0.0
        ],
        "data_block_size": 14936,
        "morph_count": 0,
        "vgmap": 0
    },
```

`id_referenceonly` is *NOT* used by the script, the meshes are calculated by entry order starting from zero (JSON convention) e.g. the first entry is always `0`, the third entry always `2`, etc, no matter what you put in that spot.  The import script doesn't even read `id_referenceonly`; it is only there for convenience.  When exporting new meshes from Blender, be sure to adhere to the filename convention of id number with 2 digits, underscore and name.  For example, the above entry should be `00_HAND0_R_VEL_HUM_000_MISHAPE.vb` for the import script to find it.

The combination of `mesh` and `submesh` should probably be unique in the file.  Most of the time `node` is `-1`.  Flags should match the mesh you are using, with the tens (hex) digit being 0x10: skinned, 0x20: morph targets, 0x40: standard world space, 0x80: bump mapping, and the ones digit being the number of UV maps in the mesh.  For example, the above is 83 (0x53) - skinned, world space, with 3 UV maps.  When figuring out the number of UV maps, it is the presence of the buffer, not whether you use them - so even if the other UV maps are blanks or repeats, they must be accounted for in the flags.

Be sure to add a comma to the } for the section prior if you are using a text editor, or better yet use a dedicated JSON editor.  I actually recommend editing JSON in a dedicated editor, because python is not forgiving if you make mistakes with the JSON structure.  (Try https://jsoneditoronline.org)  Also, be sure to point material to a real section in material_info.json.  You might want to create a new section, or use an existing one.

**Changing textures and adding materials**

First look inside mesh_info.json and find the mesh you want to edit.  For example, if you want to edit the metadata for `00_HAND0_R_VEL_HUM_000_MISHAPE.vb` then it will be the first entry and will have `name`: `HAND0_R_VEL_HUM_000_MISHAPE` (JSON numbering starts at zero).  Inside the brackets you will see material.  It looks like this:

```
    {
        "id_referenceonly": 0,
        "name": "HAND0_R_VEL_HUM_000_MISHAPE",
        "mesh": 2,
        "submesh": 0,
        "node": -1,
        "flags": 83,
        "material": "HAND1_VEL_HUM_000_MAT",
        "first_morph_wt_slot": 0,
        "padding": 0,
        "sort_priority": 0,
        "sort_center": [
            0.0,
            0.0,
            0.0
        ],
        "data_block_size": 14936,
        "morph_count": 0,
        "vgmap": 0
    },
```

Go to material_info.json, and go that section.  For example, if "material" in mesh_info was "HAND1_VEL_HUM_000_MAT" (as in the above example), then go to the section of material_info.json with the tag ```"name": "HAND1_VEL_HUM_000_MAT"```.  Under textures, you can change the file names.  When changing the texture filenames, do not put the `.totexb_d` extension as the tool will automatically add the extension when making the .TOMDLB_D file.

When making mods with new textures, I highly recommend giving them unique names, instead of asking the user to overwrite textures that already exist.  That way, you do not have to worry about when two or more models use the same textures.  Because the game uses a filename hashing system, be sure to check that the new filename does not accidentally overwrite an old name.  Another option is to overwrite unused textures, as Tales of Berseria has many unused assets left over from Tales of Zesteria.

*NOTE: While shader parameters can be changed, be very careful changing any assignments to material animations.*  `ani_color_slot`, `ani_uv_scroll_slot` and `ani_sprite_sheet_slot` are *pointers* to a different section of the file and are not currently changeable; adding new animated materials will cause a buffer overrun and the game will likely crash.  There is a lot more information on all the material parameters in the tutorial wiki linked above.

**Changing the skeleton**

It is generally not possible to change the skeleton as the skeleton is external, and different models / characters may share a skeleton.  The parameters of the physics bones can be changed, and in theory bones can be repositioned if they are inside the model.  Which skeletons belong to which model are defined in `PARTSMODELDEFINE.DAT` in Berseria (and probably Zestiria).

**Changing the physics parameters**

Physics parameters are kept in physics_info.json, and can be freely modified.  The order of the entries *must* match the order of the skeletal nodes, and as of current, entries cannot be added or removed.  The order of parameters should not be changed; they are read in order (not by label) when rebuilding models.  In general, the effects of physics is very modest and are generally overridden by the animations.

**Changing the collision meshes**

Unlike regular (visible) meshes, which are indexed in mesh_info.json, the collision meshes are indexed in collision_info.json.  The number and grouping should not be changed, but the individual meshes can be edited.  The meshes are moved into place by the nodes, though, so their position in Blender will not match their position in the game unless you parent them to the correct bone (do not forget to unparent them before exporting).

**Changing the morph targets**

Morph targets are exported as individual meshes, not as deltas.  They should be saved for import in the same format, and the import script will re-calculate new deltas from the meshes.

**Changing the animation defaults**

The game uses the animation defaults for most animation base data (as opposed to most games that use the matrices in the skeleton).  Therefore, altering these values will directly alter the bind pose, the default state of uv scrolling materials, default state of inverse kinematics, etc.  For Tales of Symphonia, for example, the model can be scaled by altering the first vector of ani_default_info.json, which is the scale of the root bone.  These values can be altered in external skeleton files too, using the script berseria_modify_model_ani_default.py.  (More info on the tutorial wiki linked above.)

### totexp_p_to_dds.py
Double click the python script in a folder with .TOTEXP_P files and it will convert them to .dds textures.  The corresponding .TOTEXB_D files are not necessary.

### dds_to_berseria_totexp_p.py
Double click the python script in a folder with .dds files and it will convert them to .TOTEXB_D / .TOTEXP_P textures for Tales of Berseria.  Only supports BC1 (DXT1), BC3 (DXT5) and ARGB8 (uncompressed) with mipmaps.  Replace both files at once when modding.

### dds_to_zestiria_totexp_p.py
The same script as `dds_to_berseria_totexp_p.py`, except it uses 32-bit addressing instead of 64-bit.  Use for making textures for Tales of Zesteria and Tales of Symphonia (PC).

### ps3_totexb_d_to_dds.py
Double click the python script in a folder with PS3 .TOTEXB_D/.TOTEXP_P files and it will convert them to .dds textures.  Both files are necessary for PS3 textures.

### dds_to_zestiria_ps3_totexb_d.py
Used for making textures for Tales of Zesteria and Tales of Symphonia Chronicles (PS3), which uses a different non-DDS format.