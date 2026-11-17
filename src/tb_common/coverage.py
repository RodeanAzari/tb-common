"""Functional coverage across test processes (cocotb-coverage).

A regression usually runs each parameter set in its own simulator process, so each process
holds only its own bins. This module gives the three steps that turn that into one
closure result:

    export(path)                        # end of each process: its bins and hit counts
    merged = merge(load(p) for p in paths)
    holes(merged, excluded)             # {item: [bins below at_least]}; empty = closed
    report_html(merged, excluded)       # one page: every item, every bin, every waiver

Bins are keyed by repr() of the cocotb-coverage bin, so ints, strings and cross tuples
survive JSON. Each item keeps its at_least threshold; a bin is covered when its hits
reach it. An exclusion is {item: {bin repr: written reason}}; one that names an item or
bin that does not exist raises, so a stale waiver cannot hide a renamed bin.

Only snapshot()/export() import cocotb_coverage; the rest is plain Python.
"""

from __future__ import annotations

import html
import json
from collections.abc import Iterable, Mapping
from pathlib import Path

Snapshot = dict[str, dict]  # item -> {"at_least": int, "bins": {repr(bin): hits}}
Excluded = Mapping[str, Mapping[str, str]]  # item -> {repr(bin): reason}


def snapshot() -> Snapshot:
    """This process's cover points and crosses (leaves only, not their groups)."""
    from cocotb_coverage.coverage import CoverCross, CoverPoint, coverage_db

    out: Snapshot = {}
    for name, item in coverage_db.items():
        if isinstance(item, CoverPoint | CoverCross):
            bins = {repr(b): int(n) for b, n in item.detailed_coverage.items()}
            out[name] = {"at_least": int(item.at_least), "bins": bins}
    return out


def export(path: str | Path) -> None:
    Path(path).write_text(json.dumps(snapshot(), indent=1, sort_keys=True))


def load(path: str | Path) -> Snapshot:
    return json.loads(Path(path).read_text())


def merge(snaps: Iterable[Snapshot]) -> Snapshot:
    """Hits summed per bin; the union of items and bins. An item's at_least must agree."""
    out: Snapshot = {}
    for snap in snaps:
        for name, item in snap.items():
            m = out.setdefault(name, {"at_least": item["at_least"], "bins": {}})
            if m["at_least"] != item["at_least"]:
                raise ValueError(f"{name}: at_least {item['at_least']} vs {m['at_least']}")
            for b, n in item["bins"].items():
                m["bins"][b] = m["bins"].get(b, 0) + n
    return out


def _check_excluded(merged: Snapshot, excluded: Excluded) -> None:
    for name, bins in excluded.items():
        if name not in merged:
            raise KeyError(f"exclusion for unknown item {name!r}")
        for b, reason in bins.items():
            if b not in merged[name]["bins"]:
                raise KeyError(f"exclusion for unknown bin {name} {b}")
            if not reason.strip():
                raise ValueError(f"exclusion {name} {b} has no written reason")


def holes(merged: Snapshot, excluded: Excluded | None = None) -> dict[str, list[str]]:
    """Bins below their item's at_least that are not excluded, per item (empty = closed)."""
    excluded = excluded or {}
    _check_excluded(merged, excluded)
    out: dict[str, list[str]] = {}
    for name, item in sorted(merged.items()):
        skip = excluded.get(name, {})
        miss = [b for b, n in item["bins"].items() if n < item["at_least"] and b not in skip]
        if miss:
            out[name] = miss
    return out


def report_html(merged: Snapshot, excluded: Excluded | None = None, title: str = "Coverage") -> str:
    """One self-contained page: a summary line, then every item with every bin."""
    excluded = excluded or {}
    gaps = holes(merged, excluded)
    n_bins = sum(len(i["bins"]) for i in merged.values())
    n_excl = sum(len(b) for b in excluded.values())
    n_miss = sum(len(b) for b in gaps.values())
    e = html.escape
    rows = []
    for name, item in sorted(merged.items()):
        skip = excluded.get(name, {})
        for b, n in item["bins"].items():
            if b in skip:
                state, note = "excluded", skip[b]
            elif n >= item["at_least"]:
                state, note = "hit", ""
            else:
                state, note = "HOLE", ""
            rows.append(
                f"<tr class='{state}'><td>{e(name)}</td><td>{e(b)}</td><td>{n}</td>"
                f"<td>{state}</td><td>{e(note)}</td></tr>"
            )
    verdict = "closed" if not gaps else f"{n_miss} hole(s)"
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{e(title)}</title><style>"
        "body{font-family:sans-serif;margin:16px}table{border-collapse:collapse}"
        "td,th{border:1px solid #999;padding:2px 6px;text-align:left}"
        ".HOLE{background:#fcc}.excluded{background:#eee}</style></head><body>"
        f"<h1>{e(title)}</h1><p>{len(merged)} items, {n_bins} bins: {verdict}; "
        f"{n_excl} excluded with a written reason.</p>"
        "<table><tr><th>item</th><th>bin</th><th>hits</th><th>state</th><th>reason</th></tr>"
        + "".join(rows)
        + "</table></body></html>"
    )
