# 手動 Smoke Test 清單（離線 / 新鮮度狀態機）

> 對應 codex-review TG-05。本專案為零建置靜態站，無自動化測試框架；
> SW 與離線狀態機的關鍵情境以本清單於瀏覽器 DevTools 手動驗證。
> 每次改動 `sw.js` 或 `index.html` 的載入 / 離線 / 更新邏輯後執行。

## 前置
- Chrome DevTools → Application 分頁（Service Workers / Cache Storage）
- Network 分頁（Offline、Disable cache 開關）
- 每輪測試前如需乾淨狀態：Application → Storage → **Clear site data**

## 分級正規化（B 群組回歸）
- [ ] `?selftest=1` 開啟頁面，Console 出現「normalizeGrade 測例執行完畢」且**無** Assertion 失敗
- [ ] 導覽列四個 pill 數字加總邏輯正確（第一/二/三級為總數之子集，未確認不計入任一級）

## 資料載入與驗證（CR-11 / CR-05）
- [ ] 正常線上載入：表格出現資料，`LIVE` 標籤為藍色
- [ ] 更新時間顯示為「最新公告 YYYY/MM/DD · 檔案部署 …」兩段式
- [ ] DevTools 將 `data/data.json` 回應改成非陣列（如 `{}`）或回 500 → 頁面顯示**紅色阻斷式錯誤**、`LIVE` 變 `ERROR`，且**未**顯示「0 筆／查無資料」的成功樣態

## 離線行為（CR-06）
- [ ] 首次造訪即離線（Clear site data 後切 Offline 重載）→ 顯示阻斷式錯誤，**非**空表格假裝成功
- [ ] 已有快取後離線（先線上載入一次 → 切 Offline 重載）→ 顯示快取資料 + 紅色離線 banner，`LIVE` 變 `CACHE`
- [ ] Application → Cache Storage 僅存在 `recall-*-v4`，無殘留舊版（CR-12：切換版本後其他 origin 專案 cache 不受影響）
- [ ] DevTools Network 確認 jQuery/DataTables 以新版本載入且**無 SRI integrity 錯誤**（Console 無 "Failed to find a valid digest"）

## 上線恢復（CR-07）
- [ ] 處於離線/CACHE 狀態 → 切回 Online：若 `data.json` 可取得，頁面**自動重新載入**並回到 `LIVE`
- [ ] 模擬「有網路但 data.json 仍 503」（DevTools 覆寫回應）切 Online → **維持**離線警示、**不**誤標 `LIVE`

## 前景更新偵測（CR-08）
- [ ] 頁面開啟中，於背景更新 `data/data.json`（改筆數或最新日期）→ 切到其他分頁再切回（visibilitychange）→ 出現「看板已更新」banner
- [ ] 點「立即更新」→ 重新載入取得新資料

## SW 生命週期（CR-09 / CR-12）
- [ ] 改 `sw.js` 內容並升 `VERSION` → 重載後 Application 顯示新 SW 安裝、舊 `recall-*` cache 被清除、其他非 `recall-` cache 保留
- [ ] 離線切換時 `OFFLINE_MODE` 訊息確實送達（離線 banner 有出現，非偶發漏送）
