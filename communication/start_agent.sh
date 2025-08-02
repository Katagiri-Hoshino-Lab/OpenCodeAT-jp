#!/bin/bash
# エージェント起動用ラッパースクリプト
# PMが使用：各エージェントを適切な場所に移動して起動
# 
# 環境変数 OPENCODEAT_ENABLE_TELEMETRY が false の場合はテレメトリなしで起動

if [ $# -lt 2 ]; then
    echo "Usage: $0 <AGENT_ID> <TARGET_DIR> [additional_options]"
    echo "Example: $0 PG1.1.1 /Flow/TypeII/single-node/intel2024/OpenMP"
    echo ""
    echo "Environment variables:"
    echo "  OPENCODEAT_ENABLE_TELEMETRY=false  # テレメトリを無効化"
    exit 1
fi

AGENT_ID=$1
TARGET_DIR=$2
shift 2

# スクリプトのディレクトリからプロジェクトルートを取得
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# エージェントタイプを判定
determine_agent_type() {
    local agent_id=$1
    # PM, SE, CI, CDはポーリング型
    if [[ "$agent_id" =~ ^(PM|SE|CI|CD) ]]; then
        echo "polling"
    else
        echo "event-driven"
    fi
}

AGENT_TYPE=$(determine_agent_type "$AGENT_ID")

# エージェントにコマンドを送信
echo "🚀 Starting agent $AGENT_ID (type: $AGENT_TYPE) at $TARGET_DIR"

# 1. プロジェクトルートを環境変数として設定
./communication/agent_send.sh "$AGENT_ID" "export OPENCODEAT_ROOT='$PROJECT_ROOT'"

# 2. ターゲットディレクトリに移動
./communication/agent_send.sh "$AGENT_ID" "!cd $PROJECT_ROOT$TARGET_DIR"

# 3. 現在地を確認
./communication/agent_send.sh "$AGENT_ID" "pwd"

# 4. Hooksを設定（OPENCODEAT_ENABLE_HOOKSがfalseでない限り有効）
if [ "${OPENCODEAT_ENABLE_HOOKS}" != "false" ]; then
    echo "🔧 Setting up hooks for $AGENT_ID"
    
    # フルパスのターゲットディレクトリを構築
    FULL_TARGET_DIR="$PROJECT_ROOT$TARGET_DIR"
    
    # setup_agent_hooks.shを実行
    if [ -f "$PROJECT_ROOT/hooks/setup_agent_hooks.sh" ]; then
        "$PROJECT_ROOT/hooks/setup_agent_hooks.sh" "$AGENT_ID" "$FULL_TARGET_DIR" "$AGENT_TYPE"
    else
        echo "⚠️  Warning: setup_agent_hooks.sh not found, skipping hooks setup"
    fi
fi

# 5. テレメトリ設定に基づいてClaude起動
if [ "${OPENCODEAT_ENABLE_TELEMETRY}" = "false" ]; then
    echo "📊 Telemetry disabled - starting agent without telemetry"
    # bash/zsh対応プロンプト設定
    ./communication/agent_send.sh "$AGENT_ID" "if [ -n \"\$ZSH_VERSION\" ]; then"
    ./communication/agent_send.sh "$AGENT_ID" "  export PROMPT=$'%{\033[1;33m%}(${AGENT_ID})%{\033[0m%} %{\033[1;32m%}%~%{\033[0m%}$ '"
    ./communication/agent_send.sh "$AGENT_ID" "elif [ -n \"\$BASH_VERSION\" ]; then"
    ./communication/agent_send.sh "$AGENT_ID" "  export PS1='(\\[\\033[1;33m\\]${AGENT_ID}\\[\\033[0m\\]) \\[\\033[1;32m\\]\\w\\[\\033[0m\\]\\$ '"
    ./communication/agent_send.sh "$AGENT_ID" "fi"
    # Claude起動
    ./communication/agent_send.sh "$AGENT_ID" "claude --dangerously-skip-permissions $@"
    echo "✅ Agent $AGENT_ID started without telemetry at $TARGET_DIR"
else
    ./communication/agent_send.sh "$AGENT_ID" "\$OPENCODEAT_ROOT/telemetry/start_agent_with_telemetry.sh $AGENT_ID $TARGET_DIR $@"
    echo "✅ Agent $AGENT_ID started with telemetry at $TARGET_DIR"
fi