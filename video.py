"""
video.py: 日記から動画を生成する（matplotlib + edge-tts + FFmpeg）
"""
import asyncio
import math
import subprocess
import textwrap
from dataclasses import asdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.font_manager as fm
import numpy as np

# 日本語フォント設定
_JP_FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
fm.fontManager.addfont(_JP_FONT)
_jp_prop = fm.FontProperties(fname=_JP_FONT)
matplotlib.rcParams["font.family"] = _jp_prop.get_name()
from PIL import Image, ImageDraw, ImageFont

from spirit import NeuroState, get_state_history

OUTPUT_DIR = Path(__file__).parent / "output"
FONT_PATH = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
BG_COLOR = (10, 8, 20)          # 深い紺黒（シズカ）
TEXT_COLOR = (220, 210, 240)    # 薄紫
ACCENT_COLOR = (180, 140, 220)  # 紫

# エミリア専用カラー（暖かみのあるローズ系）
EMILIA_BG_COLOR = (20, 10, 14)      # 深い赤黒
EMILIA_TEXT_COLOR = (240, 215, 225)  # 薄ピンク白
EMILIA_ACCENT_COLOR = (220, 140, 170)  # ローズピンク


def _make_radar_chart(state: NeuroState, out_path: Path):
    """NeuroStateのレーダーチャートを生成する"""
    labels = ["欲求", "悲しみ", "静けさ", "好奇心", "罪悪感", "高揚"]
    values = [
        state.desire, state.sorrow, state.calm,
        state.openness, state.guilt, state.euphoria
    ]

    angles = [n / 6 * 2 * math.pi for n in range(6)]
    angles += angles[:1]
    values_plot = values + values[:1]

    fig, ax = plt.subplots(figsize=(5, 5), subplot_kw=dict(polar=True))
    fig.patch.set_facecolor("#0a0814")
    ax.set_facecolor("#0a0814")

    ax.plot(angles, values_plot, color="#b48cdc", linewidth=2)
    ax.fill(angles, values_plot, color="#b48cdc", alpha=0.3)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, color="#dcd2f0", fontsize=11)
    ax.set_ylim(0, 1)
    ax.set_yticks([0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["", "", "", ""], color="gray")
    ax.grid(color="#3a2a5a", linewidth=0.8)
    ax.spines["polar"].set_color("#3a2a5a")

    # corruption 表示
    if state.corruption > 0.1:
        ax.set_title(f"歪み: {state.corruption:.2f}", color="#ff6688", fontsize=9, pad=15)

    plt.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="#0a0814")
    plt.close(fig)


def _make_emotion_flow_chart(out_path: Path):
    """直前24時間の感情推移グラフを生成する"""
    from datetime import datetime as dt
    history = get_state_history(days=1)

    fig, ax = plt.subplots(figsize=(5, 2.8))
    fig.patch.set_facecolor("#0a0814")
    ax.set_facecolor("#0a0814")

    if history:
        times = [dt.fromisoformat(h["timestamp"]).strftime("%H:%M") for h in history]
        x = list(range(len(times)))

        emotion_colors = {
            "欲求":   ("#e07080", "desire"),
            "悲しみ": ("#7090e0", "sorrow"),
            "静けさ": ("#70d0b0", "calm"),
            "好奇心": ("#e0c060", "openness"),
            "高揚":   ("#c080e0", "euphoria"),
        }
        for label, (color, key) in emotion_colors.items():
            vals = [h["state"][key] for h in history]
            ax.plot(x, vals, color=color, linewidth=1.5, label=label, alpha=0.85)

        # x軸ラベル（多すぎたら間引く）
        step = max(1, len(times) // 6)
        ax.set_xticks(x[::step])
        ax.set_xticklabels(times[::step], color="#9080b0", fontsize=7)
    else:
        ax.text(0.5, 0.5, "データなし", transform=ax.transAxes,
                ha="center", va="center", color="#9080b0", fontsize=11)

    ax.set_ylim(0, 1)
    ax.set_yticks([0, 0.5, 1.0])
    ax.set_yticklabels(["0", "0.5", "1"], color="#9080b0", fontsize=7)
    ax.tick_params(colors="#9080b0")
    ax.spines[:].set_color("#3a2a5a")
    ax.grid(color="#2a1a4a", linewidth=0.5, linestyle="--")
    ax.set_title("今日の感情の流れ", color="#dcd2f0", fontsize=9, pad=6)
    ax.legend(
        loc="upper left", fontsize=6,
        facecolor="#0a0814", edgecolor="#3a2a5a", labelcolor="#dcd2f0",
        ncol=5, borderpad=0.3, handlelength=1.2,
    )

    plt.tight_layout(pad=0.5)
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="#0a0814")
    plt.close(fig)


def _make_emilia_flow_placeholder(out_path: Path):
    """エミリア用：感情推移グラフの代わりにプレースホルダー画像を生成する"""
    fig, ax = plt.subplots(figsize=(5, 2.8))
    fig.patch.set_facecolor("#0a0814")
    ax.set_facecolor("#0a0814")
    ax.text(0.5, 0.5, "エミリアの感情推移\n（Android記録）",
            transform=ax.transAxes, ha="center", va="center",
            color="#9080b0", fontsize=11, linespacing=1.8)
    ax.axis("off")
    plt.tight_layout(pad=0.5)
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="#0a0814")
    plt.close(fig)


def _make_text_frame(
    text: str, title: str, date: str,
    radar_path: Path, flow_path: Path, out_path: Path,
    footer: str = "静霞（シズカ） — VPS精霊の日記"
):
    """テキスト + レーダーチャートを合成した画像フレームを生成する"""
    is_emilia = "エミリア" in footer
    bg    = EMILIA_BG_COLOR    if is_emilia else BG_COLOR
    fg    = EMILIA_TEXT_COLOR  if is_emilia else TEXT_COLOR
    accent = EMILIA_ACCENT_COLOR if is_emilia else ACCENT_COLOR
    date_color   = (180, 145, 160) if is_emilia else (150, 140, 180)
    line_color   = (80, 50, 65)    if is_emilia else (60, 50, 90)
    footer_color = (100, 65, 80)   if is_emilia else (80, 70, 110)

    W, H = 1280, 720
    img = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(img)

    # フォント
    try:
        font_title = ImageFont.truetype(FONT_PATH, 32)
        font_date  = ImageFont.truetype(FONT_PATH, 20)
        font_body  = ImageFont.truetype(FONT_PATH, 26)
        font_small = ImageFont.truetype(FONT_PATH, 18)
    except Exception:
        font_title = font_date = font_body = font_small = ImageFont.load_default()

    # レーダーチャート貼り付け（右上）
    radar = Image.open(radar_path).convert("RGBA").resize((330, 330))
    img.paste(radar, (910, 30), radar)

    # 感情推移グラフ貼り付け（右下）
    flow = Image.open(flow_path).convert("RGBA").resize((360, 220))
    img.paste(flow, (900, 370), flow)

    # 日付
    draw.text((60, 40), date, font=font_date, fill=date_color)

    # タイトル
    draw.text((60, 80), f"「{title}」", font=font_title, fill=accent)

    # 区切り線
    draw.line([(60, 130), (860, 130)], fill=line_color, width=1)

    # 本文（折り返し）
    wrapped = textwrap.wrap(text, width=28)
    y = 155
    for line in wrapped[:14]:  # 最大14行
        draw.text((60, y), line, font=font_body, fill=fg)
        y += 38

    # フッター
    draw.text((60, H - 40), footer, font=font_small, fill=footer_color)

    img.save(out_path)


async def _generate_tts(text: str, out_path: Path):
    """edge-ttsで音声生成（日本語女性声）"""
    import edge_tts
    communicate = edge_tts.Communicate(text, voice="ja-JP-NanamiNeural")
    await communicate.save(str(out_path))


def _compose_video(image_path: Path, audio_path: Path, out_path: Path):
    """画像 + 音声をFFmpegで合成してMP4を生成する"""
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(image_path),
        "-i", str(audio_path),
        "-c:v", "libx264", "-tune", "stillimage",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        "-shortest",
        str(out_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg失敗: {result.stderr[-500:]}")


def render_diary_video(diary: dict) -> Path:
    """
    日記データから動画を生成してパスを返す

    diary: {
        "date": str, "title": str, "text": str,
        "state": NeuroState
    }
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    _m = __import__("re").match(r"(\d{4})年(\d{1,2})月(\d{1,2})日", diary["date"])
    date_slug = f"{_m.group(1)}{int(_m.group(2)):02d}{int(_m.group(3)):02d}" if _m else diary["date"].replace("年", "").replace("月", "").replace("日", "")
    character = "emilia" if diary.get("footer") and "エミリア" in diary.get("footer", "") else "shizuka"
    work_dir = OUTPUT_DIR / date_slug / character
    work_dir.mkdir(parents=True, exist_ok=True)

    state: NeuroState = diary["state"]

    # 1. レーダーチャート生成
    radar_path = work_dir / "radar.png"
    _make_radar_chart(state, radar_path)
    print(f"  [動画] レーダーチャート生成: {radar_path}")

    # 2. 感情推移グラフ生成（エミリアの場合はプレースホルダー）
    flow_path = work_dir / "flow.png"
    if diary.get("footer"):
        # エミリア（Android）からの日記：VPS DB にアクセスできないのでプレースホルダー
        _make_emilia_flow_placeholder(flow_path)
    else:
        _make_emotion_flow_chart(flow_path)
    print(f"  [動画] 感情推移グラフ生成: {flow_path}")

    # 3. テキストフレーム生成
    frame_path = work_dir / "frame.png"
    _make_text_frame(
        text=diary["text"],
        title=diary["title"],
        date=diary["date"],
        radar_path=radar_path,
        flow_path=flow_path,
        out_path=frame_path,
        footer=diary.get("footer", "静霞（シズカ） — VPS精霊の日記"),
    )
    print(f"  [動画] フレーム生成: {frame_path}")

    # 4. TTS音声生成
    audio_path = work_dir / "voice.mp3"
    asyncio.run(_generate_tts(diary["text"], audio_path))
    print(f"  [動画] 音声生成: {audio_path}")

    # 5. 動画合成
    video_path = work_dir / "diary.mp4"
    _compose_video(frame_path, audio_path, video_path)
    print(f"  [動画] 動画合成完了: {video_path}")

    return video_path
