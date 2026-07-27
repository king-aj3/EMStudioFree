# SPDX-License-Identifier: LGPL-2.1-or-later
"""Resource path helpers for EMStudio (icons, UI files)."""

from __future__ import annotations

import os

_HERE = os.path.dirname(__file__)
ICON_DIR = os.path.join(_HERE, "icons")


def icon_path(name):
    """Absolute path to an icon file under ``resources/icons``."""
    return os.path.join(ICON_DIR, name)
