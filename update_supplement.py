"""補抓排程包裝：同步遠端 → 抓取 → 有變動才 commit/push → 全程留 log。

為什麼是本機排程而非 GitHub Actions：`consumer.fda.gov.tw` 對境外 IP 在 TLS 層
封鎖，Actions runner 與 Cloudflare Worker 皆抓不到（實測紀錄見 supplement_scraper.py
開頭）。只有台灣網路環境取得到，因此只能在這台機器跑。

行為：
  1. 先 `git pull --rebase`——GitHub Actions 每天凌晨會自動 commit data.json，
     不先同步必定 push 失敗。
  2. 跑 supplement_scraper.py；非零 exit 一律中止且不 commit，保留舊的
     supplement.json（勿以空檔覆寫——空 records 會被前端讀成「已無缺口」）。
  3. supplement.json 有變動才 commit + push。
  4. 全程寫入 update_supplement.log，排程沒跑或跑掛了可事後追。

手動執行（會顯示輸出）：
    uv run --with requests python update_supplement.py

**排程一律用 venv 的 `pythonw.exe`**，不要用 `uv run`：後者是主控台程式，工作
排程器在互動登入下執行會每天閃一個黑視窗約 16 秒。`pythonw.exe` 屬 GUI 子系統，
不配主控台。建立 venv（只需一次）：
    uv venv
    uv pip install requests==2.32.3      # 版本與 CI 的 scraper 一致

註冊每日排程（PowerShell 開一次即可，路徑依實際 repo 位置調整）：
    $repo = 'C:\\Users\\liang\\projects\\TFDA-drug-recall-dashboard'
    $a = New-ScheduledTaskAction -Execute "$repo\\.venv\\Scripts\\pythonw.exe" `
           -Argument 'update_supplement.py' -WorkingDirectory $repo
    $t = New-ScheduledTaskTrigger -Daily -At 09:00
    $s = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable `
           -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
           -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
           -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 15)
    Register-ScheduledTask -TaskName 'TFDA-recall-supplement' -Action $a -Trigger $t -Settings $s

每個參數都是修掉一個實際會咬人的預設值，別省：
- `-StartWhenAvailable`：關機錯過的排程在下次開機補跑。這台不是全天開，少了它
  會靜默漏跑——而漏跑正是前端「補抓資料已 N 天未更新」紅色警示要抓的情況。
- `-AllowStartIfOnBatteries -DontStopIfGoingOnBatteries`：**預設是筆電沒插電就
  整天不跑、跑到一半拔電源就中斷**。這是最容易漏看的一個。
- `-ExecutionTimeLimit 10 分鐘`：預設 72 小時，16 秒的工作卡住不該拖三天。

註冊後務必核對，別信預設：
    (Get-ScheduledTask -TaskName 'TFDA-recall-supplement').Settings

注意排程「執行成功」不等於「資料有更新」——git push 失敗時本檔 exit 1，但那只
寫進 log。真正的護欄是前端那個「已 N 天未更新」的紅色橫幅，它看的是結果。
"""
import os
import subprocess
import sys
from datetime import datetime

REPO = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(REPO, "update_supplement.log")
SUPPLEMENT_REL = "data/supplement.json"


def log(msg):
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line)
    # 首次建檔寫 BOM：Windows PowerShell 5.1 的 Get-Content 預設以 ANSI 讀取，
    # 無 BOM 的 UTF-8 中文會顯示成亂碼（檔案本身無損，但排查時很礙事）。
    encoding = "utf-8" if os.path.exists(LOG_PATH) else "utf-8-sig"
    with open(LOG_PATH, "a", encoding=encoding) as f:
        f.write(line + "\n")


# 排程以 pythonw.exe 執行（無主控台）以免每日閃窗。但 git 是主控台程式，
# 由無主控台的父行程啟動時，Windows 會**替每個子行程另開一個主控台視窗**——
# 等於閃窗沒消掉還變成好幾個。CREATE_NO_WINDOW 才是真正壓住閃窗的那一半。
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def run(cmd, **kwargs):
    """執行外部指令，回傳 CompletedProcess（不自動拋例外，由呼叫端判斷）。"""
    return subprocess.run(cmd, cwd=REPO, capture_output=True, text=True,
                          encoding="utf-8", errors="replace",
                          creationflags=_NO_WINDOW, **kwargs)


def main():
    log("=== 補抓作業開始 ===")

    # ── 1. 先同步遠端 ────────────────────────────────────────────────
    r = run(["git", "pull", "--rebase"])
    if r.returncode != 0:
        log("FATAL: git pull --rebase 失敗，可能有未提交變更或衝突；中止。")
        log(f"  {r.stderr.strip()}")
        return 1

    # ── 2. 抓取（非零 exit = 驗證未過，保留舊檔）─────────────────────
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = run([sys.executable, "supplement_scraper.py"], env=env)
    for line in (r.stdout + r.stderr).splitlines():
        if line.strip():
            log(f"  {line}")
    if r.returncode != 0:
        log(f"FATAL: supplement_scraper.py exit {r.returncode}，"
            f"未 commit，保留舊 supplement.json。")
        return r.returncode

    # ── 3. 有變動才 commit ───────────────────────────────────────────
    r = run(["git", "status", "--porcelain", "--", SUPPLEMENT_REL])
    if not r.stdout.strip():
        log("無變動，不 commit。")
        log("=== 補抓作業結束 ===")
        return 0

    if run(["git", "add", SUPPLEMENT_REL]).returncode != 0:
        log("FATAL: git add 失敗")
        return 1
    r = run(["git", "commit", "-m", "chore(data): 更新公告頁補抓資料"])
    if r.returncode != 0:
        log(f"FATAL: git commit 失敗：{r.stderr.strip()}")
        return 1
    r = run(["git", "push"])
    if r.returncode != 0:
        log("FATAL: git push 失敗（先查 gh auth status）；"
            "commit 已在本機，下次會一併推出。")
        log(f"  {r.stderr.strip()}")
        return 1

    log("已 commit 並 push。")
    log("=== 補抓作業結束 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
