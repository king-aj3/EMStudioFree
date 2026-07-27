# SPDX-License-Identifier: LGPL-2.1-or-later
"""Shared legal-notice strings (see DISCLAIMER.md / TRADEMARK.md for the full
text).

GUI-free; safe to import from any module. These lines are embedded in every
artifact EMStudio generates (PDF reports, spec/BOM exports) because those
documents travel to third parties — the disclaimer must travel with them —
and they back the in-app About / Legal dialogs (``EMStudio_About``,
``EMStudio_Legal``) so a user who never opens the repo still sees them.

Single source of truth: edit the wording HERE, not in the dialogs, the report
footers or the workbench activation notice.
"""

# --------------------------------------------------------------------------- #
# intended use — the FIRST thing a new user should read
# --------------------------------------------------------------------------- #
INTENDED_USE = (
    "EMStudio is intended for EDUCATIONAL, HOBBYIST and EXPERIMENTAL use. "
    "It is a learning and exploration tool, not a certified engineering "
    "product, and it is not a substitute for qualified professional "
    "engineering, for measurement, or for regulatory compliance work."
)

# short form for status bars / one-line footers
INTENDED_USE_SHORT = (
    "For educational, hobbyist and experimental use — not a certified "
    "engineering tool."
)

DEVELOPMENT_STATUS = (
    "EMStudio is under ACTIVE DEVELOPMENT. Features are still being added, "
    "refined and re-validated; interfaces, defaults and results may change "
    "between versions, and some areas are more mature than others. More to "
    "come — expect rough edges, and please report what you find."
)

# --------------------------------------------------------------------------- #
# liability
# --------------------------------------------------------------------------- #
NO_LIABILITY = (
    "NO WARRANTY AND NO LIABILITY. EMStudio is provided free of charge, "
    "\"AS IS\" and \"AS AVAILABLE\", with no warranty of any kind, express or "
    "implied — including merchantability, fitness for a particular purpose, "
    "accuracy, reliability, completeness and non-infringement. The author, "
    "the AJJ³ project, and all contributors and maintainers accept NO "
    "RESPONSIBILITY and NO LIABILITY WHATSOEVER for any damage, injury, "
    "death, loss, cost, radio interference, regulatory penalty, loss of "
    "profit or data, or any other direct, indirect, incidental, special or "
    "consequential harm arising from the software, from its outputs, or from "
    "anything designed, built, purchased, energized, transmitted or operated "
    "on the basis of them — even if advised of the possibility. You use "
    "EMStudio and everything it produces ENTIRELY AT YOUR OWN RISK."
)

VERIFY_INDEPENDENTLY = (
    "Every number, curve, field map, report, BOM and recommendation EMStudio "
    "produces is an engineering ESTIMATE that can be wrong — sometimes badly "
    "and silently wrong. You are solely responsible for independently "
    "verifying every result (measurement, prototyping, independent "
    "calculation, qualified review) before any reliance on it, and for all "
    "regulatory, spectrum, EMC and RF-safety compliance in your jurisdiction."
)

NOT_SAFETY_CRITICAL = (
    "NOT for safety-critical, life-critical or high-risk use — including "
    "medical, aviation, spaceflight, nuclear, weapons, safety-interlock or "
    "critical-infrastructure applications. EMStudio is neither designed, "
    "tested nor licensed for any of them."
)

# --------------------------------------------------------------------------- #
# brand — LGPL covers copyright, NOT trademark (see TRADEMARK.md)
# --------------------------------------------------------------------------- #
TRADEMARK_NOTICE = (
    "\"EMStudio\", \"AJJ³\", the AJJ³ logo and ajj3.com are marks of the "
    "AJJ³ project and are NOT licensed under the LGPL with the code. The "
    "source is free to copy, modify and redistribute under the LGPL; the "
    "NAMES AND BRANDING ARE NOT. Forks and redistributions carrying "
    "modifications must use a different name and must remove AJJ³ branding, "
    "and nothing in the licence grants the right to imply endorsement by, "
    "affiliation with, or origin from the AJJ³ project. See TRADEMARK.md."
)

# --------------------------------------------------------------------------- #
# composed forms
# --------------------------------------------------------------------------- #
# one-liner for report footers / spec exports / console notices
SHORT_DISCLAIMER = (
    "For educational/hobbyist/experimental use — engineering ESTIMATES only; "
    "independently verify all results before any reliance; NO WARRANTY and NO "
    "LIABILITY, use entirely at your own risk (see DISCLAIMER.md)."
)

# markdown footer block for generated spec/BOM documents
SPEC_DISCLAIMER = (
    "*DISCLAIMER: this document was produced by EMStudio, a tool for "
    "EDUCATIONAL, HOBBYIST and EXPERIMENTAL use that is under active "
    "development. All values above are engineering estimates produced by "
    "simulation/analytic models and may be inaccurate. Independently verify "
    "every value (measurement, prototyping, qualified engineering review) "
    "before manufacture, purchase, deployment, or any other reliance. "
    "Provided AS IS with NO WARRANTY of any kind; the author, contributors "
    "and the AJJ³ project accept NO RESPONSIBILITY OR LIABILITY for any "
    "damage, injury, loss, interference or cost arising from use of this "
    "document or the software that produced it. See DISCLAIMER.md in the "
    "EMStudio distribution.*"
)

# the paragraphs the in-app Legal dialog shows, in order
LEGAL_SECTIONS = (
    ("Intended use", INTENDED_USE),
    ("Development status", DEVELOPMENT_STATUS),
    ("Results are estimates — verify them", VERIFY_INDEPENDENTLY),
    ("No warranty, no liability", NO_LIABILITY),
    ("No safety-critical use", NOT_SAFETY_CRITICAL),
    ("Names and branding", TRADEMARK_NOTICE),
)

# shown once per installed version on workbench activation
FIRST_RUN_NOTICE = "\n\n".join((INTENDED_USE, DEVELOPMENT_STATUS, NO_LIABILITY))


def console_banner(version=None):
    """The multi-line notice printed to the FreeCAD console on activation."""
    head = "EMStudio" if not version else "EMStudio {0}".format(version)
    return ("{0} — {1}\n  {2}\n  {3}\n".format(
        head, INTENDED_USE_SHORT,
        "UNDER ACTIVE DEVELOPMENT — more to come; results and interfaces may "
        "change between versions.",
        SHORT_DISCLAIMER))
