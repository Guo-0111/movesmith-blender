"""Edition flags for MoveSmith.

The full and lite builds share one codebase. ``tools/build.py`` rewrites
``EDITION`` when it packages the lite zip, so this file is the single place
that decides which features exist in a given build.
"""

from __future__ import annotations

# "full" or "lite". Patched at build time for the lite package.
EDITION = "lite"

IS_LITE = EDITION != "full"

# Presets and export kinds available in the lite build.
LITE_PRESETS = ("dolly_in", "orbit")
LITE_EXPORT_KINDS = ("first",)

UPGRADE_URL = "https://superhivemarket.com/creators/movesmith"


def has_feature(feature):
    """Return True when the current edition includes ``feature``.

    ``presets``, ``passes``, ``preview`` and ``batch`` are the gated features.
    """
    if not IS_LITE:
        return True
    return feature not in {"presets", "passes", "preview", "batch"}


def preset_allowed(preset_id):
    if not IS_LITE:
        return True
    return preset_id in LITE_PRESETS


def export_kind_allowed(kind):
    if not IS_LITE:
        return True
    return kind in LITE_EXPORT_KINDS
