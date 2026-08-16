"""What the free workbench shows where a Pro feature would be.

The free build used to DELETE the Pro commands on export, so a free user's
System menu simply had a hole in it. Nobody buys a room they never learn
exists: measured 2026-08-16, 145 installs had produced 111 page views, one
star and zero sales, and the only mentions of Pro were an About-dialog
section and a Help entry that reads like an install chore. An absent room
does not sell; a locked door does.

So the entries STAY in the menu, and clicking one opens a single dialog that
says what the feature does, what it was measured against, and what it costs.

Three rules, because the line between "honest pointer" and "nagware" is the
whole reputation of an open-core addon in the FreeCAD community:

* Nothing here ever pops up on its own. Every dialog in this module is opened
  by an explicit click on a menu entry the user chose.
* Every claim is a MEASURED number from the validation gates, quoted with its
  units and its comparison — never an adjective. An RF engineer buys evidence.
* The copy names the price. `legal.PRO_TEASER_*` says why: "a pointer that
  makes you go and find out is a nag with extra steps."

NO paid logic lives here. This module ships in the PUBLIC repo and holds only
strings, a dialog, and a command class — which is also why it can quote the
Pro gate results without exporting a line of the code that produces them.
"""

from __future__ import annotations

import FreeCAD
import FreeCADGui
from PySide import QtCore, QtGui, QtWidgets

from emstudio import legal
from emstudio.resources import icon_path


#: key -> what the menu entry says, what the feature is, and the evidence.
#:
#: `blurb` is reused from ``emstudio.legal`` where a line already existed —
#: PRO_TEASER_MATCHING and PRO_TEASER_ARRAY were written for exactly this and
#: had never been displayed anywhere.
#:
#: `proof` entries are quoted from the validation gates in the private repo
#: (tests/validation/system_*.py). Keep them in step with the gates: a number
#: here that the gate no longer produces is a false claim in a paid pitch.
FEATURES = {
    "matching": {
        "menu": "Matching Designer… (Pro)",
        "title": "Impedance matching — EMStudio Pro",
        "blurb": legal.PRO_TEASER_MATCHING,
        "proof": [
            "L / pi / T / quarter-wave / binomial / single-stub / hairpin / "
            "gamma synthesis, with a topology recommender.",
            "Finite-Q component loss, and E-series snapping so the answer is "
            "a part you can actually buy.",
            "Ingests a typed impedance or a live NEC2 sweep, then plots "
            "predicted against achieved so the match is verified, not assumed.",
        ],
    },
    "array": {
        "menu": "Array Designer… (Pro)",
        "title": "Phased arrays — EMStudio Pro",
        "blurb": legal.PRO_TEASER_ARRAY,
        "proof": [
            "Element CURRENTS solved through the real mutual-impedance matrix "
            "(V = Z·I), then driven as one multi-EX NEC2 run — a cardioid "
            "measured 29.6 dB front-to-back, where the naive equal-voltage "
            "drive gives 3.4 dB.",
            "Binomial / Dolph-Chebyshev / Taylor-n̄ amplitude tapers: the "
            "−26.02 dB Chebyshev sidelobe floor reproduced to 0.04 dB, against "
            "−12.7 dB uniform.",
            "Scanning and 2-D arrays, with pattern CSV export.",
        ],
    },
    "rfdf": {
        "menu": "RF Direction Finding… (Pro)",
        "title": "RF direction finding — EMStudio Pro",
        "blurb": "Direction finding — Watson-Watt / Adcock, phase "
                 "interferometry, pseudo-Doppler and a correlative manifold "
                 "built live from your own elements — is part of EMStudio Pro "
                 "(the System Designer), " + legal.PRO_PRICE + ". See ajj3.us.",
        "proof": [
            "Watson-Watt octantal error computed from the exact crossed-pair "
            "response, not a textbook approximation.",
            "Phase interferometer sized against the 3.3σ patent criterion; "
            "pseudo-Doppler ring sizing.",
            "A correlative manifold built from one NEC2 run per element — a "
            "manifold from 5 transmit runs decoded a genuine receive run at "
            "0.00° error.",
        ],
    },
    "assistant": {
        "menu": "AI Assistant… (Pro)",
        "title": "The AI assistant — EMStudio Pro",
        "blurb": "The assistant — which reads your model, runs the solvers "
                 "and explains the result in RF terms — is part of EMStudio "
                 "Pro, " + legal.PRO_PRICE + ". See ajj3.us.",
        "proof": [
            "Answers are checked against the model before you see them: the "
            "plausibility gate is 131 checks, 16 of them proven by mutation.",
            "It reports measured quantities from YOUR run — front-to-back, "
            "HPBW, bandwidth — rather than generating prose about antennas.",
        ],
    },
}


class ProTeaserDialog(QtWidgets.QDialog):
    """One feature, what it does, what it measured, what it costs."""

    def __init__(self, key, parent=None):
        super(ProTeaserDialog, self).__init__(parent)
        feat = FEATURES[key]
        self.setWindowTitle(feat["title"])
        self.setMinimumWidth(560)

        lay = QtWidgets.QVBoxLayout(self)

        head = QtWidgets.QLabel(feat["title"])
        f = head.font()
        f.setBold(True)
        f.setPointSize(f.pointSize() + 2)
        head.setFont(f)
        lay.addWidget(head)

        blurb = QtWidgets.QLabel(feat["blurb"])
        blurb.setWordWrap(True)
        lay.addWidget(blurb)

        box = QtWidgets.QGroupBox("Measured, not claimed")
        inner = QtWidgets.QVBoxLayout(box)
        for line in feat["proof"]:
            item = QtWidgets.QLabel("•  " + line)
            item.setWordWrap(True)
            inner.addWidget(item)
        lay.addWidget(box)

        note = QtWidgets.QLabel(
            "EMStudio Pro is {0} — perpetual, no subscription and no account. "
            "This free workbench keeps every solver, template, the Element and "
            "Cable Designers, magnetics, coverage and all of its validation "
            "gates.".format(legal.PRO_PRICE))
        note.setWordWrap(True)
        lay.addWidget(note)

        btns = QtWidgets.QDialogButtonBox()
        see = btns.addButton("See EMStudio Pro", QtWidgets.QDialogButtonBox.ActionRole)
        have = btns.addButton("I already bought it…", QtWidgets.QDialogButtonBox.ActionRole)
        btns.addButton(QtWidgets.QDialogButtonBox.Close)
        see.clicked.connect(self._open_store)
        have.clicked.connect(self._open_licence)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _open_store(self):
        QtGui.QDesktopServices.openUrl(QtCore.QUrl(legal.PRO_URL))

    def _open_licence(self):
        # Chain to the real install/activate dialog rather than duplicating it:
        # a buyer arriving here has a zip and a key, and that dialog is the one
        # that knows what to do with them.
        from emstudio.ui.licence_dialog import show_licence_dialog

        self.accept()
        show_licence_dialog(self.parent())


def show_teaser(key, parent=None):
    """Open the explainer for one feature. Never called except from a click."""
    if key not in FEATURES:
        raise KeyError("unknown Pro feature %r" % (key,))
    dlg = ProTeaserDialog(key, parent or FreeCADGui.getMainWindow())
    dlg.exec_()


class ProTeaserCommand(object):
    """A menu entry standing where a Pro command would be.

    Deliberately ENABLED rather than greyed out. A disabled QAction cannot be
    clicked, so it can never explain itself — the user learns only that
    something is missing, which is the state that sold nothing for three weeks.
    """

    def __init__(self, key):
        self.key = key

    def GetResources(self):
        feat = FEATURES[self.key]
        return {
            "Pixmap": icon_path("emstudio_pro.svg"),
            "MenuText": feat["menu"],
            "ToolTip": feat["blurb"],
        }

    def IsActive(self):
        # Always: this must be reachable with no document open, exactly like
        # the licence entry it complements.
        return True

    def Activated(self):
        show_teaser(self.key, FreeCADGui.getMainWindow())
