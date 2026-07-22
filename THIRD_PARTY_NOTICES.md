# 第三方元件與授權（Third-Party Notices）

> 對應 codex-review DA-06。本專案透過 CDN 引用下列第三方元件（未重新散布原始碼）。
> 若日後改為本地託管以支援離線，請一併保留各元件之授權與版權聲明。

| 元件 | 版本 | 來源 | 授權 | 版權 |
|------|------|------|------|------|
| jQuery | 3.7.1 | https://code.jquery.com/jquery-3.7.1.min.js | MIT | © OpenJS Foundation and jQuery contributors |
| DataTables | 1.13.8 | https://cdn.datatables.net/1.13.8/ | MIT | © SpryMedia Ltd (Allan Jardine) |
| DataTables Responsive | 2.5.0 | https://cdn.datatables.net/responsive/2.5.0/ | MIT | © SpryMedia Ltd (Allan Jardine) |
| Noto Sans TC（字型） | Google Fonts | https://fonts.googleapis.com/ | SIL Open Font License 1.1 | © Google LLC / Adobe |
| DM Mono（字型） | Google Fonts | https://fonts.googleapis.com/ | SIL Open Font License 1.1 | © Colophon Foundry / Google Fonts |

## 完整性
- 所有固定版本的 script／stylesheet CDN 引用皆附 SHA-384 Subresource Integrity（SRI）與 `crossorigin="anonymous"`（見 `index.html`）。
- Google Fonts 之 CSS 回應會依 User-Agent 動態變動，故刻意不加 SRI（加了會 hash 不符而被瀏覽器阻擋）。

## 資料來源
- 藥品回收資料：政府資料開放平臺「藥品回收資料集」(dataset 6947)，來源 `https://data.fda.gov.tw/`。
  實際回收品項與處置進度應以衛福部食藥署官方公告為準。
