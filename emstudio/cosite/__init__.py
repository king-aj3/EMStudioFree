# SPDX-License-Identifier: LGPL-2.1-or-later
"""Co-site interference / EMC analysis (ROADMAP §5).

When several transmitters and receivers share one site their signals interfere —
a system-level discipline layered on top of the device-level field solvers. This
package holds:

* ``interference`` — the deterministic analytic calculator (intermodulation
  product frequencies + levels via intercept points, receiver desensitization,
  broadband-noise coupling, and frequency-plan clash / D-U analysis). Pure-python,
  Qt-free, textbook-validated.
* (future) ``isolation`` — the antenna-to-antenna coupling/isolation matrix
  extracted from the multi-port field solvers (NEC2 mutual coupling; openEMS/
  Palace port-to-port S-parameters).

Radio lists are generic and user-supplied — no specific sites are referenced.
"""
