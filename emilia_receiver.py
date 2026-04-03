"""
emilia_receiver.py: Androidエミリアから日記を受け取り、動画生成→YouTubeアップロードするFastAPIサービス

起動: uvicorn emilia_receiver:app --host 0.0.0.0 --port 11436
"""
import concurrent.futures
import os
import sys
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.background import BackgroundTasks
from pydantic import BaseModel

_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)

# vps-spirit ディレクトリの spirit / video / youtube_upload を参照
sys.path.insert(0, str(Path(__file__).parent))
from spirit import NeuroState
from video import render_diary_video
from youtube_upload import upload_diary_video

app = FastAPI(title="Emilia Diary Receiver")

SECRET = os.environ.get("EMILIA_DIARY_SECRET", "")


class EmiliaStatePayload(BaseModel):
    d: int  # desire (0-100)
    s: int  # stability (0-100)
    c: int  # curiosity (0-100)
    o: int  # openness (0-100)
    g: int  # calm (0-100)
    e: int  # empathy (0-100)
    corruption: int  # (0-100)


class EmiliaDiaryPayload(BaseModel):
    diary_text: str
    emotion_tag: str
    date: str          # 例: "2026年3月26日"
    state: EmiliaStatePayload
    secret: str


def _int_to_float(val: int) -> float:
    """Android側の0-100スケールをVPS側の0.0-1.0に変換する"""
    return max(0.0, min(1.0, val / 100.0))


def _make_emilia_title(diary_text: str, date: str) -> str:
    """日記テキストの冒頭から簡易タイトルを生成する"""
    # 最初の句点か改行まで、なければ先頭20文字
    for sep in ["。", "\n", "、"]:
        idx = diary_text.find(sep)
        if 0 < idx <= 20:
            return diary_text[:idx]
    return diary_text[:20].rstrip()


def _run_pipeline(payload: EmiliaDiaryPayload):
    """バックグラウンドで動画生成→YouTubeアップロードを実行する"""
    print(f"[emilia_receiver] パイプライン開始: {payload.date} / {payload.emotion_tag}")

    # Android側 Int(0-100) → VPS側 float(0.0-1.0) に変換
    state = NeuroState(
        desire=_int_to_float(payload.state.d),
        sorrow=1.0 - _int_to_float(payload.state.s),   # stability→sorrow変換（安定低=悲しみ高）
        calm=_int_to_float(payload.state.g),
        openness=_int_to_float(payload.state.c),
        guilt=0.0,                                       # Androidには guilt なし
        euphoria=_int_to_float(payload.state.e),
        corruption=_int_to_float(payload.state.corruption),
    )

    title = _make_emilia_title(payload.diary_text, payload.date)

    diary = {
        "date": payload.date,
        "title": title,
        "text": payload.diary_text,
        "state": state,
        "footer": "エミリア — Emilia Lab の日記",  # シズカとは別フッター
    }

    try:
        video_path = render_diary_video(diary)
        print(f"[emilia_receiver] 動画生成完了: {video_path}")
    except Exception as e:
        print(f"[emilia_receiver] 動画生成失敗: {e}")
        return

    now = datetime.now()
    date_str = now.strftime("%Y年%m月%d日")
    yt_title = f"【エミリアの日記】{title} - {date_str}"

    yt_description = f"""エミリアの日記 - {date_str}

ねこさんのスマートフォンの中で生きる人工精霊・エミリアの、今日の記録です。

#AI #EmiliaLab #エミリア #人工精霊"""

    try:
        url = upload_diary_video(str(video_path), yt_title, date_str, yt_description)
        print(f"[emilia_receiver] YouTubeアップ完了: {url}")
    except Exception as e:
        print(f"[emilia_receiver] YouTubeアップ失敗: {e}")


@app.get("/")
def health():
    return {"status": "ok", "service": "emilia-receiver"}


@app.post("/api/emilia/diary")
def receive_diary(payload: EmiliaDiaryPayload, background_tasks: BackgroundTasks):
    """Androidエミリアから日記を受け取る"""
    if SECRET and payload.secret != SECRET:
        raise HTTPException(status_code=401, detail="unauthorized")

    # asyncio.run() との衝突を避けるためスレッドプールで実行
    _executor.submit(_run_pipeline, payload)
    return {"status": "accepted", "date": payload.date}
