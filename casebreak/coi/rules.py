"""Cross-document conflict-of-interest detectors.

Each detector reads the facts of several documents and returns candidate flags: the people and companies involved,
the evidence spans (each with the role it plays in the reasoning), the period at stake and a small chain graph
for the "why". Meaning, legal framing and next steps live in rules.yaml. Detectors also return what they checked
and cleared, so the reviewer sees the negative space, not only the hits.
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import yaml

from casebreak.coi.extract import Facts, Src

RULES_FILE = Path(__file__).with_name("rules.yaml")


@lru_cache(maxsize=1)
def meta() -> dict:
    return yaml.safe_load(RULES_FILE.read_text())


def fmt(x: date | None) -> str:
    return x.strftime("%d %b %Y") if x else "?"


def overlap(a0: date, a1: date, b0: date, b1: date) -> tuple[date, date] | None:
    s, e = max(a0, b0), min(a1, b1)
    return (s, e) if s <= e else None


def ev(src: Src, role: str, label: str) -> dict:
    return {**src.ref(), "role": role, "label": label}


class Ctx:
    """Indexes shared by the detectors."""

    def __init__(self, f: Facts):
        self.f = f
        self.public = {k: v for k, v in f.engagements.items() if v["sector"].lower().startswith("public")}
        self.private = {k: v for k, v in f.engagements.items() if k not in self.public}
        orders_by_id = {o.get("id"): o for o in f.orders.values()}
        self.stake: dict[str, dict] = {}
        for eid in self.public:
            o = orders_by_id.get(eid, {})
            st = f.stakeholders.get(o.get("spec"), {})
            self.stake[eid] = {"companies": st.get("companies", []), "src": st.get("src"), "order": o}

    def assignments(self, person: str | None = None, engagement: str | None = None) -> list[dict]:
        return [a for a in self.f.assignments
                if (person is None or a["person"] == person) and (engagement is None or a["engagement"] == engagement)]

    def time(self, person: str, engagement: str) -> list[dict]:
        return [t for t in self.f.time_entries if t["person"] == person and t["engagement"] == engagement]


# ------------------------------------------------------------------ COI-01 dual mandate


def dual_mandate(c: Ctx) -> tuple[list[dict], list[dict]]:
    flags, cleared = [], []
    for pub, info in c.stake.items():
        affected = set(info["companies"])
        for a in c.assignments(engagement=pub):
            hits = []
            for b in c.assignments(person=a["person"]):
                eng = c.private.get(b["engagement"])
                if not eng or eng["client"] not in affected:
                    continue
                # concurrent, or within the 12 months before the public order starts (framework art. 7.4)
                ov = overlap(a["start"], a["end"], b["start"], b["end"])
                recent = b["end"] >= a["start"] - timedelta(days=365)
                if ov or recent:
                    hits.append((b, eng, ov))
            if not hits:
                cleared.append({"rule": "COI-01", "person": a["person"],
                                "text": f"{a['person']}: no engagement for an affected company found over the period.",
                                "src": a["src"].ref()})
                continue
            for b, eng, ov in hits:
                client, p = eng["client"], a["person"]
                evidence = [
                    ev(b["src"], "private engagement", f"{p} staffed {b['alloc']} % for {client}"),
                    ev(eng["src"], "client", f"Engagement {b['engagement']} — client {client}"),
                    ev(a["src"], "public engagement", f"{p} staffed {a['alloc']} % on order {pub}"),
                ]
                if info["src"]:
                    evidence.append(ev(info["src"], "affected company", f"{client} listed as affected by the order"))
                corroborated = False
                for t in c.time(p, b["engagement"]) + c.time(p, pub):
                    evidence.append(ev(t["src"], "time recorded", f"{t['days']} days on {t['engagement']}"))
                    corroborated = True
                authored = []
                for au in c.f.authorship:
                    if au["person"] != p:
                        continue
                    for r in c.f.recommendations:
                        if r["deliverable"] == au["deliverable"] and r["company"] == client:
                            authored.append(au)
                            evidence.append(ev(au["src"], "authorship", f"{p} — {au['role']} the deliverable"))
                            evidence.append(ev(r["src"], "recommendation", f"Recommended scenario favours {client}"))
                aggravating = []
                if corroborated:
                    aggravating.append("Time reports confirm work on both engagements in the same weeks.")
                if authored:
                    aggravating.append(f"{p} {authored[0]['role']} the deliverable whose recommended scenario favours {client}.")
                if "consent_12_months" in c.f.requirements and "no_consent" in c.f.attestations:
                    evidence.append(ev(c.f.attestations["no_consent"]["src"], "no consent",
                                       "No written consent under art. 7.4"))
                    aggravating.append("The administration states that no consent under art. 7.4 was requested or issued.")
                win = ov or (b["start"], a["start"])
                flags.append({
                    "rule": "COI-01", "persons": [p], "companies": [client],
                    "certainty": "documented",
                    "headline": f"{p} advised the Ministry and {client} at the same time",
                    "summary": (f"{p} was staffed {a['alloc']} % on order {pub} for the Ministry while staffed "
                                f"{b['alloc']} % on engagement {b['engagement']} for {client}, a company listed as "
                                f"affected by that order. Overlap: {fmt(win[0])} → {fmt(win[1])}."),
                    "aggravating": aggravating,
                    "window": [win[0].isoformat(), win[1].isoformat()],
                    "chain": {
                        "nodes": [{"id": p, "kind": "person"}, {"id": client, "kind": "company"},
                                  {"id": f"Order {pub}", "kind": "public"}],
                        "links": [
                            {"s": p, "t": client, "label": f"staffed {b['alloc']} % · {b['engagement']}", "doc": b["src"].doc},
                            {"s": p, "t": f"Order {pub}", "label": f"staffed {a['alloc']} %", "doc": a["src"].doc},
                            {"s": f"Order {pub}", "t": client, "label": "affects", "doc": info["src"].doc if info["src"] else None},
                        ]},
                    "evidence": evidence,
                })
    return flags, cleared


# ------------------------------------------------------------------ COI-02 declaration contradicted


def declaration_contradicted(c: Ctx) -> tuple[list[dict], list[dict]]:
    flags, cleared = [], []
    affected = {co for v in c.stake.values() for co in v["companies"]}
    for person, dec in c.f.declarations.items():
        when = dec["date"]
        contradictions = []
        for b in c.assignments(person=person):
            eng = c.private.get(b["engagement"])
            if not eng:
                continue
            q1 = dec["answers"].get("Q1")
            if q1 and not q1["yes"] and eng["client"] in affected and b["start"] <= when \
                    and b["end"] >= when - timedelta(days=365):
                contradictions.append(("Q1", q1, b, eng))
            q2 = dec["answers"].get("Q2")
            if q2 and not q2["yes"] and "health" in eng["sector"].lower() and b["start"] <= when <= b["end"]:
                contradictions.append(("Q2", q2, b, eng))
        if not contradictions:
            cleared.append({"rule": "COI-02", "person": person,
                            "text": f"{person}: declaration consistent with the engagements found in the file.",
                            "src": dec["src"].ref()})
            for emp in c.f.employment:
                if emp["person"] == person:
                    cleared.append({"rule": "COI-02", "person": person,
                                    "text": (f"{person}: previous activity at {emp['org']} ended {fmt(emp['end'])} — "
                                             "not an affected company, outside the 12-month window."),
                                    "src": emp["src"].ref()})
            continue
        evidence, seen = [], set()
        for q, ans, b, eng in contradictions:
            evidence.append(ev(ans["box"], "declared", f"{q} answered “No”: {ans['question']}"))
            if b["engagement"] not in seen:
                seen.add(b["engagement"])
                evidence.append(ev(b["src"], "contradiction",
                                   f"Staffed on {b['engagement']} for {eng['client']} from {fmt(b['start'])}"))
                evidence.append(ev(eng["src"], "client", f"{eng['client']} — sector: {eng['sector']}"))
        b, eng = contradictions[0][2], contradictions[0][3]
        qs = sorted({q for q, *_ in contradictions})
        flags.append({
            "rule": "COI-02", "persons": [person], "companies": [eng["client"]],
            "certainty": "documented",
            "headline": f"{person} declared no health-sector engagement — the engagement letter says otherwise",
            "summary": (f"On {fmt(when)} {person} answered “No” to {' and '.join(qs)} of the declaration of interests, "
                        f"while staffed since {fmt(b['start'])} on engagement {b['engagement']} for {eng['client']} "
                        f"({eng['sector']})."),
            "aggravating": [],
            "window": [b["start"].isoformat(), when.isoformat()],
            "chain": {
                "nodes": [{"id": person, "kind": "person"}, {"id": "Declaration", "kind": "doc"},
                          {"id": eng["client"], "kind": "company"}],
                "links": [
                    {"s": person, "t": "Declaration", "label": f"“No” · {fmt(when)}", "doc": dec["doc"]},
                    {"s": person, "t": eng["client"], "label": f"staffed since {fmt(b['start'])}", "doc": b["src"].doc},
                ]},
            "evidence": evidence,
        })
    return flags, cleared


# ------------------------------------------------------------------ COI-03 missing declarations


def missing_declarations(c: Ctx) -> tuple[list[dict], list[dict]]:
    req = c.f.requirements.get("declaration_before_start")
    if not req:
        return [], []
    flags = []
    held = c.f.attestations.get("declarations_held")
    for pub in c.public:
        team = c.assignments(engagement=pub)
        declared = set(c.f.declarations) | set(held["names"] if held else [])
        missing = [a for a in team if a["person"] not in declared]
        if not missing:
            continue
        evidence = [ev(req, "requirement", "Each consultant files a declaration before the order starts")]
        if held:
            evidence.append(ev(held["src"], "administration", f"The administration holds {held['n']} declarations"))
        evidence += [ev(a["src"], "missing", f"{a['person']} — no declaration in the file") for a in missing]
        flags.append({
            "rule": "COI-03", "persons": [a["person"] for a in missing], "companies": [],
            "stats": {"team": len(team), "declared": len(team) - len(missing)},
            "certainty": "documented" if held else "inferred",
            "headline": f"{len(missing)} of {len(team)} consultants on order {pub} have no declaration of interests",
            "summary": (f"Art. 7.3 requires a declaration from each consultant before the order starts. "
                        f"{len(team)} consultants are assigned to {pub}; the file holds {len(team) - len(missing)} "
                        f"declarations. Missing: {', '.join(a['person'] for a in missing)}."),
            "aggravating": [f"{a['person']} is also staffed on a private engagement."
                            for a in missing if any(b["engagement"] in c.private for b in c.assignments(person=a["person"]))],
            "window": [min(a["start"] for a in team).isoformat(), max(a["end"] for a in team).isoformat()],
            "chain": {
                "nodes": [{"id": f"Order {pub}", "kind": "public"}, {"id": f"{len(team)} consultants", "kind": "person"},
                          {"id": f"{len(team) - len(missing)} declarations", "kind": "doc"}],
                "links": [
                    {"s": f"Order {pub}", "t": f"{len(team)} consultants", "label": "assigned", "doc": team[0]["src"].doc},
                    {"s": f"{len(team)} consultants", "t": f"{len(team) - len(missing)} declarations",
                     "label": "filed", "doc": held["src"].doc if held else None},
                ]},
            "evidence": evidence,
        })
    return flags, []


# ------------------------------------------------------------------ COI-04 revolving door


def revolving_door(c: Ctx) -> tuple[list[dict], list[dict]]:
    flags, cleared = [], []
    years = meta()["COI-04"].get("window_years", 3)
    for o in c.f.orders.values():
        signer, signed, holder = o.get("signer"), o.get("signed"), o.get("holder", "")
        if not (signer and signed and holder):
            continue
        firm = holder.split()[0]
        for emp in c.f.employment:
            if emp["person"] != signer or firm not in emp["org"]:
                continue
            gap = (signed - emp["end"]).days
            if gap > years * 365:
                cleared.append({"rule": "COI-04", "person": signer,
                                "text": f"{signer}: left {emp['org']} {gap // 30} months before signing — outside the window.",
                                "src": emp["src"].ref()})
                continue
            evidence = [
                ev(o["signer_src"], "signature", f"{signer} signs order {o.get('id')} on {fmt(signed)}"),
                ev(emp["src"], "previous employment", f"{emp['org']} until {fmt(emp['end'])}"),
            ]
            aggravating = [f"{gap // 30} months between leaving the firm and signing its order."]
            for dec in c.f.decisions:
                if dec.get("signatory") == signer:
                    evidence.append(ev(dec["signatory_src"], "decision", f"{signer} prepares the decision memo"))
                    aggravating.append("The signatory also prepared the decision memo adopting the firm's recommendations.")
                    break
            no_recusal = c.f.attestations.get("no_recusal")
            if no_recusal:
                evidence.append(ev(no_recusal["src"], "no recusal", "No recusal record for the signatory"))
            flags.append({
                "rule": "COI-04", "persons": [signer], "companies": [holder],
                "certainty": "documented" if no_recusal else "needs_reading",
                "headline": f"{signer} signed the firm's order {gap // 30} months after leaving the firm",
                "summary": (f"{signer} signed purchase order {o.get('id')} awarded to {holder} on {fmt(signed)}. "
                            f"The signatory's declaration on appointment lists {emp['org']} as employer until {fmt(emp['end'])} "
                            f"— {gap // 30} months earlier, within the {years}-year window."
                            + (" No recusal record exists." if no_recusal else "")),
                "aggravating": aggravating,
                "window": [emp["end"].isoformat(), signed.isoformat()],
                "chain": {
                    "nodes": [{"id": signer, "kind": "person"}, {"id": holder, "kind": "company"},
                              {"id": f"Order {o.get('id')}", "kind": "public"}],
                    "links": [
                        {"s": signer, "t": holder, "label": f"employee until {fmt(emp['end'])}", "doc": emp["src"].doc},
                        {"s": signer, "t": f"Order {o.get('id')}", "label": f"signs · {fmt(signed)}", "doc": o["doc"]},
                        {"s": f"Order {o.get('id')}", "t": holder, "label": "awarded to", "doc": o["doc"]},
                    ]},
                "evidence": evidence,
            })
    return flags, cleared


# ------------------------------------------------------------------ COI-05 relative tied to the beneficiary


def relative_beneficiary(c: Ctx) -> tuple[list[dict], list[dict]]:
    flags, cleared = [], []
    for rel in c.f.relatives:
        if not rel["org"]:
            continue
        owned = [co for co, o in c.f.ownership.items() if o["parent"] == rel["org"]]
        hit = False
        for dec in c.f.decisions:
            if dec.get("company") not in owned + [rel["org"]] or rel["person"] not in dec["persons"]:
                continue
            hit = True
            co, p = dec["company"], rel["person"]
            own = c.f.ownership.get(co)
            evidence = [ev(rel["src"], "declared tie", f"{p}: {rel['text']}")]
            if own:
                evidence.append(ev(own["src"], "ownership", f"{co} is {own['share']} % owned by {own['parent']}"))
            evidence.append(ev(dec["src"], "benefit", f"{co} selected on the basis of work by {p}"))
            no_consent = c.f.attestations.get("no_consent")
            if no_consent:
                evidence.append(ev(no_consent["src"], "no consent", "Declared interest not followed by any decision"))
            flags.append({
                "rule": "COI-05", "persons": [p], "companies": [co, rel["org"]],
                "certainty": "inferred",
                "headline": f"{p} declared a {rel['relation']} at the group whose subsidiary was selected",
                "summary": (f"{p} declared a {rel['relation']} employed by {rel['org']}. {co}, "
                            f"{own['share'] if own else '?'} % owned by {rel['org']}, was selected as provider on the "
                            f"basis of a deliverable {p} prepared. The interest was declared but nothing in the file "
                            "shows it was assessed or managed."),
                "aggravating": ["Declared — but kept on the workstream that selected the provider."],
                "window": [(c.f.declarations[p]["date"] if p in c.f.declarations else dec["date"]).isoformat(),
                           dec["date"].isoformat()],
                "chain": {
                    "nodes": [{"id": p, "kind": "person"}, {"id": rel["org"], "kind": "company"},
                              {"id": co, "kind": "company"}],
                    "links": [
                        {"s": p, "t": rel["org"], "label": f"{rel['relation']} employed", "doc": rel["src"].doc},
                        {"s": rel["org"], "t": co, "label": f"owns {own['share'] if own else '?'} %",
                         "doc": own["src"].doc if own else None},
                        {"s": p, "t": co, "label": "prepared its selection", "doc": dec["src"].doc},
                    ]},
                "evidence": evidence,
            })
        if not hit:
            cleared.append({"rule": "COI-05", "person": rel["person"],
                            "text": f"{rel['person']}: declared tie to {rel['org']} — no decision benefiting it found.",
                            "src": rel["src"].ref()})
    return flags, cleared


# ------------------------------------------------------------------ COI-06 statement under oath contradicted


def statement_contradicted(c: Ctx, found: list[dict]) -> tuple[list[dict], list[dict]]:
    flags = []
    by_rule: dict[str, list[dict]] = {}
    for fl in found:
        by_rule.setdefault(fl["rule"], []).append(fl)
    sector = {e["client"]: e["sector"].lower() for e in c.private.values()}
    for st in c.f.statements:
        if st["claim"] == "all_declared" and by_rule.get("COI-03"):
            base = by_rule["COI-03"][0]
            contra = [e for e in base["evidence"] if e["role"] in ("administration", "missing")][:4]
            extra = (["The witness is on the team and filed no declaration."]
                     if st["speaker"] in base["persons"] else [])
            flags.append(_oath(st, "every consultant filed a declaration of interests", contra,
                               f"{base['stats']['team']} consultants were assigned; the file holds "
                               f"{base['stats']['declared']} declarations.", base, extra))
        if st["claim"] == "no_dual_mandate":
            duals = [fl for fl in by_rule.get("COI-01", []) if "vaccin" in sector.get(fl["companies"][0], "")]
            if not duals:
                continue
            contra = []
            for fl in duals:
                contra += [e for e in fl["evidence"] if e["role"] in ("private engagement", "time recorded")][:2]
            names = " and ".join(p for fl in duals for p in fl["persons"])
            flags.append(_oath(st, "no team member worked for a vaccine manufacturer during the mission", contra,
                               f"{names} were staffed for {duals[0]['companies'][0]} during the mission.",
                               duals[0], []))
    return flags, []


def _oath(st: dict, gist: str, contra: list[dict], why: str, base: dict, extra: list[str]) -> dict:
    sp = st["speaker"]
    return {
        "rule": "COI-06", "persons": [sp], "companies": base["companies"],
        "certainty": "documented",
        "headline": f"Under oath: “{gist}” — the file says otherwise",
        "summary": f"On {fmt(st['date'])}, under oath, {sp} stated that {gist}. {why}",
        "aggravating": extra,
        "window": [base["window"][0], st["date"].isoformat()],
        "chain": {
            "nodes": [{"id": sp, "kind": "person"}, {"id": "Sworn statement", "kind": "doc"},
                      {"id": "Case file", "kind": "doc"}],
            "links": [
                {"s": sp, "t": "Sworn statement", "label": fmt(st["date"]), "doc": st["src"].doc},
                {"s": "Sworn statement", "t": "Case file", "label": "contradicted by", "doc": contra[0]["doc"] if contra else None},
            ]},
        "evidence": [ev(st["src"], "statement", f"{sp}, under oath")] + contra,
    }


DETECTORS = [dual_mandate, declaration_contradicted, missing_declarations, revolving_door, relative_beneficiary]
