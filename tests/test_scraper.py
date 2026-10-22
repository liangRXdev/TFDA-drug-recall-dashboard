"""scraper.py 入口驗證的迴歸測試。

執行：uv run --no-project --with pytest --with requests==2.32.3 python -m pytest tests -q
"""
import pytest

import scraper
from scraper import ValidationError, compare_with_previous, validate_structure


def rec(i, grade="第二級", date="2026/10/01", product="測試藥品"):
    return {"回收分級": grade, "日期": date, "產品": f"{product}{i}",
            "文號": f"FDA{i}", "許可證字號": f"衛署藥製字第{i:06d}號", "批號": f"B{i}"}


def good(n=200):
    return [rec(i) for i in range(n)]


def test_valid_feed_passes():
    validate_structure(good())


@pytest.mark.parametrize("blank", [None, "", "   "])
@pytest.mark.parametrize("key", scraper.CORE_KEYS)
def test_majority_blank_core_values_are_hard_blocked(key, blank):
    """2026-10-22 review H1：key 齊全但值全空，原本照樣通過並覆寫看板"""
    data = good()
    for item in data:
        item[key] = blank
    with pytest.raises(ValidationError, match=key):
        validate_structure(data)


def test_missing_key_still_hard_blocked():
    data = good()
    for item in data:
        del item["產品"]
    with pytest.raises(ValidationError):
        validate_structure(data)


def test_minority_blank_grade_is_tolerated():
    """現行資料約 9% 回收分級為 null，屬格式常態，不可被硬擋（false negative 比放行更糟）"""
    data = good()
    for item in data[:20]:
        item["回收分級"] = None
    validate_structure(data)


def test_record_key_drift_is_soft_warning_not_block():
    """日期等格式漂移會讓所有 record_key 改變；依 CLAUDE.md 屬軟警告，不硬擋"""
    prev = good()
    new = [rec(i, date=f"2026/10/{1:d}") for i in range(200)]
    warns = compare_with_previous(new, prev)
    assert any("消失" in w for w in warns)


def test_shrink_is_hard_blocked():
    with pytest.raises(ValidationError, match="暴跌"):
        compare_with_previous(good(150), good(200))


# ── M3：上游停更的軟警告（2026-10-22 review）──────────────────────────
from datetime import date  # noqa: E402


def test_stale_upstream_warns_but_does_not_block():
    msg = scraper.staleness_warning(date(2026, 8, 26), date(2026, 10, 22))
    assert msg is not None and "57 天" in msg and "2026-08-26" in msg


@pytest.mark.parametrize("days,warns", [(14, False), (15, True)])
def test_stale_threshold_boundary(days, warns):
    today = date(2026, 10, 22)
    latest = date.fromordinal(today.toordinal() - days)
    assert (scraper.staleness_warning(latest, today) is not None) is warns


def test_no_parsable_date_warns():
    assert scraper.staleness_warning(None, date(2026, 10, 22)) is not None


def test_annotation_only_in_actions(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    scraper.emit_warning("甲\n乙")
    assert "::warning" not in capsys.readouterr().out
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    scraper.emit_warning("甲\n乙")
    out = capsys.readouterr().out
    assert out.startswith("::warning ") and "甲 乙" in out and "\n" not in out.rstrip("\n")
