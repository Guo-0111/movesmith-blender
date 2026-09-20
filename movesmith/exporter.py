"""Build the AI-video export package for a single shot."""

from __future__ import annotations

import json
import os
import shutil

import bpy

from . import ffmpeg_tools, motion, presets, util, variant
from .still_render import render_still

try:  # lite builds ship without the reference-pass exporters
    from . import render_passes
except ImportError:
    render_passes = None

PREVIEW_ENGINES = ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "BLENDER_WORKBENCH")


class ExportError(RuntimeError):
    pass


def scene_fps(scene):
    render = scene.render
    base = float(getattr(render, "fps_base", 1.0) or 1.0)
    fps = float(getattr(render, "fps", 24) or 24) / (base if base else 1.0)
    return max(1, int(round(fps)))


def _frame_range(scene):
    start = int(scene.frame_start)
    end = int(scene.frame_end)
    if end < start:
        start, end = end, start
    return start, end


def _mid_frames(start, end, count):
    """Evenly spaced interior frames, never duplicating first or last."""
    count = max(0, int(count))
    if count <= 0 or end - start < 2:
        return []

    span = end - start
    frames = []
    for index in range(1, count + 1):
        frame = start + int(round(span * index / (count + 1.0)))
        frame = min(max(frame, start + 1), end - 1)
        if frame not in frames:
            frames.append(frame)
    return frames


def _pick_preview_engine(scene):
    try:
        enum_items = bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items
        available = {item.identifier for item in enum_items}
    except Exception:
        return scene.render.engine

    for engine in PREVIEW_ENGINES:
        if engine in available:
            return engine
    return scene.render.engine


def render_sequence(context, camera, frames, frames_dir, size, engine_override=None):
    """Render ``frames`` into ``frames_dir`` as frame_0001.png, frame_0002.png..."""
    if os.path.isdir(frames_dir):
        shutil.rmtree(frames_dir)
    os.makedirs(frames_dir)

    written = []
    for index, frame in enumerate(frames, start=1):
        target = os.path.join(frames_dir, "frame_{0:04d}.png".format(index))
        render_still(context, camera, frame, target, size=size, engine_override=engine_override)
        written.append(target)
    return written


class ExportSettings:
    """A resolved snapshot of every choice the export needs."""

    def __init__(self, **values):
        self.output_dir = ""
        self.project = "project"
        self.resolution_key = presets.RESOLUTION_SCENE
        self.export_first = True
        self.export_last = True
        self.mid_count = 0
        self.export_depth = False
        self.export_normal = False
        self.depth_auto = True
        self.depth_near = 0.0
        self.depth_far = 0.0
        self.export_preview = False
        self.preview_quality = 50
        self.preset_id = "dolly_in"
        self.strength = 1.0
        self.easing = presets.EASING_IN_OUT
        self.ffmpeg_path = ""
        self.write_prompt = True
        self.overwrite = True
        self.__dict__.update(values)

    @classmethod
    def from_scene(cls, scene, preferences=None):
        blend_name = "untitled"
        try:
            blend_name = os.path.splitext(os.path.basename(bpy.data.filepath))[0] or "untitled"
        except Exception:
            pass

        project = getattr(scene, "movesmith_project_name", "") or blend_name
        output_dir = getattr(scene, "movesmith_output_dir", "") or ""
        if output_dir:
            output_dir = bpy.path.abspath(output_dir)
        if not output_dir and preferences is not None:
            output_dir = bpy.path.abspath(getattr(preferences, "default_output_dir", "") or "")
        if not output_dir:
            output_dir = os.path.join(
                os.path.expanduser("~"), "MoveSmith", util.sanitize_token(project)
            )

        ffmpeg_path = ""
        if preferences is not None:
            ffmpeg_path = getattr(preferences, "ffmpeg_path", "") or ""

        return cls(
            output_dir=output_dir,
            project=project,
            resolution_key=getattr(scene, "movesmith_resolution", presets.RESOLUTION_SCENE),
            export_first=bool(getattr(scene, "movesmith_export_first", True)),
            export_last=bool(getattr(scene, "movesmith_export_last", True)),
            mid_count=int(getattr(scene, "movesmith_mid_count", 0)),
            export_depth=bool(getattr(scene, "movesmith_export_depth", False)),
            export_normal=bool(getattr(scene, "movesmith_export_normal", False)),
            depth_auto=bool(getattr(scene, "movesmith_depth_auto", True)),
            depth_near=float(getattr(scene, "movesmith_depth_near", 0.0)),
            depth_far=float(getattr(scene, "movesmith_depth_far", 0.0)),
            export_preview=bool(getattr(scene, "movesmith_export_preview", False)),
            preview_quality=int(getattr(scene, "movesmith_preview_quality", 50)),
            preset_id=getattr(scene, "movesmith_preset", "dolly_in"),
            strength=float(getattr(scene, "movesmith_strength", 1.0)),
            easing=getattr(scene, "movesmith_easing", presets.EASING_IN_OUT),
            ffmpeg_path=ffmpeg_path,
            overwrite=bool(getattr(scene, "movesmith_overwrite", True)),
        )


def shot_names(settings, camera):
    project = util.sanitize_token(settings.project, "project")
    override = getattr(camera, "movesmith_shot_name", "") or ""
    shot = util.sanitize_token(override or camera.name, "shot")
    return project, shot, "{0}_{1}".format(project, shot)


def _scaled_size(scene, settings, quality_percent=100):
    size = presets.resolution_size(settings.resolution_key)
    if size is None:
        render = scene.render
        percentage = float(getattr(render, "resolution_percentage", 100) or 100) / 100.0
        width = max(2, int(float(render.resolution_x) * percentage))
        height = max(2, int(float(render.resolution_y) * percentage))
    else:
        width, height = size

    factor = max(1, int(quality_percent)) / 100.0
    if factor < 1.0:
        width = max(2, int(round(width * factor)))
        height = max(2, int(round(height * factor)))

    return width - (width % 2), height - (height % 2)


def export_shot(context, camera, settings):
    """Render every requested artefact for one camera and return a manifest."""
    scene = context.scene
    if camera is None or camera.type != "CAMERA":
        raise ExportError("Select a camera before exporting a shot package.")

    project, shot, prefix = shot_names(settings, camera)
    output_dir = util.ensure_directory(settings.output_dir)
    start, end = _frame_range(scene)
    fps = scene_fps(scene)
    size = _scaled_size(scene, settings)

    files = {}
    warnings = []

    def destination(kind, extension="png"):
        filename = "{0}_{1}.{2}".format(prefix, kind, extension)
        if settings.overwrite:
            return os.path.join(output_dir, filename)
        return util.unique_path(output_dir, filename)

    def export_kind(kind):
        return not variant.IS_LITE or variant.export_kind_allowed(kind)

    if settings.export_first and export_kind("first"):
        files["first"] = render_still(context, camera, start, destination("first"), size=size)

    if settings.export_last and export_kind("last") and end > start:
        files["last"] = render_still(context, camera, end, destination("last"), size=size)

    mids = _mid_frames(start, end, settings.mid_count) if export_kind("mid") else []
    for index, frame in enumerate(mids, start=1):
        files["mid_{0:02d}".format(index)] = render_still(
            context, camera, frame, destination("mid{0:02d}".format(index)), size=size
        )

    if settings.export_depth and export_kind("depth") and render_passes is not None:
        manual_range = None
        if not settings.depth_auto and settings.depth_far > settings.depth_near > 0.0:
            manual_range = (settings.depth_near, settings.depth_far)
        for label, frame in (("first", start), ("last", end)):
            if label == "last" and end == start:
                continue
            files["depth_{0}".format(label)] = render_passes.render_pass_still(
                context,
                camera,
                frame,
                render_passes.PASS_DEPTH,
                destination("depth_{0}".format(label)),
                depth_range=manual_range,
            )

    if settings.export_normal and export_kind("normal") and render_passes is not None:
        for label, frame in (("first", start), ("last", end)):
            if label == "last" and end == start:
                continue
            files["normal_{0}".format(label)] = render_passes.render_pass_still(
                context,
                camera,
                frame,
                render_passes.PASS_NORMAL,
                destination("normal_{0}".format(label)),
            )

    if settings.export_preview and export_kind("preview"):
        preview_size = _scaled_size(scene, settings, settings.preview_quality)
        frames_dir = os.path.join(output_dir, "_fg_preview_tmp")
        try:
            render_sequence(
                context,
                camera,
                list(range(start, end + 1)),
                frames_dir,
                preview_size,
                engine_override=_pick_preview_engine(scene),
            )
            preview_path = destination("preview", "mp4")
            ffmpeg_tools.encode_sequence(
                frames_dir,
                preview_path,
                fps,
                start_number=1,
                explicit_path=settings.ffmpeg_path,
            )
            files["preview"] = preview_path
        except ffmpeg_tools.FFmpegError as exc:
            warnings.append("Preview movie skipped: {0}".format(exc))
        finally:
            shutil.rmtree(frames_dir, ignore_errors=True)

    prompt = presets.build_prompt(
        settings.preset_id,
        settings.strength,
        fps,
        end - start + 1,
        has_first_last=("first" in files and "last" in files),
        has_depth=any(key.startswith("depth_") for key in files),
        has_normal=any(key.startswith("normal_") for key in files),
    )

    if settings.write_prompt:
        prompt_name = "{0}_prompt.txt".format(prefix)
        prompt_path = (
            os.path.join(output_dir, prompt_name)
            if settings.overwrite
            else util.unique_path(output_dir, prompt_name)
        )
        with open(prompt_path, "w", encoding="utf-8") as stream:
            stream.write(prompt)
        files["prompt"] = prompt_path

    manifest = {
        "addon": util.ADDON_NAME,
        "addon_version": util.ADDON_VERSION,
        "edition": variant.EDITION,
        "project": project,
        "shot": shot,
        "camera": camera.name,
        "preset": settings.preset_id,
        "strength": settings.strength,
        "easing": settings.easing,
        "frame_start": start,
        "frame_end": end,
        "frame_count": end - start + 1,
        "fps": fps,
        "resolution": [size[0], size[1]],
        "files": files,
        "prompt": prompt,
        "warnings": warnings,
    }

    manifest_name = "{0}_manifest.json".format(prefix)
    manifest_path = (
        os.path.join(output_dir, manifest_name)
        if settings.overwrite
        else util.unique_path(output_dir, manifest_name)
    )
    with open(manifest_path, "w", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2, ensure_ascii=False)
    files["manifest"] = manifest_path

    manifest["output_dir"] = output_dir
    return manifest


def scene_cameras(scene):
    cameras = [obj for obj in scene.objects if obj.type == "CAMERA"]
    cameras.sort(key=lambda obj: obj.name.lower())
    return cameras


def preset_for_camera(scene, camera):
    override = getattr(camera, "movesmith_shot_preset", "USE_SCENE")
    if override and override != "USE_SCENE":
        return override
    return getattr(scene, "movesmith_preset", "dolly_in")


def export_batch(context, cameras, settings, bake_moves=True, step=1, clear_animation=True):
    """Bake a move on each camera and export its package."""
    results = []
    for camera in cameras:
        entry = {"camera": camera.name, "ok": False, "manifest": None, "error": "", "bake": None}
        try:
            preset_id = preset_for_camera(context.scene, camera)
            if not variant.preset_allowed(preset_id):
                preset_id = variant.LITE_PRESETS[0]
            if bake_moves:
                entry["bake"] = motion.bake_camera_move(
                    context,
                    camera,
                    preset_id,
                    strength=settings.strength,
                    easing=settings.easing,
                    step=step,
                    clear_animation=clear_animation,
                )
            shot_settings = ExportSettings(**settings.__dict__)
            shot_settings.preset_id = preset_id
            entry["manifest"] = export_shot(context, camera, shot_settings)
            entry["ok"] = True
        except Exception as exc:
            entry["error"] = "{0}: {1}".format(type(exc).__name__, exc)
        results.append(entry)
    return results
