# SPDX-License-Identifier: LGPL-2.1-or-later
"""Install and activate EMStudio Pro — the free core's side of the paid tier.

This dialog is INSTALLER ONLY, and deliberately so. It unpacks the zip a buyer
downloads from Gumroad into its own FreeCAD Mod directory and then hands the
licence key to ``emstudio_pro.licence.activate``. It contains no verification
logic of its own, because a check that ships in LGPL code is deleted in thirty
seconds — entirely within the user's rights. All verification lives in the paid
module, which is the only place it means anything.

Two things it must get right, both of them about not damaging an existing
install:

* the zip is extracted to a SIBLING of ``Mod/EMStudio``, never into it. The
  Add-on Manager owns ``Mod/EMStudio`` and overwrites it on every update, which
  would silently delete a paid module installed inside it.
* archive members are validated before extraction. A zip entry may name
  ``../../anything``; :meth:`zipfile.ZipFile.extractall` on such an entry writes
  outside the target directory. The zip is a downloaded file, so it is treated
  as untrusted input even though it came from our own storefront.
"""

from __future__ import annotations

import importlib
import os
import sys
import zipfile

import FreeCAD
from PySide import QtCore, QtGui, QtWidgets

#: The Mod subdirectory the paid module is installed into. A sibling of
#: ``Mod/EMStudio`` — see the module docstring.
PRO_DIR_NAME = "EMStudioPro"

#: What a valid Pro archive must contain, checked before anything is written.
_REQUIRED_MEMBER = "emstudio_pro/__init__.py"

STORE_URL = "https://ajj3us.gumroad.com"


def mod_dir():
    """FreeCAD's user Mod directory for the RUNNING version.

    ``getUserAppDataDir()`` is already version-suffixed on FreeCAD >= 1.1
    (``.../FreeCAD/v1-1/``), so this resolves to the right place on both
    supported versions without special-casing either.
    """
    return os.path.join(FreeCAD.getUserAppDataDir(), "Mod")


def install_dir():
    return os.path.join(mod_dir(), PRO_DIR_NAME)


def _safe_members(zf, dest):
    """Archive members that are safe to extract, or raise ValueError.

    Rejects absolute paths, parent-directory traversal and symlink entries.
    Returns the member list so the caller extracts exactly what was validated.
    """
    dest = os.path.realpath(dest)
    members = zf.infolist()
    for info in members:
        name = info.filename
        if name.startswith("/") or name.startswith("\\") or ".." in name.split("/"):
            raise ValueError("archive contains an unsafe path: " + name)
        target = os.path.realpath(os.path.join(dest, name))
        if not (target == dest or target.startswith(dest + os.sep)):
            raise ValueError("archive would write outside the install "
                             "directory: " + name)
        # 0xA000 = S_IFLNK in the high bits of external_attr
        if (info.external_attr >> 16) & 0xF000 == 0xA000:
            raise ValueError("archive contains a symlink: " + name)
    return members


def install_zip(zip_path):
    """Extract a Pro archive into the Mod directory. Returns the install path.

    Raises ValueError with a user-readable message on anything wrong.
    """
    if not zip_path or not os.path.isfile(zip_path):
        raise ValueError("that file does not exist")
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile:
        raise ValueError("that file is not a zip archive")
    with zf:
        names = set(zf.namelist())
        if _REQUIRED_MEMBER not in names:
            raise ValueError(
                "this zip does not contain EMStudio Pro (no {0}). Check you "
                "picked the download from your purchase.".format(_REQUIRED_MEMBER))
        dest = install_dir()
        os.makedirs(dest, exist_ok=True)
        members = _safe_members(zf, dest)
        zf.extractall(dest, members=members)
    return dest


def _import_pro():
    """Import the freshly installed module without needing a FreeCAD restart.

    FreeCAD puts Mod directories on ``sys.path`` at startup, so a module
    installed during this session is not importable yet. Adding the directory
    here lets activation be verified immediately — the user still restarts to
    get the toolbars, but they find out NOW whether their key works.
    """
    dest = install_dir()
    if dest not in sys.path:
        sys.path.insert(0, dest)
    for name in [m for m in sys.modules if m == "emstudio_pro"
                 or m.startswith("emstudio_pro.")]:
        del sys.modules[name]
    # REQUIRED, and the reason is easy to miss: opening this dialog calls
    # _refresh_status(), which calls this function and fails with ImportError
    # when Pro is not installed yet. That failed lookup leaves a FileFinder in
    # sys.path_importer_cache holding a directory listing WITHOUT emstudio_pro.
    # Installing the zip a moment later does not invalidate it, so the import
    # still fails and the buyer is told their brand-new purchase is not
    # installed. Which is the primary flow.
    importlib.invalidate_caches()
    import emstudio_pro                                   # noqa: F401
    from emstudio_pro import licence
    return licence


class LicenceDialog(QtWidgets.QDialog):
    """Install the Pro zip and activate it with a licence key."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("EMStudio Pro — install and activate")
        self.setMinimumWidth(640)
        self._build_ui()
        self._refresh_status()

    # ---------------------------------------------------------------- UI ---
    def _build_ui(self):
        outer = QtWidgets.QVBoxLayout(self)

        intro = QtWidgets.QLabel(
            "EMStudio Pro adds the System Designer (matching networks, phased "
            "arrays, RF direction finding) and the AI assistant.<br>"
            "Buy it at <a href='{0}'>{0}</a> — you receive a licence key and a "
            "zip file. Install the zip here, then enter the key.<br>"
            "<b>Trying first?</b> The free 14-day trial is the same zip (the "
            "$0 trial download at the same store): install it below and press "
            "<i>Start free trial</i> — no key, no account.<br>"
            "<b>Updating?</b> Just install the new zip — your activation is "
            "kept; the key is only needed once.".format(STORE_URL))
        intro.setWordWrap(True)
        intro.setOpenExternalLinks(True)
        outer.addWidget(intro)

        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(QtCore.Qt.RichText)
        outer.addWidget(self.status)

        form = QtWidgets.QGridLayout()
        form.addWidget(QtWidgets.QLabel("Pro zip file:"), 0, 0)
        self.zip_edit = QtWidgets.QLineEdit()
        self.zip_edit.setPlaceholderText("emstudio-pro-<version>.zip from your purchase")
        form.addWidget(self.zip_edit, 0, 1)
        browse = QtWidgets.QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        form.addWidget(browse, 0, 2)

        form.addWidget(QtWidgets.QLabel("Licence key:"), 1, 0)
        self.key_edit = QtWidgets.QLineEdit()
        self.key_edit.setPlaceholderText(
            "the key from your Gumroad receipt, or an AJK1… key")
        form.addWidget(self.key_edit, 1, 1, 1, 2)
        outer.addLayout(form)

        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(150)
        outer.addWidget(self.log)

        row = QtWidgets.QHBoxLayout()
        self.remove_btn = QtWidgets.QPushButton("Remove activation")
        self.remove_btn.clicked.connect(self._remove)
        row.addWidget(self.remove_btn)
        row.addStretch(1)
        self.trial_btn = QtWidgets.QPushButton("Start free trial")
        self.trial_btn.setToolTip(
            "Full EMStudio Pro for 14 days — no key, no account. Installs "
            "the zip above first if one is selected.")
        self.trial_btn.clicked.connect(self._trial)
        row.addWidget(self.trial_btn)
        self.install_btn = QtWidgets.QPushButton("Install and activate")
        self.install_btn.setDefault(True)
        self.install_btn.clicked.connect(self._install)
        row.addWidget(self.install_btn)
        close = QtWidgets.QPushButton("Close")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        outer.addLayout(row)

    def _say(self, msg):
        self.log.appendPlainText(msg)
        FreeCAD.Console.PrintMessage("EMStudio Pro: {0}\n".format(msg))

    def _refresh_status(self):
        try:
            licence = _import_pro()
        except ImportError:
            self.status.setText(
                "<b>Status:</b> Pro is not installed. "
                "Install the zip below to add it.")
            self.remove_btn.setEnabled(False)
            return
        ok, why = licence.check()
        if ok:
            self.status.setText(
                "<b>Status:</b> Pro is installed and <b>active</b> ({0}).".format(why))
        else:
            self.status.setText(
                "<b>Status:</b> Pro is installed but <b>not active</b> — {0}. "
                "Enter your licence key below.".format(why))
        self.remove_btn.setEnabled(True)

    # ------------------------------------------------------------ actions ---
    def _browse(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select the EMStudio Pro zip", os.path.expanduser("~"),
            "Zip archives (*.zip);;All files (*)")
        if path:
            self.zip_edit.setText(path)

    def _install(self):
        zip_path = self.zip_edit.text().strip()
        key = self.key_edit.text().strip()

        # Installing the zip is optional on a re-activation: a user who already
        # has the module and just needs to re-enter a key should not have to
        # find the download again.
        if zip_path:
            try:
                dest = install_zip(zip_path)
            except (ValueError, OSError) as exc:
                self._say("Install failed: {0}".format(exc))
                QtWidgets.QMessageBox.warning(self, "Install failed", str(exc))
                return
            self._say("Installed to {0}".format(dest))

        try:
            licence = _import_pro()
        except ImportError as exc:
            self._say("Pro is not installed yet ({0}). Choose the zip file "
                      "above first.".format(exc))
            return

        if not key:
            # An UPDATE install: the activation file survives module updates
            # by design, so a user replacing the zip must not be told to dig
            # out their key again -- that message, shown next to a status
            # line saying "active", read as a demand and confused the very
            # first updater (AJ himself, 2026-08-05).
            ok, why = licence.check()
            if ok:
                self._say("Updated. Your existing activation is kept ({0}) — "
                          "no key needed. Restart FreeCAD to load the new "
                          "version.".format(why))
            else:
                self._say("Enter your licence key to activate.")
            self._refresh_status()
            return

        ok, why = licence.activate(key)
        if ok:
            self._say("Activated ({0}). Restart FreeCAD to load the Pro "
                      "commands.".format(why))
            QtWidgets.QMessageBox.information(
                self, "EMStudio Pro activated",
                "Your licence was accepted ({0}).\n\n"
                "Restart FreeCAD to load the Pro commands.".format(why))
        else:
            self._say("Activation failed: {0}".format(why))
            QtWidgets.QMessageBox.warning(
                self, "Activation failed",
                "That key was not accepted.\n\n{0}".format(why))
        self._refresh_status()

    def _trial(self):
        # Same install step as _install, then start_trial instead of a key.
        zip_path = self.zip_edit.text().strip()
        if zip_path:
            try:
                dest = install_zip(zip_path)
            except (ValueError, OSError) as exc:
                self._say("Install failed: {0}".format(exc))
                QtWidgets.QMessageBox.warning(self, "Install failed", str(exc))
                return
            self._say("Installed to {0}".format(dest))
        try:
            licence = _import_pro()
        except ImportError as exc:
            self._say("Pro is not installed yet ({0}). Choose the trial zip "
                      "above first — the $0 download at the store.".format(exc))
            return
        if not hasattr(licence, "start_trial"):
            self._say("This Pro module predates the trial — install the "
                      "current zip above first.")
            return
        ok, why = licence.start_trial()
        self._say(why if ok else "Trial not started: {0}".format(why))
        if ok:
            QtWidgets.QMessageBox.information(
                self, "EMStudio Pro trial",
                "{0}.\n\nRestart FreeCAD to load the Pro commands.\n"
                "Buy at {1} any time — entering a key simply replaces the "
                "trial.".format(why, STORE_URL))
        else:
            QtWidgets.QMessageBox.warning(
                self, "EMStudio Pro trial", why)
        self._refresh_status()

    def _remove(self):
        try:
            licence = _import_pro()
        except ImportError:
            return
        if licence.deactivate():
            self._say("Activation removed. The module is still installed at "
                      "{0}.".format(install_dir()))
        else:
            self._say("There was no activation to remove.")
        self._refresh_status()


def show_licence_dialog(parent=None):
    dlg = LicenceDialog(parent)
    dlg.exec()
    return dlg
