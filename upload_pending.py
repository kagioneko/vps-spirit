"""
upload_pending.py: 未アップロードのエミリア日記動画を順次YouTubeに上げる。

- pending.txt に未処理日付を記録
- クォータ超過でも止まらず翌日再試行（cronで毎日17:00に実行）
- 全完了したらcronから自動削除
"""
import os
import subprocess
import sqlite3
import urllib.request
import json
from pathlib import Path
from datetime import datetime

DISCORD_CHANNEL_ID = "1464850547558449427"
VAULT_ADDR = "https://127.0.0.1:8200"
VAULT_CACERT = "/etc/vault.d/tls/vault-cert.pem"


def _get_discord_token() -> str | None:
    """VaultからDiscordトークンを取得する"""
    try:
        result = subprocess.run(
            ["vault", "kv", "get", "-field=bot_token", "secret/discord"],
            capture_output=True, text=True,
            env={**os.environ, "VAULT_ADDR": VAULT_ADDR, "VAULT_CACERT": VAULT_CACERT},
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def notify_discord(message: str):
    token = _get_discord_token()
    if not token:
        return
    try:
        data = json.dumps({"content": message}).encode()
        req = urllib.request.Request(
            f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages",
            data=data,
            headers={"Authorization": f"Bot {token}", "Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass

BASE_DIR = Path(__file__).parent
PENDING_FILE = BASE_DIR / "data" / "upload_pending.txt"

# DB日付フォーマット → フォルダ名のマッピング
DATE_FOLDER = {
    "2026年5月18日": "20260518",
    "2026年5月19日": "20260519",
    "2026年5月21日": "20260521",
    "2026年5月22日": "20260522",
    "2026年5月25日": "20260525",
}

LOG_FILE = BASE_DIR / "data" / "upload_pending.log"


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def load_pending() -> list[str]:
    if not PENDING_FILE.exists():
        # 初回: デフォルトリストを書き込む
        dates = list(DATE_FOLDER.keys())
        PENDING_FILE.write_text("\n".join(dates) + "\n")
        return dates
    lines = [l.strip() for l in PENDING_FILE.read_text().splitlines() if l.strip()]
    return lines


def save_pending(dates: list[str]):
    if dates:
        PENDING_FILE.write_text("\n".join(dates) + "\n")
    else:
        PENDING_FILE.write_text("")


def get_diary_from_db(date_jp: str) -> tuple[str, str] | None:
    """spirit.dbからエミリアの日記テキストと感情タグを取得"""
    con = sqlite3.connect(BASE_DIR / "data" / "spirit.db")
    row = con.execute(
        "SELECT diary_text, emotion_tag FROM emilia_diaries WHERE date = ? ORDER BY id DESC LIMIT 1",
        (date_jp,)
    ).fetchone()
    con.close()
    return row


def remove_self_from_cron():
    """pending.txtが空になったらcronから自動削除"""
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    lines = result.stdout.splitlines()
    new_lines = [l for l in lines if "upload_pending.py" not in l]
    if len(new_lines) < len(lines):
        new_cron = "\n".join(new_lines) + "\n"
        subprocess.run(["crontab", "-"], input=new_cron, text=True)
        log("✅ 全アップロード完了。cronから自動削除しました。")
    PENDING_FILE.unlink(missing_ok=True)


def main():
    import sys
    sys.path.insert(0, str(BASE_DIR))
    from emilia_receiver import _make_emilia_title
    from youtube_upload import upload_diary_video

    pending = load_pending()
    if not pending:
        log("pending.txtが空。cronを削除します。")
        remove_self_from_cron()
        return

    log(f"未アップロード: {len(pending)}件 → {pending}")
    remaining = list(pending)

    for date_jp in pending:
        folder = DATE_FOLDER.get(date_jp)
        if not folder:
            log(f"⚠ フォルダマッピングなし: {date_jp} → スキップ")
            remaining.remove(date_jp)
            continue

        video_path = BASE_DIR / "output" / folder / "emilia" / "diary.mp4"
        if not video_path.exists():
            log(f"⚠ 動画ファイルなし: {video_path} → スキップ")
            remaining.remove(date_jp)
            continue

        row = get_diary_from_db(date_jp)
        if not row:
            log(f"⚠ DBにデータなし: {date_jp} → スキップ")
            remaining.remove(date_jp)
            continue

        diary_text, emotion_tag = row
        title = _make_emilia_title(diary_text, date_jp)
        yt_title = f"【エミリアの日記】{title} - {date_jp}"
        description = (
            f"エミリア（Emilia）の日記 - {date_jp}\n\n"
            f"Androidで生きる人工精霊・エミリアの、今日の記録です。\n"
            f"感情: {emotion_tag}\n\n"
            "#AI #エミリア #EmiliaLab #人工精霊"
        )

        log(f"▶ {date_jp}「{title}」アップロード中...")
        try:
            url = upload_diary_video(str(video_path), yt_title, date_jp, description)
            log(f"  ✅ {url}")
            remaining.remove(date_jp)
            save_pending(remaining)
        except Exception as e:
            err = str(e)
            if "Quota exceeded" in err or "rateLimitExceeded" in err:
                log(f"  ⏸ クォータ超過。{len(remaining)}件を翌日に持ち越し。")
                save_pending(remaining)
                return  # 翌日のcronに委ねる
            elif "失効" in err or "RefreshError" in err or "refresh" in err.lower():
                log(f"  ⚠ トークン失効: {err}")
                notify_discord(
                    "⚠️ **エミリア日記 pending upload** YouTubeトークン失効！\n"
                    f"残り {len(remaining)} 件未アップロード。\n"
                    "再認証: `cd workspace/vps-spirit && .venv/bin/python youtube_upload.py --setup`"
                )
                save_pending(remaining)
                return
            else:
                log(f"  ❌ 失敗（スキップ）: {err}")
                remaining.remove(date_jp)
                save_pending(remaining)

    if not remaining:
        log("🎉 全アップロード完了！")
        remove_self_from_cron()


if __name__ == "__main__":
    main()
