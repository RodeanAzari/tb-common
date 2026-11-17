"""pytest: coverage export, merge, holes and report.

Why: closure is a claim that every defined bin was hit somewhere in the regression. A merge
that drops a process's hits reports false holes; one that ORs instead of summing hides an
at_least threshold; a waiver that outlives its bin (renamed, removed) silently hides a
real hole; a report that marks a hole as hit is worse than no report. Each is pinned.
"""

from __future__ import annotations

import pytest

from tb_common import coverage as cov


def snap(at_least: int = 1, **bins: int) -> cov.Snapshot:
    return {"p": {"at_least": at_least, "bins": {repr(k): n for k, n in bins.items()}}}


def test_merge_sums_hits_across_processes() -> None:
    m = cov.merge([snap(a=1, b=0), snap(a=2, b=0), snap(a=0, b=3)])
    assert m["p"]["bins"] == {"'a'": 3, "'b'": 3}


def test_merge_is_a_union_of_items_and_bins() -> None:
    other = {"q": {"at_least": 1, "bins": {"1": 1}}}
    m = cov.merge([snap(a=1), other, snap(c=0)])
    assert set(m) == {"p", "q"} and m["p"]["bins"] == {"'a'": 1, "'c'": 0}


def test_merge_rejects_disagreeing_at_least() -> None:
    with pytest.raises(ValueError):
        cov.merge([snap(1, a=1), snap(2, a=1)])


def test_holes_use_at_least_not_nonzero() -> None:
    m = cov.merge([snap(3, a=2, b=3)])
    assert cov.holes(m) == {"p": ["'a'"]}  # 2 hits < 3 is a hole; 3 is not


def test_closed_means_no_holes() -> None:
    assert cov.holes(cov.merge([snap(a=1), snap(b=1)])) == {}


def test_exclusions_need_a_reason_and_an_existing_bin() -> None:
    m = cov.merge([snap(a=1, b=0)])
    assert cov.holes(m, {"p": {"'b'": "unreachable: reason"}}) == {}
    with pytest.raises(KeyError):
        cov.holes(m, {"p": {"'gone'": "renamed bin"}})
    with pytest.raises(KeyError):
        cov.holes(m, {"nope": {"'b'": "x"}})
    with pytest.raises(ValueError):
        cov.holes(m, {"p": {"'b'": "  "}})


def test_report_marks_every_bin_state() -> None:
    m = cov.merge([snap(a=1, b=0, c=0)])
    page = cov.report_html(m, {"p": {"'c'": "needs <hw>"}}, title="T")
    assert "1 hole(s)" in page and "1 excluded" in page
    assert "<td>'a'</td><td>1</td><td>hit</td>" in page.replace("&#x27;", "'")
    assert "<td>'b'</td><td>0</td><td>HOLE</td>" in page.replace("&#x27;", "'")
    assert "needs &lt;hw&gt;" in page  # escaped
    assert "closed" in cov.report_html(cov.merge([snap(a=1)]))


def test_export_load_round_trip_with_cocotb_coverage(tmp_path) -> None:
    pytest.importorskip("cocotb_coverage")
    from cocotb_coverage.coverage import CoverCross, CoverPoint

    @CoverPoint("rt.x", xf=lambda x, y: x, bins=[0, 1])
    @CoverPoint("rt.y", xf=lambda x, y: y, bins=["u", "v"])
    @CoverCross("rt.xy", items=["rt.x", "rt.y"])
    def sample(x: int, y: str) -> None:
        pass

    sample(0, "u")
    sample(0, "u")
    sample(1, "v")
    path = tmp_path / "c.json"
    cov.export(path)
    s = cov.load(path)
    assert s["rt.x"] == {"at_least": 1, "bins": {"0": 2, "1": 1}}
    assert s["rt.xy"]["bins"] == {"(0, 'u')": 2, "(0, 'v')": 0, "(1, 'u')": 0, "(1, 'v')": 1}
    assert "rt" not in s  # the group item is not a leaf
    assert cov.holes(cov.merge([s, s])) == {"rt.xy": ["(0, 'v')", "(1, 'u')"]}
