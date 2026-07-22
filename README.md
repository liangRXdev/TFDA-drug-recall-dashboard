# 台灣西藥回收監測看板 (TFDA Drug Recall Dashboard)

[![Live Demo](https://img.shields.io/badge/Live%20Demo-Click%20Here-blue?style=for-the-badge)](https://liangrxdev.github.io/TFDA-drug-recall-dashboard/)

**【結論】**
本專案為自動化介接「衛福部食藥署 (TFDA) 西藥回收公開資料集」之視覺化儀表板。採用 Serverless (JAMstack) 架構，將後端資料清洗與前端視覺化分離，無需維護實體伺服器即可實現每日自動更新。專為臨床醫療人員與庫房管理員設計，以提升藥物安全事件通報後的盤點與鎖檔效率。

---

## 【客觀數據與系統架構】

### 1. 技術堆疊 (Tech Stack)
* **資料管線 (Data Pipeline)**: Python (Requests) + GitHub Actions (Cron Job 定時觸發)；啟用 TLS 驗證、抓取後做結構／語意差異驗證，通過才以 `os.replace()` 原子覆寫，失敗即中斷並保留舊檔
* **資料庫 (Database)**: 本地靜態 JSON (`data/data.json`)，另產生 `data/status.json` 記錄抓取時間、筆數、最新公告日期（heartbeat）
* **網頁前端 (Frontend)**: HTML5, CSS3 (CSS Variables), JavaScript (ES6)
* **前端套件 (Libraries)**: jQuery 3.7.1, DataTables 1.13.8（CDN 引用皆附 SHA-384 SRI；授權見 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)）
* **雲端託管 (Hosting)**: GitHub Pages

### 2. 核心功能規格
* **自動化更新**: 透過 CI/CD 流程，每日自動向政府 API 拉取最新 JSON 資料並執行覆寫。
* **非同步渲染**: 前端透過 `fetch()` 拉取靜態資料，具備高併發承載力與極低延遲。
* **關鍵指標監控 (KPI)**: 即時計算「總回收件數」與第一／二／三級件數。分級以純函式 `normalizeGrade()` 正規化，統一 `第二級`/`2`/`第2級`/尾端空白等混雜格式；「疑似」與未知值標為「未確認」並排除於確定分級 KPI，避免嚴重度誤判。
* **分級過濾器 (Grade Filter)**: 提供一鍵快速篩選特定危害等級（如：僅顯示第一級回收）的動態標籤，涵蓋數字與中文兩種原始格式。
* **全局模糊搜尋 (Fuzzy Search)**: 支援以「產品名稱」、「許可證字號」、「藥廠名稱」或「批號」進行毫秒級即時檢索。
* **離線韌性 (PWA)**: Service Worker 提供離線快取；離線／過期時明確標示 `CACHE`／阻斷式錯誤（不以空資料偽裝成功），並區分「最新公告日期」與「檔案部署時間」，杜絕過期資料被誤認為即時。
* **自適應版面配置**: 針對醫療實務中常見的「多組長字串批號」進行欄寬比例鎖定與強制斷行 (`overflow-wrap`) 優化，防止跑版。

---

## 【推論觀點與臨床應用】

1.  **縮短決策時間 (Time-to-Action)**
    * **觀點**：傳統的藥品回收資訊多依賴公文或被動接收電子郵件，資訊呈現格式不一（如 PDF 掃描檔）。
    * **應用**：本系統將非結構化的文本轉換為結構化表格，管理人員可直接複製「批號」或「許可證字號」，無縫貼上至醫院資訊系統 (HIS) 進行全院庫存比對與醫令鎖檔。
2.  **降低視覺疲勞與人為疏漏**
    * **觀點**：在龐雜的文字公告中，高風險事件（第一級回收：具重大健康危害）容易被淹沒。
    * **應用**：系統層級導入色彩管理計畫 (Color-coding)，對第一級回收強制標註紅色警示與背景高亮，確保臨床藥師在查閱時的專注力正確分配。
3.  **零成本的高可用性 (Zero-cost High Availability)**
    * **觀點**：院內自行開發系統常面臨伺服器維護與資安審核成本。
    * **應用**：本專案完全依賴 GitHub 生態系，無後端程式碼在伺服器長期運行，天然免疫 SQL Injection 等常見攻擊，且伺服器成本為零。前端渲染對所有上游欄位一律 HTML 跳脫（防注入），CDN 資源附 SHA-384 SRI（防供應鏈污染）。

---

## 【開發與部署步驟】

若欲 Fork 此專案並建立個人版本，請依循以下步驟：

1.  **Fork 儲存庫**: 點擊右上角 Fork 至個人 GitHub 帳號。
2.  **開啟寫入權限**: 進入 `Settings` > `Actions` > `General`，將 Workflow permissions 設為 `Read and write permissions`。
3.  **觸發首次更新**: 進入 `Actions` 頁籤，手動觸發 `Update Data` 工作流，系統將會建立 `data/data.json` 檔案。
4.  **啟用 GitHub Pages**: 進入 `Settings` > `Pages`，將 Source 指向 `main` 分支的 `/(root)` 並儲存。數分鐘後即可取得專屬的 Live Demo 網址。

> **資料來源聲明**：本看板資料皆即時介接自 [政府資料開放平臺 - 藥品回收資料集](https://data.gov.tw/dataset/6947)，實際回收品項與處置進度應以衛福部食藥署官方公告為準。
