# armaToHKX
Export blender armatures and animations to skyrim .xml skeletons and havok projects.
This addon is intended for creating small havok projects, non-character, for skyrim. Things such as animated doors, traps, furniture and environmental objects (statics) driven by behavior and havok animations. It can also be used to set up the project, character and skeleton files for nif-animated projects using BSGamebryoSequenceGenerators instead of havok animation.

Requires: 
* hkxcmd.exe - I recommend this version https://www.loverslab.com/topic/89327-hkxcmd-15/
* convertkf.exe - Updated version of hkxcmds convertkf command by ProfJack.  You can get it here https://www.nexusmods.com/skyrimspecialedition/mods/65528?tab=description
* A working and relatively recent version of the blender niftools plugin (built and tested with v0.0.7-v0.1.5dev) https://github.com/niftools/blender_niftools_addon

These are not included in the repo

Instructions/setup:
In any 3d-viewport view in blender hit 'n' to bring up the tools sidebar, go to armaToHKX and select the paths to the above tools.
You should also create a working directory for armaToHKX or accept the default

After this you can use the three options under file -> export -> animation with armatohkx, project with armatohkx and skeleton with armatohkx

project with armatohkx (.hkx) will create three files and some subfolders:
* a havok project file (.hkx)
* four folders: behaviors/ animations/ characters/ and CharacterAssets/
* a havok character file (.hkx) inside the characters/ folder
* a havok skeleton file (.hkx) inside the CharacterAssets/ folder

skeleton with armatohkx (.hkx) creates a havok skeleton file (.hkx) only

animation with armatohkx (.hkx) creates a havok animation file (.hkx) using hkxcmd.exe and convertkf.exe

# IMPORTANT
After exporting an animation with the option "bake" selected, which you should do if you use a rig with controllers/constraints, all constraint influences in the rig will be set to zero. This lets you inspect the baked action that you exported. To return to editing your non-baked action you should hit the "restore constraints post-export" button in the armatohkx sidepanel.

To create behavior files for use with this project, see pyBehaviorBuilder, which requires a local python3 installation.
