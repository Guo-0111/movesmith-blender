"""Small shared helpers for MoveSmith."""

from __future__ import annotations

import os
import re

ADDON_NAME = "MoveSmith"
ADDON_VERSION = "1.0.0"

# Unicode-aware: CJK project and shot names are kept intact rather than being
# transliterated away, which matters for non-English users.
_UNSAFE = re.compile(r"[^\w.-]+", re.UNICODE)
_COLLAPSE = re.compile(r"_{2,}")


def sanitize_token(value, fallback="untitled", max_length=48):
    """Turn arbitrary text into a filesystem-safe, shell-friendly token.

    Letters and digits from any script survive; everything else collapses into
    single underscores. The result never contains path separators, so it is
    safe to join onto an output directory.
    """
    text = str(value or "").strip()
    if not text:
        return fallback

    text = text.replace(os.sep, "_").replace("/", "_").replace("\\", "_")
    text = _UNSAFE.sub("_", text)
    text = _COLLAPSE.sub("_", text).strip("._- ")

    if not text:
        return fallback
    return text[:max_length]


def unique_path(directory, filename):
    """Return a path inside ``directory`` that does not collide with an existing file."""
    candidate = os.path.join(directory, filename)
    if not os.path.exists(candidate):
        return candidate

    stem, extension = os.path.splitext(filename)
    index = 2
    while True:
        candidate = os.path.join(directory, "{0}_{1}{2}".format(stem, index, extension))
        if not os.path.exists(candidate):
            return candidate
        index += 1


def ensure_directory(path):
    if path and not os.path.isdir(path):
        os.makedirs(path)
    return path


def clamp(value, low, high):
    return max(low, min(high, value))
