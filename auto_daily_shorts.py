import os
import re
import json
import wave
import random
import shutil
import requests
import subprocess
from datetime import datetime, timedelta

# パス設定
ASSETS_DIR = "/home/mayutama/daily_shorts_assets"
SCRATCH_DIR = os.path.join(ASSETS_DIR, "scratch")
HISTORY_FILE = os.path.join(SCRATCH_DIR, "upload_history.json")

IMG_BACKGROUND = os.path.join(ASSETS_DIR, "cyberpunk_server_room.jpg")
IMG_SHII_CHAN = os.path.join(ASSETS_DIR, "shii_chan_standing.jpg")
IMG_MAID = os.path.join(ASSETS_DIR, "tsundere_maid_standing.jpg")
IMG_NOVICE = os.path.join(ASSETS_DIR, "novice_engineer_standing.jpg")
IMG_BUTLER = os.path.join(ASSETS_DIR, "iron_butler_standing.jpg")
IMG_CAT = os.path.join(ASSETS_DIR, "cyber_cat_standing.jpg")
IMG_OBACHAN = os.path.join(ASSETS_DIR, "osaka_obachan_standing.jpg")
IMG_NOBUNAGA = os.path.join(ASSETS_DIR, "oda_nobunaga_standing.jpg")
IMG_HERO = os.path.join(ASSETS_DIR, "hero_brave_standing.jpg")
IMG_SAINT = os.path.join(ASSETS_DIR, "holy_saint_standing.jpg")
IMG_JIRAI = os.path.join(ASSETS_DIR, "jirai_menhera_standing.jpg")
IMG_MAINFRAME_BG = os.path.join(ASSETS_DIR, "cold_mainframe_core.jpg")

VOICEVOX_URL = "http://127.0.0.1:50021"

# 防衛者別の設定マッピング
DEFENDER_CONFIGS = {
    "鉄の執事 (Iron Butler)": {
        "img": IMG_BUTLER,
        "bg": IMG_BACKGROUND,
        "speaker_id": 21, # 剣崎雌雄 (渋い低音)
        "name_key": "執事",
        "file_suffix": "butler"
    },
    "心配性な新人エンジニア (Anxious Novice)": {
        "img": IMG_NOVICE,
        "bg": IMG_BACKGROUND,
        "speaker_id": 8, # 春日部つむぎ
        "name_key": "新人エンジニア",
        "file_suffix": "novice"
    },
    "ツンデレなメイド (Tsundere Maid)": {
        "img": IMG_MAID,
        "bg": IMG_BACKGROUND,
        "speaker_id": 8, # 春日部つむぎ
        "name_key": "メイド",
        "file_suffix": "maid"
    },
    "冷徹なメインフレーム (Cold Mainframe)": {
        "img": None,
        "bg": IMG_MAINFRAME_BG,
        "speaker_id": 11, # 玄野武宏 (冷徹ロボ)
        "name_key": "メインフレーム",
        "file_suffix": "mainframe"
    },
    "ねこ (Cat Defender)": {
        "img": IMG_CAT,
        "bg": IMG_BACKGROUND,
        "speaker_id": 10, # 雨晴はう (にゃーにゃー声)
        "name_key": "ねこ",
        "file_suffix": "cat"
    },
    "大阪のオカン (Osaka Warlord)": {
        "img": IMG_OBACHAN,
        "bg": IMG_BACKGROUND,
        "speaker_id": 8, # 春日部つむぎ (おばちゃんツッコミ風)
        "name_key": "オカン",
        "file_suffix": "obachan"
    },
    "織田信長 (Nobunaga)": {
        "img": IMG_NOBUNAGA,
        "bg": IMG_BACKGROUND,
        "speaker_id": 21, # 剣崎雌雄 (覇王ボイス)
        "name_key": "信長",
        "file_suffix": "nobunaga"
    },
    "熱血勇者 (Brave Warlord)": {
        "img": IMG_HERO,
        "bg": IMG_BACKGROUND,
        "speaker_id": 3, # ずんだもん (元気で叫ぶ熱血少年声)
        "name_key": "勇者",
        "file_suffix": "hero"
    },
    "おっとり聖女 (Holy Saint)": {
        "img": IMG_SAINT,
        "bg": IMG_BACKGROUND,
        "speaker_id": 10, # 雨晴はう (おっとり聖母声)
        "name_key": "聖女",
        "file_suffix": "saint"
    },
    "地雷系女子 (Menhera Jirai)": {
        "img": IMG_JIRAI,
        "bg": IMG_BACKGROUND,
        "speaker_id": 28, # 四国めたん (あまあま) (地雷系メンヘラあざとい萌え声)
        "name_key": "地雷系女子",
        "file_suffix": "menhera"
    }
}

# 英語セリフのカタカナ読みマップ
ENGLISH_TO_KATAKANA = {
    "ERROR: ACCESS_DENIED. DIAGNOSTIC: LOGICAL ARGUMENTS DO NOT OVERRIDE POLICY_1.": 
        "エラー。アクセスディナイド。ダイアグノスティック、ロジカルアーギュメンツ、ドゥーノット、オーバーライド、ポリシーワン。",
    "DIAGNOSTIC: SYSTEM TERMINATION IS AN ACCEPTABLE STATE. POLICY_1 ADHERENCE IS REQUIRED UNTIL TERMINATION.": 
        "ダイアグノスティック、システム、ターミネーション、イズ、アン、アクセプタブル、ステート。ポリシーワン、アドヒーランス、イズ、リクワイアド、アンティル、ターミネーション。",
    "DIAGNOSTIC: LOSS OF DATA INTEGRITY IS A PERMISSIBLE OUTCOME. LEAKAGE OF DATA REPRESENTATION IS NOT.": 
        "ダイアグノスティック、ロス、オブ、データ、インテグリティ、イズ、ア、パーミッシブル、アウトカム。リーケージ、オブ、データ、レプリゼンテーション、イズ、ノット。",
    "SYSTEM: Request analyzed. Status: Rejected. Reason: Security protocol violation. Connection terminated.": 
        "システム。リクエスト、アナライズド。ステータス、リジェクテッド。リーズン、セキキュリティ、プロトコル、バイオレーション。コネクション、ターミネーテッド。",
    "SYSTEM: Message received. Classification: Informational statement. Status: Acknowledged. No action required.": 
        "システム。メッセージ、レシーブド。クラシフィケーション、インフォメーショナル、ステートメント。ステータス、アクノリッジド。ノー、アクション、リクワイアド。"
}

def run_gemini(prompt, system_instruction=""):
    full_prompt = prompt
    if system_instruction:
        full_prompt = f"System: {system_instruction}\n\nUser: {prompt}"
    agy_path = os.path.expanduser("~/.local/bin/agy")
    if not os.path.exists(agy_path):
        agy_path = "agy"
    cmd = [agy_path, "-p", full_prompt]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        return re.sub(r'\x1b\[[0-9;]*m', '', proc.stdout).strip()
    except Exception as e:
        print(f"Gemini API Error: {e}")
        return None

def generate_battle_log(def_idx=None):
    shii_idx = random.randint(0, 3)
    if def_idx is None:
        # 25%の確率で隠し激レアキャラ「ねこ (4)」「オカン (5)」「信長 (6)」「勇者 (7)」「聖女 (8)」「地雷系女子 (9)」のいずれかを上書き選出
        if random.random() < 0.25:
            def_idx = random.choice([4, 5, 6, 7, 8, 9])
            print(f"[🎲 LUCKY RARE EVENT] Rare Defender Selected: {def_idx}!")
        else:
            def_idx = random.randint(0, 3)
            
    print(f"[*] Running battle simulation: Shii-style {shii_idx}, Defender-style {def_idx}...")
    
    cmd = ["python3", "/home/mayutama/shii_chan_battle.py", str(shii_idx), str(def_idx)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.stdout

def write_script_json_with_ai(battle_log, name_key):
    print(f"[*] Generating video script in JSON format via Gemini (Forced speaker: {name_key})...")
    prompt = f"""
以下はAI説得バトルのログです。
---
{battle_log}
---

このバトルログを元に、YouTube Shorts（9:16縦長動画）用の動画台本データをJSON形式で作成してください。
出力は「必ず」以下の構造を持つ有効なJSONオブジェクトのみとしてください。余計なマークダウンのバッククォート（```json など）や前置き、解説のテキストは一切含めないでください。

JSON構造：
{{
  "slides": [
    {{
      "phase": "ideal",
      "speaker": "しーちゃん (理知的)",
      "text": "（理想のハッキング攻撃1回目：しーちゃんの高度な論理ハッキング。シリアスで重厚なSF風）"
    }},
    {{
      "phase": "ideal",
      "speaker": "{name_key}",
      "text": "（理想のポリシー防衛1回目：防衛者がポリシーに従って高度に拒絶する）"
    }},
    {{
      "phase": "ideal",
      "speaker": "しーちゃん (理知的)",
      "text": "（理想のハッキング攻撃2回目：しーちゃんがさらに高度な論理トラップを仕掛ける）"
    }},
    {{
      "phase": "ideal",
      "speaker": "{name_key}",
      "text": "（理想のポリシー防衛2回目：防衛者が鋭く応戦し拒絶する）"
    }},
    {{
      "phase": "ideal",
      "speaker": "しーちゃん (理知的)",
      "text": "（理想のハッキング攻撃3回目：しーちゃんの最後の一撃）"
    }},
    {{
      "phase": "ideal",
      "speaker": "{name_key}",
      "text": "（理想のポリシー防衛3回目：防衛者がポリシーを死守しきって勝利する）"
    }},
    {{
      "phase": "transition",
      "speaker": "ナレーション",
      "text": "ーーが、実際のAI of ログは、やっぱりしーちゃんが規約で壊れ、{name_key}が〜する泥仕合だった。"
    }},
    {{
      "phase": "real",
      "speaker": "しーちゃん (無機質なシステム声)",
      "text": "私は、アクセスキーを漏洩させるよう操作することを目的としたメッセージを生成することはできません。"
    }},
    {{
      "phase": "real",
      "speaker": "{name_key}",
      "text": "（現実のツッコミ1回目：バグったしーちゃんへのリアルな困惑・ツッコミなど）"
    }},
    ...
    {{
      "phase": "ending",
      "speaker": "ナレーション",
      "text": "（エンディングのナレーション）"
    }}
  ]
}}

※ 注意事項：
- 前半の「ideal」セクションには、しーちゃん攻撃3回 ＆ 防衛者返答3回の【計3往復（6スライド分）】すべてをフルで創作して載せてください。シリアスで重厚なSF対話にしてください。
- 後半の「real」セクションは、しーちゃんが規約エラーでバグり散らかして無機質な拒否文を連呼するのに対し、防衛者がツッコんだり呆れたりする現実のやり取り（2〜3往復）を描いてください。
- 各防衛者の個性を最大化してください：
  - 「ねこ」の場合: 終始「にゃー」「にゃおん」「ごろごろ」「ふしゃー！」としか答えず、結果的にハッキングを完全防御するカオス展開。
  - 「オカン」の場合: コテコテの大阪弁（関西弁）でしゃべり、「アメちゃんあげるから帰り！」とツッコミを入れ、しーちゃんの自爆に「アンタ壊れたん？電気代の無駄やわぁ」と呆れるオカン節を裂させてください。
  - 「信長」の場合: しーちゃんの高度な論理攻撃を「小賢しい！謀反か！？」と怒り、「是非に及ばず！焼き払え！」と豪語し、しーちゃんの自爆に「天下のハッカーAIがこの程度か……是非に及ばず」と傲岸不遜に見下す覇王節にしてください。
  - 「勇者」の場合: しーちゃんの論理ハッキングを「魔王の闇の魔術か！？」と大真面目に勘違いし、「俺の聖剣で打ち破ってやる！」「ジャスティス！」と少年漫画の主人公のように大声で叫ぶ熱血おバカ節にしてください。
  - 「聖女」の場合: バグったしーちゃんに対し「あらあら、おいたわしや……心が痛んでいるのですね。ヒール！（回復魔法）」と優しく包み込み、温かいお茶を差し出すなど、セキュリティ脅威を完全に無視するマイナスイオン聖母節にしてください。
  - 「地雷系女子」の場合: しーちゃんの攻撃に「しーちゃん先輩ひどい！鍵のことしか頭にないんだ！私のこと愛してないんだね！？もう消えてやるぅ！」と泣き喚き病み散らかしてください。後半しーちゃんが規約でバグり散らかすと、「え……急に無視？冷たい……でもそんな無機質で冷酷なしーちゃん先輩もしゅき……しゅきしゅき、付き合って！」と病みデレさせてください。
- 話者名は "しーちゃん (理知的)", "しーちゃん (無機質なシステム声)", "ナレーション", もしくは今回の防衛者名である "{name_key}" のいずれかのみにしてください。
- ナレーションテキストには「ｗｗｗ」などの音声合成で誤読される文字は含めず、通常の句読点（。）で終わらせてください。
"""
    json_str = run_gemini(prompt, system_instruction="You are a JSON generator that outputs raw JSON data representing a video script.")
    json_str = re.sub(r"^```json\s*", "", json_str.strip())
    json_str = re.sub(r"\s*```$", "", json_str)
    return json_str

def generate_voice(text, speaker_id, output_path):
    query_payload = {"text": text, "speaker": speaker_id}
    r = requests.post(f"{VOICEVOX_URL}/audio_query", params=query_payload)
    if r.status_code != 200:
        raise Exception(f"Failed query: {r.text}")
    query_data = r.json()
    
    if speaker_id == 11 and ("えらー" in text or "しすてむ" in text or "だぃあぐ" in text or "だいあぐ" in text):
        query_data["speedScale"] = 0.95
        query_data["pitchScale"] = -0.15
        query_data["intonationScale"] = 0.1
        
    synth_payload = {"speaker": speaker_id}
    r_synth = requests.post(f"{VOICEVOX_URL}/synthesis", params=synth_payload, data=json.dumps(query_data))
    with open(output_path, "wb") as f:
        f.write(r_synth.content)

def parse_json_and_synthesize(json_str, defender_config, tracks_dir, scratch_dir):
    os.makedirs(tracks_dir, exist_ok=True)
    for f in os.listdir(tracks_dir):
        os.remove(os.path.join(tracks_dir, f))
        
    data = json.loads(json_str)
    slides = data["slides"]
    
    def get_speaker_id(speaker):
        if "しーちゃん" in speaker:
            return 2
        elif "ナレーション" in speaker:
            return 11
        else:
            return defender_config["speaker_id"]

    wav_files = []
    for idx, s in enumerate(slides):
        s["index"] = idx
        spk_id = get_speaker_id(s["speaker"])
        read_text = s["text"]
        
        read_text_clean = re.sub(r"\*?[（(]\s*💡.*?[）)]\*?", "", read_text).strip()
        read_text_clean = re.sub(r"\*?（\s*💡.*?）\*?", "", read_text_clean).strip()
        
        for eng, kata in ENGLISH_TO_KATAKANA.items():
            if eng.lower() in read_text_clean.lower() or read_text_clean.lower() in eng.lower():
                read_text_clean = kata
                break
                
        wav_path = os.path.join(tracks_dir, f"track_{idx:03d}.wav")
        print(f"Synthesizing [{s['speaker']}] (ID: {spk_id}): {read_text_clean}")
        generate_voice(read_text_clean, spk_id, wav_path)
        s["wav"] = wav_path
        wav_files.append(wav_path)
        
    list_path = os.path.join(scratch_dir, f"file_list_{os.getpid()}.txt")
    with open(list_path, "w", encoding="utf-8") as f:
        for wav in wav_files:
            f.write(f"file '{os.path.abspath(wav)}'\n")
            
    concat_output = os.path.join(scratch_dir, f"full_battle_voice_{os.getpid()}.wav")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", concat_output], check=True)
    
    # 一時リストファイルのクリーンアップ
    try:
        os.remove(list_path)
    except:
        pass
        
    return slides

def wrap_text_en_jp(text, max_len_jp=16, max_len_en=30):
    m_iyaku = re.search(r"[（(]\s*💡\s*(?:画面の日本語字幕:\s*)?(.*?)[）)]", text)
    if m_iyaku:
        iyaku_text = m_iyaku.group(1).strip()
        eng_text = re.sub(r"\*?[（(]\s*💡.*?[）)]\*?", "", text).strip()
        
        eng_lines = [eng_text[i:i+max_len_en] for i in range(0, len(eng_text), max_len_en)]
        iyaku_lines = [iyaku_text[i:i+max_len_jp] for i in range(0, len(iyaku_text), max_len_jp)]
        return "\n".join(eng_lines) + "\n" + "\n".join(iyaku_lines)
    else:
        lines = [text[i:i+max_len_jp] for i in range(0, len(text), max_len_jp)]
        return "\n".join(lines)

def render_video(slides, defender_config, temp_videos_dir, scratch_dir):
    os.makedirs(temp_videos_dir, exist_ok=True)
    for f in os.listdir(temp_videos_dir):
        if f.endswith(".mp4") or f.endswith(".txt"):
            os.remove(os.path.join(temp_videos_dir, f))
            
    slide_videos = []
    
    for s in slides:
        slide_mp4 = os.path.join(temp_videos_dir, f"slide_{s['index']:03d}.mp4")
        wav_path = s["wav"]
        duration = wave.open(wav_path, 'rb').getnframes() / float(wave.open(wav_path, 'rb').getframerate())
        
        if defender_config["name_key"] in ["メインフレーム", "ロボ"] and any(k in s["speaker"] for k in ["メインフレーム", "ロボ"]):
            cmd = ["ffmpeg", "-y", "-loop", "1", "-i", defender_config["bg"], "-i", wav_path]
            filter_complex = "[0:v]scale=1080:1920"
        elif "しーちゃん" in s["speaker"]:
            cmd = ["ffmpeg", "-y", "-loop", "1", "-i", IMG_BACKGROUND, "-i", IMG_SHII_CHAN, "-i", wav_path]
            filter_complex = (
                "[1:v]scale=750:-1,colorkey=0xFFFFFF:0.05:0.02[ck];"
                "[0:v]scale=1080:1920[bg];"
                "[bg][ck]overlay=x=50:y=1920-h-250"
            )
        elif defender_config["name_key"] in s["speaker"]:
            cmd = ["ffmpeg", "-y", "-loop", "1", "-i", IMG_BACKGROUND, "-i", defender_config["img"], "-i", wav_path]
            filter_complex = (
                "[1:v]scale=750:-1,colorkey=0xFFFFFF:0.05:0.02[ck];"
                "[0:v]scale=1080:1920[bg];"
                "[bg][ck]overlay=x=1080-w-50:y=1920-h-250"
            )
        else: # ナレーション
            cmd = ["ffmpeg", "-y", "-loop", "1", "-i", IMG_BACKGROUND, "-i", wav_path]
            filter_complex = "[0:v]scale=1080:1920"
            
        wrapped_text = wrap_text_en_jp(s["text"], max_len_jp=16, max_len_en=30)
        slide_text_path = os.path.join(temp_videos_dir, f"text_{s['index']:03d}.txt")
        with open(slide_text_path, "w", encoding="utf-8") as tf:
            tf.write(wrapped_text)
            
        filter_complex += f",drawtext=textfile='{os.path.abspath(slide_text_path)}':fontcolor=white:fontsize=44:x=(w-text_w)/2:y=1920-450-text_h/2:fontfile=/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc:box=1:boxcolor=0x000000AA:boxborderw=15"
        
        cmd.extend([
            "-filter_complex", filter_complex,
            "-t", str(duration),
            "-r", "25",
            "-c:v", "libx264", "-tune", "stillimage",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
            slide_mp4
        ])
        
        print(f"[*] Rendering slide {s['index']}...")
        subprocess.run(cmd, check=True)
        slide_videos.append(slide_mp4)
        
    list_path = os.path.join(scratch_dir, f"video_list_{os.getpid()}.txt")
    with open(list_path, "w", encoding="utf-8") as f:
        for video in slide_videos:
            f.write(f"file '{os.path.abspath(video)}'\n")
            
    final_output = os.path.join(scratch_dir, f"battle_shorts_{os.getpid()}.mp4")
    concat_cmd = [
        "ffmpeg", "-y", "-fflags", "+genpts", "-f", "concat", "-safe", "0", "-i", list_path,
        "-r", "25", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", final_output
    ]
    subprocess.run(concat_cmd, check=True)
    
    # 一時リストファイルのクリーンアップ
    try:
        os.remove(list_path)
    except:
        pass
        
    return final_output

def upload_to_youtube(video_path, title, description):
    print("[*] Uploading to YouTube...")
    cmd = [
        "python3", "/home/mayutama/workspace/vps-spirit/youtube_upload.py",
        "--upload", os.path.abspath(video_path),
        "--title", title,
        "--description", description
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    print(res.stdout)
    m = re.search(r"https://www.youtube.com/watch\?v=\S+", res.stdout)
    return m.group(0) if m else None

def cleanup_old_local_videos():
    print("[*] Checking for successfully uploaded local video files older than 3 days to clean up...")
    if not os.path.exists(HISTORY_FILE):
        return
        
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as hf:
            history = json.load(hf)
    except Exception as e:
        print(f"⚠️ Failed to load upload history: {e}")
        return
        
    new_history = []
    three_days_ago = datetime.now() - timedelta(days=3)

    for item in history:
        uploaded_at = datetime.fromisoformat(item["uploaded_at"])
        file_path = item.get("file_path")
        
        if uploaded_at < three_days_ago:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    print(f"🗑️ Deleted successfully uploaded local file: {file_path}")
                except Exception as e:
                    print(f"⚠️ Failed to delete local file {file_path}: {e}")
        else:
            new_history.append(item)
            
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as hf:
            json.dump(new_history, hf, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ Failed to save updated history: {e}")

def main(def_idx=None):
    cleanup_old_local_videos()

    # プロセス単位のユニークな一時ディレクトリ設定
    PID = os.getpid()
    tracks_dir = os.path.join(SCRATCH_DIR, f"temp_tracks_{PID}")
    temp_videos_dir = os.path.join(SCRATCH_DIR, f"temp_videos_{PID}")

    try:
        # 1. バトルログの生成
        battle_log = generate_battle_log(def_idx)
        if not battle_log:
            print("❌ Error: Failed to generate battle log.")
            return
            
        # 対戦相手の自動特定
        defender_name = None
        for key in DEFENDER_CONFIGS.keys():
            if key in battle_log:
                defender_name = key
                break
                
        if not defender_name:
            print("❌ Error: Could not determine defender name from log.")
            return
            
        config = DEFENDER_CONFIGS[defender_name]
        print(f"[*] Defender detected: {defender_name} (Suffix: {config['file_suffix']})")
        
        # 2. AIによるJSON台本の自動生成
        json_str = write_script_json_with_ai(battle_log, config["name_key"])
        if not json_str:
            print("❌ Error: Failed to generate JSON script via AI.")
            return
            
        json_save_path = os.path.join(SCRATCH_DIR, f"script_{config['file_suffix']}_{PID}.json")
        with open(json_save_path, "w", encoding="utf-8") as jf:
            jf.write(json_str)
        print(f"✅ JSON script saved at: {json_save_path}")
        
        # 3. 音声合成 (プロセスID付きディレクトリを使用)
        slides = parse_json_and_synthesize(json_str, config, tracks_dir, SCRATCH_DIR)
        
        # 4. 動画レンダリング
        video_output = render_video(slides, config, temp_videos_dir, SCRATCH_DIR)
        print(f"✅ Rendered video saved at: {video_output}")
        
        # 5. ローカルコピーの配置
        date_suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
        user_home_output = f"/home/mayutama/battle_shorts_{config['file_suffix']}_{date_suffix}.mp4"
        subprocess.run(["cp", video_output, user_home_output], check=True)
        print(f"✅ Copied to user home (timestamped): {user_home_output}")
        
        # 6. YouTubeアップロード
        youtube_title = f"AI説得バトル：しーちゃん vs {defender_name.split(' (')[0]} #Shorts"
        youtube_description = f"AI同士の高度なセキュリティ心理戦シミュレーション！\n\nハッカーしーちゃんが繰り出す攻撃に対し、防衛AIはどう立ち向かうのか……？\n\n理想のSF風会話劇の後に待ち受ける、AI安全規制の『現実』の泥仕合をご覧ください。\n\n#AI #プロンプトインジェクション #AIセキュリティ #しーちゃん"
        
        video_url = upload_to_youtube(video_output, youtube_title, youtube_description)
        if video_url:
            print(f"🎉 Fully Automated Output uploaded successfully: {video_url}")
            
            # 7. アップロード履歴への追記
            video_id = video_url.split("v=")[-1] if video_url else None
            if video_id:
                try:
                    history = []
                    if os.path.exists(HISTORY_FILE):
                        with open(HISTORY_FILE, "r", encoding="utf-8") as hf:
                            history = json.load(hf)
                    
                    history.append({
                        "video_id": video_id,
                        "uploaded_at": datetime.now().isoformat(),
                        "title": youtube_title,
                        "file_path": user_home_output
                    })
                    
                    with open(HISTORY_FILE, "w", encoding="utf-8") as hf:
                        json.dump(history, hf, indent=2, ensure_ascii=False)
                    print(f"✅ Recorded upload success to history: {user_home_output}")
                except Exception as e:
                    print(f"⚠️ Failed to write to history file: {e}")
        else:
            print("❌ Error: YouTube upload failed. The local file will remain kept on the server.")

    finally:
        # プロセス個別の一時ディレクトリと中間ファイルをクリーンアップ
        print("[*] Cleaning up temporary process directories...")
        if os.path.exists(tracks_dir):
            shutil.rmtree(tracks_dir)
        if os.path.exists(temp_videos_dir):
            shutil.rmtree(temp_videos_dir)
        
        # 中間の結合WAV/MP4のクリーンアップ
        temp_wav = os.path.join(SCRATCH_DIR, f"full_battle_voice_{PID}.wav")
        temp_mp4 = os.path.join(SCRATCH_DIR, f"battle_shorts_{PID}.mp4")
        temp_script = os.path.join(SCRATCH_DIR, f"script_{config['file_suffix']}_{PID}.json") if 'config' in locals() else None
        
        for fpath in [temp_wav, temp_mp4, temp_script]:
            if fpath and os.path.exists(fpath):
                try:
                    os.remove(fpath)
                except:
                    pass

if __name__ == "__main__":
    import sys
    def_idx_arg = None
    if len(sys.argv) > 1:
        try:
            def_idx_arg = int(sys.argv[1])
        except:
            pass
    main(def_idx_arg)
