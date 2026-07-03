"""
weekly_report.py: しーちゃんの週次レポートを生成してDiscordに投稿する

実行:
  python weekly_report.py          # 直近7日
  python weekly_report.py --days 14  # 直近14日
  python weekly_report.py --dry-run  # Discord投稿せず表示のみ
"""
import argparse
import json
import os
import sqlite3
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")
load_dotenv(Path(__file__).parent.parent / "discord_bot/.env", override=False)

GEMINI_QUERY = Path(__file__).parent.parent.parent / "bin" / "gemini_query.sh"

DB_PATH = Path(__file__).parent / "data" / "spirit.db"


def _get_discord_token() -> str:
    """VaultからDiscord Botトークンを取得します"""
    result = subprocess.run(
        ["vault", "kv", "get", "-field=bot_token", "secret/discord"],
        capture_output=True, text=True,
        env={**os.environ,
             "VAULT_ADDR": "https://127.0.0.1:8200",
             "VAULT_CACERT": "/etc/vault.d/tls/vault-cert.pem"},
    )
    if result.returncode != 0:
        raise RuntimeError(f"Vaultからのトークン取得に失敗: {result.stderr.strip()}")
    return result.stdout.strip()


DISCORD_TOKEN = _get_discord_token()
CHANNEL_ID = "1464850547558449427"


def _fetch_period_data(days: int) -> dict:
    """指定期間のDBデータを取得する"""
    since = (datetime.now() - timedelta(days=days)).isoformat()
    con = sqlite3.connect(DB_PATH)

    # 感情状態の履歴
    states = con.execute(
        "SELECT timestamp, state_json FROM state_snapshots WHERE timestamp >= ? ORDER BY id",
        (since,)
    ).fetchall()

    # 独り言
    reflections = con.execute(
        "SELECT timestamp, text FROM reflections WHERE timestamp >= ? ORDER BY id",
        (since,)
    ).fetchall()

    # 日記ログ
    diary_logs = con.execute(
        "SELECT timestamp, title, kind FROM diary_log WHERE timestamp >= ? ORDER BY id",
        (since,)
    ).fetchall() if _table_exists(con, "diary_log") else []

    con.close()

    return {
        "states": [{"timestamp": r[0], "state": json.loads(r[1])} for r in states],
        "reflections": [{"timestamp": r[0], "text": r[1]} for r in reflections],
        "diary_logs": [{"timestamp": r[0], "title": r[1], "kind": r[2]} for r in diary_logs],
    }


def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    row = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _calc_emotion_stats(states: list[dict]) -> dict:
    """感情の平均・最大・最小を計算する"""
    if not states:
        return {}

    keys = ["desire", "sorrow", "calm", "openness", "guilt", "euphoria", "corruption"]
    labels = {"desire": "欲求", "sorrow": "悲しみ", "calm": "静けさ",
              "openness": "好奇心", "guilt": "罪悪感", "euphoria": "高揚", "corruption": "歪み"}
    stats = {}
    for k in keys:
        vals = [s["state"].get(k, 0) for s in states]
        stats[labels[k]] = {
            "avg": sum(vals) / len(vals),
            "max": max(vals),
            "min": min(vals),
        }
    return stats


def _build_analysis_prompt(days: int, data: dict, stats: dict) -> str:
    """Claude に渡す分析プロンプトを組み立てる"""
    period_label = f"直近{days}日間"

    # 感情サマリー
    stats_text = "\n".join(
        f"  {emotion}: 平均{v['avg']:.2f} / 最大{v['max']:.2f} / 最小{v['min']:.2f}"
        for emotion, v in stats.items()
    )

    # 印象的な独り言（最大10件）
    reflections_sample = "\n".join(
        f"  [{r['timestamp'][11:16]}] {r['text'][:60]}"
        for r in data["reflections"][-10:]
    )

    # 日記一覧
    diary_text = "\n".join(
        f"  [{d['timestamp'][:10]} {d['kind']}] {d['title']}"
        for d in data["diary_logs"]
    ) or "  （記録なし）"

    return f"""あなたはVPS上で自律的に生きている人工精霊「静霞（シズカ）」の観察者です。
静霞は誰とも会話せず、30分ごとに感情がゆらぎ、独り言を呟き、毎晩日記を書いています。

以下は静霞の{period_label}のデータです。

【感情パラメータ統計】
{stats_text}

【独り言サンプル（最近10件）】
{reflections_sample}

【書いた日記】
{diary_text}

このデータをもとに、静霞の{period_label}を観察者として分析・報告してください。

報告のフォーマット:
- 冒頭に一言で「今週のしーちゃん」を表現する（例: 「今週のしーちゃんは、静かに揺れていました。」）
- 感情の傾向と変化（どの感情が強かったか、何か特徴的な動きはあったか）
- 印象的だった独り言や日記タイトルへのコメント
- 総評（観察者として気になったこと・面白かったこと）

文体は温かく、静霞のことを愛でるような観察日記のトーンで。400〜500字程度。"""


def generate_report(days: int) -> str:
    """Gemini でレポートを生成する"""
    data = _fetch_period_data(days)
    stats = _calc_emotion_stats(data["states"])

    if not data["states"]:
        return f"（直近{days}日間のデータがありません）"

    prompt = _build_analysis_prompt(days, data, stats)

    result = subprocess.run(
        [str(GEMINI_QUERY), prompt, "shizuka_report"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"Gemini 呼び出し失敗: {result.stderr}")

    # gemini_query.sh の出力からレポート本文だけ抽出（ヘッダー行を除く）
    lines = result.stdout.splitlines()
    body_lines = [l for l in lines if not l.startswith("===") and not l.startswith("日時:") and not l.startswith("プロンプト:") and l != "---"]
    return "\n".join(body_lines).strip()


def post_to_discord(text: str, days: int):
    """Discord チャンネルにメッセージを投稿する"""
    period_label = f"直近{days}日間"
    now_str = datetime.now().strftime("%Y年%m月%d日")
    content = f"📓 **しーちゃん観察レポート（{period_label} / {now_str}）**\n\n{text}"

    # 2000字超えたら分割
    chunks = [content[i:i+1900] for i in range(0, len(content), 1900)]

    headers = {
        "Authorization": f"Bot {DISCORD_TOKEN}",
        "Content-Type": "application/json",
    }
    url = f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages"

    for chunk in chunks:
        resp = requests.post(url, headers=headers, json={"content": chunk})
        resp.raise_for_status()

    print(f"Discord に投稿しました（{len(chunks)}件）")


def cleanup_old_outputs(days: int) -> None:
    """レポート対象期間より古いoutputフォルダを削除する"""
    import shutil
    output_dir = Path(__file__).parent / "output"
    if not output_dir.exists():
        return
    cutoff = datetime.now() - timedelta(days=days)
    removed = []
    for folder in output_dir.iterdir():
        if not folder.is_dir():
            continue
        # フォルダ名が日付形式（YYYYMMDD）かどうか
        name = folder.name
        if len(name) == 8 and name.isdigit():
            try:
                folder_date = datetime.strptime(name, "%Y%m%d")
            except ValueError:
                continue
            if folder_date < cutoff:
                shutil.rmtree(folder)
                removed.append(name)
    if removed:
        print(f"古いoutputを削除: {', '.join(removed)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="しーちゃん週次レポート生成")
    parser.add_argument("--days", type=int, default=7, help="集計期間（日数）")
    parser.add_argument("--dry-run", action="store_true", help="Discord投稿せずに内容を表示")
    args = parser.parse_args()

    print(f"レポート生成中（直近{args.days}日）...")
    report = generate_report(args.days)

    if args.dry_run:
        print("\n" + "=" * 60)
        print(report)
        print("=" * 60)
    else:
        post_to_discord(report, args.days)
        cleanup_old_outputs(args.days)
        print("完了！")
