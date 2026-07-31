<!--
審查日期：2026-07-22
Codex 版本：mcp__codex__codex（codex MCP，v0.144.5 last verified）
審查範圍：整個 repository
Commit hash：45c84846a58adefa8b0e7782a9b21630ab5d6a8f
Thread ID：019f8727-9ed8-7eb0-8d72-124f8636d021
說明：以下為 Codex 原始輸出，未經修飾或刪改，供稽核。
-->

# 獨立覆審報告

覆審基準：本機 checkout `45c8484`；另以唯讀方式確認遠端已有 `44e8692`（2026-07-06），新增 2026/06/10、2026/06/29 公告。以下程式碼行號以本機檔案為準。未修改任何檔案。

## 1. Code review

### CR-01 — 資料入口完全停用 TLS 驗證

- **檔案:行號**：scraper.py:7、第 7–14 行
- **嚴重度**：Critical
- **問題描述**：`verify=False` 並關閉 `InsecureRequestWarning`，使 GitHub Actions 無法驗證回應確實來自 TFDA。中間人、被污染的 proxy/DNS 或錯誤端點可注入任意回收分級、批號與許可證字號，再由 CI 正式 commit。依本專案威脅模型，這是直接污染臨床決策資料入口。
- **建議修法**：恢復預設 TLS 驗證，移除 `verify=False` 與警告抑制。若 TFDA 憑證鏈確有相容問題，將核准 CA bundle 以 repository 檔案或 GitHub Secret 提供給 `verify=CA_BUNDLE_PATH`；不可改成全面跳過驗證。這不需要 npm、bundler 或測試框架。

### CR-02 — 抓取失敗卻回傳成功狀態

- **檔案:行號**：scraper.py:25、第 25–30 行；main.yml:17、第 17–24 行
- **嚴重度**：High
- **問題描述**：HTTP/TLS/JSON 解析失敗都執行 `sys.exit(0)`。Workflow 因此顯示成功，既不告警，也無法區分「今日沒有新公告」與「資料源已失效」。舊資料會繼續被看板當成正常資料。
- **建議修法**：錯誤輸出到 stderr 並使用非零 exit code；Workflow 讓 step 明確失敗。另可使用 GitHub Actions 原生 failure notification／issue，不需引入任何建置工具。

### CR-03 — 未驗證資料即直接覆寫正式 JSON

- **檔案:行號**：scraper.py:17、第 17–21 行
- **嚴重度**：High
- **問題描述**：任何可解析 JSON，包括 `[]`、`null`、object、缺欄位資料或欄位型別錯誤，都會覆寫 `data/data.json`。上游錯誤頁若剛好是 JSON，也可能成為正式資料。
- **建議修法**：在同一支 Python 檔內加入純函式驗證：

  - 根節點必須是非空 array。
  - 每筆必須是 object，且具備必要欄位。
  - 日期符合有效 `YYYY/MM/DD`。
  - 關鍵欄位必須是 string 或明確允許的 null。
  - 筆數不可相較前版異常暴跌。
  - 最新公告日期不可無理由倒退。
  - 未知分級值應阻擋 commit 並告警。

  通過後先寫同目錄暫存檔，再用 `os.replace()` 原子取代正式檔。

### CR-04 — 分級統計與顏色嚴重錯置

- **檔案:行號**：index.html:367、第 367–373、400–408、438–457 行
- **嚴重度**：High
- **問題描述**：程式只用 `grade.includes('一')` 判定第一級，其他所有值都算第二級。實際本機 1,708 筆資料至少包含：

  - `1`：53 筆
  - `第一級`：3 筆
  - `疑似第一級`：1 筆
  - `2`：687 筆，另有 `2 ` 21 筆
  - `第二級`：571 筆，另有尾端空白 201 筆
  - `3`／`3 `：11 筆
  - 空值：153 筆

  現況會顯示第一級僅 4 筆，其餘 1,704 筆全部灌入第二級；數字 `1` 會被標成黃色第二級。分級篩選同樣漏掉數字格式。
- **建議修法**：在內嵌 JS 建立單一 `normalizeGrade(raw)` 純函式，先 `trim()`，再用明確 mapping 將 `1/一/第一級`、`2/二/第2級/第二級`、`3/三/第三級` 正規化。未知、空白及「疑似」不可默認第二級，應顯示「未確認」並排除於確定分級 KPI。原始值仍保留供追溯。

### CR-05 — `Last-Modified` 被誤標為資料更新時間

- **檔案:行號**：index.html:353、第 353–361 行；scraper.py:20、第 20–21 行
- **嚴重度**：High
- **問題描述**：GitHub Pages 的 `Last-Modified` 只能代表 JSON 檔案部署／修改時間，不能證明 TFDA 最新公告日期或當日抓取成功。上游陣列順序不穩定又未先排序；例如本機 `45c8484` 一次產生 11,482 additions 與 11,482 deletions，但與前版比較 1,708 筆語意集合完全相同。純重排也會讓介面顯示「剛更新」，造成資料新鮮度假象。
- **建議修法**：scraper 依穩定鍵排序後再輸出；前端將 `Last-Modified` 明確標為「檔案部署時間」，並另外顯示資料內 `日期` 最大值為「最新公告日期」。可另產生小型 `data/status.json`，記錄成功抓取時間、筆數、最新公告日期與來源 URL；這仍是零建置靜態檔架構。

### CR-06 — 無網路且無資料快取時，偽造成功的空資料集

- **檔案:行號**：sw.js:50、第 50–60 行；index.html:365、第 365–395 行
- **嚴重度**：High
- **問題描述**：網路失敗且沒有 cached JSON 時，SW 回傳 HTTP 200 的 `[]`，且不送出 `OFFLINE_MODE`。前端會正常顯示總數 0、`LIVE` 與「系統最新排程」，可能被理解為「目前沒有回收資料」。
- **建議修法**：不可用 `[]` 代表基礎設施錯誤。回傳 503 JSON error，或讓請求 reject，由前端顯示阻斷式錯誤、隱藏 KPI 並取消 `LIVE`。只有確實存在快取時才能顯示資料，且必須伴隨快取時間。

### CR-07 — 網路恢復即清除警告，但沒有重新取得資料

- **檔案:行號**：index.html:543、第 543–555 行
- **嚴重度**：High
- **問題描述**：`online` event 只代表瀏覽器偵測到網路，不代表 `data.json` 已成功更新。程式立即隱藏離線警告並把 `CACHE` 改回 `LIVE`，畫面仍是舊快取內容。
- **建議修法**：`online` 時重新 fetch 並完整驗證資料；僅成功後更新 DataTable、資料時間與狀態。失敗時保留警告。長時間開啟的 PWA 也應定時或在 `visibilitychange` 時重新檢查，而非依賴 SW 更新事件。

### CR-08 — SW 更新通知不會因每日資料 commit 觸發

- **檔案:行號**：index.html:513、第 513–524 行
- **嚴重度**：Medium
- **問題描述**：`updatefound` 只在 `sw.js` 本身內容變更時觸發；單獨更新 `data/data.json` 不會安裝新 SW。因此註解所稱「每日資料更新後部署觸發」不成立，已開啟的看板不會收到新公告通知。
- **建議修法**：不要把 SW lifecycle 當資料更新訊號。以前景定時 fetch、頁面重新可見時 fetch，或比較 `status.json` 的版本／時間；均可用原生 JS 完成。

### CR-09 — 關鍵快取寫入與通知未納入 SW 生命週期

- **檔案:行號**：sw.js:28、第 28–31、47–54、73–76、87–94 行
- **嚴重度**：Medium
- **問題描述**：`cache.put()` 與 `notifyClients()` 的 Promise 多處未 `await`／return。`respondWith()` 完成後 worker 可被終止，造成新資料沒有寫入、舊快取持續存在，或離線警告未送達。
- **建議修法**：讓 `notifyClients` 回傳 Promise；資料路徑以 `await cache.put(...)`、`await notifyClients(...)` 完成後才 return response。CDN 與 static cache 同樣處理。

### CR-10 — 上游資料直接進入 `innerHTML`

- **檔案:行號**：index.html:397、第 397–417 行
- **嚴重度**：High
- **問題描述**：產品、藥廠、許可證、批號、原因與分級均未 escape，直接拼接到 `innerHTML`。本案雖無 cookie／憑證，但若 TFDA、傳輸路徑或 CI 資料被污染，任意 script 可隱藏警告、偽造 `LIVE`、改寫分級及批號，仍直接符合「誤導臨床決策」威脅模型。
- **建議修法**：使用 `createElement()` 與 `textContent` 建立 cell；或先建立一致的 HTML escape 函式並套用所有資料欄位。不要只仰賴 CSP，因目前單檔含大量 inline CSS/JS，嚴格 CSP 不易直接導入。

### CR-11 — 前端未先檢查 HTTP 狀態與資料結構

- **檔案:行號**：index.html:354、第 354–365 行
- **嚴重度**：Medium
- **問題描述**：沒有檢查 `r.ok`、Content-Type、根節點是否 array，就先顯示更新時間並呼叫 `r.json()`。有效 JSON 錯誤物件可能使後續失敗，而畫面曾短暫標示為已更新。
- **建議修法**：先檢查 `r.ok`、JSON content type 與 `Array.isArray(data)`，完成最小 schema 驗證後才更新時間、KPI 與 `LIVE`。

### CR-12 — SW 會刪除同網域其他應用的 cache

- **檔案:行號**：sw.js:18、第 18–24 行
- **嚴重度**：Medium
- **問題描述**：Cache Storage 是 origin-wide；activate 時刪除所有不在 `ALL_CACHES` 的 cache。GitHub Pages 同帳號下其他專案共享 `liangrxdev.github.io` origin，可能被本 SW 清掉離線資源。
- **建議修法**：只刪除名稱具有本專案 prefix，例如 `recall-`，且不在目前版本清單中的 cache。

---

## 2. Test gap analysis

### TG-01 — 完全沒有資料 schema 與關鍵欄位驗證

- **檔案:行號**：scraper.py:17、第 17–21 行
- **嚴重度**：Critical
- **問題描述**：目前沒有機制攔截空 array、非 array、缺欄、日期錯誤、型別變更、未知分級或 HTML/JSON 錯誤內容。
- **建議修法**：在 scraper 內嵌純函式 validator，於 workflow 正式寫入前執行。以數個 hard-coded sample 配合 `assert` 即可，不需 pytest。

### TG-02 — 沒有前後版本語意差異防線

- **檔案:行號**：main.yml:17、第 17–24 行
- **嚴重度**：High
- **問題描述**：CI 不檢查筆數暴跌、最新日期倒退、第一／二級大量消失、重複資料暴增或大量舊資料被刪除。
- **建議修法**：scraper 讀取既有 `data.json`，比較筆數、穩定識別鍵集合、最大日期與分級分布；超過保守門檻就 exit non-zero 並保留舊檔。輸出摘要供人工覆核。

### TG-03 — 沒有分級正規化案例

- **檔案:行號**：index.html:370、第 370–380、433–458 行
- **嚴重度**：High
- **問題描述**：`1`、`第一級`、尾端空白、null、`疑似第一級`、未知值等案例從未被驗證，現有正式資料已證實邏輯失敗。
- **建議修法**：把正規化寫成純函式；在 `?selftest=1` 模式執行內嵌 `console.assert` 測例，或由 scraper 同時驗證 mapping domain。無需新增測試框架。

### TG-04 — 沒有資料新鮮度／排程失敗監控

- **檔案:行號**：main.yml:3、第 3–5、17–25 行
- **嚴重度**：High
- **問題描述**：沒有 heartbeat、成功抓取時間、連續失敗計數或 stale threshold。沒有 commit 可能代表「沒有新公告」，也可能是 cron 停止、API 失敗或 workflow 權限問題。
- **建議修法**：每次成功抓取產生 status metadata；CI 檢查距離上次成功時間。連續超過 24–48 小時未成功時讓 workflow 失敗並通知，不以「是否有新 commit」判斷健康度。

### TG-05 — SW 關鍵狀態沒有驗證矩陣

- **檔案:行號**：sw.js:41、第 41–60 行；index.html:527、第 527–555 行
- **嚴重度**：High
- **問題描述**：至少以下情境沒有防護：首次造訪離線、已有舊快取離線、上線但 API 503、網路恢復後重新抓取失敗、cache put 被中止、cached JSON 格式錯誤。
- **建議修法**：建立一份人工 smoke-test checklist，使用瀏覽器 DevTools 的 Offline、Clear site data 與 Disable cache 操作逐項驗證；SW cache 版本號仍採既有手動管理。

### TG-06 — 沒有前端資料邊界值驗證

- **檔案:行號**：index.html:397、第 397–431、449–455 行
- **嚴重度**：Medium
- **問題描述**：未驗證空資料、null 欄位、超長批號、特殊 HTML 字元、非標準日期、重複公告、未知分級與數千筆資料時的結果。
- **建議修法**：用瀏覽器 console 呼叫純渲染／正規化函式處理內嵌 fixture，至少覆蓋上述案例；不需拆模組或導入 Jest。

### TG-07 — CDN／jQuery 載入失敗沒有明確降級驗證

- **檔案:行號**：index.html:348、第 348–350、419–431 行
- **嚴重度**：Medium
- **問題描述**：若 CDN 首次載入失敗、快取損壞或版本不相容，`$`／DataTables 不存在，介面只落入泛化的「data.json 路徑錯誤」訊息，誤導故障定位。
- **建議修法**：初始化前檢查 `window.jQuery`、`$.fn.DataTable` 與 Responsive plugin；顯示「前端依賴載入失敗」而非資料錯誤。將 CDN blocking 納入人工 smoke test。

---

## 3. Dependency audit

### DA-01 — 所有 CDN script／stylesheet 均無 SRI

- **檔案:行號**：index.html:17、第 17–18、348–350 行
- **嚴重度**：High
- **問題描述**：jQuery、DataTables 與 Responsive 都沒有 `integrity`、`crossorigin`。CDN 或其供應鏈若被污染，可執行任意 JS、修改所有回收資料及新鮮度警示；SW cache-first 還可能長期保存污染版本。
- **建議修法**：對固定版本 URL 加入官方公布的 SHA-384 SRI 與 `crossorigin="anonymous"`。每次升版同步更新 hash，並手動遞增 `recall-cdn-vN`；完全相容於零建置架構。

### DA-02 — jQuery 3.7.0 已被 3.7.1 取代

- **檔案:行號**：index.html:348
- **嚴重度**：Low
- **問題描述**：3.7.0 並非 3.x 最新修正版。已知的 jQuery CVE-2019-11358、CVE-2020-11022、CVE-2020-11023 均不涵蓋 3.7.0，因此未發現直接適用的已知 CVE；但仍缺少後續 bug fixes。
- **建議修法**：先升至相容性高的 3.7.1，更新 SRI 並遞增 SW CDN cache 版本，再做搜尋、篩選、Responsive 與離線 smoke test。升 jQuery 4.x 屬 major migration，不建議在未驗證 DataTables 1.x 相容性前直接切換。

### DA-03 — DataTables 1.13.6／Responsive 2.5.0 已屬舊世代

- **檔案:行號**：index.html:17、第 17–18、349–350 行
- **嚴重度**：Medium
- **問題描述**：DataTables 已進入 2.x、Responsive 已進入 3.x；現有版本明顯落後。已知 CVE-2020-28458 影響的是較早於 1.10.23 的 DataTables，故不直接影響 1.13.6；本次未確認到直接適用於 1.13.6/Responsive 2.5.0 的公開 CVE。但舊分支未來安全修正覆蓋較弱。
- **建議修法**：不要為升版導入 npm。先更新至最後相容的 1.13.x／2.5.x patch；若升 2.x／3.x，直接替換 CDN URL、SRI 與 SW cache 版本，並人工驗證現有初始化 API、排序、filter hook、pagination 與 Responsive。

### DA-04 — `requests` 未鎖版，CI 每次安裝不同依賴集合

- **檔案:行號**：main.yml:15、第 15–16 行
- **嚴重度**：Medium
- **問題描述**：`pip install requests` 無版本限制；`requests` 及其間接依賴可在沒有 repository 變更的情況下漂移，降低可重現性。
- **建議修法**：Workflow 直接指定經驗證版本，例如 `requests==x.y.z`，並定期人工升版；不必新增 package.json 或 Python package 專案。更嚴格時可同時鎖定主要間接依賴與 hash。

### DA-05 — GitHub Actions 使用舊 major 且未固定 commit SHA

- **檔案:行號**：main.yml:10、第 10–14 行
- **嚴重度**：Medium
- **問題描述**：`actions/checkout@v3`、`actions/setup-python@v4` 均已被後續 major 取代；major tag 也可移動，供應鏈不可完全重現。
- **建議修法**：升至仍受支援的 major，最好固定到經確認的完整 commit SHA，旁註對應版本 tag；這不改變零建置架構。

### DA-06 — 第三方授權資訊未集中保存

- **檔案:行號**：README.md:12、第 12–17 行
- **嚴重度**：Low
- **問題描述**：jQuery 與 DataTables 採 MIT；Google Fonts 字型通常採 SIL Open Font License。README 只列版本，repository 未見第三方 license notice。CDN 引用未必等同重新散布全部原始碼，但保留授權與來源紀錄較穩健，若日後為離線改成本地託管則更重要。
- **建議修法**：在 README 或 `THIRD_PARTY_NOTICES` 列出名稱、版本、來源 URL、license 與 copyright；不需引入任何依賴管理工具。

## 優先處理順序

1. 恢復 TLS 驗證，讓抓取失敗確實使 workflow 失敗。
2. 加入 schema／語意差異驗證，驗證後才原子覆寫。
3. 修正分級正規化與未知值呈現。
4. 修正 SW 的空資料 fallback、CACHE→LIVE 狀態與資料年齡顯示。
5. 移除資料欄位的 `innerHTML` 注入面。
6. 補 SRI、更新相容 patch 版本並遞增 SW cache 版本。
