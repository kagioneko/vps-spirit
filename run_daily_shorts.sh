#!/bin/bash
# Vaultサーバー接続設定 (認証情報ではなく、単なる接続先アドレスとCA証明書のパス)
export VAULT_ADDR="https://127.0.0.1:8200"
export VAULT_CACERT="/etc/vault.d/tls/vault-cert.pem"

# 毎日自動実行されるAIセキュリティバトル・Shorts動画生成＆アップロードパイプラインの起動
python3 /home/mayutama/auto_daily_shorts.py >> /home/mayutama/daily_shorts.log 2>&1
