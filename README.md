# MoveSmith Lite - AI Video Camera Kit for Blender

**Free.** Bakes a cinematic camera move onto your Blender camera and exports the
first frame as a ready-to-use image for AI video generators.

![Product turntable](https://raw.githubusercontent.com/Guo-0111/movesmith-blender/main/assets/gifs/01-product-turntable.gif)

## The problem

You can prompt an AI video generator for "slow push in" all day. What comes back
drifts, warps, and re-frames itself. The reliable way to control camera movement
is to hand the generator real frames: a first frame, a last frame, and a depth
reference that pins the geometry down.

Producing those by hand means building a camera rig, keyframing it, rendering
stills at both ends, setting up a Z pass, and fighting the compositor.
MoveSmith Lite does the first half of that for free.

## What Lite does

**Two camera moves, properly built.**

- **Dolly In** - push toward the subject and end tighter
- **Orbit** - arc sideways around the subject at a constant height

Both are *centred on your current framing*: the midpoint of the frame range
reproduces exactly what you already have set up, and the move extends
symmetrically around it. You never have to re-frame after applying one, and the
result does not depend on where your timeline starts.

**Exports the first frame** at vertical 9:16, landscape 16:9, square 1:1, or
your scene resolution.

**Also exports a prompt.** An English description of the camera move you just
made, ready to paste into the generator alongside the image.

## Install

1. Download `movesmith_ai_video_kit_lite-1.0.0-blender42plus.zip` from
   [Releases](../../releases).
2. In Blender 4.2 or newer: `Edit > Preferences > Add-ons > Install...` and pick
   the zip.
3. Enable **MoveSmith Lite** and open `3D View > Sidebar > MoveSmith`.

For Blender 3.6 to 4.1, use the `-legacy.zip` instead.

Tested on 4.2 LTS and 5.2 LTS.

## Use it

1. Select the camera you want to move.
2. Pick **Dolly In** or **Orbit**, set **Amount**, and hit **Apply Camera Move**.
   The move is baked as plain location and quaternion keys across the scene
   frame range.
3. Set an output folder and hit **Export Shot Package**.

Files are named `project_shot_kind`, so your export folder stays readable. The
move is non-destructive: render settings, frame position and camera are all
restored when the export finishes, and the bake is a single undo.

## What the full version adds

| | Lite | Full |
| --- | --- | --- |
| Camera moves | 2 | 10 - adds Dolly Out, Turntable, Crane Up, Crane Down, Parallax Push, Pan, Tilt, Handheld |
| First frame | yes | yes |
| Last frame and evenly spaced middle frames | - | yes |
| Depth pass, normalised against visible geometry, with a manual range override | - | yes |
| Normal pass | - | yes |
| MP4 motion preview, ffmpeg included | - | yes |
| Batch export, one package per camera | - | yes |

![Depth pass](https://raw.githubusercontent.com/Guo-0111/movesmith-blender/main/assets/gifs/03-depth-pass.gif)

The depth pass is normalised against the surfaces your camera can actually see,
not the whole scene bounding box. That matters: normalising against the bounding
box spends most of the dynamic range on empty space and washes the subject out
to flat white. There is a manual range override for scenes where a distant
floor still eats the range.

[**Get the full version**](https://payhip.com/b/3JNb7) - $29

## Design notes

Everything below is true of Lite too.

**Moves are baked, not constrained.** Each sampled frame gets a plain location
and quaternion keyframe. Baked keys render predictably on a farm, survive file
transfers, and export cleanly to any other tool. A constraint rig would be more
live, and more surprising.

**Fully offline.** No account, no cloud, no upload, no telemetry. The add-on
makes no network requests of any kind. The only permission it asks for is
writing the files you asked for.

**Renaming safe.** Project and shot names keep non-Latin characters, so CJK
project names produce usable file names rather than collapsing to `untitled`.

## Tested

The acceptance suite runs inside Blender and checks the motion maths, the baked
keyframes, the exported files, and the panel wiring, on Blender 4.2 LTS and
5.2 LTS, against both the source tree and the packaged zip.

## Licence

GPL-3.0-or-later, as Blender add-ons must be. You are free to read it, modify
it, and share it. If you repackage it, please change the add-on id so it does
not collide with this one.
