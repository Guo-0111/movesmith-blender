"""Render a single frame to an exact path, restoring every setting afterwards."""

from __future__ import annotations

import os

import bpy

from . import util


class StillRenderError(RuntimeError):
    pass


def _set(target, attribute, value):
    if target is None or not hasattr(target, attribute):
        return
    try:
        setattr(target, attribute, value)
    except Exception:
        pass


def resolve_rendered_file(output_path):
    """Blender sometimes appends a frame number; find what it actually wrote."""
    if os.path.exists(output_path):
        return output_path

    directory = os.path.dirname(output_path)
    stem, _extension = os.path.splitext(os.path.basename(output_path))
    if not os.path.isdir(directory):
        return ""

    matches = [
        os.path.join(directory, name)
        for name in os.listdir(directory)
        if name.startswith(stem) and name.lower().endswith(".png")
    ]
    if not matches:
        return ""
    matches.sort(key=os.path.getmtime)
    return matches[-1]


def render_still(
    context,
    camera,
    frame,
    output_path,
    size=None,
    engine_override=None,
    view_transform=None,
    film_transparent=None,
    color_mode="RGB",
):
    """Render a single frame to exactly ``output_path``."""
    scene = context.scene
    render = scene.render
    image_settings = render.image_settings

    view_settings = getattr(scene, "view_settings", None)
    previous = {
        "camera": scene.camera,
        "frame": scene.frame_current,
        "filepath": render.filepath,
        "engine": render.engine,
        "resolution_x": render.resolution_x,
        "resolution_y": render.resolution_y,
        "resolution_percentage": render.resolution_percentage,
        "file_format": image_settings.file_format,
        "color_mode": image_settings.color_mode,
        "film_transparent": getattr(render, "film_transparent", None),
        "view_transform": getattr(view_settings, "view_transform", None),
        "look": getattr(view_settings, "look", None),
        "exposure": getattr(view_settings, "exposure", None),
        "gamma": getattr(view_settings, "gamma", None),
    }

    util.ensure_directory(os.path.dirname(output_path))

    try:
        scene.camera = camera
        if size:
            render.resolution_x, render.resolution_y = int(size[0]), int(size[1])
        render.resolution_percentage = 100
        if engine_override:
            _set(render, "engine", engine_override)
        if film_transparent is not None:
            _set(render, "film_transparent", film_transparent)
        if view_transform is not None and view_settings is not None:
            _set(view_settings, "view_transform", view_transform)
            _set(view_settings, "look", "None")
            _set(view_settings, "exposure", 0.0)
            _set(view_settings, "gamma", 1.0)
        image_settings.file_format = "PNG"
        image_settings.color_mode = color_mode
        render.filepath = output_path
        scene.frame_set(int(frame))
        bpy.ops.render.render(write_still=True)
    finally:
        _set(render, "engine", previous["engine"])
        render.filepath = previous["filepath"]
        render.resolution_x = previous["resolution_x"]
        render.resolution_y = previous["resolution_y"]
        render.resolution_percentage = previous["resolution_percentage"]
        image_settings.file_format = previous["file_format"]
        image_settings.color_mode = previous["color_mode"]
        if previous["film_transparent"] is not None:
            _set(render, "film_transparent", previous["film_transparent"])
        if view_settings is not None:
            _set(view_settings, "view_transform", previous["view_transform"])
            _set(view_settings, "look", previous["look"])
            _set(view_settings, "exposure", previous["exposure"])
            _set(view_settings, "gamma", previous["gamma"])
        scene.frame_set(previous["frame"])
        if previous["camera"] is not None:
            scene.camera = previous["camera"]

    produced = resolve_rendered_file(output_path)
    if not produced:
        raise StillRenderError(
            "Blender reported success but no image was written for {0}".format(output_path)
        )

    if os.path.abspath(produced) != os.path.abspath(output_path):
        if os.path.exists(output_path):
            os.remove(output_path)
        os.replace(produced, output_path)
    return output_path
