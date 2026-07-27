# Contributing to EMStudio

Thanks for wanting to help. Bug reports, reproducible test cases and validation
data are especially welcome — this project's whole claim is *validated, not just
plausible*, so a case that shows a result is wrong is worth more here than in
most projects.

## Before you write code

Open an issue first for anything beyond a small fix. EMStudio follows a phased
roadmap and ships every physics feature with an automated validation gate, so a
change usually needs a gate to go with it — better to agree the approach before
you spend the time.

## The bar for a change

- **Physics features need a gate.** A benchmark against literature, a
  closed-form result, or an independent solver. "It looks right" is not a
  result; neither is a check that passes by construction.
- **Do not weaken an existing gate to make a change pass.** If a gate is wrong,
  say so in the issue and show why — that is a valuable contribution on its own.
- Match the surrounding code's style and conventions.
- Say plainly what you verified and what you did not.

## Contributor Licence Agreement (CLA)

**By submitting a contribution you agree to the terms in this section.** There
is nothing to sign; opening a pull request is your acceptance.

You agree that:

1. **You grant the AJJ³ project a perpetual, worldwide, irrevocable,
   royalty-free licence** to use, reproduce, modify, publicly display,
   sublicense and distribute your contribution, **including the right to
   distribute it under different licence terms** — whether that is the LGPL,
   another open-source licence, or a proprietary one.
2. **You keep your copyright.** This is a licence grant, not an assignment. You
   may continue to use your own work however you like.
3. **You have the right to grant it** — the work is yours, and if your employer
   has rights in it you have their permission.
4. Your contribution is provided **as-is, without warranty**, consistent with
   [DISCLAIMER.md](DISCLAIMER.md).

### Why this is asked for, stated plainly

EMStudio is **open-core**: this workbench is free and LGPL, and there is a
separate paid module. Without the licence grant in point 1, code contributed
here could never be used in that paid module, and the project could never be
relicensed or dual-licensed later — because each contributor would hold a veto.

That is a real trade and you should make it with your eyes open: **your
contribution may end up in a commercial product.** In exchange, the work you
contribute to stays free and open under the LGPL, and you are credited.

If that is not a trade you want to make, please still file the **issue** —
a precise bug report with a reproduction costs you nothing and helps just as
much.

## Names and branding

The code is LGPL; the **EMStudio** and **AJJ³** names, logo and icon set are
not. Contributing does not grant you any right to use them, and a fork must
rename. See [TRADEMARK.md](TRADEMARK.md).

## Running the checks

```bash
python3 tests/smoke.py                        # Qt-free subset
freecadcmd tests/smoke.py                     # full, under FreeCAD
python3 tests/validation/run_battery.py       # the FAST validation tier
```

`gui_smoke.py` needs a real (or offscreen) FreeCAD GUI:

```bash
QT_QPA_PLATFORM=offscreen freecad tests/gui_smoke.py
```

All of these should be green before you open a pull request. If one fails for a
reason you believe is unrelated, say so rather than leaving it unmentioned.
