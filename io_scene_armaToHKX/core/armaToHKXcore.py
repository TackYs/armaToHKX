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

import os
import bpy
import mathutils

import pyffi.spells.nif.fix

from io_scene_niftools.file_io.kf import KFFile
from io_scene_niftools.modules.nif_export import armature
from io_scene_niftools.modules.nif_export.animation.transform import TransformAnimation
from io_scene_niftools.nif_common import NifCommon
from io_scene_niftools.utils import math
from io_scene_niftools.utils.singleton import NifOp, NifData
from io_scene_niftools.utils.logging import NifLog, NifError
from io_scene_niftools.modules.nif_export import scene

import subprocess
import time


def export_animation(filepath, transform_anim, dump_file_path):
    # extract directory, base name, extension
    directory = os.path.dirname(filepath)
    filebase, fileext = os.path.splitext(os.path.basename(filepath))

    #init somehow
    #NifData.init(data)
    try: 
        b_armature = math.get_armature()
        #init bone orientation
        math.set_bone_orientation(b_armature.data.niftools.axis_forward, b_armature.data.niftools.axis_up)
    except AttributeError:
        reportStr="No armature found in scene, cancelling."
        print("ERROR "+reportStr)
        return


    #NifLog.info("Extracting f-curve animation keys")
    print("Extracting f-curve animation keys")
    if b_armature:
        b_action = get_active_action(b_armature)
        for b_bone in b_armature.data.bones:
            print(b_bone.name)
            export_transforms(b_armature, b_action, transform_anim, dump_file_path, b_bone)
    
    #addition, add end tag
    with open(dump_file_path,'a') as f:
        reportStr="[End]"
        f.write(reportStr)

    #NifLog.info("Created animation text file")
    print("Created animation text file")
    return

def export_transforms(b_obj, b_action, transform_anim, dump_file_path, bone=None):
        """
        If bone == None, object level animation is exported.
        If a bone is given, skeletal animation is exported.
        """

        # b_action may be None, then nothing is done.
        if not b_action:
            return

        # blender object must exist
        assert b_obj
        # if a bone is given, b_obj must be an armature
        if bone:
            assert type(b_obj.data) == bpy.types.Armature

        # just for more detailed error reporting later on
        bonestr = ""

        # skeletal animation - with bone correction & coordinate corrections
        if bone and bone.name in b_action.groups:
            # get bind matrix for bone or object
            bind_matrix = math.get_object_bind(bone)
            exp_fcurves = b_action.groups[bone.name].channels
            # just for more detailed error reporting later on
            #bonestr = " in bone " + bone.name
            #target_name = block_store.get_full_name(bone)
            #priority = bone.niftools.priority
        else:
            # bone isn't keyframed in this action, nothing to do here
            return

        # decompose the bind matrix
        bind_scale, bind_rot, bind_trans = math.decompose_srt(bind_matrix)

        # fill in the non-trivial values
        start_frame, stop_frame = b_action.frame_range
        # get the desired fcurves for each data type from exp_fcurves

        quaternions = [fcu for fcu in exp_fcurves if fcu.data_path.endswith("quaternion")]
        translations = [fcu for fcu in exp_fcurves if fcu.data_path.endswith("location")]
        eulers = [fcu for fcu in exp_fcurves if fcu.data_path.endswith("euler")]
        scales = [fcu for fcu in exp_fcurves if fcu.data_path.endswith("scale")]


        # ensure that those groups that are present have all their fcurves
        for fcus, num_fcus in ((quaternions, 4), (eulers, 3), (translations, 3), (scales, 3)):
            if fcus and len(fcus) != num_fcus:
                raise NifError(
                    f"Incomplete key set {bonestr} for action {b_action.name}."
                    f"Ensure that if a bone is keyframed for a property, all channels are keyframed.")

        # go over all fcurves collected above and transform and store all their keys
        quat_curve = []
        euler_curve = []
        trans_curve = []
        scale_curve = []
        for frame, quat in transform_anim.iter_frame_key(quaternions, mathutils.Quaternion):
            quat = math.export_keymat(bind_rot, quat.to_matrix().to_4x4(), bone).to_quaternion()
            quat_curve.append((frame, quat))
            
        for frame, euler in transform_anim.iter_frame_key(eulers, mathutils.Euler):
            keymat = math.export_keymat(bind_rot, euler.to_matrix().to_4x4(), bone)
            euler = keymat.to_euler("XYZ", euler)
            euler_curve.append((frame, euler))

        for frame, trans in transform_anim.iter_frame_key(translations, mathutils.Vector):
            keymat = math.export_keymat(bind_rot, mathutils.Matrix.Translation(trans), bone)
            trans = keymat.to_translation() + bind_trans
            trans_curve.append((frame, trans))

        #TODO
        #If user hasn't keyframed scales, i.e. just location + rotation, scales_curve will be empty and _NOTHING_ gets exported
        #design choice is to then set scales to 1.0, another option would be to throw an error
        for frame, scale in transform_anim.iter_frame_key(scales, mathutils.Vector):
            # just use the first scale curve and assume even scale over all curves
            scale_curve.append((frame, scale[0]))
            print(scale)
        #TODO cont
        if len(scale_curve) != len(quat_curve):
            reportStr="ArmaToHKX WARNING: scale curve empty, assuming scale 1.0 for all keyframes for bone "+bone.name
            print(reportStr)        
            scale_curve=[]
            for frame, quat in transform_anim.iter_frame_key(quaternions, mathutils.Quaternion):
                scale_curve.append((frame, 1.0))

        #Export it
        with open(dump_file_path,'a') as f:
            if not bone.parent: #root bone - will bug out if root siblings.
                reportStr="[Begin] {Data Format = (Time, Location Keys [X Y Z], Rotation Keys 'Quaternions' [W X Y Z], Scale)}\n"
                f.write(reportStr)
                reportStr="{:10.6f}\n".format((stop_frame-start_frame)/transform_anim.fps)
                f.write(reportStr)

            reportStr="Bone_Name=['"+str(bone.name)+"']\n"
            f.write(reportStr)
            reportStr=str(len(quat_curve))+"\n"
            f.write(reportStr)
            for quat_val, trans_val, scale_val in zip(quat_curve, trans_curve, scale_curve):
                if quat_val is None or trans_val is None:
                    continue
                reportStr='%s    %s %s %s    %s %s %s %s    %s\n' % ("{:10.6f}".format(quat_val[0]/transform_anim.fps), "{:10.6f}".format(trans_val[1].x), "{:10.6f}".format(trans_val[1].y), "{:10.6f}".format(trans_val[1].z), "{:10.6f}".format(quat_val[1].w),"{:10.6f}".format(quat_val[1].x),"{:10.6f}".format(quat_val[1].y),"{:10.6f}".format(quat_val[1].z),"{:10.6f}".format(scale_val[1]))
                #reportStr="\t"+str(quat_val[0])+"\t"+str(trans_val[1].x)+"\t"+str(trans_val[1].y)+"\t"+str(trans_val[1].z)+"\t"+str(quat_val[1].w)+"\t"+str(quat_val[1].x)+"\t"+str(quat_val[1].y)+"\t"+str(quat_val[1].z)+"\t1.000000"+"\n"
                f.write(reportStr)



def get_active_action(b_obj):
        # check if the blender object has a non-empty action assigned to it
        if b_obj:
            if b_obj.animation_data and b_obj.animation_data.action:
                b_action = b_obj.animation_data.action
                if b_action.fcurves:
                    return b_action


def export_skeleton(xml_file, hkx_name, skip_IK=True):
    
     
    try: 
        b_armature = math.get_armature()
        #init bone orientation
        math.set_bone_orientation(b_armature.data.niftools.axis_forward, b_armature.data.niftools.axis_up)
    except AttributeError:
        reportStr="No armature found in scene, cancelling."
        print("ERROR "+reportStr)
        return

    Armature = b_armature.data

    bone_parent_index = []
    for i,CurrentBONE in enumerate(Armature.bones):
        if CurrentBONE.name[0:3]=="IK_" and skip_IK:
            continue
        if not CurrentBONE.parent:
            bone_parent_index.append((CurrentBONE.name, -1))
        else:
            for name_index_tuple in bone_parent_index:
                if CurrentBONE.parent.name == name_index_tuple[0]:
                    bone_parent_index.append((CurrentBONE.name, name_index_tuple[1]+1))
                else:
                    continue #raise? bones parent is not in index, likely an IK bone that was skipped, and should therefore also be skipped


    numBones = 0
    bone_position_string=""

    for i,CurrentBONE in enumerate(Armature.bones):
        for name_index_tuple in bone_parent_index:
            if CurrentBONE.name == name_index_tuple[0]:
                break
        else:
            continue #Not in bone_parent index, skip the bone

        object_nif_mat = math.get_object_bind(CurrentBONE)
        rotationQuat = object_nif_mat.to_quaternion()
        rotation = ("{:.6f}".format(rotationQuat.w), "{:.6f}".format(rotationQuat.x), "{:.6f}".format(rotationQuat.y), "{:.6f}".format(rotationQuat.z))

        translationVec = object_nif_mat.to_translation().to_tuple()
        translation=("{:.6f}".format(translationVec[0]), "{:.6f}".format(translationVec[1]), "{:.6f}".format(translationVec[2]))
        
        scaleVec = object_nif_mat.to_scale().to_tuple()
        scale = ("{:.6f}".format(scaleVec[0]), "{:.6f}".format(scaleVec[1]), "{:.6f}".format(scaleVec[2]))
        
        bone_position_string+="""
        \t\t\t{translation}{rotation}{scale}""".format(translation=str(translation).replace("'",""),rotation=str(rotation).replace("'",""),scale=str(scale).replace("'",""))
        
        numBones+=1            




    bone_declarations = ""
    bone_parent_index_string=""

    for name,parent_idx in bone_parent_index:
        bone_declarations+="""
                    <hkobject>
                        <hkparam name="name">{bone_name}</hkparam>
                        <hkparam name="lockTranslation">true</hkparam>
                    </hkobject>
    """.format(bone_name=name)
        bone_parent_index_string+="""{index} """.format(index=parent_idx)
        
    textblock = """<?xml version="1.0" encoding="ascii"?>
    <hkpackfile classversion="8" contentsversion="hk_2010.2.0-r1" toplevelobject="#0044">

        <hksection name="__data__">

            <hkobject name="#0045" class="hkMemoryResourceContainer" signature="0x4762f92a">
                <!-- memSizeAndFlags SERIALIZE_IGNORED -->
                <!-- referenceCount SERIALIZE_IGNORED -->
                <hkparam name="name"></hkparam>
                <!-- parent SERIALIZE_IGNORED -->
                <hkparam name="resourceHandles" numelements="0"></hkparam>
                <hkparam name="children" numelements="0"></hkparam>
            </hkobject>

            <hkobject name="#0046" class="hkaSkeleton" signature="0x366e8220">
                <!-- memSizeAndFlags SERIALIZE_IGNORED -->
                <!-- referenceCount SERIALIZE_IGNORED -->
                <hkparam name="name">{skeleton_name}</hkparam>
                <hkparam name="parentIndices" numelements="{nBones}">
                    {bone_parent_index_string}
                </hkparam>
                <hkparam name="bones" numelements="{nBones}">{bone_declarations}
                </hkparam>
                <hkparam name="referencePose" numelements="{nBones}">{bone_positions}
                </hkparam>
                <hkparam name="referenceFloats" numelements="0"></hkparam>
                <hkparam name="floatSlots" numelements="0"></hkparam>
                <hkparam name="localFrames" numelements="0"></hkparam>
            </hkobject>

            <hkobject name="#0047" class="hkaAnimationContainer" signature="0x8dc20333">
                <!-- memSizeAndFlags SERIALIZE_IGNORED -->
                <!-- referenceCount SERIALIZE_IGNORED -->
                <hkparam name="skeletons" numelements="1">
                    #0046
                </hkparam>
                <hkparam name="animations" numelements="0"></hkparam>
                <hkparam name="bindings" numelements="0"></hkparam>
                <hkparam name="attachments" numelements="0"></hkparam>
                <hkparam name="skins" numelements="0"></hkparam>
            </hkobject>

            <hkobject name="#0044" class="hkRootLevelContainer" signature="0x2772c11e">
                <hkparam name="namedVariants" numelements="2">
                    <hkobject>
                        <hkparam name="name">Merged Animation Container</hkparam>
                        <hkparam name="className">hkaAnimationContainer</hkparam>
                        <hkparam name="variant">#0047</hkparam>
                    </hkobject>
                    <hkobject>
                        <hkparam name="name">Resource Data</hkparam>
                        <hkparam name="className">hkMemoryResourceContainer</hkparam>
                        <hkparam name="variant">#0045</hkparam>
                    </hkobject>
                </hkparam>
            </hkobject>

        </hksection>

    </hkpackfile>""".format(nBones = str(numBones),bone_positions=bone_position_string, bone_declarations=bone_declarations, bone_parent_index_string=bone_parent_index_string, skeleton_name=hkx_name.replace(".hkx",""))

    with open(xml_file,"w") as f:
        f.write(textblock)


def export_project(xml_file, skeleton_hkx_name):
    #Simple function to export a project file

    textblock = """<?xml version="1.0" encoding="ascii"?>
<hkpackfile classversion="8" contentsversion="hk_2010.2.0-r1" toplevelobject="#0008">

    <hksection name="__data__">

        <hkobject name="#0009" class="hkbProjectStringData" signature="0x76ad60a">
            <!-- memSizeAndFlags SERIALIZE_IGNORED -->
            <!-- referenceCount SERIALIZE_IGNORED -->
            <hkparam name="animationFilenames" numelements="0"></hkparam>
            <hkparam name="behaviorFilenames" numelements="0"></hkparam>
            <hkparam name="characterFilenames" numelements="1">
                <hkcstring>Characters\\{character_hkx_name}</hkcstring>
            </hkparam>
            <hkparam name="eventNames" numelements="0"></hkparam>
            <hkparam name="animationPath"></hkparam>
            <hkparam name="behaviorPath"></hkparam>
            <hkparam name="characterPath"></hkparam>
            <hkparam name="fullPathToSource"></hkparam>
            <!-- rootPath SERIALIZE_IGNORED -->
        </hkobject>

        <hkobject name="#0010" class="hkbProjectData" signature="0x13a39ba7">
            <!-- memSizeAndFlags SERIALIZE_IGNORED -->
            <!-- referenceCount SERIALIZE_IGNORED -->
            <hkparam name="worldUpWS">(0.000000 0.000000 1.000000 0.000000)</hkparam>
            <hkparam name="stringData">#0009</hkparam>
            <hkparam name="defaultEventMode">EVENT_MODE_IGNORE_FROM_GENERATOR</hkparam>
        </hkobject>

        <hkobject name="#0008" class="hkRootLevelContainer" signature="0x2772c11e">
            <hkparam name="namedVariants" numelements="1">
                <hkobject>
                    <hkparam name="name">hkbProjectData</hkparam>
                    <hkparam name="className">hkbProjectData</hkparam>
                    <hkparam name="variant">#0010</hkparam>
                </hkobject>
            </hkparam>
        </hkobject>

    </hksection>

</hkpackfile>""".format(character_hkx_name=skeleton_hkx_name)

    with open(xml_file,"w") as f:
        f.write(textblock)

    return


def export_character(xml_file, character_hkx_name, skeleton_hkx_name, behavior_hkx_name):
    #Simple function to export a character file
    textblock = """<?xml version="1.0" encoding="ascii"?>
<hkpackfile classversion="8" contentsversion="hk_2010.2.0-r1" toplevelobject="#0022">

    <hksection name="__data__">

        <hkobject name="#0023" class="hkbMirroredSkeletonInfo" signature="0xc6c2da4f">
            <!-- memSizeAndFlags SERIALIZE_IGNORED -->
            <!-- referenceCount SERIALIZE_IGNORED -->
            <hkparam name="mirrorAxis">(1.000000 0.000000 0.000000 0.000000)</hkparam>
            <hkparam name="bonePairMap" numelements="0"></hkparam>
        </hkobject>

        <hkobject name="#0024" class="hkbCharacterStringData" signature="0x655b42bc">
            <!-- memSizeAndFlags SERIALIZE_IGNORED -->
            <!-- referenceCount SERIALIZE_IGNORED -->
            <hkparam name="deformableSkinNames" numelements="0"></hkparam>
            <hkparam name="rigidSkinNames" numelements="0"></hkparam>
            <hkparam name="animationNames" numelements="0"></hkparam>
            <hkparam name="animationFilenames" numelements="0"></hkparam>
            <hkparam name="characterPropertyNames" numelements="0"></hkparam>
            <hkparam name="retargetingSkeletonMapperFilenames" numelements="0"></hkparam>
            <hkparam name="lodNames" numelements="0"></hkparam>
            <hkparam name="mirroredSyncPointSubstringsA" numelements="0"></hkparam>
            <hkparam name="mirroredSyncPointSubstringsB" numelements="0"></hkparam>
            <hkparam name="name">{character_name}</hkparam>
            <hkparam name="rigName">CharacterAssets\\{skeleton_hkx}</hkparam>
            <hkparam name="ragdollName">&#9216;</hkparam>
            <hkparam name="behaviorFilename">Behaviors\\{behavior_hkx}</hkparam>
        </hkobject>

        <hkobject name="#0025" class="hkbVariableValueSet" signature="0x27812d8d">
            <!-- memSizeAndFlags SERIALIZE_IGNORED -->
            <!-- referenceCount SERIALIZE_IGNORED -->
            <hkparam name="wordVariableValues" numelements="0"></hkparam>
            <hkparam name="quadVariableValues" numelements="0"></hkparam>
            <hkparam name="variantVariableValues" numelements="0"></hkparam>
        </hkobject>

        <hkobject name="#0026" class="hkbCharacterData" signature="0x300d6808">
            <!-- memSizeAndFlags SERIALIZE_IGNORED -->
            <!-- referenceCount SERIALIZE_IGNORED -->
            <hkparam name="characterControllerInfo">
                <hkobject>
                    <hkparam name="capsuleHeight">1.700000</hkparam>
                    <hkparam name="capsuleRadius">0.400000</hkparam>
                    <hkparam name="collisionFilterInfo">1</hkparam>
                    <hkparam name="characterControllerCinfo">null</hkparam>
                </hkobject>
            </hkparam>
            <hkparam name="modelUpMS">(0.000000 0.000000 0.000000 1.000000)</hkparam>
            <hkparam name="modelForwardMS">(1.000000 0.000000 0.000000 0.000000)</hkparam>
            <hkparam name="modelRightMS">(-0.000000 -1.000000 -0.000000 0.000000)</hkparam>
            <hkparam name="characterPropertyInfos" numelements="0"></hkparam>
            <hkparam name="numBonesPerLod" numelements="0"></hkparam>
            <hkparam name="characterPropertyValues">#0025</hkparam>
            <hkparam name="footIkDriverInfo">null</hkparam>
            <hkparam name="handIkDriverInfo">null</hkparam>
            <hkparam name="stringData">#0024</hkparam>
            <hkparam name="mirroredSkeletonInfo">#0023</hkparam>
            <hkparam name="scale">1.000000</hkparam>
            <!-- numHands SERIALIZE_IGNORED -->
            <!-- numFloatSlots SERIALIZE_IGNORED -->
        </hkobject>

        <hkobject name="#0022" class="hkRootLevelContainer" signature="0x2772c11e">
            <hkparam name="namedVariants" numelements="1">
                <hkobject>
                    <hkparam name="name">hkbCharacterData</hkparam>
                    <hkparam name="className">hkbCharacterData</hkparam>
                    <hkparam name="variant">#0026</hkparam>
                </hkobject>
            </hkparam>
        </hkobject>

    </hksection>

</hkpackfile>""".format(character_name=character_hkx_name.replace(".hkx",""), skeleton_hkx=skeleton_hkx_name, behavior_hkx=behavior_hkx_name)
    
    with open(xml_file,"w") as f:
        f.write(textblock)
        
    return