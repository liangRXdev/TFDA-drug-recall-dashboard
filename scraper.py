"""TFDA 西藥回收公開資料抓取器（資料入口強固版）。

設計原則（對應 codex-review A 群組）：
- CR-01：預設啟用 TLS 驗證；不再 verify=False。若 CI 憑證鏈有異，
         透過環境變數 TFDA_CA_BUNDLE 指定核准的 CA bundle，絕不靜默跳過驗證。
- CR-02：任何失敗一律非零 exit，讓 GitHub Actions 明確失敗（不再 sys.exit(0)）。
- CR-03 / TG-01：驗證通過才寫入；先寫暫存檔再 os.replace() 原子取代，
         失敗時保留舊的 data.json，不覆寫。
- TG-02：與前版做語意差異防線（筆數暴跌 / 大量舊資料消失 / 最新日期倒退）。
- TG-04：每次成功抓取產生 data/status.json（heartbeat：時間、筆數、最新公告日期）。

硬性失敗（HARD FAIL，阻擋 commit 並保留舊檔）：
  網路/TLS/HTTP 錯誤、非 JSON、根節點非陣列、空陣列、筆數低於絕對下限、
  筆數相較前版暴跌。這些代表資料源失效或被污染。

軟性警告（WARN，輸出 stderr 但仍寫入）：
  未知分級格式、核心欄位缺漏、最新公告日期倒退、大量記錄消失。
  刻意採寬鬆策略：TFDA 偶爾變動格式，硬擋反而造成 false negative（整批更新被拒、
  舊資料續用），比放行更糟。
"""
import json
import os
import sys
from datetime import datetime, timezone

import requests

URL = "https://data.fda.gov.tw/data/opendata/export/34/json"
SOURCE = "政府資料開放平臺 - 藥品回收資料集 (dataset 6947)"
DATA_PATH = os.path.join("data", "data.json")
STATUS_PATH = os.path.join("data", "status.json")

# ── 驗證門檻 ──────────────────────────────────────────────────────────
MIN_ABSOLUTE_COUNT = 100      # 低於此筆數視為資料源失效
MAX_SHRINK_RATIO = 0.90       # 新筆數 < 前版 * 此比例 → 暴跌，硬擋
MAX_DELETION_RATIO = 0.05     # 消失記錄 > 前版 * 此比例 → 軟警告

EXPECTED_KEYS = ["回收分級", "文號", "日期", "產品",
                 "許可證字號", "批號", "許可證持有者", "原因"]
CORE_KEYS = ["回收分級", "日期", "產品"]  # 結構性指標，大量缺漏視為 feed 損壞
GRADE_TOKENS = ("一", "二", "三", "1", "2", "3")


class ValidationError(Exception):
    """資料未通過健全性驗證，應阻擋 commit 並保留舊檔。"""


# ── 抓取 ──────────────────────────────────────────────────────────────
def fetch_data(url):
    """抓取並解析上游 JSON。啟用 TLS 驗證；失敗一律拋例外。"""
    ca_bundle = os.environ.get("TFDA_CA_BUNDLE")  # 選用：核准的 CA bundle 路徑
    verify = ca_bundle if ca_bundle else True
    response = requests.get(url, timeout=30, verify=verify)
    response.raise_for_status()
    return response.json()


# ── 純函式：日期 ──────────────────────────────────────────────────────
def parse_date(value):
    """將 'YYYY/MM/DD' 轉為 date；無法解析回 None。"""
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value.strip(), "%Y/%m/%d").date()
    except ValueError:
        return None


def latest_date(data):
    """回傳資料集中最新的有效公告日期（date），無有效日期回 None。"""
    dates = [d for d in (parse_date(item.get("日期")) for item in data
                         if isinstance(item, dict)) if d]
    return max(dates) if dates else None


def record_key(item):
    """組出穩定識別鍵，用於前後版本集合比對（與磁碟順序無關）。"""
    return tuple(str(item.get(k, "")) for k in
                 ("日期", "文號", "產品", "許可證字號", "批號"))


# ── 結構驗證（硬性）──────────────────────────────────────────────────
def validate_structure(data):
    """根節點結構檢查；不通過拋 ValidationError。"""
    if not isinstance(data, list):
        raise ValidationError(f"根節點應為陣列，實得 {type(data).__name__}")
    if len(data) == 0:
        raise ValidationError("資料為空陣列，疑似上游失效")
    if len(data) < MIN_ABSOLUTE_COUNT:
        raise ValidationError(
            f"筆數 {len(data)} 低於絕對下限 {MIN_ABSOLUTE_COUNT}，疑似資料源失效")
    non_dict = sum(1 for item in data if not isinstance(item, dict))
    if non_dict:
        raise ValidationError(f"有 {non_dict} 筆非物件記錄，結構異常")
    for key in CORE_KEYS:
        missing = sum(1 for item in data if key not in item)
        if missing > len(data) * 0.5:
            raise ValidationError(
                f"逾半數記錄缺少核心欄位「{key}」({missing}/{len(data)})，feed 結構已變")


# ── 前版比對（硬性 + 軟性）───────────────────────────────────────────
def load_previous(path):
    """讀取現有 data.json；不存在或損壞回 None（首次執行不做差異防線）。"""
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            prev = json.load(f)
        return prev if isinstance(prev, list) else None
    except (ValueError, OSError):
        return None


def compare_with_previous(new_data, prev_data):
    """語意差異防線。暴跌拋 ValidationError；其餘回傳警告字串 list。"""
    if not prev_data:
        return []
    warnings = []
    if len(new_data) < len(prev_data) * MAX_SHRINK_RATIO:
        raise ValidationError(
            f"筆數暴跌：{len(prev_data)} → {len(new_data)}"
            f"（低於 {MAX_SHRINK_RATIO:.0%}），疑似上游異常或被污染")

    prev_keys = {record_key(i) for i in prev_data if isinstance(i, dict)}
    new_keys = {record_key(i) for i in new_data if isinstance(i, dict)}
    removed = prev_keys - new_keys
    if len(removed) > len(prev_keys) * MAX_DELETION_RATIO:
        warnings.append(
            f"有 {len(removed)} 筆舊記錄在新版消失（>{MAX_DELETION_RATIO:.0%}），請人工覆核")

    prev_latest, new_latest = latest_date(prev_data), latest_date(new_data)
    if prev_latest and new_latest and new_latest < prev_latest:
        warnings.append(
            f"最新公告日期倒退：{prev_latest} → {new_latest}，疑似上游供舊快照")
    return warnings


# ── 軟性資料品質檢查 ─────────────────────────────────────────────────
def soft_checks(data):
    """回傳 (警告字串 list, 分級分佈 dict)。不阻擋 commit。"""
    warnings = []
    grade_dist = {}
    unknown_grades = set()
    for item in data:
        grade = item.get("回收分級")
        key = (grade.strip() if isinstance(grade, str) else repr(grade))
        grade_dist[key] = grade_dist.get(key, 0) + 1
        if isinstance(grade, str) and grade.strip():
            if not any(tok in grade for tok in GRADE_TOKENS):
                unknown_grades.add(grade.strip())
    if unknown_grades:
        warnings.append(f"未知分級格式（不阻擋）：{sorted(unknown_grades)}")
    return warnings, grade_dist


# ── 原子寫入 ─────────────────────────────────────────────────────────
def atomic_write_json(path, payload):
    """先寫同目錄暫存檔再 os.replace() 原子取代，避免半寫壞檔。"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def write_status(count, latest, grade_dist):
    """TG-04 heartbeat：記錄成功抓取時間、筆數、最新公告日期、來源。"""
    status = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "record_count": count,
        "latest_announcement": latest.isoformat() if latest else None,
        "source": SOURCE,
        "url": URL,
        "grade_distribution": grade_dist,
    }
    atomic_write_json(STATUS_PATH, status)


# ── 主流程 ───────────────────────────────────────────────────────────
def main():
    try:
        data = fetch_data(URL)
    except requests.exceptions.RequestException as e:
        print(f"[FATAL] API/TLS 請求失敗：{e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"[FATAL] JSON 解析失敗：{e}", file=sys.stderr)
        return 1

    try:
        validate_structure(data)
        warnings = compare_with_previous(data, load_previous(DATA_PATH))
    except ValidationError as e:
        print(f"[FATAL] 資料驗證未通過，保留舊檔不覆寫：{e}", file=sys.stderr)
        return 1

    soft_warns, grade_dist = soft_checks(data)
    warnings += soft_warns
    latest = latest_date(data)

    try:
        atomic_write_json(DATA_PATH, data)
        write_status(len(data), latest, grade_dist)
    except OSError as e:
        print(f"[FATAL] 寫入失敗：{e}", file=sys.stderr)
        return 1

    for w in warnings:
        print(f"[WARN] {w}", file=sys.stderr)
    print(f"抓取與驗證成功：{len(data)} 筆，"
          f"最新公告 {latest.isoformat() if latest else '未知'}，"
          f"警告 {len(warnings)} 則。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
