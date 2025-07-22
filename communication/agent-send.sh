#!/bin/bash

# 🧬 OpenCodeAT Agent間メッセージ送信システム
# HPC最適化用マルチエージェント通信

# directory_map.txt読み込み
load_agent_map() {
    local map_file="./Agent-shared/directory_map.txt"
    
    if [[ ! -f "$map_file" ]]; then
        echo "❌ エラー: directory_map.txt が見つかりません"
        echo "先に ./communication/setup.sh を実行してください"
        return 1
    fi
    
    # associative array宣言
    declare -gA AGENT_MAP
    
    # directory_map.txt解析
    while IFS= read -r line; do
        # コメントと空行をスキップ
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ -z "${line// }" ]] && continue
        
        # agent_name: session=xxx, pane=yyy 形式を解析
        if [[ "$line" =~ ^([^:]+):[[:space:]]*tmux_session=([^,]+),[[:space:]]*tmux_pane=(.+)$ ]]; then
            local agent_name="${BASH_REMATCH[1]// /}"
            local session="${BASH_REMATCH[2]// /}"
            local pane="${BASH_REMATCH[3]// /}"
            AGENT_MAP["$agent_name"]="$session:$pane"
        fi
    done < "$map_file"
}

# エージェント→tmuxターゲット変換
get_agent_target() {
    local agent_name="$1"
    
    # 大文字小文字を統一
    agent_name=$(echo "$agent_name" | tr '[:lower:]' '[:upper:]')
    
    # AGENT_MAPから取得
    if [[ -n "${AGENT_MAP[$agent_name]}" ]]; then
        echo "${AGENT_MAP[$agent_name]}"
    else
        echo ""
    fi
}

# エージェント役割取得
get_agent_role() {
    local agent_name="$1"
    
    case "${agent_name:0:2}" in
        "PM") echo "プロジェクト管理・要件定義" ;;
        "SE") echo "システム設計・監視" ;;
        "CI") echo "SSH・ビルド・実行" ;;
        "PG") echo "コード生成・最適化" ;;
        "CD") echo "GitHub・デプロイ管理" ;;
        *) echo "専門エージェント" ;;
    esac
}

# エージェント色コード取得
get_agent_color() {
    local agent_name="$1"
    
    case "${agent_name:0:2}" in
        "PM") echo "1;35" ;;  # マゼンタ
        "SE") echo "1;36" ;;  # シアン
        "CI") echo "1;33" ;;  # イエロー
        "PG") echo "1;32" ;;  # グリーン
        "CD") echo "1;31" ;;  # レッド
        *) echo "1;37" ;;     # ホワイト
    esac
}

# 使用方法表示
show_usage() {
    cat << EOF
🧬 OpenCodeAT Agent間メッセージ送信システム

使用方法:
  $0 [エージェント名] [メッセージ]
  $0 --list
  $0 --status
  $0 --broadcast [メッセージ]

基本コマンド:
  PM "requirement_definition.mdを確認してください"
  SE1 "監視状況を報告してください"
  CI1 "SSH接続を確認してください"
  PG1 "コード最適化を開始してください"
  CD "GitHub同期を実行してください"

特殊コマンド:
  --list        : 利用可能エージェント一覧表示
  --status      : 全エージェント状態確認
  --broadcast   : 全エージェントにメッセージ送信
  --help        : このヘルプを表示

メッセージ種別 (推奨フォーマット):
  [依頼] コンパイル実行お願いします
  [報告] SOTA更新: 285.7 GFLOPS達成
  [質問] visible_paths.txtの更新方法は？
  [完了] プロジェクト初期化完了しました

特殊コマンド (PMの管理用):
  "!cd /path/to/directory"              # エージェント再配置（記憶維持）
  
注意: 再配置は各エージェントの現在位置からの移動

例:
  $0 SE1 "[依頼] PG1.1.1にOpenMP最適化タスクを配布してください"
  $0 PG1 "[質問] OpenACCの並列化警告が出ています。どう対処しますか？"
  $0 CI1 "[報告] job_12345 実行完了、結果をchanges.mdに追記しました"
  
  # 再配置例（絶対パス）
  $0 PG1 "!cd /absolute/path/to/OpenCodeAT/Flow/TypeII/single-node/gcc/OpenMP_MPI"
  
  # 再配置例（相対パス - エージェントの現在位置から）
  $0 PG2 "!cd ../../../gcc/CUDA"          # 同階層の別戦略へ移動
  $0 SE1 "!cd ../multi-node"              # 上位階層へ移動
  
  $0 --broadcast "[緊急] 全エージェント状況報告してください"
EOF
}

# エージェント一覧表示
show_agents() {
    echo "📋 OpenCodeAT エージェント一覧:"
    echo "================================"
    
    if [[ ${#AGENT_MAP[@]} -eq 0 ]]; then
        echo "❌ エージェントが見つかりません"
        echo "先に ./communication/setup.sh を実行してください"
        return 1
    fi
    
    # エージェント種別ごとに表示
    local agent_types=("PM" "SE" "CI" "PG" "CD")
    
    for type in "${agent_types[@]}"; do
        echo ""
        echo "📍 ${type} エージェント:"
        local found=false
        
        for agent in "${!AGENT_MAP[@]}"; do
            if [[ "$agent" =~ ^${type}[0-9]*$ ]]; then
                local target="${AGENT_MAP[$agent]}"
                local role=$(get_agent_role "$agent")
                local color=$(get_agent_color "$agent")
                
                # セッション存在確認
                local session="${target%%:*}"
                if tmux has-session -t "$session" 2>/dev/null; then
                    echo -e "  \033[${color}m$agent\033[0m → $target ($role)"
                else
                    echo -e "  \033[${color}m$agent\033[0m → [未起動] ($role)"
                fi
                found=true
            fi
        done
        
        if [[ "$found" == false ]]; then
            echo "  (該当エージェントなし)"
        fi
    done
    
    echo ""
    echo "総エージェント数: ${#AGENT_MAP[@]}"
}

# エージェント状態確認
show_status() {
    echo "📊 OpenCodeAT エージェント状態:"
    echo "================================"
    
    if [[ ${#AGENT_MAP[@]} -eq 0 ]]; then
        echo "❌ エージェントが見つかりません"
        return 1
    fi
    
    local active_count=0
    local total_count=${#AGENT_MAP[@]}
    
    for agent in "${!AGENT_MAP[@]}"; do
        local target="${AGENT_MAP[$agent]}"
        local session="${target%%:*}"
        local pane="${target##*:}"
        
        # セッション・ペイン存在確認
        if tmux has-session -t "$session" 2>/dev/null; then
            if tmux list-panes -t "$session" -F "#{pane_index}" 2>/dev/null | grep -q "^$pane$"; then
                echo "✅ $agent : アクティブ"
                ((active_count++))
            else
                echo "⚠️  $agent : セッション存在、ペイン不明"
            fi
        else
            echo "❌ $agent : 未起動"
        fi
    done
    
    echo ""
    echo "アクティブ: $active_count / $total_count"
    
    # tmuxセッション情報
    echo ""
    echo "📺 tmuxセッション情報:"
    if tmux has-session -t opencodeat 2>/dev/null; then
        tmux list-sessions -F "#{session_name}: #{session_windows} windows" | grep opencodeat || echo "opencodeat: 情報取得失敗"
    else
        echo "opencodeat: 未起動"
    fi
}

# ブロードキャスト送信
broadcast_message() {
    local message="$1"
    local sent_count=0
    local failed_count=0
    
    echo "📢 ブロードキャスト送信開始: '$message'"
    echo "================================"
    
    for agent in "${!AGENT_MAP[@]}"; do
        local target="${AGENT_MAP[$agent]}"
        
        if send_message "$target" "$message" "$agent"; then
            ((sent_count++))
        else
            ((failed_count++))
        fi
    done
    
    echo ""
    echo "📊 ブロードキャスト結果:"
    echo "  成功: $sent_count"
    echo "  失敗: $failed_count"
    echo "  総計: ${#AGENT_MAP[@]}"
}

# メッセージ送信
send_message() {
    local target="$1"
    local message="$2"
    local agent_name="$3"
    
    local session="${target%%:*}"
    local pane="${target##*:}"
    
    # セッション存在確認
    if ! tmux has-session -t "$session" 2>/dev/null; then
        echo "❌ $agent_name: セッション '$session' が見つかりません"
        return 1
    fi
    
    # ペイン存在確認
    if ! tmux list-panes -t "$session" -F "#{pane_title}" 2>/dev/null | grep -q "^$pane$"; then
        echo "❌ $agent_name: ペイン '$pane' が見つかりません"
        return 1
    fi
    
    # メッセージ送信
    echo "📤 $agent_name ← '$message'"
    
    # Claude Codeのプロンプトを一度クリア
    tmux send-keys -t "$session:$pane" C-c 2>/dev/null
    sleep 0.2
    
    # メッセージ送信
    tmux send-keys -t "$session:$pane" "$message"
    sleep 0.1
    
    # エンター押下
    tmux send-keys -t "$session:$pane" C-m
    sleep 0.3
    
    return 0
}

# ログ記録
log_message() {
    local agent="$1"
    local message="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    mkdir -p ./communication/logs
    echo "[$timestamp] $agent: \"$message\"" >> ./communication/logs/send_log.txt
}

# メイン処理
main() {
    # directory_map.txt読み込み
    if ! load_agent_map; then
        exit 1
    fi
    
    # 引数チェック
    if [[ $# -eq 0 ]]; then
        show_usage
        exit 1
    fi
    
    # オプション処理
    case "$1" in
        --help|-h)
            show_usage
            exit 0
            ;;
        --list|-l)
            show_agents
            exit 0
            ;;
        --status|-s)
            show_status
            exit 0
            ;;
        --broadcast|-b)
            if [[ $# -lt 2 ]]; then
                echo "❌ ブロードキャスト用のメッセージが必要です"
                exit 1
            fi
            broadcast_message "$2"
            exit 0
            ;;
        *)
            if [[ $# -lt 2 ]]; then
                echo "❌ エージェント名とメッセージが必要です"
                show_usage
                exit 1
            fi
            ;;
    esac
    
    local agent_name="$1"
    local message="$2"
    
    # エージェント名を大文字に統一
    agent_name=$(echo "$agent_name" | tr '[:lower:]' '[:upper:]')
    
    # エージェントターゲット取得
    local target=$(get_agent_target "$agent_name")
    
    if [[ -z "$target" ]]; then
        echo "❌ エラー: 不明なエージェント '$agent_name'"
        echo "利用可能エージェント: $0 --list"
        exit 1
    fi
    
    # メッセージ送信
    if send_message "$target" "$message" "$agent_name"; then
        # ログ記録
        log_message "$agent_name" "$message"
        echo "✅ 送信完了: $agent_name"
    else
        echo "❌ 送信失敗: $agent_name"
        exit 1
    fi
}

main "$@"