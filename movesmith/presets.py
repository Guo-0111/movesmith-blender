"""Camera move presets, resolution presets and prompt templates.

This module deliberately avoids ``bpy`` so the motion math can be exercised
without a Blender session. Every preset answers the same question: given the
camera's starting transform and a focus point, where should the camera be and
what should it look at at normalized time ``t``?

All moves are *centred* on the camera's current framing: ``t = 0.5`` reproduces
exactly what the artist already framed, and the move extends symmetrically
around it. That makes the result predictable no matter where the timeline
starts, and it means the artist never has to re-frame after applying a preset.
"""

from __future__ import annotations

import math

from mathutils import Matrix, Vector

WORLD_UP = Vector((0.0, 0.0, 1.0))
FALLBACK_RIGHT = Vector((1.0, 0.0, 0.0))

EASING_LINEAR = "LINEAR"
EASING_IN = "EASE_IN"
EASING_OUT = "EASE_OUT"
EASING_IN_OUT = "EASE_IN_OUT"
EASING_SMOOTH = "SMOOTH_IN_OUT"

EASING_ITEMS = (
    (EASING_LINEAR, "Linear", "Constant speed, most mechanical"),
    (EASING_IN, "Ease In", "Starts slow, accelerates into the end"),
    (EASING_OUT, "Ease Out", "Starts fast, settles at the end"),
    (EASING_IN_OUT, "Ease In-Out", "Slow at both ends, the safest default"),
    (EASING_SMOOTH, "Smooth In-Out", "Softer than Ease In-Out, good for long moves"),
)

RESOLUTION_SCENE = "scene"

RESOLUTION_ITEMS = (
    (RESOLUTION_SCENE, "Scene Resolution", "Keep whatever the scene currently renders"),
    ("vertical_1080", "Vertical 9:16 - 1080x1920", "Reels, Shorts, TikTok"),
    ("vertical_720", "Vertical 9:16 - 720x1280", "Faster vertical drafts"),
    ("horizontal_1080", "Landscape 16:9 - 1920x1080", "YouTube, general purpose"),
    ("horizontal_720", "Landscape 16:9 - 1280x720", "Faster landscape drafts"),
    ("square_1080", "Square 1:1 - 1080x1080", "Feed posts, product shots"),
)

RESOLUTION_SIZES = {
    "vertical_1080": (1080, 1920),
    "vertical_720": (720, 1280),
    "horizontal_1080": (1920, 1080),
    "horizontal_720": (1280, 720),
    "square_1080": (1080, 1080),
}


def resolution_size(key):
    """Return (width, height) for a resolution preset, or None for scene default."""
    return RESOLUTION_SIZES.get(key)


def apply_easing(kind, t):
    """Map a raw 0..1 parameter through an easing curve."""
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)

    if kind == EASING_IN:
        return t * t
    if kind == EASING_OUT:
        return 1.0 - (1.0 - t) * (1.0 - t)
    if kind == EASING_IN_OUT:
        return t * t * (3.0 - 2.0 * t)
    if kind == EASING_SMOOTH:
        return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)
    return t


class ShotContext:
    """Camera framing data a preset needs in order to build a move."""

    __slots__ = ("origin", "focus", "forward", "right", "distance", "strength", "easing")

    def __init__(self, origin, focus, strength=1.0, easing=EASING_IN_OUT):
        self.origin = Vector(origin)
        self.focus = Vector(focus)
        self.strength = float(strength)
        self.easing = easing

        delta = self.focus - self.origin
        distance = delta.length
        if distance < 1e-6:
            delta = Vector((0.0, 0.0, -1.0))
            distance = 1.0
        self.distance = distance
        self.forward = delta.normalized()

        right = self.forward.cross(WORLD_UP)
        if right.length < 1e-6:
            right = FALLBACK_RIGHT.copy()
        self.right = right.normalized()


def _dolly(context, strength, t, direction):
    span = min(0.85 * context.distance, 0.6 * strength * context.distance)
    offset = context.forward * (direction * span * (t - 0.5))
    return context.origin + offset, context.focus


def _crane(context, strength, t, direction):
    span = min(0.9 * context.distance, 0.5 * strength * context.distance)
    offset = WORLD_UP * (direction * span * (t - 0.5))
    return context.origin + offset, context.focus


def _orbit(context, strength, t, turns):
    offset = context.origin - context.focus
    radius = Vector((offset.x, offset.y, 0.0)).length
    if radius < 1e-4:
        radius = max(context.distance * 0.5, 0.5)
    height = offset.z
    start_angle = math.atan2(offset.y, offset.x)
    sweep = 2.0 * math.pi * turns
    angle = start_angle + sweep * (t - 0.5)
    position = context.focus + Vector(
        (radius * math.cos(angle), radius * math.sin(angle), height)
    )
    return position, context.focus


def _parallax_push(context, strength, t):
    lateral = 0.6 * strength * context.distance
    push = 0.3 * strength * context.distance
    offset = context.right * (lateral * (t - 0.5)) + context.forward * (push * (t - 0.5))
    return context.origin + offset, context.focus


def _pan(context, strength, t):
    yaw = math.radians(45.0) * strength
    rotation = Matrix.Rotation(yaw * (t - 0.5), 3, "Z")
    aim = rotation @ context.forward
    return context.origin, context.origin + aim * context.distance


def _tilt(context, strength, t):
    pitch = math.radians(30.0) * strength
    rotation = Matrix.Rotation(pitch * (t - 0.5), 3, context.right)
    aim = rotation @ context.forward
    return context.origin, context.origin + aim * context.distance


def _handheld(context, strength, t):
    # Deterministic multi-frequency wobble: reads as organic camera noise but
    # reproduces identically on every run, which matters for batch exports.
    amplitude = 0.010 * strength * context.distance
    phase = t * 2.0 * math.pi

    offset = (
        context.right * (amplitude * math.sin(2.7 * phase + 0.4))
        + WORLD_UP * (amplitude * math.sin(3.3 * phase + 1.1))
        + context.forward * (amplitude * 0.6 * math.sin(2.1 * phase + 2.0))
    )
    aim_offset = (
        context.right * (amplitude * 1.6 * math.sin(2.9 * phase + 0.9))
        + WORLD_UP * (amplitude * 1.3 * math.sin(3.7 * phase + 1.7))
    )
    return context.origin + offset, context.focus + aim_offset


PRESET_SPECS = (
    {
        "id": "dolly_in",
        "label": "Dolly In",
        "description": "Push the camera toward the subject and end tighter",
        "easing_locked": False,
        "prompt": (
            "a {speed} dolly-in (push-in) toward the subject. The camera travels "
            "forward on a straight line and ends in a tighter framing while the "
            "subject stays centred"
        ),
    },
    {
        "id": "orbit",
        "label": "Orbit",
        "description": "Arc the camera around the subject",
        "easing_locked": False,
        "prompt": (
            "a {speed} orbital arc around the subject. The camera curves sideways "
            "on a constant-height circle, keeping the subject locked in the centre "
            "of frame and revealing its side profile"
        ),
    },
    # Everything below is stripped out of the lite build by tools/build.py, so
    # the source that ships for free does not contain the paid moves at all.
)

PRESET_BY_ID = {spec["id"]: spec for spec in PRESET_SPECS}


def preset_items():
    return tuple((spec["id"], spec["label"], spec["description"]) for spec in PRESET_SPECS)


def preset_ids():
    return tuple(spec["id"] for spec in PRESET_SPECS)


def preset_spec(preset_id):
    spec = PRESET_BY_ID.get(preset_id)
    if spec is None:
        spec = PRESET_BY_ID["dolly_in"]
    return spec


def evaluate(preset_id, context, t):
    """Return ``(position, look_at)`` for raw timeline parameter ``t`` in 0..1."""
    spec = preset_spec(preset_id)
    strength = context.strength

    if spec["easing_locked"]:
        eased = apply_easing(EASING_LINEAR, t)
    else:
        eased = apply_easing(context.easing, t)

    if preset_id == "dolly_in":
        return _dolly(context, strength, eased, 1.0)
    if preset_id == "dolly_out":
        return _dolly(context, strength, eased, -1.0)
    if preset_id == "orbit":
        return _orbit(context, strength, eased, 0.25 * max(strength, 0.05))
    if preset_id == "turntable":
        return _orbit(context, strength, eased, min(max(strength, 0.1), 1.0))
    if preset_id == "crane_up":
        return _crane(context, strength, eased, 1.0)
    if preset_id == "crane_down":
        return _crane(context, strength, eased, -1.0)
    if preset_id == "parallax_push":
        return _parallax_push(context, strength, eased)
    if preset_id == "pan":
        return _pan(context, strength, eased)
    if preset_id == "tilt":
        return _tilt(context, strength, eased)
    if preset_id == "handheld":
        return _handheld(context, strength, eased)

    return _dolly(context, strength, eased, 1.0)


def speed_phrase(strength):
    if strength < 0.6:
        return "subtle"
    if strength < 1.2:
        return "smooth"
    if strength < 2.0:
        return "pronounced"
    return "dramatic"


def build_prompt(preset_id, strength, fps, frame_count, has_first_last, has_depth, has_normal):
    """Build a paste-ready prompt describing the shot for an AI video tool."""
    spec = preset_spec(preset_id)
    motion = spec["prompt"].format(speed=speed_phrase(strength))
    duration = (frame_count / float(fps)) if fps else 0.0

    lines = [
        "Camera movement: {0}.".format(motion),
        "Motion quality: smooth, physically plausible, no warping or morphing, "
        "stable subject, consistent lighting.",
        "Frame rate: {0} fps. Duration: {1:.2f} seconds ({2} frames).".format(
            int(fps), duration, int(frame_count)
        ),
    ]

    references = []
    if has_first_last:
        references.append(
            "use {first} as the starting frame and {last} as the ending frame".format(
                first="the *_first image", last="the *_last image"
            )
        )
    if has_depth:
        references.append("the *_depth image is the matching depth map for scene layout")
    if has_normal:
        references.append("the *_normal image is the matching normal pass for surface detail")
    if references:
        lines.append("Reference passes: {0}.".format("; ".join(references)))

    return "\n".join(lines) + "\n"
