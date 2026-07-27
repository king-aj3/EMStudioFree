# SPDX-License-Identifier: LGPL-2.1-or-later
"""Result container for eigenmode (resonant-cavity) analyses — Palace backend.

Not a frequency sweep — an eigenmode solve returns a set of resonant modes
(frequency + Q). Shared by the runner, GUI dialog, and validation gates;
Qt-free and FreeCAD-free.
"""
from __future__ import annotations


class EigenModeResult:
    """Resonant modes of a cavity: frequency (GHz) and Q per mode."""

    def __init__(self, modes, meta=None):
        #: list of {"index", "freq_ghz", "imag_ghz", "q"} sorted by frequency
        self.modes = list(modes)
        self.meta = dict(meta or {})

    def freqs_ghz(self):
        return [m["freq_ghz"] for m in self.modes]

    def dominant_ghz(self):
        """Lowest resonant frequency (the fundamental mode), or None."""
        return self.modes[0]["freq_ghz"] if self.modes else None

    def summary_text(self):
        lines = ["EMStudio eigenmode results (Palace, FEM)"]
        lines.append("")
        lines.append("  {0:>4}  {1:>14}  {2:>12}".format("mode", "f [GHz]", "Q"))
        for m in self.modes:
            q = m["q"]
            q_txt = "inf" if q != q or q == float("inf") else "{0:.4g}".format(q)
            lines.append("  {0:>4}  {1:>14.6f}  {2:>12}".format(
                m["index"], m["freq_ghz"], q_txt))
        lines.append("")
        if self.meta.get("workdir"):
            lines.append("workdir: {0}".format(self.meta["workdir"]))
        if self.meta.get("duration_s") is not None:
            lines.append("solve time: {0:.1f} s".format(self.meta["duration_s"]))
        return "\n".join(lines)

    def save_csv(self, path):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("mode,freq_ghz,imag_ghz,q\n")
            for m in self.modes:
                fh.write("{0},{1:.9g},{2:.9g},{3:.9g}\n".format(
                    m["index"], m["freq_ghz"], m["imag_ghz"], m["q"]))
        return path
