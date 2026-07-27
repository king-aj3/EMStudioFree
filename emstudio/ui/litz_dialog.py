# SPDX-License-Identifier: LGPL-2.1-or-later
"""Back-compat shim — the Litz / Wire Designer became the Cable Designer (v0.37.0).

The full dialog now lives in :mod:`emstudio.ui.cable_dialog` with a top-level
Construction selector (Litz | Coax | Single Wire); the litz page is unchanged.
"""

from emstudio.ui.cable_dialog import CableDesignerDialog, LitzDesignerDialog  # noqa: F401
