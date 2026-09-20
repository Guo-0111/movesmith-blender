"""Sidebar UI for MoveSmith."""

from __future__ import annotations

from bpy.types import Panel

from . import operators, presets, variant


class MOVESMITH_PT_main(Panel):
    bl_label = "MoveSmith"
    bl_idname = "MOVESMITH_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MoveSmith"

    def draw(self, context):
        scene = context.scene
        layout = self.layout

        layout.prop(scene, "movesmith_project_name", text="Project")

        box = layout.box()
        box.label(text="Shot", icon="CAMERA_DATA")
        box.prop(scene, "movesmith_camera", text="")
        camera = operators.active_camera(context)
        if camera is None:
            box.label(text="No camera in this scene", icon="ERROR")
        else:
            box.prop(camera, "movesmith_shot_name", text="Shot Name")
            box.prop(camera, "movesmith_shot_preset", text="Move")
        box.prop(scene, "movesmith_focus_object", text="Focus")

        range_box = layout.box()
        range_box.label(
            text="Range: {0} - {1} ({2} frames)".format(
                int(scene.frame_start), int(scene.frame_end), int(scene.frame_end) - int(scene.frame_start) + 1
            ),
            icon="TIME",
        )

        move = layout.box()
        move.label(text="Camera Move", icon="DRIVER_DISTANCE")

        if variant.IS_LITE:
            move.label(text="Lite build: Dolly In and Orbit only", icon="LOCKED")

        move.prop(scene, "movesmith_preset", text="")
        spec = presets.preset_spec(getattr(scene, "movesmith_preset", "dolly_in"))
        move.label(text=spec["description"], icon="INFO")

        move.prop(scene, "movesmith_strength", text="Amount")
        move.prop(scene, "movesmith_easing", text="Easing")

        advanced = move.column(align=True)
        advanced.prop(scene, "movesmith_keyframe_step", text="Keyframe Step")
        advanced.prop(scene, "movesmith_clear_animation", text="Clear Old Keys")

        move.operator("movesmith.apply_move", icon="KEYFRAME_HLT")

        export = layout.box()
        export.label(text="Export Package", icon="EXPORT")
        export.prop(scene, "movesmith_resolution", text="")

        row = export.row(align=True)
        row.prop(scene, "movesmith_export_first", toggle=True)
        row.prop(scene, "movesmith_export_last", toggle=True)
        row.prop(scene, "movesmith_mid_count", text="Mid")

        if variant.IS_LITE:
            locked = export.column()
            locked.enabled = False
            locked.prop(scene, "movesmith_export_depth")
            locked.prop(scene, "movesmith_export_normal")
            locked.prop(scene, "movesmith_export_preview")
            export.label(text="Depth, normal and preview need the full build", icon="LOCKED")
        else:
            passes = export.column(align=True)
            passes.prop(scene, "movesmith_export_depth")
            if getattr(scene, "movesmith_export_depth", False):
                depth_options = export.column(align=True)
                depth_options.prop(scene, "movesmith_depth_auto")
                if not getattr(scene, "movesmith_depth_auto", True):
                    depth_options.prop(scene, "movesmith_depth_near")
                    depth_options.prop(scene, "movesmith_depth_far")
            passes.prop(scene, "movesmith_export_normal")
            passes.prop(scene, "movesmith_export_preview")
            if getattr(scene, "movesmith_export_preview", False):
                export.prop(scene, "movesmith_preview_quality", text="Preview Size")

        export.prop(scene, "movesmith_output_dir", text="")
        export.prop(scene, "movesmith_overwrite")

        actions = layout.column(align=True)
        actions.operator("movesmith.export_shot", icon="RENDER_STILL")
        actions.operator("movesmith.preview_prompt", icon="TEXT")
        actions.operator("movesmith.open_output_dir", icon="FILE_FOLDER")

        if not variant.IS_LITE:
            batch = layout.box()
            batch.label(text="Batch", icon="SEQUENCE")
            batch.label(text="One package per camera in the scene")
            batch.operator("movesmith.batch_export", icon="RENDER_ANIMATION")
            report = getattr(scene, "movesmith_report", "")
            if report:
                column = batch.column(align=True)
                for line in report.splitlines()[:12]:
                    column.label(text=line[:64])

        status = getattr(scene, "movesmith_status", "")
        if status:
            status_box = layout.box()
            status_box.label(text="Last Result", icon="CHECKMARK")
            for line in _wrap(status, 46)[:6]:
                status_box.label(text=line)

        layout.operator("movesmith.reset_defaults", icon="LOOP_BACK")

        footer = layout.box()
        footer.label(text="Edition: {0}".format(variant.EDITION), icon="INFO")
        footer.label(text="Runs offline, no account needed")


def _wrap(text, width):
    words = str(text).split()
    lines = []
    current = ""
    for word in words:
        candidate = (current + " " + word).strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


CLASSES = (MOVESMITH_PT_main,)


def register():
    from bpy.utils import register_class

    for cls in CLASSES:
        register_class(cls)


def unregister():
    from bpy.utils import unregister_class

    for cls in reversed(CLASSES):
        unregister_class(cls)
