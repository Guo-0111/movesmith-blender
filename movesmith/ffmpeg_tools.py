"""Locate and run ffmpeg for preview movie encoding.

MoveSmith ships its own ffmpeg build so that a buyer never has to install
anything, but it also honours an explicit path from the add-on preferences and
falls back to a system ffmpeg when one is available.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys

DEFAULT_TIMEOUT_SECONDS = 30 * 60
MAX_ERROR_CHARS = 4000

STANDARD_BIN_DIRS = (
    "/usr/local/bin",
    "/opt/homebrew/bin",
    "/usr/bin",
)


class FFmpegError(RuntimeError):
    pass


def package_root():
    return os.path.dirname(os.path.abspath(__file__))


def _runtime_root():
    return os.path.join(package_root(), "runtime", "ffmpeg")


def _bundled_candidates():
    root = _runtime_root()
    if sys.platform.startswith("win"):
        machine = platform.machine().lower()
        if sys.maxsize <= 2 ** 32:
            names = ("windows-x86", "windows-x86_64", "windows-arm64")
        elif machine in ("arm64", "aarch64"):
            names = ("windows-arm64", "windows-x86_64", "windows-x86")
        else:
            names = ("windows-x86_64", "windows-x86", "windows-arm64")
        return [os.path.join(root, name, "ffmpeg.exe") for name in names]

    if sys.platform == "darwin":
        machine = platform.machine().lower()
        if machine in ("arm64", "aarch64"):
            names = ("macos-aarch64", "macos-x86_64")
        else:
            names = ("macos-x86_64", "macos-aarch64")
        return [os.path.join(root, name, "ffmpeg") for name in names]

    return [os.path.join(root, "linux-x86_64", "ffmpeg")]


def _subprocess_env():
    env = os.environ.copy()
    existing = env.get("PATH", "")
    parts = [item for item in STANDARD_BIN_DIRS if item and os.path.isdir(item)]
    env["PATH"] = os.pathsep.join(parts + ([existing] if existing else []))
    return env


def candidates(explicit_path=""):
    """Every ffmpeg location worth trying, in priority order."""
    found = []

    if explicit_path:
        found.append(explicit_path)

    env_path = os.environ.get("MOVESMITH_FFMPEG")
    if env_path:
        found.append(env_path)

    found.extend(_bundled_candidates())

    which = shutil.which("ffmpeg", path=_subprocess_env().get("PATH"))
    if which:
        found.append(which)

    found.extend(("/usr/local/bin/ffmpeg", "/opt/homebrew/bin/ffmpeg", "/usr/bin/ffmpeg"))
    if sys.platform.startswith("win"):
        for root in (
            os.environ.get("ProgramFiles", ""),
            os.environ.get("ProgramFiles(x86)", ""),
            os.environ.get("LOCALAPPDATA", ""),
        ):
            if root:
                found.append(os.path.join(root, "ffmpeg", "bin", "ffmpeg.exe"))

    unique = []
    seen = set()
    for candidate in found:
        if not candidate:
            continue
        key = os.path.normcase(os.path.abspath(candidate))
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def path_is_usable(path):
    if not path or not os.path.exists(path):
        return False
    if sys.platform.startswith("win"):
        return True
    return os.access(path, os.X_OK)


def available_path(explicit_path=""):
    for candidate in candidates(explicit_path):
        if path_is_usable(candidate):
            return candidate
    return ""


def _decode(output):
    if isinstance(output, bytes):
        output = output.decode("utf-8", "replace")
    text = str(output or "").strip()
    if len(text) > MAX_ERROR_CHARS:
        text = "..." + text[-MAX_ERROR_CHARS:]
    return text


def _prepare(path):
    if not sys.platform.startswith("win"):
        try:
            os.chmod(path, os.stat(path).st_mode | 0o755)
        except Exception:
            pass
    return path_is_usable(path)


def _remove(path):
    if not path:
        return
    try:
        if os.path.exists(path):
            os.unlink(path)
    except OSError:
        pass


def missing_ffmpeg_help():
    """Explain what to do when no ffmpeg could be found on this platform.

    Only a Windows build is vendored, so telling a macOS user that the add-on
    "ships one" would send them looking for a file that is not there.
    """
    if sys.platform.startswith("win"):
        return (
            "No usable ffmpeg was found. MoveSmith ships one for Windows, so "
            "reinstalling the add-on usually fixes this, or point at your own copy "
            "in the add-on preferences."
        )
    if sys.platform == "darwin":
        return (
            "No usable ffmpeg was found. MoveSmith only bundles ffmpeg for Windows. "
            "Install it with 'brew install ffmpeg', or point at your own copy in the "
            "add-on preferences."
        )
    return (
        "No usable ffmpeg was found. MoveSmith only bundles ffmpeg for Windows. "
        "Install it with your package manager, or point at your own copy in the "
        "add-on preferences."
    )


def run(arguments, output_path=None, explicit_path="", timeout_seconds=None):
    """Run ffmpeg with the given arguments, trying each known binary in turn."""
    timeout = float(timeout_seconds or DEFAULT_TIMEOUT_SECONDS)
    failures = []
    attempted = []

    for candidate in candidates(explicit_path):
        if not _prepare(candidate):
            continue

        binary = os.path.abspath(candidate)
        attempted.append(binary)
        _remove(output_path)

        command = [binary] + list(arguments)
        try:
            subprocess.check_output(
                command,
                env=_subprocess_env(),
                stderr=subprocess.STDOUT,
                timeout=timeout,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                if sys.platform.startswith("win")
                else 0,
            )
        except subprocess.TimeoutExpired as exc:
            detail = _decode(getattr(exc, "output", None))
            reason = "timed out after {0:g} seconds".format(timeout)
            failures.append("{0}: {1}{2}".format(binary, reason, ": " + detail if detail else ""))
            _remove(output_path)
            continue
        except subprocess.CalledProcessError as exc:
            detail = _decode(exc.output) or "exit code {0}".format(exc.returncode)
            failures.append("{0}: {1}".format(binary, detail))
            _remove(output_path)
            continue
        except OSError as exc:
            failures.append("{0}: {1}".format(binary, exc))
            _remove(output_path)
            continue

        if output_path and (not os.path.exists(output_path) or os.path.getsize(output_path) <= 0):
            failures.append("{0}: produced no output at {1}".format(binary, output_path))
            _remove(output_path)
            continue

        return binary

    if not attempted:
        raise FFmpegError(missing_ffmpeg_help())

    raise FFmpegError("ffmpeg failed in every candidate.\n" + "\n".join(failures))


def encode_sequence(frames_dir, output_path, fps, start_number=1, explicit_path=""):
    """Encode a PNG sequence into an H.264 MP4 that AI video tools accept."""
    pattern = os.path.join(frames_dir, "frame_%04d.png")
    arguments = [
        "-y",
        "-framerate",
        str(int(fps) or 24),
        "-start_number",
        str(int(start_number)),
        "-i",
        pattern,
        "-vf",
        "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-tag:v",
        "avc1",
        "-movflags",
        "+faststart",
        output_path,
    ]
    run(arguments, output_path=output_path, explicit_path=explicit_path)
    return output_path
