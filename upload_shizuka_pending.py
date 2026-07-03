"""
upload_shizuka_pending.py: しーちゃん未アップ動画をまとめてYouTubeに上げる。

- pending_shizuka.txt に未処理日付（YYYYMMDD）を記録
- クォータ超過で止まっても翌日再試行（cronで毎日16:30に実行）
- 全完了したらcronから自動削除 + .skip_upload フラグも削除
"""
import re
import sqlite3
import subprocess
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent
PENDING_FILE = BASE_DIR / "data" / "pending_shizuka.txt"
LOG_FILE = BASE_DIR / "data" / "upload_shizuka_pending.log"
SKIP_FLAG = BASE_DIR / "data" / ".skip_upload"
DIARY_LOG = BASE_DIR / "data" / "diary.log"


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def load_pending() -> list[str]:
    if not PENDING_FILE.exists():
        return []
    return [l.strip() for l in PENDING_FILE.read_text().splitlines() if l.strip()]


def save_pending(dates: list[str]):
    PENDING_FILE.write_text("\n".join(dates) + "\n" if dates else "")


def get_title_from_log(date_folder: str) -> str | None:
    """diary.logからタイトルを取得（YYYYMMDD形式）"""
    try:
        content = DIARY_LOG.read_text()
        # output/YYYYMMDD/shizuka/diary.mp4 の後のタイトルを探す
        # re.DOTALL の影響でファイル末尾までマッチするのを防ぐため [^\n]+ を使用
        pattern = rf"output/{date_folder}/shizuka/diary\.mp4.*?タイトル: ([^\n]+)"
        m = re.search(pattern, content, re.DOTALL)
        if m:
            return m.group(1).strip()
    except Exception:
        pass
    return None


def remove_self_from_cron():
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    lines = result.stdout.splitlines()
    new_lines = [l for l in lines if "upload_shizuka_pending.py" not in l]
    if len(new_lines) < len(lines):
        new_cron = "\n".join(new_lines) + "\n"
        subprocess.run(["crontab", "-"], input=new_cron, text=True)
        log("✅ 全完了。cronから自動削除しました。")
    PENDING_FILE.unlink(missing_ok=True)
    # .skip_uploadフラグも削除（通常のアップロード再開）
    SKIP_FLAG.unlink(missing_ok=True)
    log("✅ .skip_upload フラグを削除。しーちゃんの通常アップロードを再開します。")


def main():
    import sys
    sys.path.insert(0, str(BASE_DIR))
    from youtube_upload import upload_diary_video

    pending = load_pending()
    if not pending:
        log("未処理なし。終了します。")
        remove_self_from_cron()
        return

    log(f"未アップロード: {len(pending)}件 → {pending}")
    remaining = list(pending)

    for date_folder in pending:
        video_path = BASE_DIR / "output" / date_folder / "shizuka" / "diary.mp4"
        if not video_path.exists():
            log(f"⚠ 動画なし: {video_path} → スキップ")
            remaining.remove(date_folder)
            continue

        raw_title = get_title_from_log(date_folder)
        if not raw_title:
            raw_title = "日記"
        date_jp = f"{date_folder[:4]}年{date_folder[4:6]}月{date_folder[6:8]}日"
        yt_title = f"【静霞の日記】{raw_title} - {date_jp}"

        log(f"▶ {date_jp}「{raw_title}」アップロード中...")
        try:
            url = upload_diary_video(str(video_path), yt_title, date_jp)
            # diary_logに記録
            con = sqlite3.connect(BASE_DIR / "data" / "spirit.db")
            con.execute(
                "INSERT INTO diary_log (timestamp, title, kind) VALUES (?, ?, ?)",
                (datetime.now().isoformat(), yt_title, "日次")
            )
            con.commit()
            con.close()
            log(f"  ✅ {url}")
            remaining.remove(date_folder)
            save_pending(remaining)
        except Exception as e:
            err = str(e)
            if "Quota exceeded" in err or "rateLimitExceeded" in err:
                log(f"  ⏸ クォータ超過。{len(remaining)}件を翌日に持ち越し。")
                save_pending(remaining)
                return
            else:
                log(f"  ❌ 失敗（スキップ）: {err}")
                remaining.remove(date_folder)
                save_pending(remaining)

    if not remaining:
        log("🎉 全アップロード完了！")
        remove_self_from_cron()


if __name__ == "__main__":
    main()
