"""MoveSmith - turn a Blender scene into AI-video-ready camera moves and passes.

MoveSmith is deliberately offline: it renders with Blender, encodes with a
bundled ffmpeg, and never talks to a network service.
"""

from __future__ import annotations

import os

bl_info = {
    "name": "MoveSmith - AI Video Camera Kit",
    "author": "Zimeng Guo",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > MoveSmith",
    "description": (
        "Bake cinematic camera moves and export first/last frames, depth and "
        "normal passes for AI video generation."
    ),
    "category": "Animation",
}

import bpy
from bpy.app.handlers import persistent

from . import operators, panel, preferences, properties


def _default_project_name():
    try:
        name = os.path.splitext(os.path.basename(bpy.data.filepath))[0]
    except Exception:
        name = ""
    return name or ""


def _sync_scene(scene):
    if scene is None:
        return
    try:
        if not getattr(scene, "movesmith_project_name", ""):
            scene.movesmith_project_name = _default_project_name()
    except Exception:
        pass


@persistent
def _on_load(_dummy=None):
    _sync_scene(getattr(bpy.context, "scene", None))


def register():
    properties.register()
    operators.register()
    panel.register()
    preferences.register()

    if _on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load)

    _sync_scene(getattr(bpy.context, "scene", None))


def unregister():
    try:
        if _on_load in bpy.app.handlers.load_post:
            bpy.app.handlers.load_post.remove(_on_load)
    except Exception:
        pass

    preferences.unregister()
    panel.unregister()
    operators.unregister()
    properties.unregister()


if __name__ == "__main__":
    register()
