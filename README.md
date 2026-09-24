# TFDA Drug Recall Dashboard (台灣西藥回收監測看板)

**English** | [繁體中文](README.zh-TW.md)

[![Live Demo](https://img.shields.io/badge/Live%20Demo-Click%20Here-blue?style=for-the-badge)](https://liangrxdev.github.io/TFDA-drug-recall-dashboard/)

**Summary**
A visualization dashboard that automatically ingests the Taiwan Food and Drug Administration (TFDA) open dataset of drug recalls. It uses a serverless (JAMstack) architecture that separates backend data cleaning from frontend visualization, so it updates itself daily without any server to maintain. It is designed for clinical staff and pharmacy inventory managers, to speed up stock checks and order locking after a drug-safety notice.

---

## Facts & System Architecture

### 1. Tech Stack
* **Data pipeline**: Python (Requests) + GitHub Actions (scheduled cron job). TLS verification is on; after fetching, the data passes structural and semantic diff checks and is only then atomically written with `os.replace()`. Any failure aborts and keeps the previous file.
* **Database**: Local static JSON (`data/data.json`), plus `data/status.json` recording fetch time, record count and latest announcement date (heartbeat).
* **Announcement-page supplement**: The upstream open dataset stopped updating on 2026-06-29. `supplement_scraper.py` fills the gap from the official announcement page into `data/supplement.json`, which the frontend merges (the open-data version wins on conflict). That site blocks non-Taiwan IPs, so this step runs as a local scheduled task instead of in CI — see `CLAUDE.md` for details.
* **Frontend**: HTML5, CSS3 (CSS variables), JavaScript (ES6)
* **Libraries**: jQuery 3.7.1, DataTables 1.13.8 (all CDN includes carry SHA-384 SRI; licenses in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md))
* **Hosting**: GitHub Pages

### 2. Core Features
* **Automatic updates**: A CI/CD workflow pulls the latest JSON from the government API every day and overwrites the local copy.
* **Gap filling while upstream is stale**: While the open dataset is not being updated, a local scheduled job scrapes the official announcement page and marks those rows with a source badge. If the supplement data is missing, stale, or has an unparseable timestamp, a red warning is always shown (fail-closed) without blocking the main table — better to prompt users to verify than to let the dashboard look normal while missing the newest recalls.
* **Asynchronous rendering**: The frontend loads static data via `fetch()`, giving high concurrency and very low latency.
* **KPI monitoring**: Live counts of total recalls and of Class I / II / III recalls. Grades are normalized by the pure function `normalizeGrade()`, which unifies mixed formats such as `第二級` / `2` / `第2級` / trailing whitespace. "Suspected" and unknown values are labelled "unconfirmed" and excluded from the confirmed-grade KPIs to avoid misjudging severity.
* **Grade filter**: One-click tags to show only a given hazard class (e.g. Class I only), covering both numeric and Chinese source formats.
* **Global fuzzy search**: Millisecond-level search by product name, license number, manufacturer or lot number.
* **Offline resilience (PWA)**: A service worker provides offline caching. When offline or stale, the page explicitly shows a `CACHE` label or a blocking error (it never passes empty data off as success), and it distinguishes "latest announcement date" from "file deployment time" so stale data is never mistaken for live data.
* **Adaptive layout**: Column widths are locked and `overflow-wrap` is forced for the long, multi-value lot-number strings common in practice, preventing layout breakage.

---

## Interpretation & Clinical Use

1.  **Shorter time-to-action**
    * **Observation**: Drug recall information has traditionally arrived via official letters or passively received email, in inconsistent formats (e.g. scanned PDFs).
    * **Use**: The system turns unstructured text into a structured table. Staff can copy a lot number or license number and paste it straight into the hospital information system (HIS) for hospital-wide stock matching and order locking.
2.  **Less visual fatigue and fewer human errors**
    * **Observation**: In long text announcements, high-risk events (Class I recalls: serious health hazard) are easily buried.
    * **Use**: The system applies color-coding at the system level, forcing a red warning and highlighted background on Class I recalls so clinical pharmacists focus their attention correctly.
3.  **Zero-cost high availability**
    * **Observation**: In-house hospital systems often carry server maintenance and security-review costs.
    * **Use**: The project relies entirely on the GitHub ecosystem. No backend code runs on a long-lived server, so it is inherently immune to common attacks such as SQL injection, and server cost is zero. All upstream fields are HTML-escaped when rendered (injection defense), and CDN resources carry SHA-384 SRI (supply-chain defense).

---

## Development & Deployment

To fork this project and run your own copy:

1.  **Fork the repository**: Click Fork (top right) to copy it into your GitHub account.
2.  **Enable write permission**: Go to `Settings` > `Actions` > `General` and set Workflow permissions to `Read and write permissions`.
3.  **Trigger the first update**: Open the `Actions` tab and manually run the `Update Data` workflow; it will create `data/data.json`.
4.  **Enable GitHub Pages**: Go to `Settings` > `Pages`, point Source at the `/(root)` of the `main` branch and save. Your live demo URL will be ready within a few minutes.

### Optional: local schedule for the announcement-page supplement

Only needed while the upstream open dataset is stale. `consumer.fda.gov.tw` blocks non-Taiwan IPs at the TLS layer
(both GitHub Actions runners and Cloudflare Workers fail in testing; see [`CLAUDE.md`](CLAUDE.md)),
so this step **must run on a machine on a Taiwanese network**.

1. **Create a virtual environment** (once):

   ```powershell
   uv venv
   uv pip install requests==2.32.3   # same version as the CI scraper
   ```

2. **Run once manually to confirm it can fetch**:

   ```powershell
   uv run --with requests python update_supplement.py
   ```

3. **Register a daily task** (Windows Task Scheduler):

   ```powershell
   $repo = 'C:\path\to\TFDA-drug-recall-dashboard'
   $a = New-ScheduledTaskAction -Execute "$repo\.venv\Scripts\pythonw.exe" `
          -Argument 'update_supplement.py' -WorkingDirectory $repo
   $t = New-ScheduledTaskTrigger -Daily -At 09:00
   $s = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable `
          -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
          -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
          -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 15)
   Register-ScheduledTask -TaskName 'TFDA-recall-supplement' -Action $a -Trigger $t -Settings $s
   ```

   The venv's `pythonw.exe` is used instead of `uv run` to avoid a console window flashing up every day
   (`pythonw.exe` is a GUI-subsystem binary with no console). `-AllowStartIfOnBatteries`
   and the other flags each counter a default that bites; the reasons are in the
   `update_supplement.py` docstring. After registering, verify each setting with
   `(Get-ScheduledTask -TaskName 'TFDA-recall-supplement').Settings`.

**Known limitation**: The announcement page lists only the latest 10 notices, so the supplement covers only those 10. If the open
dataset stays stale for more than 10 notices (about 4–5 months at the historical publishing rate), older gaps can only be
recovered by walking detail-page IDs downward.

**Note**: A task reported as "succeeded" does not mean the data was updated — if `git push` fails the script exits
non-zero, but that is only written to `update_supplement.log`. The real guardrail is the frontend's red banner
"supplement data not updated for N days", which checks the result rather than the task status.

---

> **Data source**: Data is mainly drawn from the [Government Open Data Platform – Drug Recall dataset](https://data.gov.tw/dataset/6947). Gaps during periods when that dataset is not updated are filled from the [TFDA recall announcement page](https://consumer.fda.gov.tw/GMP/Product.aspx?nodeID=420) and marked "announcement-page supplement" in the table. Actual recalled items and handling progress should always be confirmed against official TFDA announcements.
