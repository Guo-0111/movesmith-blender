"""Add-on preferences for MoveSmith."""

from __future__ import annotations

import os

import bpy
from bpy.props import StringProperty
from bpy.types import AddonPreferences

from . import variant


def _default_output_dir():
    return os.path.join(os.path.expanduser("~"), "MoveSmith")


class MoveSmithPreferences(AddonPreferences):
    bl_idname = __package__

    default_output_dir = StringProperty(
        name="Default Output Folder",
        description="Used when a scene has no output folder of its own",
        subtype="DIR_PATH",
        default=_default_output_dir(),
    )
    ffmpeg_path = StringProperty(
        name="ffmpeg Path",
        description=(
            "Leave empty to use the ffmpeg build shipped with MoveSmith. "
            "Set this only if you want to point at your own copy"
        ),
        subtype="FILE_PATH",
        default="",
    )

    def draw(self, context):
        del context
        layout = self.layout
        layout.prop(self, "default_output_dir")
        layout.prop(self, "ffmpeg_path")

        box = layout.box()
        box.label(text="Edition: {0}".format(variant.EDITION), icon="INFO")
        if variant.IS_LITE:
            box.label(text="Lite build: 2 camera moves and first-frame export.", icon="LOCKED")
            box.label(text="The full build adds 8 more moves, depth/normal passes,")
            box.label(text="preview movies and batch export.")
        else:
            box.label(text="MoveSmith runs fully offline. It makes no network requests.")


CLASSES = (MoveSmithPreferences,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
