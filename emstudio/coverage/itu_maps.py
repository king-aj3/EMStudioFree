# SPDX-License-Identifier: LGPL-2.1-or-later
"""ITU digital-map installer for the vendored P.452 / P.2001 engines.

The ITU-R digital maps (DN50/N050 for P.452-18; the 14 radio-climatic map
files for P.2001-6) are *integral digital products* of their Recommendations
— ITU forbids redistribution, so EMStudio never bundles them. This module
gets them onto the user's machine honestly:

* ``install_p452_maps()`` / ``install_p2001_maps()`` — download the OFFICIAL
  Recommendation zip from itu.int (or take a user-supplied zip/directory as
  the manual fallback), extract the required map files, and build the
  ``P452.npz`` / ``P2001.npz`` archives the vendored engines read (same
  layout as the upstream ``initiate_digital_maps.py`` scripts produce).
* npz files land in the per-user maps directory (:func:`maps_dir`), which the
  vendored engines search lazily on first use — the workbench imports and
  runs fine without the maps; only a P.452/P.2001 computation needs them.

Search order for an npz: ``EMSTUDIO_ITU_MAPS_DIR`` env var -> the per-user
maps dir -> the vendored package directory (for users who ran the upstream
initiate script in place). Qt-free, FreeCAD-free (stdlib + numpy).
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
import zipfile

# Official ITU-R Recommendation zips (the "!!ZIP-E" publication variant
# carries the Recommendation's integral attachments, incl. the digital maps).
P452_ZIP_URL = ("https://www.itu.int/dms_pubrec/itu-r/rec/p/"
                "R-REC-P.452-18-202310-I!!ZIP-E.zip")
P2001_ZIP_URL = ("https://www.itu.int/dms_pubrec/itu-r/rec/p/"
                 "R-REC-P.2001-6-202509-I!!ZIP-E.zip")

# Map .txt inventories — EXACTLY the upstream initiate_digital_maps.py lists.
P452_MAP_FILES = ("DN50.TXT", "N050.TXT")
P2001_MAP_FILES = ("DN_Median.txt", "DN_SubSlope.txt", "DN_SupSlope.txt",
                   "dndz_01.txt", "Esarain_Mt_v5.txt", "Esarain_Pr6_v5.txt",
                   "Esarain_Beta_v5.txt", "FoEs0.1.txt", "FoEs01.txt",
                   "FoEs10.txt", "FoEs50.txt", "h0.txt",
                   "surfwv_50_fixed.txt", "TropoClim.txt")


def maps_dir():
    """Per-user directory holding the built npz map archives (created lazily).

    ``EMSTUDIO_ITU_MAPS_DIR`` overrides; else the platform user-data dir.
    """
    env = os.environ.get("EMSTUDIO_ITU_MAPS_DIR")
    if env:
        return env
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "EMStudio", "itu_maps")
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        return os.path.join(home, "Library", "Application Support",
                            "EMStudio", "itu_maps")
    xdg = os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local",
                                                          "share")
    return os.path.join(xdg, "EMStudio", "itu_maps")


def _vendor_dir(npz_name):
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pkg = {"P452.npz": "py452", "P2001.npz": "py2001",
           "P1812.npz": "py1812"}.get(npz_name)
    return os.path.join(here, "vendor", pkg) if pkg else None


def find_npz(npz_name):
    """Absolute path of an installed npz map archive, or None."""
    candidates = [os.path.join(maps_dir(), npz_name)]
    vd = _vendor_dir(npz_name)
    if vd:
        candidates.append(os.path.join(vd, npz_name))
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def missing_message(model):
    """The user-facing 'maps not installed' error text for a model name."""
    url = {"P452": P452_ZIP_URL, "P2001": P2001_ZIP_URL}.get(model, "itu.int")
    return (
        "The ITU-R {0} digital maps ({0}.npz) are not installed — they are "
        "integral ITU products that EMStudio may not redistribute. Install "
        "them once with emstudio.coverage.itu_maps.install_{1}_maps() "
        "(downloads the official Recommendation zip from {2}), or pass that "
        "zip (downloaded yourself) as install_{1}_maps(source=<path>). The "
        "maps land in {3} and every later run finds them there."
        .format(model, model.lower(), url, maps_dir()))


def _iter_zip_members(zpath, depth=0):
    """Yield (member_name, bytes) for every file in a zip, recursing into
    nested zips (the ITU publication zips nest their attachments). Members
    merely NAMED .zip that are not valid zips are yielded but not recursed."""
    with zipfile.ZipFile(zpath) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            data = zf.read(info)
            yield info.filename, data
            if info.filename.lower().endswith(".zip") and depth < 3:
                with tempfile.NamedTemporaryFile(suffix=".zip",
                                                 delete=False) as tmp:
                    tmp.write(data)
                    inner = tmp.name
                try:
                    if zipfile.is_zipfile(inner):
                        for item in _iter_zip_members(inner, depth + 1):
                            yield item
                finally:
                    os.unlink(inner)


def _collect_map_texts(source, wanted):
    """Find the wanted map .txt files in ``source`` (zip file or directory).

    Matching is case-insensitive on the basename. Returns
    {canonical_name: bytes} in ``wanted`` order (so the npz build is
    byte-identical to the upstream scripts'); raises if any file is missing.
    Stray unreadable .zip files in a directory source are skipped, and the
    walk stops as soon as everything wanted is found.
    """
    lookup = {w.lower(): w for w in wanted}
    found = {}
    if os.path.isdir(source):
        for root, _dirs, names in os.walk(source):
            for name in names:
                key = lookup.get(name.lower())
                if key and key not in found:
                    with open(os.path.join(root, name), "rb") as fh:
                        found[key] = fh.read()
                elif (name.lower().endswith(".zip")
                      and zipfile.is_zipfile(os.path.join(root, name))):
                    for member, data in _iter_zip_members(
                            os.path.join(root, name)):
                        mkey = lookup.get(os.path.basename(member).lower())
                        if mkey and mkey not in found:
                            found[mkey] = data
                if len(found) == len(wanted):
                    break
            if len(found) == len(wanted):
                break
    elif zipfile.is_zipfile(source):
        for member, data in _iter_zip_members(source):
            key = lookup.get(os.path.basename(member).lower())
            if key and key not in found:
                found[key] = data
    elif not os.path.exists(source):
        raise FileNotFoundError("source path does not exist: "
                                "{0}".format(source))
    else:
        raise ValueError("source must be a directory or a zip file: "
                         "{0}".format(source))
    missing = [w for w in wanted if w not in found]
    if missing:
        raise FileNotFoundError(
            "map files not found in {0}: {1}".format(source,
                                                     ", ".join(missing)))
    return {w: found[w] for w in wanted}


def _download(url, dest_path, timeout=120):
    import urllib.request

    req = urllib.request.Request(url, headers={
        "User-Agent": "EMStudio-map-installer/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp, \
            open(dest_path, "wb") as out:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
    return dest_path


def _build_npz(texts, out_path, int_files=(), compressed=False):
    """np.loadtxt each map text and savez to ``out_path`` — byte-compatible
    with the upstream initiate_digital_maps.py outputs (incl. the FoEs0.1 ->
    FoEs0p1 key rename)."""
    import numpy as np

    maps = {}
    for name, data in texts.items():
        dtype = "int" if name in int_files else float
        matrix = np.loadtxt(io.BytesIO(data), dtype=dtype)
        key = os.path.splitext(name)[0]
        if key == "FoEs0.1":
            key = "FoEs0p1"
        maps[key] = matrix
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    if compressed:
        np.savez_compressed(out_path, **maps)
    else:
        np.savez(out_path, **maps)
    return out_path


def _install(source, url, wanted, npz_name, int_files=(), compressed=False,
             dest=None):
    out_path = os.path.join(dest or maps_dir(), npz_name)
    if source is None:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            zip_path = tmp.name
        try:
            _download(url, zip_path)
            if not zipfile.is_zipfile(zip_path):
                raise RuntimeError(
                    "the file downloaded from {0} is not a valid zip (a "
                    "proxy/portal may have intercepted the request, or ITU "
                    "moved the Recommendation) — download the zip manually "
                    "in a browser and pass it as source=<path>".format(url))
            texts = _collect_map_texts(zip_path, wanted)
        finally:
            os.unlink(zip_path)
    else:
        texts = _collect_map_texts(source, wanted)
    return _build_npz(texts, out_path, int_files=int_files,
                      compressed=compressed)


def install_p452_maps(source=None, dest=None):
    """Install the P.452-18 maps (DN50/N050 -> P452.npz).

    ``source=None`` downloads the official Recommendation zip from itu.int;
    otherwise pass a downloaded zip path or a directory containing the .TXT
    files (the manual fallback for offline/firewalled machines). Returns the
    npz path.
    """
    return _install(source, P452_ZIP_URL, P452_MAP_FILES, "P452.npz",
                    dest=dest)


def install_p2001_maps(source=None, dest=None):
    """Install the P.2001-6 maps (14 files -> P2001.npz). See
    :func:`install_p452_maps` for the source semantics."""
    return _install(source, P2001_ZIP_URL, P2001_MAP_FILES, "P2001.npz",
                    int_files=("TropoClim.txt",), compressed=True, dest=dest)
