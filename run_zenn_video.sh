#!/bin/bash
# Zenn記事解説動画をtmuxセッション内で生成する（SSH切れても継続）
#
# 使い方:
#   ./run_zenn_video.sh /path/to/article.md
#   ./run_zenn_video.sh /path/to/article.md --no-upload

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ARTICLE="$1"

if [ -z "$ARTICLE" ]; then
    echo "使い方: $0 /path/to/article.md [--no-upload]"
    exit 1
fi

SESSION="zenn_video"
UPLOAD_FLAG="${2:-}"

# 既存セッションが残っていたら削除
if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "既存セッション '$SESSION' を終了します..."
    tmux kill-session -t "$SESSION"
fi

CMD="cd '$SCRIPT_DIR' && .venv/bin/python zenn_video.py '$ARTICLE' $UPLOAD_FLAG 2>&1 | tee output/zenn_video_last.log; echo '=== 完了 ==='"

tmux new-session -d -s "$SESSION" -x 220 -y 50 "bash -c \"$CMD\""

echo "tmuxセッション '$SESSION' で実行開始しました。"
echo ""
echo "ログ確認: tmux attach -t $SESSION"
echo "バックグラウンド確認: tail -f $SCRIPT_DIR/output/zenn_video_last.log"
