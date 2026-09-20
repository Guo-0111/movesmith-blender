"""Resolve a focus point and bake a preset camera move onto a Blender camera."""

from __future__ import annotations

import math

import bpy
from mathutils import Matrix, Vector

from . import presets
from .presets import ShotContext


class MotionError(RuntimeError):
    pass


def camera_forward(camera):
    """World-space direction the camera is currently looking along."""
    return (camera.matrix_world.to_quaternion() @ Vector((0.0, 0.0, -1.0))).normalized()


def scene_bounds(scene):
    """World-space bounding box centre and radius of visible mesh objects."""
    minimum = None
    maximum = None

    for obj in scene.objects:
        if obj.type != "MESH":
            continue
        try:
            if not obj.visible_get():
                continue
        except Exception:
            pass

        for corner in obj.bound_box:
            world = obj.matrix_world @ Vector(corner)
            if minimum is None:
                minimum = world.copy()
                maximum = world.copy()
            else:
                for axis in range(3):
                    minimum[axis] = min(minimum[axis], world[axis])
                    maximum[axis] = max(maximum[axis], world[axis])

    if minimum is None or maximum is None:
        return None

    centre = (minimum + maximum) * 0.5
    radius = (maximum - minimum).length * 0.5
    return centre, max(radius, 1e-3)


def resolve_focus_point(context, camera):
    """Pick the point the move should revolve around.

    Order of preference: an explicit focus object, the first surface the camera
    is already looking at, then the centre of the scene's bounding box.
    """
    scene = context.scene
    focus_object = getattr(scene, "movesmith_focus_object", None)
    if focus_object is not None:
        return focus_object.matrix_world.translation.copy(), "focus object"

    origin = camera.matrix_world.translation.copy()
    forward = camera_forward(camera)
    clip_end = float(camera.data.clip_end) if camera.data else 100.0

    try:
        depsgraph = context.evaluated_depsgraph_get()
        hit, location, _normal, _index, hit_object, _matrix = scene.ray_cast(
            depsgraph, origin, forward, distance=clip_end
        )
        if hit and hit_object is not camera:
            return Vector(location), "camera ray hit"
    except Exception:
        pass

    bounds = scene_bounds(scene)
    if bounds is not None:
        centre, radius = bounds
        along = (centre - origin).dot(forward)
        if along <= radius * 0.1:
            along = radius * 2.0
        return origin + forward * along, "scene bounding box"

    return origin + forward * 5.0, "default distance"


def _iter_fcurves(animation_data):
    """Yield fcurves across legacy and Blender 4.4+ slotted actions."""
    action = getattr(animation_data, "action", None)
    if action is None:
        return

    fcurves = getattr(action, "fcurves", None)
    if fcurves is not None:
        try:
            for fcurve in fcurves:
                yield fcurve
            return
        except Exception:
            pass

    for layer in getattr(action, "layers", None) or ():
        for strip in getattr(layer, "strips", None) or ():
            for channelbag in getattr(strip, "channelbags", None) or ():
                for fcurve in getattr(channelbag, "fcurves", None) or ():
                    yield fcurve


def _ensure_object_mode():
    try:
        if bpy.context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
    except Exception:
        pass


def frame_list(start, end, step):
    """Inclusive frame list that always ends exactly on ``end``."""
    start = int(start)
    end = int(end)
    step = max(1, int(step))
    if end < start:
        start, end = end, start

    frames = list(range(start, end + 1, step))
    if frames[-1] != end:
        frames.append(end)
    return frames


def bake_camera_move(
    context,
    camera,
    preset_id,
    strength=1.0,
    easing=presets.EASING_IN_OUT,
    step=1,
    clear_animation=True,
):
    """Write a preset move onto ``camera`` as one keyframe set per sampled frame."""
    scene = context.scene
    if camera is None or camera.type != "CAMERA":
        raise MotionError("Select a camera before applying a camera move.")

    _ensure_object_mode()

    focus, focus_source = resolve_focus_point(context, camera)
    origin = camera.matrix_world.translation.copy()
    shot = ShotContext(origin=origin, focus=focus, strength=strength, easing=easing)

    frames = frame_list(scene.frame_start, scene.frame_end, step)
    if len(frames) < 2:
        raise MotionError(
            "The scene frame range must span at least two frames to build a move."
        )

    previous_frame = scene.frame_current
    previous_camera = scene.camera

    try:
        scene.camera = camera
        camera.rotation_mode = "QUATERNION"

        if clear_animation:
            camera.animation_data_clear()

        span = float(frames[-1] - frames[0]) or 1.0
        for frame in frames:
            raw_t = (frame - frames[0]) / span
            position, look_at = presets.evaluate(preset_id, shot, raw_t)

            direction = look_at - position
            if direction.length < 1e-6:
                direction = Vector((0.0, 0.0, -1.0))
            quaternion = direction.to_track_quat("-Z", "Y")

            camera.matrix_world = Matrix.Translation(position) @ quaternion.to_matrix().to_4x4()
            camera.keyframe_insert(data_path="location", frame=frame)
            camera.keyframe_insert(data_path="rotation_quaternion", frame=frame)

        interpolation = "LINEAR" if step <= 1 else "BEZIER"
        for fcurve in _iter_fcurves(camera.animation_data):
            for keyframe in fcurve.keyframe_points:
                keyframe.interpolation = interpolation
    finally:
        scene.frame_set(previous_frame)
        if previous_camera is not None:
            scene.camera = previous_camera

    constraints = [constraint.type for constraint in camera.constraints]
    return {
        "preset": preset_id,
        "frames": len(frames),
        "frame_start": frames[0],
        "frame_end": frames[-1],
        "focus_source": focus_source,
        "constraints": constraints,
    }
