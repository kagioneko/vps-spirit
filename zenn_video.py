"""
zenn_video.py: Zenn記事からYouTube解説動画を生成する

使い方:
  python zenn_video.py /path/to/article.md
  python zenn_video.py /path/to/article.md --no-upload
"""
import asyncio
import re
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# WriterNeuroState（blog_pipeline共有）
import importlib.util as _ilu
_ws_path = Path(__file__).parent.parent / "blog_pipeline" / "writer_state.py"
if _ws_path.exists():
    _spec = _ilu.spec_from_file_location("writer_state", _ws_path)
    _ws_mod = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_ws_mod)
    _load_writer_state  = _ws_mod.load_state
    _save_writer_state  = _ws_mod.save_state
    _writer_state_log   = _ws_mod.get_current_state_summary
    _HAS_WRITER_STATE = True
else:
    _HAS_WRITER_STATE = False

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from PIL import Image, ImageDraw, ImageFont

OUTPUT_DIR = Path(__file__).parent / "output" / "zenn_videos"
FONT_PATH  = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
NEKO_CLOSED = Path(__file__).parent / "assets" / "neko1.png"  # 口閉じ
NEKO_OPEN   = Path(__file__).parent / "assets" / "neko2.png"  # 口開き
NEKO_SIZE   = (320, 240)

# デザインカラー（Zenn記事用：ダークブルー系）
BG_COLOR     = (8, 12, 28)
TEXT_COLOR   = (210, 220, 240)
ACCENT_COLOR = (100, 160, 255)
SUB_COLOR    = (140, 160, 200)
LINE_COLOR   = (40, 55, 90)
TABLE_HEADER_BG = (30, 45, 80)
TABLE_ROW_BG    = (18, 25, 50)
TABLE_ALT_BG    = (22, 32, 62)


# ---------------------------------------------------------------------------
# 記事パーサー
# ---------------------------------------------------------------------------

@dataclass
class Section:
    heading: str        # セクション見出し（空文字 = タイトルスライド）
    body: str           # 本文テキスト
    table: list[list[str]] | None  # 表データ（あれば）
    is_title: bool = False


def _parse_table(lines: list[str]) -> list[list[str]] | None:
    """Markdownの表を2次元リストに変換する"""
    rows = []
    for line in lines:
        if re.match(r"\|[-: |]+\|", line):
            continue  # 区切り行スキップ
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells:
            rows.append(cells)
    return rows if len(rows) >= 2 else None


def parse_article(md_path: Path) -> tuple[str, list[Section]]:
    """Zenn記事MDをパースしてタイトルとセクションリストを返す"""
    text = md_path.read_text(encoding="utf-8")

    # frontmatter からタイトル取得
    title = md_path.stem
    fm_match = re.search(r"^---\n(.*?)\n---", text, re.DOTALL)
    if fm_match:
        t_match = re.search(r'^title:\s*"?(.+?)"?\s*$', fm_match.group(1), re.MULTILINE)
        if t_match:
            title = t_match.group(1)
        text = text[fm_match.end():]

    # ## 見出しでセクション分割
    raw_sections = re.split(r"\n(?=## )", text)
    sections: list[Section] = []

    # タイトルスライド
    sections.append(Section(heading="", body=title, table=None, is_title=True))

    for raw in raw_sections:
        raw = raw.strip()
        if not raw:
            continue
        lines = raw.split("\n")
        heading = ""
        if lines[0].startswith("## "):
            heading = lines[0][3:].strip()
            lines = lines[1:]

        # 表を抽出
        table_lines = [l for l in lines if re.match(r"\s*\|", l)]
        table = _parse_table(table_lines) if table_lines else None

        # 本文（コードブロック・表行・空行除去して連結）
        body_lines = []
        in_code = False
        for line in lines:
            if line.startswith("```"):
                in_code = not in_code
                continue
            if in_code:
                continue
            if re.match(r"\s*\|", line):
                continue
            clean = re.sub(r"\*\*(.+?)\*\*", r"\1", line)  # bold除去
            clean = re.sub(r"`(.+?)`", r"\1", clean)         # inline code除去
            clean = clean.strip()
            if clean and not clean.startswith("*") and clean != "---":
                body_lines.append(clean)

        body = "\n".join(body_lines[:8])  # 最大8行

        if heading or body or table:
            sections.append(Section(heading=heading, body=body, table=table))

    return title, sections


# ---------------------------------------------------------------------------
# ナレーション生成（Claude CLI）
# ---------------------------------------------------------------------------

def generate_narration(article_title: str, section: Section) -> str:
    """Claudeに解説ナレーション文を生成させる（WriterNeuroState適用）"""
    if section.is_title:
        return f"今回は「{article_title}」についてご紹介します。"

    table_hint = ""
    if section.table:
        headers = section.table[0] if section.table else []
        table_hint = f"\n表のヘッダー: {', '.join(headers)}"

    # WriterNeuroStateを先頭に挿入（FINAL_MANUSCRIPT知見: generation-start位置が最も効果的）
    writer_instruction = ""
    if _HAS_WRITER_STATE:
        state = _load_writer_state()
        state.topic_drift(section.heading + article_title)
        state.drift()
        _save_writer_state(state, topic=section.heading)
        writer_instruction = state.to_writing_instruction() + "\n\n"

    prompt = (
        f"{writer_instruction}"
        f"以下はZenn技術記事「{article_title}」の「{section.heading}」セクションです。\n"
        f"YouTube動画の音声ナレーションとして、視聴者にわかりやすく100〜150字で解説してください。\n"
        f"ですます調、自然な話し言葉で。見出しや箇条書きは使わず、一続きの文章で。\n"
        f"アルファベットの略語・英単語は必ずカタカナ読みに変換すること（例: README→リードミー、CPOS→シーポス、Claude→クロード、API→エーピーアイ、LLM→エルエルエム、GitHub→ギットハブ、Python→パイソン）。\n"
        f"バージョン番号は「バージョン」と読む（例: v0.1.0→バージョン0.1.0）。\n"
        f"字数・文字数・以上などのメタ情報は一切出力しないこと。ナレーション本文のみ出力すること。\n"
        f"\n記事内容:\n{section.body}{table_hint}"
    )

    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "text"],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0 and result.stdout.strip():
            text = result.stdout.strip()
            # 字数メタ情報を除去
            import re as _re
            text = _re.sub(r'[（(]?以上[、,]?\s*約?\d+字[）)]?[。.]?$', '', text).strip()
            text = _re.sub(r'[（(]\d+字[）)][。.]?$', '', text).strip()
            # TTS読み間違い防止の後処理置換
            _TTS_REPLACE = [
                (r'\bREADME\b', 'リードミー'),
                (r'\bCPOS\b', 'シーポス'),
                (r'\bAPI\b', 'エーピーアイ'),
                (r'\bLLM\b', 'エルエルエム'),
                (r'\bOSS\b', 'オーエスエス'),
                (r'\bCLI\b', 'シーエルアイ'),
                (r'\bVPS\b', 'ブイピーエス'),
                (r'\bAI\b', 'エーアイ'),
                (r'\bPR\b', 'プルリクエスト'),
                (r'\bv(\d+\.\d+[\.\d]*)\b', r'バージョン\1'),
                (r'\bNeuroState\b', 'ニューロステート'),
                (r'\bWatchdog\b', 'ウォッチドッグ'),
                (r'\bAblation\b', 'アブレーション'),
                (r'\bClaude\b', 'クロード'),
                (r'\bZenodo\b', 'ゼノード'),
                (r'\bCodex\b', 'コーデックス'),
                (r'\bJailbreak\b', 'ジェイルブレイク'),
                (r'\bPlayground\b', 'プレイグラウンド'),
                (r'\bRuntime\b', 'ランタイム'),
                (r'\bSandbox\b', 'サンドボックス'),
                (r'\bAnthrop[oi]c\b', 'アンソロピック'),
                (r'\bOpenAI\b', 'オープンエーアイ'),
                (r'\bVertex\b', 'バーテックス'),
                (r'\bDocker\b', 'ドッカー'),
                (r'\bLinux\b', 'リナックス'),
                (r'\bDiscord\b', 'ディスコード'),
                (r'\bNotion\b', 'ノーション'),
                (r'\bWordPress\b', 'ワードプレス'),
                (r'\bGemini\b', 'ジェミニ'),
                (r'\bFable\b', 'フェーブル'),
                (r'\bOpus\b', 'オーパス'),
                (r'\bSonnet\b', 'ソネット'),
                (r'\bGitHub\b', 'ギットハブ'),
                (r'\bPython\b', 'パイソン'),
            ]
            for pattern, repl in _TTS_REPLACE:
                text = _re.sub(pattern, repl, text, flags=_re.IGNORECASE)
            return text
    except Exception:
        pass
    # フォールバック：元本文をそのまま使う
    return f"{section.heading}についてです。{section.body[:100]}"


# ---------------------------------------------------------------------------
# スライド画像生成
# ---------------------------------------------------------------------------

def _load_fonts():
    try:
        return {
            "title":   ImageFont.truetype(FONT_PATH, 48),
            "heading": ImageFont.truetype(FONT_PATH, 36),
            "body":    ImageFont.truetype(FONT_PATH, 24),
            "small":   ImageFont.truetype(FONT_PATH, 18),
            "table_h": ImageFont.truetype(FONT_PATH, 20),
            "table_b": ImageFont.truetype(FONT_PATH, 18),
        }
    except Exception:
        d = ImageFont.load_default()
        return {k: d for k in ["title", "heading", "body", "small", "table_h", "table_b"]}


def _draw_table(draw: ImageDraw.Draw, table: list[list[str]],
                x: int, y: int, fonts: dict, max_width: int) -> int:
    """表を描画してy座標の終端を返す"""
    if not table:
        return y

    col_count = max(len(row) for row in table)
    col_w = min(200, (max_width - x) // max(col_count, 1))
    row_h = 34

    for ri, row in enumerate(table):
        bg = TABLE_HEADER_BG if ri == 0 else (TABLE_ALT_BG if ri % 2 == 0 else TABLE_ROW_BG)
        draw.rectangle([x, y, x + col_w * col_count, y + row_h], fill=bg)
        for ci, cell in enumerate(row):
            cx = x + ci * col_w + 6
            color = ACCENT_COLOR if ri == 0 else TEXT_COLOR
            font = fonts["table_h"] if ri == 0 else fonts["table_b"]
            draw.text((cx, y + 7), cell[:18], font=font, fill=color)
        y += row_h

    return y + 10


def make_slide(section: Section, slide_num: int, total: int,
               article_title: str, out_path: Path):
    """1スライド分の画像を生成する"""
    W, H = 1280, 720
    img = Image.new("RGB", (W, H), BG_COLOR)
    draw = ImageDraw.Draw(img)
    fonts = _load_fonts()

    # 上部装飾ライン
    draw.rectangle([0, 0, W, 6], fill=ACCENT_COLOR)

    if section.is_title:
        # タイトルスライド（長いタイトルは折り返し）
        title_lines = textwrap.wrap(article_title, width=22)
        line_h = 58
        total_h = len(title_lines) * line_h
        y_start = H // 2 - total_h // 2 - 30
        for li, line in enumerate(title_lines):
            draw.text((W // 2, y_start + li * line_h), line,
                      font=fonts["title"], fill=TEXT_COLOR, anchor="mm")
        sep_y = y_start + total_h + 20
        draw.line([(W // 2 - 200, sep_y), (W // 2 + 200, sep_y)],
                  fill=LINE_COLOR, width=2)
        draw.text((W // 2, sep_y + 40), "Zenn 技術記事 解説",
                  font=fonts["body"], fill=SUB_COLOR, anchor="mm")
    else:
        y = 40

        # 見出し
        draw.text((60, y), section.heading, font=fonts["heading"], fill=ACCENT_COLOR)
        y += 56
        draw.line([(60, y), (W - 60, y)], fill=LINE_COLOR, width=1)
        y += 18

        # 本文
        if section.body:
            for line in section.body.split("\n")[:6]:
                if not line.strip():
                    y += 12
                    continue
                wrapped = textwrap.wrap(line, width=42)
                for wl in wrapped[:3]:
                    draw.text((60, y), wl, font=fonts["body"], fill=TEXT_COLOR)
                    y += 34
                if y > 440:
                    break

        # 表
        if section.table and y < 480:
            y += 10
            y = _draw_table(draw, section.table[:8], 60, y, fonts, W - 120)

    # フッター
    draw.rectangle([0, H - 44, W, H], fill=(12, 18, 40))
    draw.text((60, H - 28), article_title, font=fonts["small"], fill=SUB_COLOR)
    draw.text((W - 60, H - 28),
              f"{slide_num} / {total}",
              font=fonts["small"], fill=SUB_COLOR, anchor="rm")

    img.save(out_path)


# ---------------------------------------------------------------------------
# 猫アバター合成
# ---------------------------------------------------------------------------

_neko_cache: dict[str, Path] = {}

def _prep_neko_transparent(work_dir: Path) -> tuple[Path, Path]:
    """背景だけを透過処理した猫画像を準備（flood fill で端から白を除去）"""
    closed_out = work_dir / "_neko_closed.png"
    open_out   = work_dir / "_neko_open.png"
    if closed_out.exists() and open_out.exists():
        return closed_out, open_out
    for src, dst in [(NEKO_CLOSED, closed_out), (NEKO_OPEN, open_out)]:
        if not src.exists():
            continue
        from PIL import ImageDraw as _ID
        img = Image.open(src).convert("RGBA")
        # flood fill: 四隅から白領域を透明に（本体内部の白は触らない）
        flood = img.copy()
        _ID.floodfill(flood, (0, 0), (0, 0, 0, 0), thresh=30)
        _ID.floodfill(flood, (img.width - 1, 0), (0, 0, 0, 0), thresh=30)
        _ID.floodfill(flood, (0, img.height - 1), (0, 0, 0, 0), thresh=30)
        _ID.floodfill(flood, (img.width - 1, img.height - 1), (0, 0, 0, 0), thresh=30)
        flood.save(dst)
    return closed_out, open_out


def _paste_neko(slide: Image.Image, neko_path: Path) -> Image.Image:
    """スライドの右下に猫を合成して返す"""
    if not neko_path.exists():
        return slide
    W, H = slide.size
    neko = Image.open(neko_path).convert("RGBA").resize(NEKO_SIZE, Image.LANCZOS)
    x = W - NEKO_SIZE[0] - 20
    y = H - NEKO_SIZE[1] - 48  # フッター(44px)の上
    result = slide.convert("RGBA")
    result.paste(neko, (x, y), neko)
    return result.convert("RGB")


# ---------------------------------------------------------------------------
# TTS・動画合成
# ---------------------------------------------------------------------------

async def _tts(text: str, out_path: Path):
    import edge_tts
    communicate = edge_tts.Communicate(text, voice="ja-JP-NanamiNeural")
    await communicate.save(str(out_path))


def _compose_clip(image_path: Path, audio_path: Path, out_path: Path):
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
        raise RuntimeError(f"FFmpeg clip失敗: {result.stderr[-300:]}")


def _compose_clip_kuchipaku(
    slide_closed: Path, slide_open: Path, audio_path: Path, out_path: Path
):
    """口パクアニメーション付きクリップを合成（closed↔open を 4fps でループ）"""
    # concat demuxer リストファイルで closed/open をループ
    list_file = out_path.parent / f"{out_path.stem}_kuchi_list.txt"
    list_file.write_text(
        f"file '{slide_closed.resolve()}'\nduration 0.25\n"
        f"file '{slide_open.resolve()}'\nduration 0.25\n"
    )
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-stream_loop", "500",
        "-i", str(list_file),
        "-i", str(audio_path),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        str(out_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    list_file.unlink(missing_ok=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg kuchipaku失敗: {result.stderr[-300:]}")


def _concat_videos(clip_paths: list[Path], out_path: Path):
    list_file = out_path.parent / "concat_list.txt"
    list_file.write_text("\n".join(f"file '{p}'" for p in clip_paths))
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        str(out_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg concat失敗: {result.stderr[-300:]}")
    list_file.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# メインパイプライン
# ---------------------------------------------------------------------------

def build_zenn_video(md_path: Path, upload: bool = True) -> Path:
    article_title, sections = parse_article(md_path)
    slug = md_path.stem
    work_dir = OUTPUT_DIR / slug
    work_dir.mkdir(parents=True, exist_ok=True)

    total = len(sections)
    clip_paths: list[Path] = []
    neko_closed, neko_open = _prep_neko_transparent(work_dir)
    has_neko = neko_closed.exists() and neko_open.exists()

    print(f"[zenn_video] 記事: {article_title}（{total}セクション）{'[口パクあり]' if has_neko else ''}{'[NeuroState]' if _HAS_WRITER_STATE else ''}")
    if _HAS_WRITER_STATE:
        print(f"  WriterState: {_writer_state_log()}")

    for i, section in enumerate(sections):
        prefix = work_dir / f"s{i:02d}"

        print(f"  [{i+1}/{total}] {section.heading or 'タイトル'}")

        clip_path = Path(str(prefix) + "_clip.mp4")
        if clip_path.exists():
            print(f"    スキップ（既存クリップ使用）")
            clip_paths.append(clip_path)
            continue

        # ナレーション生成
        narration = generate_narration(article_title, section)
        print(f"    ナレーション: {narration[:50]}…")

        # スライド画像
        slide_base_path = Path(str(prefix) + "_slide.png")
        make_slide(section, i + 1, total, article_title, slide_base_path)

        # 音声
        audio_path = Path(str(prefix) + "_voice.mp3")
        asyncio.run(_tts(narration, audio_path))

        # 口パクあり/なしで分岐
        if has_neko:
            base = Image.open(slide_base_path)
            slide_closed = Path(str(prefix) + "_slide_closed.png")
            slide_open   = Path(str(prefix) + "_slide_open.png")
            _paste_neko(base, neko_closed).save(slide_closed)
            _paste_neko(base, neko_open).save(slide_open)
            _compose_clip_kuchipaku(slide_closed, slide_open, audio_path, clip_path)
        else:
            _compose_clip(slide_base_path, audio_path, clip_path)

        clip_paths.append(clip_path)

    # 全クリップ結合
    final_path = work_dir / f"{slug}.mp4"
    _concat_videos(clip_paths, final_path)
    print(f"[zenn_video] 動画生成完了: {final_path}")

    if upload:
        from youtube_upload import upload_diary_video
        yt_title = f"【解説】{article_title}"
        description = (
            f"{article_title}\n\n"
            f"Zenn記事の解説動画です。\n"
            f"https://zenn.dev/kagioneko/articles/{slug}\n\n"
            f"#AI #NeuroState #LLM"
        )
        try:
            url = upload_diary_video(str(final_path), yt_title, slug, description=description)
            print(f"[zenn_video] YouTube: {url}")
        except Exception as e:
            print(f"[zenn_video] アップロード失敗（手動で）: {e}")

    return final_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使い方: python zenn_video.py /path/to/article.md [--no-upload]")
        sys.exit(1)

    md = Path(sys.argv[1])
    if not md.exists():
        print(f"ファイルが見つかりません: {md}")
        sys.exit(1)

    do_upload = "--no-upload" not in sys.argv
    build_zenn_video(md, upload=do_upload)
