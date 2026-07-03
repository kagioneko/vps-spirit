#!/bin/bash
cd /home/mayutama/workspace/vps-spirit

# VOICEVOX一時停止
VOICEVOX_PID=$(pgrep -f "voicevox/linux")
if [ -n "$VOICEVOX_PID" ]; then
    kill $VOICEVOX_PID
    sleep 3
fi

# 日記生成・動画作成・YouTubeアップロード
python3 pipeline.py diary >> data/diary.log 2>&1

# VOICEVOX再起動
/home/mayutama/voicevox/linux-cpu-x64/run --host 127.0.0.1 --port 50021 &
