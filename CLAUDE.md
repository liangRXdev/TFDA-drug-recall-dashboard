# TFDA-drug-recall-dashboard — 專案規則

台灣西藥回收監測看板。零建置靜態站（GitHub Pages）+ Python scraper + GitHub Actions 每日排程。

**這個 repo 的多數設計是「刻意不做某件事」**，2026-07-22 經完整審查後定案（稽核紀錄在本機未追蹤的 `.ai-review/`）。下面每條都寫了理由——看起來像疏漏的地方，先讀理由再動。

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

## Service Worker（`sw.js`）

- **cache 刪除只限 `recall-` 前綴**（`CACHE_PREFIX`）。origin 與你其他 GH Pages 專案共用，全刪會誤傷別的應用
- **離線且無快取回 503，不可回 `[]`**——空陣列會偽裝成「查無回收」，在病安場景是危險的假陰性
- 前端載入前驗 `r.ok` + `Array.isArray`
- **改 shell 或 CDN → 升 `VERSION`**（目前 `v4`）

## 前端

- 分級一律走純函式 `normalizeGrade()`，統一 `第二級` / `2` / `第2級` / 尾端空白等混雜格式。原始值以 `title` 保留供追溯
- `?selftest=1` 跑 `console.assert` 測例（無測試框架）。改 `normalizeGrade` 後務必跑一次
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
