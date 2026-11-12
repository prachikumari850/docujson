"""Stage 2 - group atoms into indivisible math units, using geometry only.

A unit is something that must never be split between two options or two
questions: an arrow with its letter, a fraction's bar with its numerator and
denominator, a radical sign with its overbar and radicand, a base with its
exponent or subscript.  Every unit lists the exact atoms that justify it.
Anything ambiguous is emitted as ``uncertain`` with a reason - never guessed.
"""
from __future__ import annotations

import hashlib
from bisect import bisect_left, bisect_right
from typing import Literal

from pydantic import BaseModel, Field

from app.ir import Atom, BBox

UnitKind = Literal["vec", "hat", "frac", "radical", "script"]

FRAC_X_SLACK = 2.0          # pt: content may stick out of the bar by this much
FRAC_MAX_GAP = 7.0          # pt: vertical gap between bar and numerator/denominator
FRAC_MAX_BAR = 60.0         # pt: longer rules are table lines or underlines, not fraction bars
SCRIPT_MAX_GAP = 3.0        # pt: horizontal gap between base and script
SCRIPT_MAX_RATIO = 0.85     # script size / base size
# Baseline shift of the script relative to its base, as a fraction of the base font size.
# Measured on the SRG paper: superscripts -0.3..-0.5, subscripts +0.16..+0.2, same-baseline
# smaller text (integral limits like pi/4) 0.0.
SCRIPT_SUP_MAX = -0.25
SCRIPT_SUB_RANGE = (0.10, 0.35)
SCRIPT_SAME_BASELINE = 0.10
SCRIPT_UNRELATED = 0.60     # beyond this the small glyph belongs to something else


class MathUnit(BaseModel):
    id: str
    kind: UnitKind
    status: Literal["confirmed", "uncertain"]
    page: int
    bbox: BBox
    parts: dict[str, list[str]] = Field(default_factory=dict)   # role -> atom ids
    reasons: list[str] = Field(default_factory=list)

    @property
    def atom_ids(self) -> list[str]:
        return [a for ids in self.parts.values() for a in ids]


class Cluster(BaseModel):
    """Connected set of units sharing atoms: the atomic block used for option/question assignment."""
    id: str
    page: int
    bbox: BBox
    unit_ids: list[str]
    atom_ids: list[str]


# --------------------------------------------------------------------------- helpers
def _b(a: Atom) -> BBox:
    return a.source.bbox


def _cx(b: BBox) -> float:
    return (b.x0 + b.x1) / 2


def _cy(b: BBox) -> float:
    return (b.y0 + b.y1) / 2


MIN_GLYPH_WIDTH = 0.3       # pt: Devanagari matras etc. are reported with collapsed, unreliable boxes


def _geom(a: Atom) -> bool:
    """True when the atom's box can be trusted for geometric reasoning."""
    return (_b(a).x1 - _b(a).x0) >= MIN_GLYPH_WIDTH


def _x_overlap(a: BBox, b: BBox) -> float:
    return max(0.0, min(a.x1, b.x1) - max(a.x0, b.x0))


def _make(kind: UnitKind, status: str, parts: dict[str, list[Atom]], reasons: list[str] | None = None) -> MathUnit:
    flat = [a for lst in parts.values() for a in lst]
    ids = sorted(a.id for a in flat)
    uid = f"u{flat[0].source.page:02d}-{kind}-" + hashlib.sha1("|".join(ids).encode()).hexdigest()[:8]
    return MathUnit(id=uid, kind=kind, status=status, page=flat[0].source.page,  # type: ignore[arg-type]
                    bbox=BBox.union_all([_b(a) for a in flat]),
                    parts={k: [a.id for a in v] for k, v in parts.items()}, reasons=reasons or [])


# --------------------------------------------------------------------------- vectors
ARROW_ORIGIN_X_TOL = 1.5    # pt: a vector mark starts at the same x as its first letter
ARROW_MAX_RISE = 14.0       # pt: arrow origin may sit this far above the letter baseline


HAT_CHARS = ("ˆ", "^")      # circumflex as printed by MathType, or a plain caret
HAT_CENTRE_TOL = 3.0        # pt: hat centre vs letter centre
HAT_MIN_RISE = 2.0          # pt: a hat sits at least this far above its letter baseline (3.0 over "a", 5.9 over "b")


def _is_mark(a: Atom) -> bool:
    return bool(a.origin) and ((a.kind == "symbol" and a.type3 and a.text == "→")
                               or (a.kind in ("text", "symbol") and a.text in HAT_CHARS))


def vector_units(atoms: list[Atom]) -> list[MathUnit]:
    """Vector arrows (Type3 "→") and unit-vector hats ("ˆ") drawn above letters.

    A mark whose origin sits above a letter's baseline and starts at that letter's x belongs to
    that letter (and to following letters it still covers horizontally).  Origins are used because
    Type3 boxes are unreliable.  Arrows that sit inline between letters (a -> s) share no x with
    any letter and are skipped."""
    letters = [a for a in atoms if a.kind == "text" and _geom(a) and a.origin and a.text not in HAT_CHARS]
    out: list[MathUnit] = []
    for mark in (a for a in atoms if _is_mark(a)):
        kind, role = ("vec", "arrow") if mark.text == "→" else ("hat", "mark")
        ax, ay = mark.origin  # type: ignore[misc]
        ab = _b(mark)
        min_rise = -1.0 if kind == "vec" else HAT_MIN_RISE
        # arrows start at their letter's x; hats are centred over it (MathType)
        aligned = (lambda l: abs(l.origin[0] - ax) <= ARROW_ORIGIN_X_TOL) if kind == "vec" else \
                  (lambda l: abs(_cx(_b(l)) - _cx(ab)) <= HAT_CENTRE_TOL)             # type: ignore[index]
        first = [l for l in letters if aligned(l) and min_rise <= l.origin[1] - ay <= ARROW_MAX_RISE]   # type: ignore[index]
        if first:
            first.sort(key=lambda l: abs(_cx(_b(l)) - _cx(ab)))
            head = first[0]
            under = [head]
            for l in sorted(letters, key=lambda l: _b(l).x0):
                if l is head or abs(l.origin[1] - head.origin[1]) > 0.5:             # type: ignore[index]
                    continue
                lb = _b(l)
                if lb.x0 > _b(head).x1 and _x_overlap(ab, lb) >= 0.5 * (lb.x1 - lb.x0):
                    under.append(l)
            out.append(_make(kind, "confirmed", {role: [mark], "base": under}))      # type: ignore[arg-type]
            continue
        inline = any(abs(l.origin[1] - ay) < 14 and 0 <= max(_b(l).x0 - ab.x1, ab.x0 - _b(l).x1) < 8   # type: ignore[index]
                     for l in letters)
        if not inline:
            out.append(_make(kind, "uncertain", {role: [mark]},                      # type: ignore[arg-type]
                             [f"{'arrow' if kind == 'vec' else 'hat'} mark with no letter under its origin"]))
    return out

# --------------------------------------------------------------------------- radicals and fractions
def radical_and_fraction_units(atoms: list[Atom]) -> list[MathUnit]:
    content = [a for a in atoms if a.kind in ("text", "symbol") and _geom(a)]
    rules = [a for a in atoms if a.kind == "rule"]
    vlines = [_b(a) for a in atoms if a.kind == "drawing" and (_b(a).x1 - _b(a).x0) <= 1.5 and (_b(a).y1 - _b(a).y0) >= 6]
    out: list[MathUnit] = []
    used_rules: set[str] = set()

    # radicals: sign glyph, then an overbar starting where the sign ends, just above its top
    for sign in (a for a in content if a.type3 and a.text == "√"):
        sb = _b(sign)
        bar = next((r for r in rules if r.id not in used_rules
                    and abs(_b(r).x0 - sb.x1) <= 0.8 and sb.y0 - 2.0 <= _b(r).y0 <= sb.y0 + 0.5), None)
        if bar is None:
            out.append(_make("radical", "uncertain", {"sign": [sign]}, ["no overbar found next to the radical sign"]))
            continue
        used_rules.add(bar.id)
        rb = _b(bar)
        radicand = [a for a in content if a is not sign and rb.x0 - 0.5 <= _cx(_b(a)) <= rb.x1 + 0.5
                    and rb.y1 <= _cy(_b(a)) <= sb.y1 + 4]
        if radicand:
            out.append(_make("radical", "confirmed", {"sign": [sign], "overbar": [bar], "radicand": radicand}))
        else:
            out.append(_make("radical", "uncertain", {"sign": [sign], "overbar": [bar]}, ["empty radicand"]))

    # fractions: every remaining horizontal rule is a candidate bar
    for bar in (r for r in rules if r.id not in used_rules):
        bb = _b(bar)
        if bb.x1 - bb.x0 > FRAC_MAX_BAR:
            continue
        if any(v.y0 - 1.5 <= _cy(bb) <= v.y1 + 1.5 and (abs(v.x0 - bb.x0) <= 1.5 or abs(v.x0 - bb.x1) <= 1.5) for v in vlines):
            continue                                  # a table cell border, not a fraction bar
        inside = [a for a in content if bb.x0 - FRAC_X_SLACK <= _cx(_b(a)) <= bb.x1 + FRAC_X_SLACK]

        def layer(above: bool) -> list[Atom]:
            near = [a for a in inside
                    if (-2.0 <= bb.y0 - _b(a).y1 <= FRAC_MAX_GAP if above else -2.0 <= _b(a).y0 - bb.y1 <= FRAC_MAX_GAP)]
            if not near:
                return []
            lo, hi = min(_b(a).y0 for a in near), max(_b(a).y1 for a in near)
            return [a for a in inside if lo - 0.5 <= _cy(_b(a)) <= hi + 0.5
                    and (_cy(_b(a)) < _cy(bb)) == above]

        num, den = layer(True), layer(False)
        if num and den:
            out.append(_make("frac", "confirmed", {"bar": [bar], "numerator": num, "denominator": den}))
        elif num or den:
            out.append(_make("frac", "uncertain", {"bar": [bar], "numerator": num, "denominator": den},
                             ["bar has content on one side only (underline or table line?)"]))
        # a rule with nothing above or below is a plain line: not a math unit
    return out


# --------------------------------------------------------------------------- scripts
def _shift(script: Atom, base: Atom) -> float:
    """Baseline shift of ``script`` relative to ``base`` in units of the base font size (negative = raised)."""
    return (script.origin[1] - base.origin[1]) / max(base.size or 1.0, 1e-6)    # type: ignore[index]


def script_units(atoms: list[Atom]) -> list[MathUnit]:
    """Smaller characters, same font, directly after a larger one with a shifted baseline.

    Uses baselines (origins), not box centres: glyph boxes come from font metrics and are skewed.
    Chaining is geometric, not by PDF line index (the PDF may split "pi/4" over several lines).
    Smaller text on the SAME baseline (integral limits) is deliberately not a script."""
    cand = sorted((a for a in atoms if a.kind == "text" and a.size and a.origin and _geom(a)),
                  key=lambda a: _b(a).x0)
    keys = [_b(a).x0 for a in cand]
    out: list[MathUnit] = []
    taken: set[str] = set()
    for base in cand:
        if base.id in taken:
            continue
        bb, bsize = _b(base), base.size or 0
        lo, hi = bisect_left(keys, bb.x1 - 0.5), bisect_right(keys, bb.x1 + SCRIPT_MAX_GAP)
        firsts = [s for s in cand[lo:hi] if s.id != base.id and s.id not in taken and s.font == base.font
                  and (s.size or 0) <= bsize * SCRIPT_MAX_RATIO
                  and SCRIPT_SAME_BASELINE <= abs(_shift(s, base)) <= SCRIPT_UNRELATED]
        if not firsts:
            continue
        first = min(firsts, key=lambda s: _b(s).x0)
        run = [first]
        while True:
            prev = run[-1]
            lo2, hi2 = bisect_left(keys, _b(prev).x1 - 0.5), bisect_right(keys, _b(prev).x1 + SCRIPT_MAX_GAP)
            nxt = [s for s in cand[lo2:hi2] if s.id != prev.id and s.id not in taken and s.font == first.font
                   and abs((s.size or 0) - (first.size or 0)) <= 0.3
                   and abs(s.origin[1] - first.origin[1]) <= 0.35 * (first.size or 1)]      # type: ignore[index]
            if not nxt:
                break
            run.append(min(nxt, key=lambda s: _b(s).x0))
        taken.update(a.id for a in run)
        shift = _shift(first, base)
        if shift <= SCRIPT_SUP_MAX:
            out.append(_make("script", "confirmed", {"base": [base], "superscript": run}))
        elif SCRIPT_SUB_RANGE[0] <= shift <= SCRIPT_SUB_RANGE[1]:
            out.append(_make("script", "confirmed", {"base": [base], "subscript": run}))
        else:
            role = "superscript" if shift < 0 else "subscript"
            out.append(_make("script", "uncertain", {"base": [base], role: run},
                             [f"baseline shift {shift:+.2f} of font size fits neither superscript nor subscript"]))
    return out


# --------------------------------------------------------------------------- public API
def build_units(atoms: list[Atom]) -> list[MathUnit]:
    return [*vector_units(atoms), *radical_and_fraction_units(atoms), *script_units(atoms)]


def build_clusters(units: list[MathUnit]) -> list[Cluster]:
    """Union units that share any atom (a vector inside a numerator, a radical inside a denominator ...)."""
    parent = list(range(len(units)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    owner: dict[str, int] = {}
    for idx, u in enumerate(units):
        for a in u.atom_ids:
            if a in owner:
                parent[find(idx)] = find(owner[a])
            else:
                owner[a] = idx
    groups: dict[int, list[int]] = {}
    for idx in range(len(units)):
        groups.setdefault(find(idx), []).append(idx)
    out: list[Cluster] = []
    for members in groups.values():
        us = [units[m] for m in members]
        atom_ids = sorted({a for u in us for a in u.atom_ids})
        cid = f"c{us[0].page:02d}-" + hashlib.sha1("|".join(atom_ids).encode()).hexdigest()[:8]
        out.append(Cluster(id=cid, page=us[0].page, bbox=BBox.union_all([u.bbox for u in us]),
                           unit_ids=sorted(u.id for u in us), atom_ids=atom_ids))
    return sorted(out, key=lambda c: (c.page, c.bbox.y0, c.bbox.x0))