"""Stage 3 - read atoms into rows of text and math, in reading order.

Input: the atoms of one page and the math units found in them.
Output: ``Row`` objects.  A row is one visual line of one column; its tokens are plain text
or math runs.  A math run carries a semantic ``MathNode`` tree built from the atoms and, only
when every leaf has a known meaning, LaTeX derived from that tree.  Nothing is parsed from
strings: stacking and exponents come from the units found in stage 2.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from statistics import median
from typing import Literal

from pydantic import BaseModel, Field

from app.ir import Atom, BBox, MathNode
from app.services.math_units import MIN_GLYPH_WIDTH, Cluster, MathUnit, build_clusters

ROW_TOL = 2.5               # pt: glyph baselines closer than this are on one row
SPACE_GAP = 0.2             # of font size: a larger gap between glyphs is a word space
RUN_GAP = 6.5               # pt: max gap for plain glyphs to join a neighbouring math cluster
FRAC_ROW_REACH = 8.0        # pt: how far a fraction may sit from the row that carries it
FRAC_BASELINE_OFFSET = 1.4  # pt: typical (row baseline - bar y), measured 0.1 .. 2.6
PRIORITY = {"frac": 0, "radical": 1, "vec": 2, "hat": 2, "script": 3}

GREEK = {"α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "ε": "epsilon", "θ": "theta",
         "λ": "lambda", "μ": "mu", "π": "pi", "ρ": "rho", "σ": "sigma", "τ": "tau", "φ": "phi",
         "ω": "omega", "Δ": "Delta", "Σ": "Sigma", "Ω": "Omega", "Φ": "Phi", "ℓ": "ell"}
SYMBOLS = {"−": "-", "–": "-", "-": "-", "+": "+", "=": "=", "(": "(", ")": ")", "[": "[", "]": "]",
           ",": ",", ".": ".", ":": ":", "/": "/", "!": "!", "<": "<", ">": ">", "|": "|",
           "×": r"\times", "÷": r"\div", "•": r"\cdot", "·": r"\cdot", "±": r"\pm", "∞": r"\infty",
           "≤": r"\leq", "≥": r"\geq", "≠": r"\neq", "∝": r"\propto", "→": r"\rightarrow",
           "°": r"^{\circ}", "%": r"\%"}
FUNCS = ["sin", "cos", "tan", "cot", "sec", "csc", "log", "ln", "exp"]


class Unsafe(Exception):
    """A leaf has no verified LaTeX meaning; the run stays uncertain."""


class Token(BaseModel):
    kind: Literal["text", "math"]
    text: str                                   # text tokens: the words; math tokens: raw glyphs
    bbox: BBox
    atom_ids: list[str]
    unit_ids: list[str] = Field(default_factory=list)
    node: MathNode | None = None
    latex: str | None = None
    status: Literal["confirmed", "uncertain"] = "confirmed"
    reasons: list[str] = Field(default_factory=list)


class Row(BaseModel):
    page: int
    column: str
    baseline: float
    bbox: BBox
    tokens: list[Token]

    def plain(self) -> str:
        out = ""
        for t in self.tokens:
            piece = t.text if t.kind == "text" else (f"${t.latex}$" if t.latex else f"[math? {t.text}]")
            if not piece:
                continue
            out += piece if (not out or piece[0] in ".,:;)") else " " + piece
        return out


# --------------------------------------------------------------------------- glyphs and items
@dataclass
class _Glyph:
    atoms: list[Atom]
    text: str
    box: BBox
    baseline: float
    font: str | None
    size: float


@dataclass
class _Item:
    x0: float
    x1: float
    box: BBox
    glyph: _Glyph | None = None
    cluster: Cluster | None = None


def _b(a: Atom) -> BBox:
    return a.source.bbox


def _glyphs(free: list[Atom]) -> list[_Glyph]:
    """Free atoms in stream order.  Zero-width combining marks ride on the previous glyph of the
    same PDF line: their own boxes are unreliable, their position in the stream is not."""
    out: list[_Glyph] = []
    last: dict[int | None, _Glyph] = {}
    for a in free:
        zero = a.kind == "text" and (_b(a).x1 - _b(a).x0) < MIN_GLYPH_WIDTH
        if zero and a.line in last:
            g = last[a.line]
            g.atoms.append(a)
            g.text += a.text or ""
            continue
        g = _Glyph([a], a.text or "", _b(a), a.origin[1] if a.origin else _b(a).y1,
                   a.font, a.size or 0.0)
        out.append(g)
        last[a.line] = g
    return out


def _cluster_baseline(c: Cluster, amap: dict[str, Atom], units: dict[str, MathUnit],
                      rows: list[list[_Item]], row_base: list[float]) -> float | None:
    """Baseline of the row that carries a cluster; None means 'make a new row'."""
    fracs = [units[u] for u in c.unit_ids if units[u].kind == "frac"]
    if fracs:
        big = max(fracs, key=lambda u: u.bbox.y1 - u.bbox.y0)
        bar = _b(amap[big.parts["bar"][0]])
        target = (bar.y0 + bar.y1) / 2 + FRAC_BASELINE_OFFSET
        near = [b for b in row_base if abs(b - target) <= FRAC_ROW_REACH]
        return min(near, key=lambda b: abs(b - target)) if near else target
    skip: set[str] = set()
    for uid in c.unit_ids:
        for role in ("arrow", "mark", "superscript", "subscript", "overbar", "bar", "sign"):
            skip.update(units[uid].parts.get(role, []))
    ys = [amap[i].origin[1] for i in c.atom_ids if i not in skip and amap[i].kind == "text" and amap[i].origin]
    return median(ys) if ys else None


# --------------------------------------------------------------------------- math trees
def _leaf(a: Atom) -> MathNode:
    t = a.text or ""
    op = "num" if (t.isdigit() or t == ".") else ("var" if t.isalpha() else "sym")
    return MathNode(op=op, value=t, atom_ids=[a.id])  # type: ignore[arg-type]


MAX_MATH_NESTING = 24


def _nodes_for(
    content: list[Atom],
    units: list[MathUnit],
    amap: dict[str, Atom],
    ancestor_atom_sets: frozenset[frozenset[str]] = frozenset(),
    depth: int = 0,
) -> list[MathNode]:
    """Build a tree without allowing a page-level unit to recurse into itself.

    Rule atoms are not textual leaves, so a malformed/nested unit can have the
    same text-atom set as one of its numerator or denominator groups. Tracking
    ancestor atom sets prevents that unit from becoming its own child. The depth
    guard preserves raw evidence as unresolved instead of exhausting the stack.
    """
    ids = {a.id for a in content}
    if not ids:
        return []
    if depth >= MAX_MATH_NESTING:
        return [MathNode(op="unresolved", value="".join(a.text or "" for a in content), atom_ids=sorted(ids))]

    def tset(u: MathUnit) -> set[str]:
        return {i for i in u.atom_ids if amap[i].kind in ("text", "symbol")}

    cand = [
        (u, tset(u))
        for u in units
        if tset(u) and tset(u) <= ids and frozenset(tset(u)) not in ancestor_atom_sets
    ]
    top = [(u, s) for u, s in cand
           if not any(v is not u and (s < t or (s == t and PRIORITY[v.kind] < PRIORITY[u.kind])) for v, t in cand)]
    used: set[str] = set()
    for _, s in top:
        if used & s:                                  # partially overlapping units: refuse to guess
            return [MathNode(op="unresolved", value="".join(a.text or "" for a in sorted(content, key=lambda a: _b(a).x0)),
                             atom_ids=sorted(ids))]
        used |= s

    items: list[tuple[float, MathNode]] = []
    for u, s in top:
        atoms = lambda role: [amap[i] for i in u.parts.get(role, [])]            # noqa: E731
        nested_ancestors = ancestor_atom_sets | {frozenset(s)}
        if u.kind == "frac":
            node = MathNode(op="frac", atom_ids=sorted(s), children=[
                MathNode(op="group", children=_nodes_for(atoms("numerator"), units, amap, nested_ancestors, depth + 1)),
                MathNode(op="group", children=_nodes_for(atoms("denominator"), units, amap, nested_ancestors, depth + 1))])
        elif u.kind == "radical":
            node = MathNode(op="sqrt", atom_ids=sorted(s), children=[
                MathNode(op="group", children=_nodes_for(atoms("radicand"), units, amap, nested_ancestors, depth + 1))])
        elif u.kind in ("vec", "hat"):
            node = MathNode(op=u.kind, atom_ids=sorted(s) + u.parts.get("arrow", []) + u.parts.get("mark", []), children=[
                MathNode(op="group", children=[_leaf(a) for a in sorted(atoms("base"), key=lambda a: _b(a).x0)])])
        else:                                                                       # script
            role = "superscript" if "superscript" in u.parts else "subscript"
            node = MathNode(op="sup" if role == "superscript" else "sub", atom_ids=sorted(s), children=[
                _leaf(atoms("base")[0]),
                MathNode(op="group", children=_nodes_for(atoms(role), units, amap, nested_ancestors, depth + 1))])
        items.append((u.bbox.x0, node))
    for a in content:
        if a.id not in used:
            items.append((_b(a).x0, _leaf(a)))
    items.sort(key=lambda p: p[0])
    return _finalize([n for _, n in items])


def _finalize(nodes: list[MathNode]) -> list[MathNode]:
    merged: list[MathNode] = []
    for n in nodes:                                                 # 1,2 -> 12 ; 3 . 5 -> 3.5
        prev = merged[-1] if merged else None
        if prev and n.op == "num" and prev.op == "num":
            prev.value = (prev.value or "") + (n.value or "")
            prev.atom_ids += n.atom_ids
        else:
            merged.append(n)
    out: list[MathNode] = []
    i = 0
    while i < len(merged):                                          # c,o,s(^-1) -> \cos^{-1}
        hit = None
        for name in sorted(FUNCS, key=len, reverse=True):
            k = len(name)
            if i + k > len(merged):
                continue
            win = merged[i:i + k]
            def letter(n: MathNode) -> str | None:
                if n.op == "var":
                    return n.value
                if n.op in ("sup", "sub") and n.children[0].op == "var":
                    return n.children[0].value
                return None
            if all(letter(w) == ch for w, ch in zip(win, name)) and all(w.op == "var" for w in win[:-1]):
                hit = (name, win)
                break
        if hit:
            name, win = hit
            ids = [a for w in win for a in w.atom_ids]
            fn = MathNode(op="func", value=name, atom_ids=ids)
            last = win[-1]
            out.append(MathNode(op=last.op, atom_ids=ids, children=[fn, last.children[1]])
                       if last.op in ("sup", "sub") else fn)
            i += len(name)
        else:
            out.append(merged[i])
            i += 1
    return out


def _tex(n: MathNode) -> str:
    if n.op == "num":
        return n.value or ""
    if n.op == "var":
        v = n.value or ""
        if v in GREEK:
            return "\\" + GREEK[v]
        if re.fullmatch(r"[A-Za-z]", v):
            return v
        raise Unsafe(v)
    if n.op == "sym":
        if (n.value or "") in SYMBOLS:
            return SYMBOLS[n.value or ""]
        raise Unsafe(n.value or "")
    if n.op == "func":
        return "\\" + (n.value or "")
    if n.op == "group":
        return _join([_tex(c) for c in n.children])
    if n.op == "frac":
        return "\\frac{%s}{%s}" % (_tex(n.children[0]), _tex(n.children[1]))
    if n.op == "sqrt":
        return "\\sqrt{%s}" % _tex(n.children[0])
    if n.op in ("vec", "hat"):
        return "\\%s{%s}" % (n.op, _tex(n.children[0]))
    if n.op in ("sup", "sub"):
        return "%s%s{%s}" % (_tex(n.children[0]), "^" if n.op == "sup" else "_", _tex(n.children[1]))
    raise Unsafe(n.op)


def _join(parts: list[str]) -> str:
    out = ""
    for p in parts:
        if out and re.search(r"\\[A-Za-z]+$", out) and re.match(r"[A-Za-z0-9]", p):
            out += " "
        out += p
    return out


# --------------------------------------------------------------------------- rows
def _text_of(glyphs: list[_Glyph]) -> str:
    out = ""
    prev: _Glyph | None = None
    for g in glyphs:
        if prev is not None and g.box.x0 - prev.box.x1 > SPACE_GAP * max(prev.size, 1.0):
            out += " "
        out += g.text
        prev = g
    return out


def read_rows(atoms: list[Atom], units: list[MathUnit]) -> list[Row]:
    amap = {a.id: a for a in atoms}
    umap = {u.id: u for u in units}
    clusters = build_clusters(units)
    in_cluster = {i for c in clusters for i in c.atom_ids}
    free = [a for a in atoms if a.kind in ("text", "symbol") and a.id not in in_cluster]
    rows_out: list[Row] = []

    for column in sorted({a.source.column or "full" for a in atoms if a.kind in ("text", "symbol")}):
        glyphs = [g for g in _glyphs([a for a in free if (a.source.column or "full") == column])]
        cols = [c for c in clusters if (amap[next(i for i in c.atom_ids if amap[i].kind in ("text", "symbol"))].source.column
                                        or "full") == column
                and any(amap[i].kind in ("text", "symbol") for i in c.atom_ids)]
        # 1. rows from free glyphs
        glyphs.sort(key=lambda g: g.baseline)
        row_items: list[list[_Item]] = []
        row_base: list[float] = []
        for g in glyphs:
            it = _Item(g.box.x0, g.box.x1, g.box, glyph=g)
            if row_items and abs(g.baseline - row_base[-1]) <= ROW_TOL:
                row_items[-1].append(it)
                row_base[-1] = median([x.glyph.baseline for x in row_items[-1]])      # type: ignore[union-attr]
            else:
                row_items.append([it])
                row_base.append(g.baseline)
        # 2. place clusters
        for c in cols:
            content = [amap[i] for i in c.atom_ids if amap[i].kind in ("text", "symbol")]
            it = _Item(c.bbox.x0, c.bbox.x1, c.bbox, cluster=c)
            target = _cluster_baseline(c, amap, umap, row_items, row_base)
            if target is None:
                target = median([a.origin[1] for a in content if a.origin])
            hit = [k for k, b in enumerate(row_base) if abs(b - target) <= ROW_TOL]
            if hit:
                row_items[hit[0]].append(it)
            else:
                row_items.append([it])
                row_base.append(target)
        # 3. tokens
        for items, base in sorted(zip(row_items, row_base), key=lambda p: p[1]):
            items.sort(key=lambda x: x.x0)
            rows_out.append(_build_row(items, base, column, atoms[0].source.page, amap, umap))
    return rows_out


LABEL_RE = re.compile(r"^\(?[0-9]{1,2}[\).]$|^\([A-Da-d]\)$")
_LETTER_RUN = re.compile(r"[A-Za-z]+")


def _absorbable(word: str) -> bool:
    """May this stretch of plain glyphs belong to an adjacent math cluster?

    Yes for digits, operators, brackets, Greek, single letters and known function names ("2t",
    "log", "+", "(x").  No for ordinary words ("with", "respect"), other scripts, or option labels.
    Fonts are NOT compared: this paper mixes Kokila and Times inside one expression."""
    if LABEL_RE.match(word):
        return False
    for ch in word:
        if not (ch.isdigit() or ch in SYMBOLS or ch in GREEK or re.match(r"[A-Za-z]", ch)):
            return False
    return all(len(run) == 1 or run in FUNCS for run in _LETTER_RUN.findall(word))


def _build_row(items: list[_Item], base: float, column: str, page: int,
               amap: dict[str, Atom], umap: dict[str, MathUnit]) -> Row:
    n = len(items)
    word_of: list[int | None] = [None] * n                          # contiguous plain glyphs without a word gap
    words: list[list[int]] = []
    for i, it in enumerate(items):
        if it.glyph is None:
            continue
        prev = items[i - 1] if i else None
        if prev is not None and prev.glyph is not None and \
                it.x0 - prev.x1 <= SPACE_GAP * max(prev.glyph.size, 1.0) and word_of[i - 1] is not None:
            words[word_of[i - 1]].append(i)                         # type: ignore[index]
            word_of[i] = word_of[i - 1]
        else:
            words.append([i])
            word_of[i] = len(words) - 1
    def edge(j: int, last: bool, size: float, gap_to: float) -> str:
        """Letter of an adjacent cluster that touches this word (so "co" + s^-1 can read as "cos")."""
        c = items[j].cluster if 0 <= j < n else None
        if c is None or gap_to > SPACE_GAP * max(size, 1.0):
            return ""
        atoms = sorted((amap[i] for i in c.atom_ids if amap[i].kind == "text"), key=lambda a: _b(a).x0)
        return (atoms[-1] if last else atoms[0]).text or "" if atoms else ""

    ok = []
    for w in words:
        text = "".join(items[i].glyph.text for i in w)                              # type: ignore[union-attr]
        size = items[w[0]].glyph.size                                                # type: ignore[union-attr]
        before = edge(w[0] - 1, True, size, items[w[0]].x0 - items[w[0] - 1].x1) if w[0] else ""
        after = edge(w[-1] + 1, False, size, items[w[-1] + 1].x0 - items[w[-1]].x1) if w[-1] + 1 < n else ""
        ok.append(_absorbable(text) or _absorbable(before + text + after))

    mathy = [it.cluster is not None for it in items]
    changed = True
    while changed:
        changed = False
        for i in range(n):
            if not mathy[i]:
                continue
            for j in (i - 1, i + 1):
                if not 0 <= j < n or mathy[j]:
                    continue
                gap = items[j].x0 - items[i].x1 if j > i else items[i].x0 - items[j].x1
                if gap > RUN_GAP:
                    continue
                if items[j].cluster is not None:
                    mathy[j] = changed = True
                elif word_of[j] is not None and ok[word_of[j]]:        # type: ignore[index]
                    for m in words[word_of[j]]:                         # type: ignore[index]
                        mathy[m] = True
                    changed = True
    for i in range(n):                                              # "... between a and b." : the stop is prose
        if mathy[i] and items[i].glyph is not None and items[i].glyph.text in (".", ",", ":", ";") \
                and (i == n - 1 or not mathy[i + 1] or i == 0 or not mathy[i - 1]):
            mathy[i] = False
    tokens: list[Token] = []
    k = 0
    while k < n:
        m = k
        while m < n and mathy[m] == mathy[k]:
            m += 1
        group = items[k:m]
        box = BBox.union_all([g.box for g in group])
        if mathy[k]:
            tokens.append(_math_token(group, box, amap, umap))
        else:
            gl = [g.glyph for g in group if g.glyph]
            tokens.append(Token(kind="text", text=_text_of(gl), bbox=box,
                                atom_ids=[a.id for g in gl for a in g.atoms]))
        k = m
    return Row(page=page, column=column, baseline=round(base, 2),
               bbox=BBox.union_all([t.bbox for t in tokens]), tokens=tokens)


def _math_token(group: list[_Item], box: BBox, amap: dict[str, Atom], umap: dict[str, MathUnit]) -> Token:
    content: list[Atom] = []
    units: dict[str, MathUnit] = {}
    atom_ids: list[str] = []
    for it in group:
        if it.glyph:
            content += it.glyph.atoms
            atom_ids += [a.id for a in it.glyph.atoms]
        else:
            c = it.cluster
            content += [amap[i] for i in c.atom_ids if amap[i].kind in ("text", "symbol")]          # type: ignore[union-attr]
            atom_ids += c.atom_ids                                                                    # type: ignore[union-attr]
            units.update({u: umap[u] for u in c.unit_ids})                                            # type: ignore[union-attr]
    nodes = _nodes_for(content, list(units.values()), amap)
    root = MathNode(op="group", children=nodes, atom_ids=sorted({a.id for a in content}))
    raw = "".join(a.text or "" for a in sorted(content, key=lambda a: _b(a).x0))
    reasons = [r for u in units.values() if u.status != "confirmed" for r in u.reasons]
    latex: str | None = None
    try:
        latex = _tex(root)
    except Unsafe as e:
        reasons.append(f"no verified LaTeX meaning for {str(e)!r}")
    status = "confirmed" if latex is not None and not reasons else "uncertain"
    return Token(kind="math", text=raw, bbox=box, atom_ids=atom_ids, unit_ids=list(units), node=root,
                 latex=latex if status == "confirmed" else None, status=status, reasons=reasons)
