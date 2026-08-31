# TFDA-drug-recall-dashboard — 專案規則

台灣西藥回收監測看板。零建置靜態站（GitHub Pages）+ Python scraper + GitHub Actions 每日排程。

**這個 repo 的多數設計是「刻意不做某件事」**，2026-07-22 經完整審查後定案。下面每條都寫了理由——看起來像疏漏的地方，先讀理由再動。

完整來由在 `.ai-review/`：`codex-review.md`（原始審查報告）與 `verdict.md`（25 項逐項裁決，含 4 項「部分接受」的降級理由）。要推翻本檔任何一條決策前，先讀那兩份。

> ⚠️ 與 `TFDA-drug-recall-alert` 是**不同 repo**。那個跑在 GAS 上、會被 .gov.tw 擋 Google IP；本 repo 由 GitHub Actions runner 直抓 `data.fda.gov.tw`，TLS 正常，不要把那邊的 workaround 搬過來。

---

## 刻意不做的事（勿「修正」）

| 看起來缺什麼 | 為什麼是刻意的 |
|---|---|
| **無 CSP** | GH Pages 不控標頭。改 inline script / sw.js **不需**重算 hash（`TFDA-drug-info-search` 有 CSP，別搞混） |
| **Google Fonts 沒加 SRI** | CSS 回應內容隨 UA 變動，加了 hash 必然不符而被擋。其他 CDN 資源一律要有 SRI |
| **未知分級不預設為第二級** | 標「未確認」並排除於確定分級 KPI。舊 bug 曾把第一級低估 14 倍（4 → 56） |
| **格式漂移只軟警告、不擋** | 見下節 |

## scraper：TLS 與驗證分寸

**TLS 驗證絕不關閉。** `verify=False` 已移除。唯一逃生門是環境變數 `TFDA_CA_BUNDLE` 指定核准的 CA bundle（`scraper.py:51-53`）。

CI 出現 TLS 錯誤是**預期的「大聲失敗」**，不是要你關驗證。

驗證力道刻意分兩級：

- **結構性災難 → 硬擋 + 非零 exit + 保留舊檔**：空陣列、筆數暴跌（`MAX_SHRINK_RATIO = 0.90`）、核心欄位逾半缺失
- **格式漂移 → 軟警告放行**：未知分級、尾端空白等

硬擋 TFDA 偶發的格式變動＝false negative（整批更新被拒、使用者續看舊資料），比放行更糟。加嚴驗證前先想清楚落在哪一級。

任何失敗一律非零 exit，不再有 `sys.exit(0)` 假成功。

## 公告頁補抓（`supplement_scraper.py` / `data/supplement.json`）

**背景**：上游 opendata（dataset 34）自 `2026/06/29` 起停更，官方公告頁
`consumer.fda.gov.tw/GMP/Product.aspx?nodeID=420` 仍持續發布。看板若只吃 opendata，
會在「外觀正常」的狀態下漏掉最新回收——病安場景的假陰性。2026-08-31 起以本機
補抓填補缺口。

**為什麼在本機跑，不要再試 CI**（2026-08-31 實測）：`consumer.fda.gov.tw` 對境外 IP
在 TLS 層直接切斷（TCP 通、ClientHello 後 RST）。

| 出口 | 結果 |
|---|---|
| 台灣家用 IP | HTTP 200 |
| GitHub Actions runner（Azure 美東） | `SSLError UNEXPECTED_EOF`；換 TLS 版本／cipher／SECLEVEL／legacy renegotiation／UA 全無效 |
| Cloudflare Worker（LAX/SJC） | 520/525 SSL handshake failed；免費方案 workers.dev 不落台灣 colo，Smart Placement 需付費且不保證區域 |
| 對照 `data.fda.gov.tw`、`www.fda.gov.tw`、`www.nhi.gov.tw` | 皆正常 |

即：**不是可用參數繞過的技術不相容，是照來源封鎖**。別再花時間試 CI 直抓或加
proxy——除非哪天封鎖政策變了。

**架構決策：補抓資料只寫 `data/supplement.json`，絕不寫進 `data.json`。**
`scraper.py` 每天用 opendata 全量覆寫 `data.json`，任何併進去的補抓資料隔天就被
沖掉，且筆數差太小（1710 vs 1713），既有的 `MAX_SHRINK_RATIO`／`MAX_DELETION_RATIO`
兩道防線都不會示警——會是靜默資料流失。合併改由前端載入時做。

- 去重鍵是 **文號 + 產品**（去空白），`supplement_scraper.py` 的 `merge_key()` 與
  前端 `supplementKey()` 必須同義，**要改就兩邊一起改**，否則同一則公告會重複列出
- 前端載入時**再去重一次**不是多餘：`supplement.json` 可能產生於 opendata 補上之前
- 詳情頁欄位與 opendata schema 一對一（`日期` 對應公告頁的**發布日期**，非發文日期）；
  已用 id=1832 逐字比對過既有記錄，連 `批號` 的「，共N批藥品。」尾綴都相同
- **退場**：每次執行重算「opendata 尚未收錄的筆」，上游補上後 records 自動歸零，
  整套（`supplement_scraper.py`／`update_supplement.py`／前端 SUP 區塊／排程）可直接刪除

**失敗一律保留舊檔**：網路/TLS 錯誤、列表頁抓不到詳情連結、詳情頁解析不出核心欄位
→ 非零 exit 且不寫檔。空的 `records` 會被前端讀成「已無缺口」，與 sw.js
「離線不可回空陣列」是同一條病安理由。

**排程**：`update_supplement.py`（先 `git pull --rebase`，因為 Actions 每天會自動
commit `data.json`）。Windows 工作排程器每日呼叫，註冊指令寫在該檔 docstring。
機器沒開就會漏跑，這正是前端「補抓資料已 N 天未更新」紅色警示要抓的情境。

## Service Worker（`sw.js`）

- **cache 刪除只限 `recall-` 前綴**（`CACHE_PREFIX`）。origin 與你其他 GH Pages 專案共用，全刪會誤傷別的應用
- **離線且無快取回 503，不可回 `[]`**——空陣列會偽裝成「查無回收」，在病安場景是危險的假陰性
- 前端載入前驗 `r.ok` + `Array.isArray`
- **改 shell 或 CDN → 升 `VERSION`**（目前 `v5`）
- `data/supplement.json` 與 `data.json` 同走 `handleData`（network-first、離線無快取回 503）

## 前端

- 分級一律走純函式 `normalizeGrade()`，統一 `第二級` / `2` / `第2級` / 尾端空白等混雜格式。原始值以 `title` 保留供追溯
- `?selftest=1` 跑 `console.assert` 測例（無測試框架）。改 `normalizeGrade`、
  `supplementKey`、`mergeSupplement`、`supplementBadge` 後務必跑一次
- **SUP 測例必須放在 `const SUPPLEMENT_*` 宣告之後**：那些是 `const`，提前引用會踩
  暫時性死區拋 `ReferenceError`，並中斷整個 `<script>` 區塊，連主資料都載入不了
- 補抓狀態橫幅 fail-closed：載入失敗、檔案不存在、`generated_at` 無法解析，一律
  當作「可能有缺口」顯示紅色警示。判斷不了就示警，不可預設「應該還新」
- 所有上游欄位渲染前 HTML 跳脫
- 明確區分「最新公告日期」與「檔案部署時間」，避免過期資料被誤認為即時

## 升級 CDN 版本的完整流程

1. 從**實際檔案**重算 SRI：`openssl dgst -sha384 -binary <file> | openssl base64`（不要抄別處的 hash）
2. 更新 `index.html` 的 `integrity` + `crossorigin`
3. 升 `sw.js` 的 `VERSION`
4. 跑 `SMOKE_TEST.md` 全部項目
5. 授權異動同步 `THIRD_PARTY_NOTICES.md`

## CI

- `requests==2.32.3` 鎖版本
- GitHub Actions 固定完整 commit SHA（非 tag）——`checkout` v4.2.2、`setup-python` v5.3.0
- commit step 必須同時 `git add data/data.json data/status.json`。少加 `status.json`，heartbeat 就不進版控

## 樣式

字型 `Noto Sans TC` + `DM Mono`（此 repo 用 DM Mono，EBM calc 系列用 JetBrains Mono，不必統一）。批號常是多組長字串，欄寬比例已鎖定並用 `overflow-wrap` 強制斷行，改版面時先確認不跑版。
