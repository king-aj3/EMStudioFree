# SPDX-License-Identifier: LGPL-2.1-or-later
"""About EMStudio + the Legal notice, and the once-per-version first-run
notice shown on workbench activation.

Three entry points, all reachable from the EMStudio menu (Help group):

* :class:`AboutDialog`   — ``EMStudio_About``: what the workbench is, the
  version, the development status, credits and links.
* :class:`LegalDialog`   — ``EMStudio_Legal``: intended use, no-warranty /
  no-liability, verification duty, safety exclusion and the brand notice.
* :func:`maybe_show_first_run_notice` — shown ONCE per installed version so a
  user who installs from the Add-on Manager and never opens the repo still
  reads the intended-use and liability terms.

Every word of the legal text comes from :mod:`emstudio.legal` — edit it there,
never here, so the dialogs, the report footers and DISCLAIMER.md cannot drift
apart.
"""

from __future__ import annotations

import FreeCAD
from PySide import QtCore, QtGui, QtWidgets

from emstudio import legal

#: preference flag; the INSTALLED VERSION is stored so the notice reappears
#: after an upgrade (the terms travel with whatever the user just installed)
_PREF_GROUP = "User parameter:BaseApp/Preferences/Mod/EMStudio"
_NOTICE_VERSION_KEY = "LegalNoticeAcknowledgedVersion"

REPO_URL = "https://github.com/king-aj3/EMStudioFree"
SITE_URL = "https://ajj3.com"

#: solver backends are separate programs under their own licences — naming
#: them is both a courtesy and part of staying honest about what is ours
BACKENDS = [
    ("openEMS", "FDTD full-wave", "GPL-3.0, separate process"),
    ("nec2c", "MoM wire antennas", "GPL-2.0, separate process"),
    ("Elmer", "FEM magnetics / thermal", "LGPL-2.1 / GPL-2.0, separate process"),
    ("AWS Palace", "FEM eigenmode / driven", "Apache-2.0, separate process"),
    ("FastHenry", "inductance extraction", "MIT-like, separate process"),
    ("Gmsh", "meshing", "GPL-2.0, separate process"),
]


def _version():
    try:
        from emstudio.version import __version__

        return __version__
    except Exception:  # noqa: BLE001 — the dialog must never fail to open
        return "unknown"


def _icon():
    try:
        from emstudio.resources import icon_path

        return QtGui.QPixmap(icon_path("emstudio_workbench.svg"))
    except Exception:  # noqa: BLE001
        return QtGui.QPixmap()


def _banner(text, fg, bg):
    """A loud, unmissable notice strip."""
    lab = QtWidgets.QLabel(text)
    lab.setWordWrap(True)
    lab.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
    lab.setStyleSheet(
        "QLabel {{ background: {0}; color: {1}; border: 1px solid {1}; "
        "border-radius: 4px; padding: 8px; font-weight: bold; }}".format(bg, fg))
    return lab


def _scrolled(widget):
    area = QtWidgets.QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(widget)
    return area


class LegalDialog(QtWidgets.QDialog):
    """The full in-app legal notice — every section from ``emstudio.legal``."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("EMStudio — Legal notice, disclaimer and terms")
        self.resize(720, 640)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(_banner(legal.INTENDED_USE, "#8a4b00", "#fff3d6"))

        body = QtWidgets.QWidget()
        vb = QtWidgets.QVBoxLayout(body)
        vb.setContentsMargins(4, 4, 4, 4)
        for title, text in legal.LEGAL_SECTIONS:
            head = QtWidgets.QLabel(title)
            f = head.font()
            f.setBold(True)
            f.setPointSize(max(9, f.pointSize() + 1))
            head.setFont(f)
            vb.addWidget(head)
            par = QtWidgets.QLabel(text)
            par.setWordWrap(True)
            par.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            vb.addWidget(par)
            vb.addSpacing(10)
        tail = QtWidgets.QLabel(
            "This in-app notice is a plain-language summary and does not "
            "replace the software licence. The GNU Lesser General Public "
            "License v2.1 (LICENSE) governs the software, including its "
            "warranty disclaimer (§15) and limitation of liability "
            "(§16). The full texts ship with EMStudio as DISCLAIMER.md "
            "and TRADEMARK.md. Nothing here is legal advice.")
        tail.setWordWrap(True)
        tail.setStyleSheet("QLabel { color: palette(mid); }")
        vb.addWidget(tail)
        vb.addStretch(1)
        layout.addWidget(_scrolled(body), 1)

        btns = QtWidgets.QHBoxLayout()
        for label, fname in (("Open DISCLAIMER.md", "DISCLAIMER.md"),
                             ("Open TRADEMARK.md", "TRADEMARK.md"),
                             ("Open LICENSE", "LICENSE")):
            b = QtWidgets.QPushButton(label)
            b.clicked.connect(lambda _=False, n=fname: _open_repo_file(n))
            btns.addWidget(b)
        btns.addStretch(1)
        close = QtWidgets.QPushButton("Close")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        btns.addWidget(close)
        layout.addLayout(btns)


def _repo_root():
    import os

    import emstudio

    return os.path.dirname(os.path.dirname(os.path.abspath(emstudio.__file__)))


def _open_repo_file(name):
    """Open a shipped legal file with the desktop handler; fall back to
    showing its text in a dialog if the desktop cannot open it."""
    import os

    path = os.path.join(_repo_root(), name)
    if not os.path.exists(path):
        QtWidgets.QMessageBox.information(
            None, "EMStudio",
            "{0} is not present in this installation.\nSee {1}".format(
                name, REPO_URL))
        return
    if QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(path)):
        return
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError as exc:
        QtWidgets.QMessageBox.warning(
            None, "EMStudio", "Could not read {0}: {1}".format(name, exc))
        return
    dlg = QtWidgets.QDialog()
    dlg.setWindowTitle("EMStudio — " + name)
    dlg.resize(760, 640)
    lay = QtWidgets.QVBoxLayout(dlg)
    view = QtWidgets.QPlainTextEdit(text)
    view.setReadOnly(True)
    lay.addWidget(view)
    btn = QtWidgets.QPushButton("Close")
    btn.clicked.connect(dlg.accept)
    lay.addWidget(btn)
    dlg.exec_()


class AboutDialog(QtWidgets.QDialog):
    """What EMStudio is, what state it is in, and who is behind it."""

    def __init__(self, parent=None):
        super().__init__(parent)
        ver = _version()
        self.setWindowTitle("About EMStudio")
        self.resize(700, 620)

        layout = QtWidgets.QVBoxLayout(self)

        # --- header ------------------------------------------------------- #
        head = QtWidgets.QHBoxLayout()
        pix = _icon()
        if not pix.isNull():
            ic = QtWidgets.QLabel()
            ic.setPixmap(pix.scaled(64, 64, QtCore.Qt.KeepAspectRatio,
                                    QtCore.Qt.SmoothTransformation))
            head.addWidget(ic)
        title = QtWidgets.QLabel(
            "<h2 style='margin:0'>EMStudio {0}</h2>"
            "<div>RF / electromagnetic modeling and simulation for FreeCAD</div>"
            "<div style='color:gray'>an <b>AJJ³</b> project · "
            "LGPL-2.1-or-later</div>".format(ver))
        title.setTextFormat(QtCore.Qt.RichText)
        head.addWidget(title, 1)
        layout.addLayout(head)

        # --- the two things a new user must read --------------------------- #
        layout.addWidget(_banner(
            "UNDER ACTIVE DEVELOPMENT — more to come. " +
            legal.DEVELOPMENT_STATUS, "#004c8c", "#dceaff"))
        layout.addWidget(_banner(legal.INTENDED_USE, "#8a4b00", "#fff3d6"))

        # --- body ---------------------------------------------------------- #
        body = QtWidgets.QWidget()
        vb = QtWidgets.QVBoxLayout(body)
        vb.setContentsMargins(4, 4, 4, 4)

        def section(head_text, text):
            h = QtWidgets.QLabel(head_text)
            f = h.font()
            f.setBold(True)
            h.setFont(f)
            vb.addWidget(h)
            p = QtWidgets.QLabel(text)
            p.setWordWrap(True)
            p.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            vb.addWidget(p)
            vb.addSpacing(8)

        section("What it is",
                "A free, open-source workbench that wraps best-of-breed "
                "open-source electromagnetic solvers behind one guided "
                "workflow: geometry → materials → ports → mesh "
                "→ solve → results. Alongside the field solvers it "
                "carries system-level engineering tools — antenna element "
                "and array design, impedance matching, filters, cable and "
                "litz-wire design, co-site interference, and geographic "
                "coverage — each with its own validated regime.")
        section("Why it exists",
                "To make RF / antenna / PCB / wire analysis as approachable as "
                "possible — real calculations, clear visualization, "
                "minimal prerequisite theory — and then to produce "
                "professional deliverables (reports, BOMs, build specs) so an "
                "idea can be handed to a supplier and built.")
        section("How results are checked",
                "Physics features ship with an automated validation gate "
                "against published references, closed-form results or an "
                "independent field solver. A gate passing means those specific "
                "cases reproduced those specific reference values on the "
                "developer's machine — it is not a guarantee of accuracy "
                "for your case. See the Legal notice.")

        h = QtWidgets.QLabel("Solver backends")
        f = h.font()
        f.setBold(True)
        h.setFont(f)
        vb.addWidget(h)
        grid = QtWidgets.QLabel("<table cellspacing='0' cellpadding='3'>" +
                                "".join(
                                    "<tr><td><b>{0}</b></td><td>{1}</td>"
                                    "<td style='color:gray'>{2}</td></tr>"
                                    .format(n, w, lic)
                                    for n, w, lic in BACKENDS) + "</table>")
        grid.setTextFormat(QtCore.Qt.RichText)
        vb.addWidget(grid)
        vb.addSpacing(4)
        note = QtWidgets.QLabel(
            "Solvers are invoked as separate, unmodified subprocesses under "
            "their own licences — no solver code is linked or bundled. "
            "EMStudio makes no warranty for their behaviour.")
        note.setWordWrap(True)
        note.setStyleSheet("QLabel { color: palette(mid); }")
        vb.addWidget(note)
        vb.addSpacing(8)

        section("Credits",
                "Built on FreeCAD, and on the work of the openEMS, nec2c, "
                "Elmer, Palace, FastHenry and Gmsh projects — plus the "
                "published work of C.R. Sullivan, J.A. Ferreira and A.D. Watt "
                "on winding losses and VLF engineering.")
        vb.addWidget(_banner(legal.TRADEMARK_NOTICE, "#5a3d00", "#f6efdd"))
        vb.addStretch(1)
        layout.addWidget(_scrolled(body), 1)

        # --- buttons -------------------------------------------------------- #
        btns = QtWidgets.QHBoxLayout()
        b_legal = QtWidgets.QPushButton("Legal notice && disclaimer…")
        b_legal.clicked.connect(self._show_legal)
        btns.addWidget(b_legal)
        b_site = QtWidgets.QPushButton("AJJ³ site")
        b_site.clicked.connect(
            lambda: QtGui.QDesktopServices.openUrl(QtCore.QUrl(SITE_URL)))
        btns.addWidget(b_site)
        b_src = QtWidgets.QPushButton("Source && issues")
        b_src.clicked.connect(
            lambda: QtGui.QDesktopServices.openUrl(QtCore.QUrl(REPO_URL)))
        btns.addWidget(b_src)
        btns.addStretch(1)
        close = QtWidgets.QPushButton("Close")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        btns.addWidget(close)
        layout.addLayout(btns)

    def _show_legal(self):
        dlg = LegalDialog(self)
        dlg.exec_()


class FirstRunNoticeDialog(QtWidgets.QDialog):
    """The once-per-version notice. Deliberately blunt and short."""

    def __init__(self, parent=None, version="unknown"):
        super().__init__(parent)
        self.setWindowTitle("EMStudio {0} — please read".format(version))
        self.resize(620, 460)
        layout = QtWidgets.QVBoxLayout(self)

        layout.addWidget(_banner(
            "EMStudio is UNDER ACTIVE DEVELOPMENT — more to come.",
            "#004c8c", "#dceaff"))
        layout.addWidget(_banner(legal.INTENDED_USE, "#8a4b00", "#fff3d6"))

        body = QtWidgets.QWidget()
        vb = QtWidgets.QVBoxLayout(body)
        for text in (legal.DEVELOPMENT_STATUS, legal.VERIFY_INDEPENDENTLY,
                     legal.NO_LIABILITY, legal.NOT_SAFETY_CRITICAL):
            p = QtWidgets.QLabel(text)
            p.setWordWrap(True)
            p.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            vb.addWidget(p)
            vb.addSpacing(8)
        vb.addStretch(1)
        layout.addWidget(_scrolled(body), 1)

        hint = QtWidgets.QLabel(
            "You can reopen this at any time from the "
            "<b>EMStudio → Help</b> menu (About / Legal notice).")
        hint.setTextFormat(QtCore.Qt.RichText)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        btns = QtWidgets.QHBoxLayout()
        b_legal = QtWidgets.QPushButton("Full legal notice…")
        b_legal.clicked.connect(lambda: LegalDialog(self).exec_())
        btns.addWidget(b_legal)
        btns.addStretch(1)
        ok = QtWidgets.QPushButton("I understand — continue")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        btns.addWidget(ok)
        layout.addLayout(btns)


def show_about(parent=None):
    AboutDialog(parent).exec_()


def show_legal(parent=None):
    LegalDialog(parent).exec_()


def maybe_show_first_run_notice(parent=None):
    """Show the notice once per installed version.

    Never raises: this is called from the workbench ``Activated`` hook, where
    an exception is swallowed by FreeCAD and can destabilize activation.
    Returns the dialog (kept alive by the caller) or None.
    """
    try:
        ver = _version()
        params = FreeCAD.ParamGet(_PREF_GROUP)
        if params.GetString(_NOTICE_VERSION_KEY, "") == ver:
            return None
        params.SetString(_NOTICE_VERSION_KEY, ver)
        dlg = FirstRunNoticeDialog(parent=parent, version=ver)
        dlg.show()          # non-modal: never block workbench activation
        dlg.raise_()
        dlg.activateWindow()
        return dlg
    except Exception as exc:  # noqa: BLE001 — best effort, never fatal
        try:
            FreeCAD.Console.PrintWarning(
                "EMStudio: first-run notice skipped: {0}\n".format(exc))
        except Exception:
            pass
        return None
