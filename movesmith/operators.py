"""MoveSmith operators."""

from __future__ import annotations

import os
import subprocess
import sys

import bpy
from bpy.types import Operator

from . import exporter, motion, presets, util, variant


def addon_preferences(context):
    try:
        package = __package__
        addon = context.preferences.addons.get(package)
        return addon.preferences if addon else None
    except Exception:
        return None


def active_camera(context):
    scene = context.scene
    camera = getattr(scene, "movesmith_camera", None)
    if camera is not None and camera.type == "CAMERA":
        return camera
    camera = scene.camera
    if camera is not None and camera.type == "CAMERA":
        return camera
    return None


def _set_status(scene, text, report=""):
    scene.movesmith_status = text
    if report:
        scene.movesmith_report = report


class MOVESMITH_OT_apply_move(Operator):
    bl_idname = "movesmith.apply_move"
    bl_label = "Apply Camera Move"
    bl_description = (
        "Bake the selected camera move onto the camera as keyframes across the "
        "scene frame range"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def execute(self, context):
        scene = context.scene
        camera = active_camera(context)
        if camera is None:
            self.report({"ERROR"}, "Select a camera before applying a move.")
            return {"CANCELLED"}

        preset_id = getattr(scene, "movesmith_preset", "dolly_in")
        if not variant.preset_allowed(preset_id):
            self.report(
                {"ERROR"},
                "The {0} build only includes 2 camera moves. Upgrade for the full set.".format(
                    variant.EDITION
                ),
            )
            return {"CANCELLED"}

        try:
            result = motion.bake_camera_move(
                context,
                camera,
                preset_id,
                strength=float(getattr(scene, "movesmith_strength", 1.0)),
                easing=getattr(scene, "movesmith_easing", presets.EASING_IN_OUT),
                step=int(getattr(scene, "movesmith_keyframe_step", 1)),
                clear_animation=bool(getattr(scene, "movesmith_clear_animation", True)),
            )
        except motion.MotionError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        except Exception as exc:
            self.report({"ERROR"}, "Could not apply the move: {0}".format(exc))
            return {"CANCELLED"}

        message = "{0} baked on {1}: {2} keyframes, frames {3}-{4}, focus from {5}".format(
            presets.preset_spec(preset_id)["label"],
            camera.name,
            result["frames"],
            result["frame_start"],
            result["frame_end"],
            result["focus_source"],
        )
        if result["constraints"]:
            message += ". Warning: this camera has constraints ({0}) that may fight the baked keys".format(
                ", ".join(result["constraints"])
            )

        _set_status(scene, message)
        self.report({"INFO"}, message)
        return {"FINISHED"}


class MOVESMITH_OT_export_shot(Operator):
    bl_idname = "movesmith.export_shot"
    bl_label = "Export Shot Package"
    bl_description = "Render the current camera's move into an AI-video-ready package"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def execute(self, context):
        scene = context.scene
        camera = active_camera(context)
        if camera is None:
            self.report({"ERROR"}, "Select a camera before exporting.")
            return {"CANCELLED"}

        settings = exporter.ExportSettings.from_scene(scene, addon_preferences(context))

        try:
            manifest = exporter.export_shot(context, camera, settings)
        except Exception as exc:
            message = "Export failed: {0}".format(exc)
            _set_status(scene, message)
            self.report({"ERROR"}, message)
            return {"CANCELLED"}

        files = manifest["files"]
        scene.movesmith_last_output_dir = manifest.get("output_dir", "")
        summary = "Exported {0} file(s) for {1} into {2}".format(
            len(files), camera.name, manifest.get("output_dir", "")
        )
        if manifest.get("warnings"):
            summary += " | " + " | ".join(manifest["warnings"])

        _set_status(scene, summary)
        self.report({"INFO"}, summary)
        return {"FINISHED"}


class MOVESMITH_OT_batch_export(Operator):
    bl_idname = "movesmith.batch_export"
    bl_label = "Batch Export All Cameras"
    bl_description = (
        "Bake a move on every camera in the scene and export one package per camera"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def execute(self, context):
        scene = context.scene
        if variant.IS_LITE:
            self.report(
                {"ERROR"}, "Batch export is part of the full build of MoveSmith."
            )
            return {"CANCELLED"}

        cameras = exporter.scene_cameras(scene)
        if not cameras:
            self.report({"ERROR"}, "This scene has no cameras to export.")
            return {"CANCELLED"}

        settings = exporter.ExportSettings.from_scene(scene, addon_preferences(context))

        try:
            results = exporter.export_batch(
                context,
                cameras,
                settings,
                bake_moves=True,
                step=int(getattr(scene, "movesmith_keyframe_step", 1)),
                clear_animation=bool(getattr(scene, "movesmith_clear_animation", True)),
            )
        except Exception as exc:
            message = "Batch export failed: {0}".format(exc)
            _set_status(scene, message)
            self.report({"ERROR"}, message)
            return {"CANCELLED"}

        succeeded = [entry for entry in results if entry["ok"]]
        failed = [entry for entry in results if not entry["ok"]]

        lines = []
        for entry in succeeded:
            preset_id = entry["bake"]["preset"] if entry["bake"] else "unchanged"
            lines.append("OK   {0}  ({1})".format(entry["camera"], preset_id))
        for entry in failed:
            lines.append("FAIL {0}  {1}".format(entry["camera"], entry["error"]))

        scene.movesmith_last_output_dir = settings.output_dir
        _set_status(
            scene,
            "{0} of {1} cameras exported into {2}".format(
                len(succeeded), len(results), settings.output_dir
            ),
            "\n".join(lines),
        )

        if failed:
            self.report(
                {"WARNING"},
                "{0} camera(s) exported, {1} failed. See the Batch Report panel.".format(
                    len(succeeded), len(failed)
                ),
            )
        else:
            self.report({"INFO"}, "{0} camera(s) exported.".format(len(succeeded)))
        return {"FINISHED"}


class MOVESMITH_OT_preview_prompt(Operator):
    bl_idname = "movesmith.preview_prompt"
    bl_label = "Show Prompt"
    bl_description = "Build the paste-ready prompt for the current move and open it as text"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def execute(self, context):
        scene = context.scene
        preset_id = getattr(scene, "movesmith_preset", "dolly_in")

        text = presets.build_prompt(
            preset_id,
            float(getattr(scene, "movesmith_strength", 1.0)),
            exporter.scene_fps(scene),
            int(scene.frame_end) - int(scene.frame_start) + 1,
            has_first_last=bool(getattr(scene, "movesmith_export_first", True))
            and bool(getattr(scene, "movesmith_export_last", True)),
            has_depth=bool(getattr(scene, "movesmith_export_depth", False)),
            has_normal=bool(getattr(scene, "movesmith_export_normal", False)),
        )

        block_name = "MoveSmith Prompt"
        block = bpy.data.texts.get(block_name)
        if block is None:
            block = bpy.data.texts.new(block_name)
        block.clear()
        block.write(text)

        copied = False
        window_manager = getattr(context, "window_manager", None)
        if window_manager is not None:
            try:
                window_manager.clipboard = text
                copied = True
            except Exception:
                copied = False

        message = "Prompt written to the '{0}' text block.".format(block_name)
        if copied:
            message += " It is also on your clipboard."
        _set_status(scene, message)
        self.report({"INFO"}, message)
        return {"FINISHED"}


class MOVESMITH_OT_open_output_dir(Operator):
    bl_idname = "movesmith.open_output_dir"
    bl_label = "Open Output Folder"
    bl_description = "Open the export folder in your file browser"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def execute(self, context):
        scene = context.scene
        directory = scene.movesmith_last_output_dir or ""
        if not directory:
            settings = exporter.ExportSettings.from_scene(scene, addon_preferences(context))
            directory = settings.output_dir
        directory = bpy.path.abspath(directory)

        if not directory:
            self.report({"ERROR"}, "No output folder is set yet.")
            return {"CANCELLED"}

        if not os.path.isdir(directory):
            try:
                os.makedirs(directory)
            except Exception as exc:
                self.report({"ERROR"}, "Could not create {0}: {1}".format(directory, exc))
                return {"CANCELLED"}

        try:
            if sys.platform.startswith("win"):
                os.startfile(directory)  # noqa: S606 - opening our own export folder
            elif sys.platform == "darwin":
                subprocess.Popen(["open", directory])
            else:
                subprocess.Popen(["xdg-open", directory])
        except Exception as exc:
            self.report({"ERROR"}, "Could not open {0}: {1}".format(directory, exc))
            return {"CANCELLED"}

        self.report({"INFO"}, "Opened {0}".format(directory))
        return {"FINISHED"}


class MOVESMITH_OT_reset_defaults(Operator):
    bl_idname = "movesmith.reset_defaults"
    bl_label = "Reset MoveSmith Settings"
    bl_description = "Restore every MoveSmith setting in this scene to its default"
    bl_options = {"REGISTER", "UNDO"}

    DEFAULTS = (
        ("movesmith_preset", "dolly_in"),
        ("movesmith_strength", 1.0),
        ("movesmith_easing", presets.EASING_IN_OUT),
        ("movesmith_keyframe_step", 1),
        ("movesmith_clear_animation", True),
        ("movesmith_resolution", presets.RESOLUTION_SCENE),
        ("movesmith_export_first", True),
        ("movesmith_export_last", True),
        ("movesmith_mid_count", 0),
        ("movesmith_export_depth", False),
        ("movesmith_export_normal", False),
        ("movesmith_depth_auto", True),
        ("movesmith_depth_near", 0.0),
        ("movesmith_depth_far", 0.0),
        ("movesmith_export_preview", False),
        ("movesmith_preview_quality", 50),
        ("movesmith_overwrite", True),
    )

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def execute(self, context):
        scene = context.scene
        for name, value in self.DEFAULTS:
            if hasattr(scene, name):
                try:
                    setattr(scene, name, value)
                except Exception:
                    pass
        _set_status(scene, "MoveSmith settings reset to defaults.")
        self.report({"INFO"}, "MoveSmith settings reset to defaults.")
        return {"FINISHED"}


CLASSES = (
    MOVESMITH_OT_apply_move,
    MOVESMITH_OT_export_shot,
    MOVESMITH_OT_batch_export,
    MOVESMITH_OT_preview_prompt,
    MOVESMITH_OT_open_output_dir,
    MOVESMITH_OT_reset_defaults,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
