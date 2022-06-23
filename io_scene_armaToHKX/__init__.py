# ***** BEGIN LICENSE BLOCK *****
#
# Copyright © 2019, NIF File Format Library and Tools contributors.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
#    * Redistributions of source code must retain the above copyright
#      notice, this list of conditions and the following disclaimer.
#
#    * Redistributions in binary form must reproduce the above
#      copyright notice, this list of conditions and the following
#      disclaimer in the documentation and/or other materials provided
#      with the distribution.
#
#    * Neither the name of the NIF File Format Library and Tools
#      project nor the names of its contributors may be used to endorse
#      or promote products derived from this software without specific
#      prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
# ***** END LICENSE BLOCK *****

#Broken out parts and some hacks of blender_niftools_plugin to export skeletons to .hkx as well as
#Exporting animations using kfmaker instead of the blender_niftools_plugin
#MUST HAVE blender_niftools_plugin installed in blender for this script to work.
#Built using v0.0.9, might not work with future versions or pyffi updates

bl_info = {
    "name": "armaToHKX",
    "description": "Export armature to hkx and animation to hkx using hkxcmd and KFmaker",
    "blender": (2, 80, 0),
    "location": "File > Import-Export",
    "category": "Import-Export",
}

import bpy
from bpy.props import (StringProperty,
                       PointerProperty,
                       BoolProperty,
                       EnumProperty,
                       FloatProperty
                       )
from bpy.types import (Panel,
                       Operator,
                       AddonPreferences,
                       PropertyGroup,
                       )
from bpy_extras.io_utils import ExportHelper, ImportHelper
from io_scene_armaToHKX.core.armaToHKXcore import TransformAnimation, export_animation, export_skeleton, export_character, export_project
from io_scene_armaToHKX.core.armaToHKXUtils import sample_constraints, reintroduce_constraints, get_armature, get_anim_markers, set_anim_markers
from io_scene_niftools.utils.singleton import NifOp
import os
import subprocess
import time
import shutil

#Global var sampled constraints, lasting for duration of session
#To be used to restore constrain influences post exporting.
sampled_constraints={}

class armaToHKXProperties(bpy.types.PropertyGroup):
    path : StringProperty(
        name="skeleton",
        description="Path to Skeleton .hkx file",
        default="skeleton.hkx",
        maxlen=1024,
        subtype='FILE_PATH')

    hkxcmd : StringProperty(
        name="hkxcmd",
        description="Path to hkxcmd.exe",
        default="hkxcmd",
        maxlen=1024,
        subtype='FILE_PATH')

    convertKF : StringProperty(
        name="convertKF",
        description="Path to convertKF.exe",
        default="convertKF",
        maxlen=1024,
        subtype='FILE_PATH')

    workdir : StringProperty(
        name="Workdir",
        description="Working directory for temporary files",
        default=os.path.join(os.path.dirname(os.path.realpath(__file__)),"tmp"), #"workdir",
        maxlen=1024,
        subtype='DIR_PATH')

    bakeprop : BoolProperty(
        name="BakeSelected",
        description="When baking, only bake selected bones",
        default=False)


class OBJECT_PT_armaToHKXPanel(Panel):
    bl_idname = "OBJECT_PT_armaToHKXPanel"
    bl_label = "Hkx skeleton, hkxcmd, convertKF and workdir/tmpdir"
    bl_space_type = "VIEW_3D"   
    bl_region_type = "UI"
    bl_category = "armaToHKX"

    def draw(self, context):
        layout = self.layout
        scn = context.scene
        col = layout.column(align=True)
        layout.row()
        layout.row()
        col.prop(scn.armaToHKX, "path", text="")
        col.prop(scn.armaToHKX, "hkxcmd", text="")
        col.prop(scn.armaToHKX, "convertKF", text="")
        col.prop(scn.armaToHKX, "workdir", text="")
        layout.row()
        layout.row()
        layout.row()
        layout.operator("armatohkx.sample_and_bake", icon="MESH_CUBE", text="sample and bake action")
        layout.prop(scn.armaToHKX, "bakeprop", text="only bake selected bones")
        layout.row()
        layout.row()
        layout.operator("armatohkx.constraintops", icon="MESH_CUBE", text="restore constraints post-export")

class ARMATOHKX_OT_sample_and_bake(Operator):
    bl_idname = "armatohkx.sample_and_bake"
    bl_label = "sample constraints and bake action"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        global sampled_constraints
        arm_obj = get_armature(context)
        if arm_obj is None:
            return {"CANCELLED"}
        print("Sampling armature constraints before export")
        sampled_constraints=sample_constraints(arm_obj)
        print("Baking action...")
        #Collect starting and ending frame first
        start=context.scene.frame_start
        end=context.scene.frame_end
        bpy.ops.nla.bake(frame_start=start, frame_end=end, step=1, only_selected=scene.armaToHKX.bakeprop, visual_keying=True, clear_constraints=False, clear_parents=False, use_current_action=False, clean_curves=False, bake_types={'POSE'})
        #Set influence of constraints to zero
        print("Setting bone constraint influences to zero (use 'restore constraints' in the armatoHKX panel to restore)")
        for pbone in arm_obj.pose.bones:
            if pbone.constraints:
                for constraint in pbone.constraints:
                    constraint.influence=0.0
        return {"FINISHED"}


class ARMATOHKX_OT_constraintsOPs(Operator):
    bl_idname = "armatohkx.constraintops"
    bl_label = "restore constraints"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        global sampled_constraints
        if not isinstance(sampled_constraints,dict):
            self.report({"ERROR"},"sampled constraint dict has the wrong dtype")
            return{"CANCELLED"}
        else:
            if len(sampled_constraints)<1:
                self.report({"ERROR"},"No stored constraint influences to restore (have you exported anything yet?)")
                return{"CANCELLED"}
        arma_obj = get_armature(context)
        if arma_obj is not None:
            reintroduce_constraints(arma_obj,sampled_constraints)
        return {"FINISHED"}

class ExportProjectToHKX(Operator, ExportHelper):
    """Export project hkx file, as well as folder structure and character.hkx"""
    bl_idname = "export_project.file_names"  # important since its how bpy.ops.import_test.some_data is constructed
    bl_label = "Export project.hkx"

    # ExportHelper mixin class uses this
    filename_ext = ".hkx"

    filter_glob: StringProperty(
        default="*.txt",
        options={'HIDDEN'},
        maxlen=255,  # Max internal buffer length, longer would be clamped.
    )

    # List of operator properties, the attributes will be assigned
    # to the class instance from the operator settings before calling.

    skyrim_version: EnumProperty(
    name="Skyrim version",
    description="Choose between LE or SSE",
    items=(
        ('LE', "LE", "Export LE hkx files"),
        ('SSE', "SSE", "Export SSE hkx files"),
    ),
    default='LE'
    )

    character_name: StringProperty(
        name="Character file",
        description="Name of character .hkx file, is created on export",
        default="character.hkx",
    )

    skeleton_name: StringProperty(
        name="skeleton file",
        description="Name of skeleton .hkx file, is created on export",
        default="skeleton.hkx",
    )

    behavior_name: StringProperty(
        name="behavior file",
        description="Name of behavior .hkx file, is NOT created but doesn't have to exist yet",
        default="behavior.hkx",
    )

    also_export_LE_skeleton: BoolProperty(
        name="Also export LE skeleton",
        description="Exports a LE version of the skeleton .hkx file to use for animation export. Only has effect if 'SSE' export is selected",
        default=True,
    )
    
    def execute(self, context):
        #The execute self.filepath is the project.hkx file, we should create the folders
        # Animations/ Behaviors/ Characters/ and CharacterAssets/ where it is if they don't exist and add the other files to them
        scene = context.scene
        # Init helper systems
        transform_anim = TransformAnimation()
        scene = context.scene        

        #Check workdir
        if not os.path.exists(context.scene.armaToHKX.workdir) or not os.path.isdir(context.scene.armaToHKX.workdir):
            reportStr="Workdir INVALID, either doesn't exists or is not a directory. Cancelling"
            self.report({"ERROR"},reportStr)
            return {"CANCELLED"}

        if os.path.exists(os.path.abspath(os.path.dirname(self.filepath))) and os.path.isdir(os.path.abspath(os.path.dirname(self.filepath))):
            base_export_folder = os.path.abspath(os.path.dirname(self.filepath))

        #Check animations    
        if not os.path.exists(os.path.join(base_export_folder,"Animations/")):
            os.mkdir(os.path.join(base_export_folder,"Animations"))
        elif not os.path.isdir(os.path.join(base_export_folder,"Animations")):
            reportStr="Non-folder file named 'Animations' present in export folder, not allowed!"
            self.report({"ERROR"},reportStr)

        #Check Behaviors
        if not os.path.exists(os.path.join(base_export_folder,"Behaviors/")):
            os.mkdir(os.path.join(base_export_folder,"Behaviors"))
        elif not os.path.isdir(os.path.join(base_export_folder,"Behaviors")):
            reportStr="Non-folder file named 'Behaviors' present in export folder, not allowed!"
            self.report({"ERROR"},reportStr)

        #Check CharacterAssets
        if not os.path.exists(os.path.join(base_export_folder,"CharacterAssets/")):
            os.mkdir(os.path.join(base_export_folder,"CharacterAssets"))
        elif not os.path.isdir(os.path.join(base_export_folder,"CharacterAssets")):
            reportStr="Non-folder file named 'CharacterAssets' present in export folder, not allowed!"
            self.report({"ERROR"},reportStr)

        #Check Characters
        if not os.path.exists(os.path.join(base_export_folder,"Characters/")):
            os.mkdir(os.path.join(base_export_folder,"Characters"))
        elif not os.path.isdir(os.path.join(base_export_folder,"Characters")):
            reportStr="Non-folder file named 'Characters' present in export folder, not allowed!"
            self.report({"ERROR"},reportStr)

        print("Exporting project, skeleton and character to tmp .xml file")
        #export skeleton
        skeleton_xml = os.path.join(context.scene.armaToHKX.workdir,"skeleton.xml")
        export_skeleton(skeleton_xml, self.skeleton_name)

        #Export Character
        character_xml = os.path.join(context.scene.armaToHKX.workdir,"character.xml")
        export_character(character_xml, self.character_name, self.skeleton_name, self.behavior_name)

        #Export project
        project_xml = os.path.join(context.scene.armaToHKX.workdir,"project.xml")
        export_project(project_xml, self.character_name)

        print("Converting skeleton to hkx")
        if self.skyrim_version=="LE":
            #convert to LE hkx
            skeleton_out_path = base_export_folder+"\\CharacterAssets\\"+self.skeleton_name
            cmd = "\""+context.scene.armaToHKX.hkxcmd + "\" convert -v:WIN32 " +"\""+ skeleton_xml + "\" \"" + skeleton_out_path+"\""
            print(cmd)
            proc = subprocess.Popen(cmd)
            time.sleep(1.0)
            subprocess.Popen("TASKKILL /F /PID {pid} /T".format(pid=proc.pid))
            time.sleep(1.0)
        elif self.skyrim_version=="SSE":
            skeleton_out_path = base_export_folder+"\\CharacterAssets\\"+self.skeleton_name
            cmd = "\""+context.scene.armaToHKX.hkxcmd + "\" convert -v:AMD64 " +"\""+ skeleton_xml + "\" \"" + skeleton_out_path+"\""
            print(cmd)
            proc = subprocess.Popen(cmd)
            time.sleep(1.0)
            subprocess.Popen("TASKKILL /F /PID {pid} /T".format(pid=proc.pid))
            time.sleep(1.0)
            if self.also_export_LE_skeleton:
                #Also exporting a LE skeleton to use for making animations
                print("SSE selected but also exporting a LE skeleton hkx to use for animation")
                cmd = "\""+context.scene.armaToHKX.hkxcmd + "\" convert -v:WIN32 " +"\""+ skeleton_xml + "\" \"" + skeleton_out_path.replace(".hkx","_LE.hkx")+"\""
                print(cmd)
                proc = subprocess.Popen(cmd)
                time.sleep(1.0)
                subprocess.Popen("TASKKILL /F /PID {pid} /T".format(pid=proc.pid))
                time.sleep(1.0)
        else:
            raise

        print("Converting character to hkx")
        #Convert character
        if self.skyrim_version=="LE":
            #convert to LE hkx
            character_out_path = base_export_folder+"\\Characters\\"+self.character_name
            cmd = "\""+context.scene.armaToHKX.hkxcmd + "\" convert -v:WIN32 " +"\""+ character_xml + "\" \"" + character_out_path+"\""
            print(cmd)
            proc = subprocess.Popen(cmd)
            time.sleep(1.0)
            subprocess.Popen("TASKKILL /F /PID {pid} /T".format(pid=proc.pid))
            time.sleep(1.0)
        elif self.skyrim_version=="SSE":
            #convert to SSE hkx
            character_out_path = base_export_folder+"\\Characters\\"+self.character_name
            cmd = "\""+context.scene.armaToHKX.hkxcmd + "\" convert -v:AMD64 " +"\""+ character_xml + "\" \"" + character_out_path+"\""
            print(cmd)
            proc = subprocess.Popen(cmd)
            time.sleep(1.0)
            subprocess.Popen("TASKKILL /F /PID {pid} /T".format(pid=proc.pid))
            time.sleep(1.0)
        else:
            raise

        print("Converting project to hkx")
        #Convert project
        if self.skyrim_version=="LE":
            #convert to LE hkx
            cmd = "\""+context.scene.armaToHKX.hkxcmd + "\" convert -v:WIN32 " +"\""+ project_xml + "\" \"" + self.filepath+"\""
            print(cmd)
            proc = subprocess.Popen(cmd)
            time.sleep(1.0)
            subprocess.Popen("TASKKILL /F /PID {pid} /T".format(pid=proc.pid))
            time.sleep(1.0)
        elif self.skyrim_version=="SSE":
            #convert to SSE hkx
            cmd = "\""+context.scene.armaToHKX.hkxcmd + "\" convert -v:AMD64 " +"\""+ project_xml + "\" \"" + self.filepath+"\""
            print(cmd)
            proc = subprocess.Popen(cmd)
            time.sleep(1.0)
            subprocess.Popen("TASKKILL /F /PID {pid} /T".format(pid=proc.pid))
            time.sleep(1.0)
        else:
            raise

        print("DONE")
        return {"FINISHED"}



class ExportArmaToHKX(Operator, ExportHelper):
    """Export animation to LE and SSE hkx using the niftools plugin, convertKF and hkxcmd"""
    bl_idname = "animation.animation_to_hkx"  
    bl_label = "Export animation to .hkx"

    # ExportHelper mixin class uses this
    filename_ext = ".hkx"

    filter_glob: StringProperty(
        default="*.hkx",
        options={'HIDDEN'},
        maxlen=255,  # Max internal buffer length, longer would be clamped.
    )

    bake: BoolProperty(
        name="Bake action",
        description="Bakes current action, required if using constraints such as IK",
        default=True,
    )

    scale_correction : FloatProperty(
        name="scale correction",
        description="Scale correction used by niftools export_kf operator - model will be scaled by 1/<this number> i.e. 0.1 will result in animation getting upscaled to an armature 10 times as big.",
        default = 1.0, 
        soft_min = 0.1, 
        soft_max = 1.0, 
        step = 0.1)

    def execute(self, context):
        # Init helper systems
        transform_anim = TransformAnimation()
        scene = context.scene
        if context.scene.armaToHKX.path == "" or context.scene.armaToHKX.path[-4:]!=".hkx":
            reportStr="No, or invalid skeleton.hkx file selected. Select in 3D view from the armaToHKX tool panel. Canceling."
            self.report({"ERROR"},reportStr)
            return {"CANCELLED"}

        if not os.path.exists(context.scene.armaToHKX.hkxcmd):
            reportStr="hkxcmd.exe path invalid. Cancelling."
            self.report({"ERROR"},reportStr)
            return {"CANCELLED"}

        if not os.path.exists(context.scene.armaToHKX.convertKF):
            reportStr="convertKF.exe path invalid. Cancelling."
            self.report({"ERROR"},reportStr)
            return {"CANCELLED"}

        if not os.path.exists(context.scene.armaToHKX.workdir) or not os.path.isdir(context.scene.armaToHKX.workdir):
            reportStr="Workdir INVALID, either doesn't exists or is not a directory. Cancelling"
            self.report({"ERROR"},reportStr)
            return {"CANCELLED"}

        # shutil.copyfile( os.path.abspath(os.path.join(os.path.dirname(__file__), 'tmp/empty.kf')),  context.scene.armaToHKX.workdir+"empty.kf")

        # dump_file_path = os.path.abspath(os.path.join(context.scene.armaToHKX.workdir, 'dump.txt'))
        # #If dump file exists, delete it before making a new dump.txt
        # if os.path.exists(dump_file_path):
        #     os.remove(dump_file_path)
        # empty_kf_path = os.path.abspath(os.path.join(context.scene.armaToHKX.workdir, 'empty.kf'))
        # empty_new_kf_path = os.path.abspath(os.path.join(context.scene.armaToHKX.workdir, 'empty_new.kf'))
        # export_animation(self.filepath, 
        #                 transform_anim, 
        #                 dump_file_path)


        # #Convert to kf
        # cmd = "\""+context.scene.armaToHKX.KFMaker+"\" \""+empty_kf_path+"\" \""+dump_file_path+"\""
        # print(cmd)
        # proc = subprocess.Popen(cmd)
        # time.sleep(1.0)
        # subprocess.Popen("TASKKILL /F /PID {pid} /T".format(pid=proc.pid))
        # time.sleep(1.0)

        #Export kf with io_scene_niftools
        #The io_scenes_niftools exports require baked keyframes, this can be done manually or called as an option below.
        #Manually this corresponds to hitting F3, search bake action and below settings
        # unselect "only selected"
        # select   "visual keyring"
        # select   "clear constraints"
        # unselect "clear parents"
        # select/unselect   "overwrite current action"
        # unselect "clean curves"
        # bake data dropdown should be "Pose"
        # The operator is bpy.ops.nla.bake
        # docs at https://docs.blender.org/api/current/bpy.ops.nla.html
        global sampled_constraints
        
        if self.bake:
            arm_obj = get_armature(context)
            if arm_obj is None:
                return {"CANCELLED"}
            print("Sampling armature constraints before export")
            sampled_constraints=sample_constraints(arm_obj)
            print("collecting markers from action")
            anim_markers = get_anim_markers(arm_obj)
            print("Baking action...")
            #Collect starting and ending frame first
            start=context.scene.frame_start
            end=context.scene.frame_end            
            bpy.ops.nla.bake(frame_start=start, frame_end=end, step=1, only_selected=False, visual_keying=True, clear_constraints=False, clear_parents=False, use_current_action=False, clean_curves=False, bake_types={'POSE'})
            #Set influence of constraints to zero
            print("Setting bone constraint influences to zero (use 'restore constraints' in the armatoHKX panel to restore)")
            for pbone in arm_obj.pose.bones:
                if pbone.constraints:
                    for constraint in pbone.constraints:
                        constraint.influence=0.0
            if anim_markers:
                print("Transfering markers from previous action")
                set_anim_markers(arm_obj, anim_markers)
        print("Exporting kf through io_scene_niftools")
        if bpy.context.scene.niftools_scene.scale_correction != self.scale_correction:
            reportStr="WARNING: niftools scale correction not equal to "+str(self.scale_correction)+", overriding."
            bpy.context.scene.niftools_scene.scale_correction = self.scale_correction
        empty_new_kf_path = os.path.abspath(os.path.join(context.scene.armaToHKX.workdir, 'empty_new.kf'))
        bpy.ops.export_scene.kf(filepath=empty_new_kf_path)

        #convert to LE hkx
        print("Converting kf -> LE hkx")
        cmd = "\""+context.scene.armaToHKX.convertKF +"\" \""+ context.scene.armaToHKX.path + "\" \"" + empty_new_kf_path + "\" \"" + self.filepath.replace(".hkx", "_LE.hkx")+"\"" #outpath.replace("tmp_out.xml","out\\"+hkx_name.replace(".hkx","_LE.hkx"))
        print(cmd)
        proc = subprocess.Popen(cmd)
        time.sleep(2)
        #subprocess.Popen("TASKKILL /F /PID {pid} /T".format(pid=proc.pid))
        #time.sleep(1.0)
        #convert to SSE hkx
        print("Converting LE hkx -> SSE hkx")
        cmd = "\""+context.scene.armaToHKX.hkxcmd + "\" convert -v:AMD64 " +"\""+ self.filepath.replace(".hkx", "_LE.hkx") + "\" \"" + self.filepath+"\""
        print(cmd)
        proc = subprocess.Popen(cmd)
        time.sleep(2)
        #subprocess.Popen("TASKKILL /F /PID {pid} /T".format(pid=proc.pid))
        #time.sleep(1.0)

        print("DONE")

        return {"FINISHED"}

    def invoke(self, context, event):
        wm = context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


class armaToHKX(bpy.types.Operator, ExportHelper):
    """Exporting armature to hkx using hkxcmd"""     
    bl_idname = "object.armature_to_hkx"        
    bl_label = "Export Armature to .hkx"         

    # ExportHelper mixin class uses this
    filename_ext = ".hkx"

    filter_glob: StringProperty(
        default="*.hkx",
        options={'HIDDEN'},
        maxlen=255,  # Max internal buffer length, longer would be clamped.
    )

    skyrim_version: EnumProperty(
    name="Skyrim version",
    description="Choose between LE or SSE",
    items=(
        ('LE', "LE", "Export LE hkx files"),
        ('SSE', "SSE", "Export SSE hkx files"),
    ),
    default='LE'
    )

    skip_IK: BoolProperty(
        name="Skip IK bones",
        description="Skips any bones with names starting with 'IK_'",
        default=True,
    )

    def execute(self, context):       

        scene = context.scene
        # Init helper systems
        transform_anim = TransformAnimation()
        scene = context.scene



        if self.filepath == "" or self.filepath[-4:]!=".hkx":
            reportStr="Output filepath must end with .hkx extension. Canceling."
            self.report({"ERROR"},reportStr)
            return {"CANCELLED"}

        if not os.path.exists(context.scene.armaToHKX.hkxcmd):
            reportStr="hkxcmd.exe path invalid. Cancelling."
            self.report({"ERROR"},reportStr)
            return {"CANCELLED"}

        #tmp .xml file
        tmp_xml = os.path.join(context.scene.armaToHKX.workdir,"skeleton.xml")

        #Skeleton_name
        skeleton_basename = os.path.basename(self.filepath)

        print("skeleton export")
        export_skeleton(tmp_xml, skeleton_basename, self.skip_IK)

        if self.skyrim_version == "LE":
            #convert to LE hkx
            cmd = "\""+context.scene.armaToHKX.hkxcmd + "\" convert -v:WIN32 " +"\""+ tmp_xml + "\" \"" + self.filepath+"\""
            print(cmd)
            proc = subprocess.Popen(cmd)
            time.sleep(1.0)
            subprocess.Popen("TASKKILL /F /PID {pid} /T".format(pid=proc.pid))
            time.sleep(1.0)
        elif self.skyrim_version == "SSE":
            #convert to SSE hkx
            cmd = "\""+context.scene.armaToHKX.hkxcmd + "\" convert -v:AMD64 " +"\""+ tmp_xml + "\" \"" + self.filepath+"\""
            print(cmd)
            proc = subprocess.Popen(cmd)
            time.sleep(1.0)
            subprocess.Popen("TASKKILL /F /PID {pid} /T".format(pid=proc.pid))
            time.sleep(1.0)
        else:
            raise

        print("DONE")
        return {'FINISHED'}            # Lets Blender know the operator finished successfully.

    def invoke(self, context, event):
        wm = context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

classes = (
    armaToHKXProperties,
    armaToHKX,
    OBJECT_PT_armaToHKXPanel,
    ExportArmaToHKX,
    ExportProjectToHKX,
    ARMATOHKX_OT_constraintsOPs,
    ARMATOHKX_OT_sample_and_bake,
)


def armaToHKX_menu_skeleton_export(self,context):
    self.layout.operator(armaToHKX.bl_idname, text="skeleton with armaToHKX (.hkx)")

def armaToHKX_menu_export(self, context):
    self.layout.operator(ExportArmaToHKX.bl_idname, text="animation with armaToHKX (.hkx)")

def armaToHKX_menu_project_export(self, context):
    self.layout.operator(ExportProjectToHKX.bl_idname, text="project with armaToHKX (.hkx)")


def register():
    for cls in reversed(classes):
        bpy.utils.register_class(cls)
    bpy.types.Scene.armaToHKX = PointerProperty(type=armaToHKXProperties)
    bpy.types.TOPBAR_MT_file_export.append(armaToHKX_menu_export)
    bpy.types.TOPBAR_MT_file_export.append(armaToHKX_menu_skeleton_export)
    bpy.types.TOPBAR_MT_file_export.append(armaToHKX_menu_project_export)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.armaToHKX
    bpy.types.TOPBAR_MT_file_export.remove(armaToHKX_menu_export)
    bpy.types.TOPBAR_MT_file_export.remove(armaToHKX_menu_skeleton_export)
    bpy.types.TOPBAR_MT_file_export.remove(armaToHKX_menu_project_export)

if __name__ == "__main__":
    register()