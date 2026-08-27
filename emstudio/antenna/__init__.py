# SPDX-License-Identifier: LGPL-2.1-or-later
"""Antenna analytics: the synthesis engines behind the Element Designer.

The first resident was the electrically-small-antenna analytic module used for
VLF/LF/MF characterization, where antennas are a tiny fraction of a wavelength
and the full-wave field solvers are impractical (see docs/CAPABILITIES.md
"Frequency range" and docs/ROADMAP.md §4). It has since been joined by the
other seven Element Designer families — wire, Yagi-Uda (TN-688), microstrip
patch, LPDA (Carrel), pyramidal horn, printed inverted-F and PIFA — plus the
deterministic ``element_picker`` recommender. The AI assistant is not future
work either: ROADMAP §3 shipped in v0.71-v0.73 and is a registered command.
"""
