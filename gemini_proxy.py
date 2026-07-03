"""
gemini_proxy.py: Antigravity CLI (agy) を Ollama 互換 API でラップするプロキシ
ポート: 11435
エンドポイント: POST /api/generate  (OllamaClient がそのまま使える)
"""
import asyncio
import json
import subprocess
import re
import logging
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

# Antigravity CLI を使用
GEMINI_BIN = "agy"

class GenerateRequest(BaseModel):
    model: str = "gemini"
    prompt: str
    system: str = ""
    stream: bool = False


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str = "gemini"
    messages: list[ChatMessage]
    stream: bool = False


def _strip_thinking_leakage(text: str) -> str:
    """Antigravity CLIが思考プロセスを本文に混ぜて出力する場合に除去する"""
    lines = text.splitlines()
    
    # 英語の思考漏れ行を除去（セッションの冒頭によく出る特定のフレーズのみを対象にする）
    thinking_patterns = [
        r'^Looking at.*',
        r'^Reading .*',
        r'^I will .*',
        r'^I need to .*',
        r'^I should .*',
        r'^I must .*',
        r'^Let me .*',
        r'^Let\'s .*',
        r'^First, .*',
        r'^Now, I .*',
        r'^To .*',
    ]
    
    cleaned = []
    for line in lines:
        s_line = line.strip()
        # 会話の一部として自然なものは残したいので、エンジニアリング用語が含まれる場合のみ消す
        is_thought = any(re.match(p, s_line, re.IGNORECASE) for p in thinking_patterns)
        if is_thought and any(kw in s_line.lower() for kw in ["file", "directory", "workspace", "code", "implement", "investigate", "research"]):
            continue
        cleaned.append(line)
    
    return "\n".join(cleaned).strip()


async def call_gemini(full_prompt: str) -> str:
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: subprocess.run(
            [GEMINI_BIN, "-p", full_prompt],
            capture_output=True, text=True, timeout=300,  # タイムアウトを5分に延長
            env={**__import__("os").environ, "HOME": "/home/mayutama", "PATH": "/home/mayutama/.local/bin:/usr/local/bin:/usr/bin:/bin"}
        )
    )
    
    if result.returncode != 0:
        logging.error(f"Antigravity CLI Error: {result.stderr}")
        if "exhausted your capacity" in result.stderr.lower():
            return "（現在AIの利用制限がかかっています。しばらくしてからお試しください）"
        return f"エラー: {result.stderr.strip()}"
    
    return _strip_thinking_leakage(result.stdout.strip())


@app.post("/api/generate")
async def generate(req: GenerateRequest):
    full_prompt = f"{req.system}\n\n{req.prompt}".strip() if req.system else req.prompt
    response = await call_gemini(full_prompt)
    return {"model": req.model, "response": response, "done": True}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    try:
        parts = []
        for msg in req.messages:
            if msg.role == "system":
                parts.insert(0, msg.content)
            else:
                parts.append(msg.content)
        full_prompt = "\n\n".join(parts)
        response = await call_gemini(full_prompt)
        return {
            "model": req.model,
            "message": {"role": "assistant", "content": response},
            "done": True
        }
    except Exception as e:
        return {
            "model": req.model,
            "message": {"role": "assistant", "content": f"エラー: {e}"},
            "done": True
        }


@app.get("/")
def health():
    return {"status": "ok", "backend": "antigravity"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=11435)
