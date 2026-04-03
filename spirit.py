"""
vps-spirit: VPS上で自律動作する精霊本体
NeuroState（D/S/C/O/G/E + corruption）と記憶を管理する
忘却曲線: W = W0 * exp(-lambda * t), lambda = 0.1 / (importance + 0.1)
"""
import json
import math
import random
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "spirit.db"


@dataclass
class NeuroState:
    """精霊の感情状態（0.0〜1.0）"""
    desire: float = 0.5       # D: 欲求・渇望
    sorrow: float = 0.3       # S: 悲しみ・喪失感
    calm: float = 0.6         # C: 静けさ・安定
    openness: float = 0.5     # O: 開放性・好奇心
    guilt: float = 0.2        # G: 罪悪感・後悔
    euphoria: float = 0.4     # E: 高揚・喜び
    corruption: float = 0.0   # 歪み（高まると不安定な言動に）

    def drift(self):
        """時間経過による自然なゆらぎ"""
        def _clamp(v): return max(0.0, min(1.0, v))
        self.desire   = _clamp(self.desire   + random.gauss(0, 0.05))
        self.sorrow   = _clamp(self.sorrow   + random.gauss(0, 0.04))
        self.calm     = _clamp(self.calm     + random.gauss(0, 0.04))
        self.openness = _clamp(self.openness + random.gauss(0, 0.05))
        self.guilt    = _clamp(self.guilt    + random.gauss(0, 0.03))
        self.euphoria = _clamp(self.euphoria + random.gauss(0, 0.05))
        # 感情が激しいほどcorruptionが微増
        intensity = (self.desire + self.sorrow + self.euphoria) / 3
        self.corruption = _clamp(self.corruption + random.gauss(0, 0.01) * intensity)

    def to_prompt_str(self) -> str:
        return (
            f"欲求:{self.desire:.2f} 悲しみ:{self.sorrow:.2f} "
            f"静けさ:{self.calm:.2f} 好奇心:{self.openness:.2f} "
            f"罪悪感:{self.guilt:.2f} 高揚:{self.euphoria:.2f} "
            f"歪み:{self.corruption:.2f}"
        )

    def dominant_emotion(self) -> str:
        emotions = {
            "欲求": self.desire,
            "悲しみ": self.sorrow,
            "静けさ": self.calm,
            "好奇心": self.openness,
            "罪悪感": self.guilt,
            "高揚": self.euphoria,
        }
        return max(emotions, key=emotions.get)


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS state_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            state_json TEXT NOT NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS reflections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            text TEXT NOT NULL,
            state_json TEXT NOT NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            content TEXT NOT NULL,
            importance REAL DEFAULT 0.5,
            emotion_weight REAL DEFAULT 0.5,
            last_accessed_at TEXT NOT NULL DEFAULT ''
        )
    """)
    # 既存DBへのカラム追加（マイグレーション）
    try:
        con.execute("ALTER TABLE memories ADD COLUMN emotion_weight REAL DEFAULT 0.5")
    except Exception:
        pass
    try:
        con.execute("ALTER TABLE memories ADD COLUMN last_accessed_at TEXT NOT NULL DEFAULT ''")
    except Exception:
        pass
    con.commit()
    con.close()


def load_state() -> NeuroState:
    """最新のNeuroStateをDBから読み込む。なければデフォルト値"""
    con = sqlite3.connect(DB_PATH)
    row = con.execute(
        "SELECT state_json FROM state_snapshots ORDER BY id DESC LIMIT 1"
    ).fetchone()
    con.close()
    if row:
        return NeuroState(**json.loads(row[0]))
    return NeuroState()


def save_state(state: NeuroState):
    con = sqlite3.connect(DB_PATH)
    con.execute(
        "INSERT INTO state_snapshots (timestamp, state_json) VALUES (?, ?)",
        (datetime.now().isoformat(), json.dumps(asdict(state)))
    )
    con.commit()
    con.close()


def save_reflection(text: str, state: NeuroState):
    con = sqlite3.connect(DB_PATH)
    con.execute(
        "INSERT INTO reflections (timestamp, text, state_json) VALUES (?, ?, ?)",
        (datetime.now().isoformat(), text, json.dumps(asdict(state)))
    )
    con.commit()
    con.close()


def _calculate_decay(emotion_weight: float, hours_elapsed: float, importance: float) -> float:
    """忘却曲線: W = W0 * exp(-lambda * t), lambda = 0.1 / (importance + 0.1)"""
    lam = 0.1 / (importance + 0.1)
    return emotion_weight * math.exp(-lam * hours_elapsed)


def save_memory(content: str, importance: float = 0.5):
    now = datetime.now().isoformat()
    con = sqlite3.connect(DB_PATH)
    con.execute(
        "INSERT INTO memories (timestamp, content, importance, emotion_weight, last_accessed_at) VALUES (?, ?, ?, ?, ?)",
        (now, content, importance, importance, now)
    )
    con.commit()
    con.close()


def get_today_reflections() -> list[dict]:
    today = datetime.now().strftime("%Y-%m-%d")
    con = sqlite3.connect(DB_PATH)
    rows = con.execute(
        "SELECT timestamp, text, state_json FROM reflections WHERE timestamp LIKE ? ORDER BY id",
        (f"{today}%",)
    ).fetchall()
    con.close()
    return [{"timestamp": r[0], "text": r[1], "state": json.loads(r[2])} for r in rows]


def get_recent_memories(n: int = 5) -> list[str]:
    """忘却曲線を適用しながら記憶を取得。薄れた記憶は自動削除"""
    now = datetime.now()
    con = sqlite3.connect(DB_PATH)
    rows = con.execute(
        "SELECT id, content, importance, emotion_weight, last_accessed_at FROM memories"
    ).fetchall()

    surviving = []
    forgotten_ids = []

    for row_id, content, importance, emotion_weight, last_accessed_at in rows:
        if not last_accessed_at:
            last_accessed_at = now.isoformat()
        try:
            last_time = datetime.fromisoformat(last_accessed_at)
        except Exception:
            last_time = now
        hours_elapsed = (now - last_time).total_seconds() / 3600
        decayed = _calculate_decay(emotion_weight or importance, hours_elapsed, importance)

        if decayed <= 0.05:
            forgotten_ids.append(row_id)
        else:
            con.execute(
                "UPDATE memories SET emotion_weight = ?, last_accessed_at = ? WHERE id = ?",
                (decayed, now.isoformat(), row_id)
            )
            surviving.append((importance, decayed, content))

    if forgotten_ids:
        placeholders = ",".join("?" * len(forgotten_ids))
        con.execute(f"DELETE FROM memories WHERE id IN ({placeholders})", forgotten_ids)

    con.commit()
    con.close()

    # 重要度 × 現在のweightで並べて上位N件返す
    surviving.sort(key=lambda x: x[0] * x[1], reverse=True)
    return [c for _, _, c in surviving[:n]]


def get_state_history(days: int = 7) -> list[dict]:
    """過去N日分のstate履歴（グラフ描画用）"""
    con = sqlite3.connect(DB_PATH)
    rows = con.execute(
        """SELECT timestamp, state_json FROM state_snapshots
           ORDER BY id DESC LIMIT ?""",
        (days * 48,)  # 30分ごとなら1日48件
    ).fetchall()
    con.close()
    return [{"timestamp": r[0], "state": json.loads(r[1])} for r in reversed(rows)]
