# 覆核裁決（Verdict）

- 審查範圍：整個 repository
- Commit：`45c84846a58adefa8b0e7782a9b21630ab5d6a8f`
- 覆核日期：2026-07-22
- 覆核方式：每一項均實際回讀對應檔案行號驗證；分級分佈與 git churn 以本機 `data/data.json`（1,708 筆）與 `git show --stat` 實測確認。
- 整體結論：Codex 報告品質高，行號準確，**未發現幻覺**；且明確避免捏造 CVE（正確排除不適用的 CVE-2020-28458 / 11022 / 11023）。共 25 項：**接受 21 / 部分接受 4 / 拒絕 0**。

## 1. Code review

| # | 項目 | 嚴重度 | 判定 | 理由 |
|---|------|--------|------|------|
| CR-01 | scraper 停用 TLS 驗證 | Critical | **接受** | `scraper.py:14` `verify=False` 屬實，`:8` 抑制警告。此為「污染資料入口」最高權重風險，威脅模型下 Critical 正確。修法（提供 CA bundle 給 `verify=`）與零建置架構相容。 |
| CR-02 | 抓取失敗回傳成功狀態 | High | **接受** | `scraper.py:27,30` 兩處 `sys.exit(0)`；`main.yml:24` `git commit ... || exit 0`。失敗會被 CI 當成功，舊資料續用。與 memory「非 200 勿靜默 return」同一類。 |
| CR-03 | 未驗證即覆寫正式 JSON | High | **接受** | `scraper.py:17-21` 直接 `json.dump` 覆寫，無任何 schema/筆數/型別檢查。`[]`、`null`、錯誤頁 JSON 皆會成為正式資料。與 CR-01/TG-01 同源，建議合併處理。 |
| CR-04 | 分級統計與顏色錯置 | High | **接受** | 實測確認：`index.html:373` `grade.includes('一') ? class1++ : class2++`。1,708 筆中 `includes('一')` 僅命中 **4 筆**（第一級×3＋疑似第一級×1），其餘 **1,704 筆全灌入第二級**——含數字 `'1'`×53、`None`×153、第三級等。臨床分級誤判，High 正確。`normalizeGrade` 純函式修法相容架構。 |
| CR-05 | Last-Modified 誤標為資料時間 | High→**Medium** | **部分接受** | 問題屬實：`index.html:357-361` 以 GitHub Pages `Last-Modified`（部署時間）當「資料更新時間」；實測 `45c8484` 為 11,482 insert／11,482 delete 但語意集合不變（純重排），確會造成假新鮮度。修法（排序穩定鍵＋分開標示「部署時間」與「最新公告日期」＋`status.json`）正確採納。**惟嚴重度建議降 Medium**：每日 auto-commit 下部署時間與抓取時間大致同步，誤導幅度有限，核心價值在「Last-Modified≠最新公告日期」的語意澄清。 |
| CR-06 | 無快取時偽造空資料集 | High | **接受** | `sw.js:57-60` catch 中回傳 `[]` 且 HTTP 200，未呼叫 `notifyClients('OFFLINE_MODE')`（對比 `:53` 有快取時有呼叫）。前端會顯示總數 0＋`LIVE`，被誤解為「無回收資料」。威脅模型下 High 成立。 |
| CR-07 | online 清警告但不重抓 | High→**Medium** | **部分接受** | 屬實：`index.html:547-556` `online` 事件直接隱藏 offlineBanner 並把 `CACHE→LIVE`，未重新 fetch/驗證，畫面仍舊快取。修法（online/visibilitychange 重抓成功後才改狀態）正確。**嚴重度建議 Medium**：需先進入離線快取狀態才觸發，屬既有離線流程的收尾瑕疵，非獨立高危入口。 |
| CR-08 | SW 更新通知不因資料 commit 觸發 | Medium | **接受** | 屬實：`index.html:517-524` 依賴 `updatefound`，只在 `sw.js` 內容變更時觸發；每日僅改 `data/data.json` 不會安裝新 SW，`:518` 註解「每日資料更新後部署觸發」不成立。修法（前景輪詢/比對 status.json）相容架構。 |
| CR-09 | SW 快取寫入/通知未 await | Medium | **接受** | 屬實：`sw.js:29-31` `notifyClients` 未回傳 Promise；`:75`、`:90` `caches.open(...).then(put)` 未 await 即 return response。`respondWith` 結束後 worker 可被終止導致寫入/通知遺失。修法正確。 |
| CR-10 | 上游資料直進 innerHTML | High | **接受** | 屬實：`index.html:406-417` 產品/藥廠/字號/批號/原因/分級皆未 escape 拼入樣板字串後 `:417` `innerHTML=rows`。此為 CR-01 入口被污染後的「渲染面」放大器（可偽造 LIVE、竄改分級/批號），符合誤導臨床決策威脅模型。`textContent`/escape 修法相容架構。**註**：優先級低於 CR-01 入口封堵。 |
| CR-11 | 前端未檢查 HTTP 狀態/結構 | Medium | **接受** | 屬實：`index.html:354-365` 未檢查 `r.ok`／Content-Type／`Array.isArray` 即先寫 updateTime 再 `r.json()`。修法正確且輕量。 |
| CR-12 | SW 刪除同 origin 其他 app cache | Medium | **接受** | 屬實：`sw.js:20-24` activate 刪除所有不在 `ALL_CACHES` 的 cache；Cache Storage 為 origin-wide。實測同 origin `liangrxdev.github.io` 另有 TFDA-drug-info-search（含自有 sw.js）、pharmacy-portal、dx/tx-ebm-calc，會被誤刪離線資源。修法（限定 `recall-` prefix）正確。 |

## 2. Test gap analysis

| # | 項目 | 嚴重度 | 判定 | 理由 |
|---|------|--------|------|------|
| TG-01 | 無資料 schema/欄位驗證 | Critical | **接受** | 與 CR-03 同源，`scraper.py:17-21` 確無任何驗證。內嵌純函式 validator＋assert 的修法明確相容「無建置工具」前提。建議與 CR-03/CR-01 合併為第一優先。 |
| TG-02 | 無前後版本語意差異防線 | High | **接受** | `main.yml:17-24` 確無 diff/門檻檢查；筆數暴跌、日期倒退、分級消失皆無防護。scraper 讀舊檔比對的修法相容架構。 |
| TG-03 | 無分級正規化案例 | High | **接受** | 現有正式資料已證實 CR-04 邏輯失效（實測 1,704 筆錯分）。`?selftest=1`＋`console.assert` 的零框架修法可行。 |
| TG-04 | 無新鮮度/排程失敗監控 | High | **接受** | `main.yml:3-5` 僅 cron＋dispatch，無 heartbeat/連續失敗計數；「無 commit」無法區分「無新公告」與「pipeline 死亡」。status metadata＋stale threshold 修法相容。 |
| TG-05 | SW 狀態無驗證矩陣 | High→**Medium** | **部分接受** | 列舉的離線/503/重抓失敗/cache abort 情境確實無防護，屬實。**惟嚴重度建議 Medium**：這是「缺人工 smoke-test checklist」的測試缺口，非可獨立觸發的執行期高危；修法本身即為手動 checklist，與 CR-06/07/09 修好後一併驗證即可。 |
| TG-06 | 無前端邊界值驗證 | Medium | **接受** | 空資料/null/超長批號/HTML 特殊字元/未知分級等均無測例。以 console 呼叫純函式跑內嵌 fixture 的修法相容架構。 |
| TG-07 | CDN 載入失敗無降級驗證 | Medium | **接受** | 屬實：`index.html:420` 直接用 `$('#recallTable').DataTable(...)`，若 CDN 失敗則 `$`/DataTable 不存在，僅落入 `:507-510` 泛化「data.json 路徑錯誤」，誤導定位。初始化前檢查 `window.jQuery`/`$.fn.DataTable` 修法正確。 |

## 3. Dependency audit

| # | 項目 | 嚴重度 | 判定 | 理由 |
|---|------|--------|------|------|
| DA-01 | CDN 資源全無 SRI | High | **接受** | 實測 `grep integrity` 無任何結果；`index.html:17-18,348-350` jQuery/DataTables/Responsive 皆無 `integrity`/`crossorigin`。CDN 供應鏈污染可執行任意 JS 並被 SW cache-first 長期保存，屬供應鏈入口風險。SHA-384 SRI＋遞增 `recall-cdn-vN` 修法相容架構。 |
| DA-02 | jQuery 3.7.0→3.7.1 | Low | **接受** | 誠實標註「未發現直接適用 CVE」，未捏造漏洞。屬維護性小項，Low 正確。 |
| DA-03 | DataTables 1.13.6/Responsive 2.5.0 過舊 | Medium→**Low（安全面）** | **部分接受** | 版本落後屬實，且 Codex 正確排除 CVE-2020-28458（不影響 1.13.6）、未確認到直接適用之 CVE。**故從純安全視角嚴重度應為 Low**（無已知可利用漏洞）；Medium 較適用於「維護性/未來修正覆蓋」考量。不導入 npm、直接換 CDN URL＋SRI 的修法相容架構。 |
| DA-04 | requests 未鎖版 | Medium | **接受** | 屬實：`main.yml:16` `pip install requests` 無版本約束，可重現性弱。指定 `requests==x.y.z` 的修法相容架構。嚴重度 Medium 偏保守可接受。 |
| DA-05 | Actions 舊 major 未固定 SHA | Medium | **接受** | 屬實：`main.yml:10-13` `actions/checkout@v3`、`actions/setup-python@v4`；major tag 可移動，供應鏈不可完全重現。固定 commit SHA 修法相容架構。 |
| DA-06 | 第三方授權未集中保存 | Low | **接受** | 屬實，repo 無 THIRD_PARTY_NOTICES。屬合規衛生小項，Low 正確；若日後改本地託管更重要。 |

## 覆核註記

- **無幻覺 / 無架構誤解**：所有引用之檔案、行號、API 均存在且正確；Codex 明確尊重「單檔零建置」前提，所有修法皆標明「不需 npm/bundler/測試框架」的替代作法。
- **主要重疊群組**（建議合併修復，避免重工）：
  - 資料入口強固 = CR-01 ＋ CR-03 ＋ TG-01 ＋ TG-02（scraper 一次改：恢復 TLS、schema/語意驗證、原子覆寫、非零 exit）。
  - 離線/新鮮度狀態機 = CR-05 ＋ CR-06 ＋ CR-07 ＋ CR-08 ＋ CR-11 ＋ TG-05。
  - 分級正規化 = CR-04 ＋ TG-03。
