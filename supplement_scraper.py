"""TFDA 回收公告頁補抓器（本機執行，補 opendata 停更期間的缺口）。

**為什麼存在**：上游 opendata（dataset 34）自 2026/06/29 起停更，但官方公告頁
`consumer.fda.gov.tw/GMP/Product.aspx?nodeID=420` 持續發布。看板若只吃 opendata，
會在「顯示正常」的外觀下漏掉最新回收——病安場景的假陰性。

**為什麼在本機跑而不是 GitHub Actions**（2026-08-31 實測，勿再嘗試）：
`consumer.fda.gov.tw` 對境外 IP 在 TLS 層直接切斷（TCP 通、ClientHello 後 RST）。
  - GitHub Actions runner（Azure 美東）→ SSLError UNEXPECTED_EOF，換 TLS 版本／
    cipher／SECLEVEL／legacy renegotiation／UA 全部無效
  - Cloudflare Worker（LAX/SJC）→ 520/525 SSL handshake failed；免費方案的
    workers.dev 不落台灣 colo，Smart Placement 需付費且不保證區域
  - 對照組 `data.fda.gov.tw` 與其他 .gov.tw 主機皆正常 → 是這台主機的境外封鎖
台灣連線可正常取得（HTTP 200），故本抓取器只能在台灣網路環境執行。

**與 scraper.py 的關係**：完全不干涉。`scraper.py` 每天用 opendata 全量覆寫
`data/data.json`，任何寫進去的補抓資料隔天就會被沖掉（且筆數差太小，既有的
MAX_SHRINK_RATIO / MAX_DELETION_RATIO 防線都不會示警）。因此補抓資料一律只寫
`data/supplement.json`，由前端載入時合併，opendata 版本優先。

**退場**：每次執行都重新計算「opendata 尚未收錄的筆」。opendata 補上後
records 自然歸零，不需人工清理，整支腳本可直接刪除。

硬性失敗（exit 1，保留舊的 supplement.json 不覆寫）：
  網路/TLS 錯誤、列表頁抓不到詳情連結、詳情頁解析不出核心欄位、
  data/data.json 不存在或損壞（無從比對就無從判斷缺口）。
  失敗一律不寫空檔——空的 records 會被前端讀成「opendata 已無缺口」，
  與 scraper.py「離線不可回空陣列」同一條病安理由。
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from html import unescape

import requests

LIST_URL = "https://consumer.fda.gov.tw/GMP/Product.aspx?nodeID=420"
DETAIL_URL = "https://consumer.fda.gov.tw/GMP/ProductDetail.aspx?nodeID=420&id={id}"
SOURCE = "衛生福利部食品藥物管理署 - 西藥、醫療器材、化粧品回收專區"

DATA_PATH = os.path.join("data", "data.json")
SUPPLEMENT_PATH = os.path.join("data", "supplement.json")

UA = "Mozilla/5.0 (compatible; TFDA-recall-dashboard/1.0; +https://github.com/liangRXdev)"
REQUEST_TIMEOUT = 30
REQUEST_DELAY = 1.0   # 對公務機關站台的禮貌間隔，勿調低

TAIPEI = timezone(timedelta(hours=8))

# 詳情頁欄位 → opendata schema 欄位。opendata 的「日期」對應公告頁的「發布日期」
# （非「發文日期」）——已用 id=1832 對過既有記錄逐字驗證。
FIELD_MAP = {
    "回收分級": "回收分級",
    "文號": "文號",
    "發布日期": "日期",
    "產品": "產品",
    "許可證字號": "許可證字號",
    "批號": "批號",
    "許可證持有者": "許可證持有者",
    "原因": "原因",
}
CORE_FIELDS = ("回收分級", "日期", "產品")  # 缺任一即視為解析失敗
SCHEMA_FIELDS = ("回收分級", "文號", "日期", "產品",
                 "許可證字號", "批號", "許可證持有者", "原因")


class SupplementError(Exception):
    """補抓流程失敗，應保留舊檔並以非零 exit 結束。"""


# ── 抓取 ──────────────────────────────────────────────────────────────
def http_get(url):
    """單次 GET；TLS 驗證維持開啟（與 scraper.py 同紀律，絕不 verify=False）。"""
    r = requests.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": UA})
    r.raise_for_status()
    r.encoding = "utf-8"
    return r.text


# ── 純函式：解析 ──────────────────────────────────────────────────────
def strip_tags(fragment):
    """去標籤並正規化空白；保留換行（原因／備註常有分行）。"""
    text = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = re.sub(r"[ \t ]+", " ", text)
    return "\n".join(line.strip() for line in text.split("\n")).strip()


def extract_detail_ids(html):
    """從列表頁取出所有詳情頁 id（去重後由新到舊）。抓不到即代表版面已改。"""
    ids = {int(m.group(1)) for m in
           re.finditer(r"ProductDetail\.aspx\?nodeID=420&(?:amp;)?id=(\d+)", html)}
    return sorted(ids, reverse=True)


def parse_detail(html):
    """把詳情頁解析成 opendata schema 的 dict。核心欄位缺漏回 None。"""
    fields = {}
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = re.findall(r"<(t[dh])[^>]*>(.*?)</\1>", row, re.S)
        if len(cells) < 2:
            continue
        label = strip_tags(cells[0][1])
        if label in FIELD_MAP:
            fields[FIELD_MAP[label]] = strip_tags(cells[1][1])
    if any(not fields.get(k) for k in CORE_FIELDS):
        return None
    # 補齊 schema 其餘欄位，讓補抓記錄與 opendata 記錄同形
    return {key: fields.get(key, "") for key in SCHEMA_FIELDS}


def merge_key(record):
    """去重鍵：文號 + 產品。

    刻意不含批號／日期——批號字串長且可能有空白差異；文號是每則公告的唯一識別，
    加上產品即可定位到單一列。
    """
    def norm(v):
        return re.sub(r"\s+", "", str(v or ""))
    return (norm(record.get("文號")), norm(record.get("產品")))


def latest_date(records):
    """回傳 YYYY/MM/DD 字串最大值（零填補故可字典序比較）；無則回 None。"""
    dates = [r.get("日期", "") for r in records
             if re.fullmatch(r"\d{4}/\d{2}/\d{2}", str(r.get("日期", "")))]
    return max(dates) if dates else None


# ── 既有資料 ──────────────────────────────────────────────────────────
def load_opendata(path):
    """讀取 scraper.py 產出的 data.json。缺檔或損壞即硬失敗——無從比對。"""
    if not os.path.exists(path):
        raise SupplementError(f"{path} 不存在，無法判斷 opendata 已收錄哪些公告")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (ValueError, OSError) as e:
        raise SupplementError(f"{path} 讀取失敗：{e}")
    if not isinstance(data, list) or not data:
        raise SupplementError(f"{path} 非有效陣列或為空，拒絕在此狀態下計算缺口")
    return data


def atomic_write_json(path, payload):
    """先寫暫存檔再 os.replace()，避免半寫壞檔（與 scraper.py 同作法）。"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ── 主流程 ───────────────────────────────────────────────────────────
def main():
    try:
        opendata = load_opendata(DATA_PATH)
    except SupplementError as e:
        print(f"[FATAL] {e}", file=sys.stderr)
        return 1

    known = {merge_key(r) for r in opendata if isinstance(r, dict)}

    try:
        list_html = http_get(LIST_URL)
    except requests.exceptions.RequestException as e:
        print(f"[FATAL] 列表頁抓取失敗（{type(e).__name__}）：{e}", file=sys.stderr)
        print("[HINT] 本站對境外 IP 在 TLS 層封鎖，必須在台灣網路環境執行。",
              file=sys.stderr)
        return 1

    ids = extract_detail_ids(list_html)
    if not ids:
        print("[FATAL] 列表頁找不到任何詳情連結，版面可能已改；保留舊 supplement.json",
              file=sys.stderr)
        return 1
    print(f"列表頁取得 {len(ids)} 則公告，id {ids[-1]}-{ids[0]}")

    missing = []
    for idx, detail_id in enumerate(ids):
        if idx:
            time.sleep(REQUEST_DELAY)
        try:
            detail_html = http_get(DETAIL_URL.format(id=detail_id))
        except requests.exceptions.RequestException as e:
            print(f"[FATAL] 詳情頁 id={detail_id} 抓取失敗：{e}", file=sys.stderr)
            return 1

        record = parse_detail(detail_html)
        if record is None:
            # 版面變動時寧可整批失敗，也不要寫出「看起來沒缺口」的殘缺結果
            print(f"[FATAL] 詳情頁 id={detail_id} 解析不出核心欄位，版面可能已改；"
                  f"保留舊 supplement.json", file=sys.stderr)
            return 1

        if merge_key(record) in known:
            continue
        record["_來源"] = "公告頁"
        record["_公告頁id"] = detail_id
        record["_公告頁網址"] = DETAIL_URL.format(id=detail_id)
        missing.append(record)

    missing.sort(key=lambda r: (r.get("日期", ""), r.get("_公告頁id", 0)), reverse=True)

    payload = {
        "generated_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
        "source": SOURCE,
        "list_url": LIST_URL,
        "checked_ids": ids,
        "opendata_count": len(opendata),
        "opendata_latest": latest_date([r for r in opendata if isinstance(r, dict)]),
        "records": missing,
    }
    try:
        atomic_write_json(SUPPLEMENT_PATH, payload)
    except OSError as e:
        print(f"[FATAL] 寫入失敗：{e}", file=sys.stderr)
        return 1

    if missing:
        print(f"opendata 尚缺 {len(missing)} 則公告：")
        for r in missing:
            print(f"  {r['日期']}  {r['回收分級']}  {r['產品'][:40]}")
    else:
        print("opendata 已涵蓋公告頁所有公告，無缺口。")
    print(f"已寫入 {SUPPLEMENT_PATH}（opendata {len(opendata)} 筆，"
          f"最新 {payload['opendata_latest']}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
