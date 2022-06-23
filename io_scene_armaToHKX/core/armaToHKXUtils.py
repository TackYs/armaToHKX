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

import bpy

def sample_constraints(armature_obj):
	constraints_dict = {}
	for pb in armature_obj.pose.bones:
		if pb.constraints:
			for constraint in pb.constraints:
				if pb.name in constraints_dict.keys():
					constraints_dict[pb.name].append([constraint, constraint.influence])
				else:
					constraints_dict[pb.name]=[[constraint, constraint.influence]]
	return constraints_dict


def reintroduce_constraints(armature_obj, constraints_dict):
	n=0
	for pb in armature_obj.pose.bones:
		if pb.name in constraints_dict.keys():
			for constraint_influence_tuple in constraints_dict[pb.name]:
				constraint_influence_tuple[0].influence = constraint_influence_tuple[1]
				n+=1
	print("Restored "+str(n)+" sampled constraint influences.")


def get_armature(context):
    #find all armatures in scene, if just one use it. If more than one, use selected. If more than one and none selected, cancel and error.
    arm_obj_list = []
    for obj in context.scene.objects: 
        if obj.type == 'ARMATURE':
            arm_obj_list.append(obj)
    if len(arm_obj_list) == 1:
        #Only one armature in scene
        return arm_obj_list[0]
    else:
        #More than one armature in scene, is one of them the currently active object?
        if context.active_object.type == 'ARMATURE':
            print('INFO get_armature: More than one armature in scene, using the currently active armature.')
            return context.active_object
        else:
            #More than one, and none of them is active, is one at least selected?
            nSelectedArmatures=0
            for obj in context.selected_objects:
                if obj.type == 'ARMATURE':
                    arma_obj = obj
                    nSelectedArmatures+=1
            if nSelectedArmatures > 1:
                print('ERROR in get_armature: More than one armature in scene, and more than one of them currently selected.')
                return None
            elif nSelectedArmatures < 1:
                print('ERROR in get_armature: More than one armature in scene, none of them are currently selected.')
                return None
            else:
                print('INFO get_armature: More than one armature in scene, using the currently selected armature.')
    return arma_obj

def get_active_obj_action_name(obj):
    action_name = (bpy.data.objects[obj.name].animation_data.action.name
        if bpy.data.objects[obj.name].animation_data is not None and
        bpy.data.objects[obj.name].animation_data.action is not None
        else None)
    return action_name

def get_anim_markers(arma_obj):

    action_name = get_active_obj_action_name(arma_obj)

    anim_markers=[]
    if action_name is not None:
        if not any([bpy.data.actions[action_name].pose_markers, bpy.context.scene.timeline_markers]):
            print("No markers to collect.")
            return anim_markers
        #Copy pose markers
        for pose_marker in bpy.data.actions[action_name].pose_markers:
            frame =  pose_marker.frame
            marker =  pose_marker.name
            anim_markers.append((frame, marker))
        #Copy timeline markers
        for timeline_marker in bpy.context.scene.timeline_markers:
            frame = timeline_marker.frame
            marker = timeline_marker.name
            anim_markers.append((frame, marker))
    return anim_markers

def set_anim_markers(arm_obj, list_tuple_marker_frame):
    action_name = get_active_obj_action_name(arm_obj)
    if action_name is not None:
        for (frame, marker) in list_tuple_marker_frame:
            new_pm = bpy.data.actions[action_name].pose_markers.new(marker)
            new_pm.frame = int(frame) # bpy 3.1+ requires explicit int, wont implicitly convert float
    else:
        print("No active action - baking failed?")
    return