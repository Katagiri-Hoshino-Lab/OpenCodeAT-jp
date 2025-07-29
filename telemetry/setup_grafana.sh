#!/bin/bash
# Grafanaローカル環境セットアップスクリプト

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 色付きログ関数
log_info() {
    echo -e "\033[1;32m[INFO]\033[0m $1"
}

log_success() {
    echo -e "\033[1;34m[SUCCESS]\033[0m $1"
}

log_error() {
    echo -e "\033[1;31m[ERROR]\033[0m $1"
}

# 使用方法表示
show_usage() {
    cat << EOF
📊 OpenCodeAT Grafana環境セットアップ

使用方法:
  $0 [オプション]

オプション:
  --check-only   : 設定確認のみ（Docker起動しない）
  --reset        : 既存のコンテナを削除して再作成
  --help         : このヘルプを表示

このスクリプトは以下を自動的に実行します：
1. .envファイルの確認・作成
2. Docker環境の確認
3. Grafana + Prometheus + OTel Collectorの起動
4. 接続情報の表示

EOF
}

# .env設定確認・作成
setup_env() {
    log_info "📝 OpenTelemetry設定を確認中..."
    
    cd "$SCRIPT_DIR"
    
    if [ -f "otel_config.env" ]; then
        log_success "既存の otel_config.env を使用します"
    elif [ -f "otel_config.env.example" ]; then
        cp otel_config.env.example otel_config.env
        log_success "otel_config.env を作成しました"
    else
        log_error "otel_config.env.example が見つかりません"
        exit 1
    fi
    
    # デフォルト設定の確認
    if grep -q "OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317" otel_config.env; then
        log_info "✅ デフォルトのローカルエンドポイント設定を確認"
    else
        log_info "⚠️  カスタムエンドポイントが設定されています"
        grep "OTEL_EXPORTER_OTLP_ENDPOINT" otel_config.env || true
    fi
}

# Docker環境確認
check_docker() {
    log_info "🐳 Docker環境を確認中..."
    
    if ! command -v docker &> /dev/null; then
        log_error "Dockerがインストールされていません"
        echo "Dockerのインストール方法: https://docs.docker.com/get-docker/"
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        log_error "Dockerデーモンが起動していません"
        echo "Docker Desktopを起動してください"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null 2>&1; then
        log_error "Docker Composeがインストールされていません"
        exit 1
    fi
    
    log_success "Docker環境の確認完了"
}

# Grafana環境起動
start_grafana() {
    log_info "🚀 Grafana環境を起動中..."
    
    cd "$SCRIPT_DIR"
    
    # Docker Compose v2の場合
    if docker compose version &> /dev/null 2>&1; then
        docker compose up -d
    else
        docker-compose up -d
    fi
    
    # 起動確認
    sleep 5
    
    if docker ps | grep -q "grafana"; then
        log_success "✅ Grafana環境の起動完了"
    else
        log_error "Grafana環境の起動に失敗しました"
        docker logs opencodeat-grafana 2>&1 | tail -20
        exit 1
    fi
}

# 接続情報表示
show_connection_info() {
    echo ""
    echo "=================================================="
    echo "📊 OpenCodeAT Grafana環境が起動しました"
    echo "=================================================="
    echo ""
    echo "🌐 アクセスURL:"
    echo "   Grafana: http://localhost:3000"
    echo "   ユーザー名: admin"
    echo "   パスワード: admin"
    echo ""
    echo "📡 エージェント接続設定:"
    echo "   OTLP エンドポイント: http://localhost:4317"
    echo ""
    echo "🔧 コンテナ管理:"
    echo "   状態確認: docker ps"
    echo "   ログ確認: docker logs [コンテナ名]"
    echo "   停止: cd $SCRIPT_DIR && docker compose down"
    echo ""
    echo "📈 メトリクス確認方法:"
    echo "   1. http://localhost:3000 にアクセス"
    echo "   2. 左メニューから「Explore」を選択"
    echo "   3. データソース「Prometheus」を選択"
    echo "   4. メトリクス名を入力（例: agent_token_usage）"
    echo ""
}

# リセット処理
reset_containers() {
    log_info "🔄 既存のコンテナを削除中..."
    
    cd "$SCRIPT_DIR"
    
    if docker compose version &> /dev/null 2>&1; then
        docker compose down -v
    else
        docker-compose down -v
    fi
    
    log_success "既存のコンテナを削除しました"
}

# メイン処理
main() {
    case "${1:-}" in
        --help|-h)
            show_usage
            exit 0
            ;;
        --check-only)
            setup_env
            check_docker
            log_success "設定確認完了"
            exit 0
            ;;
        --reset)
            check_docker
            reset_containers
            setup_env
            start_grafana
            show_connection_info
            ;;
        "")
            setup_env
            check_docker
            start_grafana
            show_connection_info
            ;;
        *)
            log_error "不明なオプション: $1"
            show_usage
            exit 1
            ;;
    esac
}

main "$@"