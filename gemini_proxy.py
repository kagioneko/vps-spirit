"""
gemini_proxy.py: Gemini CLI を Ollama 互換 API でラップするプロキシ
ポート: 11435
エンドポイント: POST /api/generate  (OllamaClient がそのまま使える)
"""
import asyncio
import json
import subprocess
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

GEMINI_BIN = "/root/.nvm/versions/node/v22.19.0/bin/gemini"


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
    """Gemini CLIが思考プロセスを本文に混ぜて出力する場合に除去する"""
    lines = text.splitlines()
    # 英語の思考漏れ行を除去（"I will", "I need to", "Let me" 等で始まる英語行）
    import re
    thinking_pattern = re.compile(
        r'^(I will|I need|I should|I must|Let me|Let\'s|First,|Next,|Now,|To |Reading|Looking)',
        re.IGNORECASE
    )
    cleaned = [line for line in lines if not thinking_pattern.match(line.strip())]
    return "\n".join(cleaned).strip()


async def call_gemini(full_prompt: str) -> str:
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: subprocess.run(
            [GEMINI_BIN, "-p", full_prompt],
            capture_output=True, text=True, timeout=120,
            env={**__import__("os").environ, "HOME": "/root", "PATH": "/root/.nvm/versions/node/v22.19.0/bin:/usr/bin:/bin"}
        )
    )
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
    return {"status": "ok", "backend": "gemini-cli"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=11435)
