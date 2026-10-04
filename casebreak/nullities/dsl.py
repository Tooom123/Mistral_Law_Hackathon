"""Rules as data — a small, safe expression language evaluated on the case graph.

A catalogue entry (one YAML file per rule) describes, for each version of the law:

    let:        named expressions computed once        {start: "t('custody.custody_start')", ...}
    outcomes:   ordered list, the first whose `when` is true gives the result
      - when:   "start is None"
        status: needs_reading | possible_nullity | satisfied | skip
        certainty: documented | inferred | needs_reading          (default from status)
        kind:   rule | missing_mention | contradiction | graph    (default: the rule's kind)
        say:    "Custody of {name}: {dhm(start)} → {dhm(end)}, i.e. {dur(total)}."   ({expr} placeholders)
        cite:   [custody_start, custody.custody_end]              (attribute paths → page + quote)
        grey:   {attr: delay_justification}                       (judge consulted on this attribute)
        proof:  {kind: duration_gt, start: "iso(start)", ...}      (facts handed to Lean)
        details:{delay_minutes: "delay"}

No rule is written in Python: adding a rule = adding a YAML file. Attribute paths are generic over the graph:

    attr                         attribute of the act being checked
    custody.attr                 attribute of the custody the act belongs to
    <subtype>.attr               attribute of the act of that subtype for the same person (rights_notification.lawyer_requested)
    case:<subtype>.attr          attribute of the first act of that subtype anywhere in the case file
    <prefix>.@start|@end|@framework|@subtype   field of the node itself
    @attr_holding_sources        (in `cite` only) an attribute whose value is a list of sources

Expressions use Python syntax restricted to: literals, names (let-variables, params, context), and/or/not,
comparisons, + - * /, `x if c else y`, `params['k']`, and the whitelisted functions in FUNCS. Anything else is
rejected when the catalogue is loaded.
"""

from __future__ import annotations

import ast
import operator
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from typing import Any

from casebreak.schemas import Attr, Node, Src


class RuleError(ValueError):
    pass


@dataclass
class Result:
    status: str  # satisfied | possible_nullity | needs_reading
    statement: str
    sources: list[Src] = field(default_factory=list)
    certainty: str = "documented"  # the engine may downgrade it (OCR, values extracted by a model)
    details: dict = field(default_factory=dict)
    grey: bool = False
    grey_attr: str | None = None
    proof: dict | None = None
    kind: str | None = None


# ----------------------------------------------------------------------------- graph context


class GraphCtx:
    """Indexes of the case graph used to resolve attribute paths."""

    def __init__(self, nodes: list[Node], edges, pages):
        self.nodes = {n.id: n for n in nodes}
        self.edges = edges
        self.pages = pages
        self.by_person: dict[str, list[Node]] = {}
        self.by_subtype: dict[str, list[Node]] = {}
        for n in nodes:
            if n.type != "ACT":
                continue
            self.by_subtype.setdefault(n.subtype, []).append(n)
            if n.person:
                self.by_person.setdefault(n.person, []).append(n)
        self._inferred = {(a.src.page, a.src.quote) for n in nodes for a in n.attrs.values()
                          if a.status == "inferred" and a.src}

    def person_acts(self, n: Node, subtype: str) -> list[Node]:
        return [x for x in self.by_person.get(n.person or "", []) if x.subtype == subtype]

    def custody(self, n: Node) -> Node | None:
        if n.subtype == "garde_a_vue":
            return n
        cid = n.val("custody_id")
        if cid and cid in self.nodes:
            return self.nodes[cid]
        lst = self.person_acts(n, "garde_a_vue")
        return lst[0] if lst else None

    def name(self, n: Node) -> str:
        p = self.nodes.get(n.person or "")
        return p.label if p else "the person"

    def ocr_pages(self, srcs: list[Src]) -> list[int]:
        return [s.page for s in srcs if s.page in self.pages and self.pages[s.page].ocr != "native"]

    def inferred_quotes(self, srcs: list[Src]) -> bool:
        return any((s.page, s.quote) in self._inferred for s in srcs)

    def target(self, n: Node, prefix: str) -> Node | None:
        if prefix in ("", "self"):
            return n
        if prefix == "custody":
            return self.custody(n)
        if prefix.startswith("case:"):
            lst = self.by_subtype.get(prefix[5:], [])
            return lst[0] if lst else None
        lst = self.person_acts(n, prefix)
        return lst[0] if lst else None


NODE_FIELDS = {"@start": "start", "@end": "end", "@framework": "framework", "@subtype": "subtype", "@label": "label"}


def split_path(path: str) -> tuple[str, str]:
    if "." in path:
        prefix, key = path.rsplit(".", 1)
        return prefix, key
    return "", path


# ----------------------------------------------------------------------------- functions


def _fmt_dur(minutes: float | None) -> str:
    if minutes is None:
        return "?"
    m = int(round(minutes))
    h, mm = divmod(abs(m), 60)
    return f"{h}h{mm:02d}" if h else f"{mm} min"


def _to_dt(v: Any) -> datetime | None:
    if isinstance(v, datetime):
        return v
    if isinstance(v, str) and "T" in v:
        try:
            return datetime.fromisoformat(v)
        except ValueError:
            return None
    return None


def _to_date(v: Any) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        try:
            return date.fromisoformat(v[:10])
        except ValueError:
            return None
    return None


class Env:
    """Evaluation environment for one rule version on one node."""

    def __init__(self, node: Node, ctx: GraphCtx, params: dict, trace: list | None = None):
        self.node, self.ctx, self.params = node, ctx, params
        self.trace = trace  # receives (node_id, attribute) for every attribute read that was absent or unreadable
        self.vars: dict[str, Any] = {
            "params": params, "subtype": node.subtype, "framework": node.framework, "name": ctx.name(node),
            "None": None, "True": True, "False": False,
        }

    # -- attribute access
    def attr(self, path: str) -> Attr | None:
        prefix, key = split_path(path)
        t = self.ctx.target(self.node, prefix)
        if t is None:
            return None
        if key in NODE_FIELDS:
            v = getattr(t, NODE_FIELDS[key])
            return None if v is None else Attr(value=v.isoformat() if isinstance(v, datetime) else v)
        a = t.attrs.get(key)
        if self.trace is not None and (a is None or a.status in ("missing", "unreadable") or a.value is None):
            self.trace.append((t.id, key))
        return a

    def value(self, path: str):
        a = self.attr(path)
        return None if a is None else a.value

    def sources(self, path: str) -> list[Src]:
        if path.startswith("@"):  # attribute whose value is a list of sources
            raw = self.node.val(path[1:]) or []
            return [Src(**s) for s in raw if isinstance(s, dict)]
        a = self.attr(path)
        return [a.src] if a is not None and a.src is not None else []

    def funcs(self) -> dict:
        e = self
        return {
            # attributes
            "val": e.value,
            "t": lambda p: _to_dt(e.value(p)),
            "d": lambda p: _to_date(e.value(p)),
            "defined": lambda p: e.attr(p) is not None,
            "has": lambda p: (a := e.attr(p)) is not None and a.value is not None and a.value is not False,
            "is_true": lambda p: e.value(p) is True,
            "is_false": lambda p: e.value(p) is False,
            "missing": lambda p: (a := e.attr(p)) is None or a.status == "missing" or (a.value is None and a.status != "unreadable"),
            "unreadable": lambda p: (a := e.attr(p)) is not None and a.status == "unreadable",
            "has_src": lambda p: (a := e.attr(p)) is not None and a.src is not None,
            "exists": lambda p: e.ctx.target(e.node, p) is not None,
            # graph
            "acts": lambda subtype: len(e.ctx.person_acts(e.node, subtype)),
            "case_acts": lambda subtype: len(e.ctx.by_subtype.get(subtype, [])),
            # time arithmetic
            "minutes": lambda a, b: None if a is None or b is None else (b - a).total_seconds() / 60,
            "clock": lambda x: None if x is None else x.hour * 60 + x.minute,
            "hhmm": lambda s: int(s[:2]) * 60 + int(s[3:5]),
            "add_minutes": lambda x, m: None if x is None or m is None else x + timedelta(minutes=m),
            "end_of_day": lambda x: None if _to_date(x) is None else datetime.combine(_to_date(x), time(23, 59)),
            "coalesce": lambda *xs: next((x for x in xs if x is not None), None),
            "first_defined": lambda *ps: next((p for p in ps if (a := e.attr(p)) is not None and a.value is not None), ps[-1]),
            # formatting
            "hm": lambda x: "?" if x is None else x.strftime("%H:%M"),
            "dhm": lambda x: "?" if x is None else x.strftime("%d/%m/%Y %H:%M"),
            "dm": lambda x: "?" if x is None else x.strftime("%d/%m"),
            "dur": _fmt_dur,
            "iso": lambda x: None if x is None else x.isoformat(),
            "text": lambda x: "" if x is None else str(x),
            "join": lambda *xs: ", ".join(str(x) for x in xs if x not in (None, "")),
            "min": min, "max": max, "round": round, "int": int,
        }


# ----------------------------------------------------------------------------- safe evaluator

_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
_CMP = {ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge,
        ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Is: operator.is_, ast.IsNot: operator.is_not,
        ast.In: lambda a, b: a in b, ast.NotIn: lambda a, b: a not in b}
_ALLOWED = (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not, ast.USub, ast.BinOp, ast.Compare,
            ast.IfExp, ast.Call, ast.Name, ast.Load, ast.Constant, ast.Subscript, ast.List, ast.Tuple,
            *_BIN.keys(), *_CMP.keys())
ALLOWED_FUNCS = {"val", "t", "d", "defined", "has", "is_true", "is_false", "missing", "unreadable", "has_src", "exists",
                 "acts", "case_acts", "minutes", "clock", "hhmm", "add_minutes", "end_of_day", "coalesce", "first_defined",
                 "hm", "dhm", "dm", "dur", "iso", "text", "join", "min", "max", "round", "int"}


@lru_cache(maxsize=4096)
def compile_expr(src: str) -> ast.Expression:
    try:
        tree = ast.parse(src.strip(), mode="eval")
    except SyntaxError as e:
        raise RuleError(f"syntax error in {src!r}: {e.msg}") from e
    for nd in ast.walk(tree):
        if not isinstance(nd, _ALLOWED):
            raise RuleError(f"not allowed in a rule expression: {type(nd).__name__} in {src!r}")
        if isinstance(nd, ast.Call) and not (isinstance(nd.func, ast.Name) and nd.func.id in ALLOWED_FUNCS):
            raise RuleError(f"unknown function in {src!r}")
        if isinstance(nd, ast.Call) and nd.keywords:
            raise RuleError(f"keyword arguments not allowed in {src!r}")
    return tree


def _ev(nd: ast.AST, names: dict, funcs: dict):
    if isinstance(nd, ast.Expression):
        return _ev(nd.body, names, funcs)
    if isinstance(nd, ast.Constant):
        return nd.value
    if isinstance(nd, ast.Name):
        if nd.id not in names:
            raise RuleError(f"unknown name {nd.id!r}")
        return names[nd.id]
    if isinstance(nd, (ast.List, ast.Tuple)):
        return [_ev(x, names, funcs) for x in nd.elts]
    if isinstance(nd, ast.BoolOp):
        if isinstance(nd.op, ast.And):
            v = True
            for x in nd.values:
                v = _ev(x, names, funcs)
                if not v:
                    return v
            return v
        v = False
        for x in nd.values:
            v = _ev(x, names, funcs)
            if v:
                return v
        return v
    if isinstance(nd, ast.UnaryOp):
        v = _ev(nd.operand, names, funcs)
        if isinstance(nd.op, ast.Not):
            return not v
        return None if v is None else -v
    if isinstance(nd, ast.BinOp):
        a, b = _ev(nd.left, names, funcs), _ev(nd.right, names, funcs)
        if a is None or b is None:
            return None
        return _BIN[type(nd.op)](a, b)
    if isinstance(nd, ast.Compare):
        left = _ev(nd.left, names, funcs)
        for op, rc in zip(nd.ops, nd.comparators):
            right = _ev(rc, names, funcs)
            if (left is None or right is None) and not isinstance(op, (ast.Is, ast.IsNot, ast.Eq, ast.NotEq)):
                return False  # an unknown value never satisfies an ordering condition
            if not _CMP[type(op)](left, right):
                return False
            left = right
        return True
    if isinstance(nd, ast.IfExp):
        return _ev(nd.body, names, funcs) if _ev(nd.test, names, funcs) else _ev(nd.orelse, names, funcs)
    if isinstance(nd, ast.Subscript):
        base = _ev(nd.value, names, funcs)
        key = _ev(nd.slice, names, funcs)
        return None if base is None else base.get(key) if isinstance(base, dict) else base[key]
    if isinstance(nd, ast.Call):
        return funcs[nd.func.id](*[_ev(a, names, funcs) for a in nd.args])
    raise RuleError(f"cannot evaluate {type(nd).__name__}")


class _LazyNames(dict):
    """Context names + `let` variables evaluated on first use only: a variable that no reached outcome needs is
    never computed, so it never reads (or traces as missing) an attribute the rule did not need."""

    def __init__(self, base: dict, lets: dict, funcs: dict):
        super().__init__(base)
        self._lets, self._funcs, self._busy = dict(lets), funcs, set()

    def __contains__(self, k) -> bool:
        return dict.__contains__(self, k) or k in self._lets

    def __missing__(self, k):
        if k not in self._lets or k in self._busy:
            raise KeyError(k)
        self._busy.add(k)
        v = _ev(compile_expr(str(self._lets[k])), self, self._funcs)
        self[k] = v
        return v


_PLACEHOLDER = re.compile(r"\{([^{}]+)\}")


def render(template: str, names: dict, funcs: dict) -> str:
    def repl(m: re.Match) -> str:
        v = _ev(compile_expr(m.group(1)), names, funcs)
        if isinstance(v, datetime):
            return v.strftime("%d/%m/%Y %H:%M")
        if isinstance(v, float):
            return f"{v:g}"
        return "?" if v is None else str(v)
    return _PLACEHOLDER.sub(repl, template)


def validate_version(v) -> None:
    """Compile every expression of a version: a broken rule fails at catalogue load, not during an analysis."""
    for _, src in (v.let or {}).items():
        compile_expr(str(src))
    for o in v.outcomes:
        compile_expr(str(o.get("when", "True")))
        for m in _PLACEHOLDER.finditer(o.get("say", "")):
            compile_expr(m.group(1))
        for src in list((o.get("proof") or {}).values()) + list((o.get("details") or {}).values()):
            if isinstance(src, str) and src not in {"duration_gt", "duration_le", "duration_lt", "clock_ge", "clock_lt"}:
                compile_expr(src)
        if o.get("status") not in {"satisfied", "possible_nullity", "needs_reading", "skip"}:
            raise RuleError(f"bad status {o.get('status')!r}")


DEFAULT_CERTAINTY = {"possible_nullity": "documented", "satisfied": "documented", "needs_reading": "needs_reading"}


def evaluate(version, node: Node, ctx: GraphCtx, trace: list | None = None) -> Result | None:
    """Run one rule version on one node. None = the rule does not apply / nothing to say.
    `trace` (optional) collects the attributes the evaluation needed but did not find (rule-driven extraction)."""
    env = Env(node, ctx, dict(version.params or {}), trace)
    funcs = env.funcs()
    names = _LazyNames(env.vars, version.let or {}, funcs)
    for o in version.outcomes:
        if not _ev(compile_expr(str(o.get("when", "True"))), names, funcs):
            continue
        status = o["status"]
        if status == "skip":
            return None
        srcs: list[Src] = []
        for p in o.get("cite", []):
            for s in env.sources(p):
                if (s.page, s.quote) not in {(x.page, x.quote) for x in srcs}:
                    srcs.append(s)
        proof = None
        if o.get("proof"):
            proof = {k: (v if k == "kind" else _ev(compile_expr(str(v)), names, funcs)) for k, v in o["proof"].items()}
        details = {k: _ev(compile_expr(str(v)), names, funcs) for k, v in (o.get("details") or {}).items()}
        details.update(o.get("notes") or {})
        grey = o.get("grey") or {}
        if grey.get("on_answer"):
            details["_on_answer"] = grey["on_answer"]
        return Result(status=status, statement=render(o.get("say", ""), names, funcs), sources=srcs,
                      certainty=o.get("certainty", DEFAULT_CERTAINTY[status]), details=details,
                      grey=bool(grey), grey_attr=grey.get("attr"), proof=proof, kind=o.get("kind"))
    return None


# ----------------------------------------------------------------------------- what the rules need

_ATTR_FUNCS = {"val", "t", "d", "defined", "has", "is_true", "is_false", "missing", "unreadable", "has_src"}


def referenced_paths(version) -> set[str]:
    """Every attribute path a rule version reads (string arguments of the attribute functions + `cite`)."""
    out: set[str] = set()
    exprs = list((version.let or {}).values())
    for o in version.outcomes:
        exprs.append(str(o.get("when", "True")))
        exprs += [m.group(1) for m in _PLACEHOLDER.finditer(o.get("say", ""))]
        exprs += [str(v) for k, v in (o.get("proof") or {}).items() if k != "kind"]
        exprs += [str(v) for v in (o.get("details") or {}).values()]
        out |= {c for c in o.get("cite", []) if not c.startswith("@")}
    for src in exprs:
        for nd in ast.walk(compile_expr(src)):
            if isinstance(nd, ast.Call) and nd.func.id in _ATTR_FUNCS and nd.args and isinstance(nd.args[0], ast.Constant):
                out.add(str(nd.args[0].value))
    return out


def needs_by_subtype(catalogue: dict) -> dict[str, set[str]]:
    """subtype → attributes the catalogue reads on acts of that subtype. Drives extraction (no list kept by hand)."""
    need: dict[str, set[str]] = {}
    for nl in catalogue.values():
        for v in nl.versions:
            for path in referenced_paths(v):
                prefix, key = split_path(path)
                if key.startswith("@"):
                    continue
                targets = nl.applies_to if prefix in ("", "self") else \
                    ["garde_a_vue"] if prefix == "custody" else [prefix[5:] if prefix.startswith("case:") else prefix]
                for st in targets:
                    need.setdefault(st, set()).add(key)
    return need
