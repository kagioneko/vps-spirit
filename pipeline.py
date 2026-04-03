"""
pipeline.py: 精霊の日次パイプライン統括

用途:
  python pipeline.py reflect   # 30分ごとの独り言（cronで実行）
  python pipeline.py diary     # 日次日記生成 + 動画作成（cronで実行）
"""
import sqlite3
import sys
from datetime import datetime, timedelta

from diary import generate_daily_diary, generate_reflection
from spirit import (
    DB_PATH, init_db, load_state, save_memory, save_reflection, save_state
)
from video import render_diary_video
from youtube_upload import upload_diary_video

# 臨時日記の閾値・連投防止インターバル
EMERGENCY_INTENSITY_THRESHOLD = 0.8
EMERGENCY_COOLDOWN_HOURS = 2


def _last_diary_time() -> datetime | None:
    """直近の日記生成時刻をDBから取得する"""
    con = sqlite3.connect(DB_PATH)
    row = con.execute(
        "SELECT timestamp FROM diary_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    con.close()
    if row:
        try:
            return datetime.fromisoformat(row[0])
        except Exception:
            return None
    return None


def _save_diary_log(title: str, kind: str):
    """日記生成ログを保存する（連投防止用）"""
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS diary_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            title TEXT NOT NULL,
            kind TEXT NOT NULL
        )
    """)
    con.execute(
        "INSERT INTO diary_log (timestamp, title, kind) VALUES (?, ?, ?)",
        (datetime.now().isoformat(), title, kind)
    )
    con.commit()
    con.close()


def cmd_reflect():
    """30分ごとの独り言を生成・保存する"""
    print(f"[{datetime.now().strftime('%H:%M')}] 内省中...")

    init_db()
    state = load_state()
    state.drift()
    save_state(state)

    text = generate_reflection(state)
    save_reflection(text, state)

    print(f"  状態: {state.to_prompt_str()}")
    print(f"  独り言: {text}")

    # 強い感情の瞬間は記憶として保存
    intensity = (state.desire + state.euphoria + state.sorrow) / 3
    if intensity > 0.65:
        save_memory(text, importance=intensity)
        print(f"  → 記憶に保存（重要度: {intensity:.2f}）")

    # 感情が閾値を超えたら臨時日記を発動
    if intensity > EMERGENCY_INTENSITY_THRESHOLD:
        last_diary = _last_diary_time()
        if last_diary and (datetime.now() - last_diary) < timedelta(hours=EMERGENCY_COOLDOWN_HOURS):
            print(f"  → 感情急騰（{intensity:.2f}）だが直近{EMERGENCY_COOLDOWN_HOURS}時間以内に日記あり。スキップ")
        else:
            print(f"  → 感情急騰（{intensity:.2f}）！臨時日記を生成します")
            cmd_diary(kind="臨時")


def cmd_diary(kind: str = "日次"):
    """日記を生成して動画を作成する（kind: 日次 or 臨時）"""
    print(f"[{datetime.now().strftime('%H:%M')}] 日記生成パイプライン開始（{kind}）")

    init_db()
    state = load_state()

    # 日記生成
    print("  [1/3] 日記生成中...")
    diary = generate_daily_diary(state)
    print(f"  タイトル: {diary['title']}")
    print(f"  本文（先頭）: {diary['text'][:80]}...")

    # 動画生成
    print("  [2/3] 動画生成中...")
    video_path = render_diary_video(diary)

    # YouTube アップロード（限定公開）
    print("  [3/3] YouTubeアップロード中...")
    now = datetime.now()
    date_str = now.strftime("%Y年%m月%d日")
    if kind == "臨時":
        title = f"【静霞の日記・臨時】{diary['title']} - {date_str} {now.strftime('%H:%M')}"
    else:
        title = f"【静霞の日記】{diary['title']} - {date_str}"
    try:
        url = upload_diary_video(str(video_path), title, date_str)
        _save_diary_log(title, kind)
        print(f"\n完了！動画: {video_path}")
        print(f"YouTube: {url}")
    except Exception as e:
        print(f"  [警告] アップロード失敗: {e}")
        print(f"\n完了！動画: {video_path}（YouTubeアップは手動で）")
    return video_path


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "reflect"
    if cmd == "reflect":
        cmd_reflect()
    elif cmd == "diary":
        cmd_diary()
    else:
        print(f"不明なコマンド: {cmd}")
        print("使い方: python pipeline.py [reflect|diary]")
        sys.exit(1)
