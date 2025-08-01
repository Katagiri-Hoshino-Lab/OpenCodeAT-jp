#!/bin/bash
# OpenCodeAT エージェント用hooks設定スクリプト
# PMが各エージェント起動時に実行

set -e

# 引数チェック
if [ $# -lt 3 ]; then
    echo "Usage: $0 <AGENT_ID> <AGENT_DIR> <AGENT_TYPE>"
    echo "Example: $0 PG1.1.1 /path/to/agent/dir event-driven"
    echo "AGENT_TYPE: polling or event-driven"
    exit 1
fi

AGENT_ID=$1
AGENT_DIR=$2
AGENT_TYPE=$3

# プロジェクトルートを取得
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TEMPLATE_DIR="$PROJECT_ROOT/hooks/templates"

echo "🔧 Setting up hooks for agent: $AGENT_ID (type: $AGENT_TYPE)"

# .claude/hooks ディレクトリ作成
mkdir -p "$AGENT_DIR/.claude/hooks"

# session_start.pyをコピー（全エージェント共通）
cp "$TEMPLATE_DIR/session_start.py" "$AGENT_DIR/.claude/hooks/"

# エージェントタイプに応じたstop hookをコピー
if [ "$AGENT_TYPE" = "polling" ]; then
    cp "$TEMPLATE_DIR/stop_polling.py" "$AGENT_DIR/.claude/hooks/stop.py"
    # settings.jsonを作成（絶対パスを使用）
    cat > "$AGENT_DIR/.claude/settings.local.json" << EOF
{
  "hooks": {
    "Stop": [{
      "hooks": [{
        "type": "command",
        "command": "$AGENT_DIR/.claude/hooks/stop.py"
      }]
    }],
    "SessionStart": [{
      "hooks": [{
        "type": "command",
        "command": "$AGENT_DIR/.claude/hooks/session_start.py"
      }]
    }]
  }
}
EOF
    echo "✅ Polling agent hooks configured with absolute paths"
else
    cp "$TEMPLATE_DIR/stop_event.py" "$AGENT_DIR/.claude/hooks/stop.py"
    # settings.jsonを作成（絶対パスを使用）
    cat > "$AGENT_DIR/.claude/settings.local.json" << EOF
{
  "hooks": {
    "Stop": [{
      "hooks": [{
        "type": "command",
        "command": "$AGENT_DIR/.claude/hooks/stop.py"
      }]
    }],
    "SessionStart": [{
      "hooks": [{
        "type": "command",
        "command": "$AGENT_DIR/.claude/hooks/session_start.py"
      }]
    }]
  }
}
EOF
    echo "✅ Event-driven agent hooks configured with absolute paths"
fi

# 実行権限を付与
chmod +x "$AGENT_DIR/.claude/hooks/"*.py

echo "✅ Hooks setup completed for $AGENT_ID at $AGENT_DIR"