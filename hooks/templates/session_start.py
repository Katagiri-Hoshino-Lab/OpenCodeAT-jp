#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 
# uvがある場合は以下で実行されます:
# #!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

"""
OpenCodeAT SessionStart Hook
各エージェントの.claude/hooks/に配置してsession_idを記録
"""

import json
import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime


def find_project_root(start_path):
    """プロジェクトルート（OpenCodeAT-jp）を探す"""
    current = Path(start_path).resolve()
    
    while current != current.parent:
        if (current / "CLAUDE.md").exists() and (current / "Agent-shared").exists():
            return current
        current = current.parent
    
    return None


def update_agent_table(session_id, source):
    """agent_and_pane_id_table.jsonlを更新"""
    cwd = Path.cwd()
    project_root = find_project_root(cwd)
    
    if not project_root:
        return None, None
    
    table_file = project_root / "Agent-shared" / "agent_and_pane_id_table.jsonl"
    
    # tmux環境変数から自分の情報を取得
    tmux_pane = os.getenv('TMUX_PANE', '')
    
    # デバッグ: 環境変数の状態を記録
    debug_file = project_root / "Agent-shared" / "session_start_debug.log"
    with open(debug_file, 'a') as f:
        f.write(f"\n[{datetime.utcnow()}] SessionStart hook called\n")
        f.write(f"session_id: {session_id}\n")
        f.write(f"source: {source}\n")
        f.write(f"cwd: {cwd}\n")
        f.write(f"TMUX_PANE: '{tmux_pane}'\n")
        f.write(f"project_root: {project_root}\n")
    
    if not tmux_pane:
        with open(debug_file, 'a') as f:
            f.write("ERROR: TMUX_PANE is empty, returning None\n")
        return None, None
    
    # ファイルを読み込んで更新
    updated_lines = []
    agent_id = None
    agent_type = None
    
    if table_file.exists():
        with open(table_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                    
                entry = json.loads(line)
                
                # 複数の方法でマッチングを試みる
                match_found = False
                
                # 方法1: 作業ディレクトリで判定（PMの場合）
                if str(cwd) == str(project_root) and entry['agent_id'] == 'PM':
                    match_found = True
                    with open(debug_file, 'a') as f:
                        f.write(f"MATCH by cwd (PM): entry='{entry['agent_id']}' cwd='{cwd}'\n")
                
                # 方法2: TMUX環境変数でのマッチング（セッション名とペイン番号を組み合わせ）
                if not match_found and tmux_pane:
                    # TMUX_PANEからグローバルペイン番号を取得
                    global_pane = tmux_pane.lstrip('%')
                    
                    # tmuxコマンドで現在のセッション情報を取得（可能な場合）
                    try:
                        result = subprocess.run(
                            ['tmux', 'list-panes', '-a', '-F', '#{session_name}:#{window_index}.#{pane_index} %#{pane_id}'],
                            capture_output=True, text=True
                        )
                        if result.returncode == 0:
                            for line in result.stdout.strip().split('\n'):
                                parts = line.split()
                                if len(parts) >= 2 and parts[1] == f'%{global_pane}':
                                    session_info = parts[0]  # e.g., "GEMM_PM:0.0"
                                    session_name = session_info.split(':')[0]
                                    pane_index = int(session_info.split('.')[-1])
                                    
                                    if (entry['tmux_session'] == session_name and 
                                        entry['tmux_pane'] == pane_index):
                                        match_found = True
                                        with open(debug_file, 'a') as f:
                                            f.write(f"MATCH by tmux: session={session_name}, pane={pane_index}\n")
                                        break
                    except Exception as e:
                        with open(debug_file, 'a') as f:
                            f.write(f"tmux command failed: {e}\n")
                
                if match_found:
                    with open(debug_file, 'a') as f:
                        f.write(f"Updating agent_id={entry['agent_id']} with session_id={session_id}\n")
                    
                    entry['claude_session_id'] = session_id
                    entry['status'] = 'running'
                    entry['last_updated'] = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
                    entry['cwd'] = str(cwd)
                    agent_id = entry['agent_id']
                    
                    # エージェントタイプを判定
                    if agent_id in ['PM', 'SE', 'CD'] or agent_id.startswith(('SE', 'CI', 'CD')):
                        agent_type = 'polling'
                    else:
                        agent_type = 'event-driven'
                    
                    # PMが初回起動時にプロジェクト開始時刻を記録
                    if agent_id == 'PM' and source == 'startup':
                        start_time_file = project_root / "Agent-shared" / "project_start_time.txt"
                        if not start_time_file.exists() or start_time_file.stat().st_size == 0:
                            start_time_file.write_text(datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ\n'))
                
                updated_lines.append(json.dumps(entry, ensure_ascii=False))
        
        # ファイルを書き戻す
        with open(table_file, 'w') as f:
            f.write('\n'.join(updated_lines) + '\n')
    
    return agent_id, agent_type


def get_required_files(agent_id):
    """エージェントに応じた必須ファイルリストを返す"""
    # 共通ファイル
    common_files = [
        "CLAUDE.md",
        "Agent-shared/directory_map.txt"
    ]
    
    # 役割を抽出（例: PG1.1.1 -> PG）
    role = agent_id.split('.')[0].rstrip('0123456789') if agent_id else ''
    
    role_files = {
        "PM": [
            "instructions/PM.md",
            "_remote_info/",
            "Agent-shared/typical_hpc_code.md",
            "Agent-shared/evolutional_flat_dir.md",
            "requirement_definition.md（存在する場合）"
        ],
        "SE": [
            "instructions/SE.md",
            "Agent-shared/changelog_analysis_template.py"
        ],
        "CI": [
            "instructions/CI.md",
            "_remote_info/*/command.md",
            "Agent-shared/ssh_guide.md",
            "Agent-shared/compile_warning_workflow.md"
        ],
        "PG": [
            "instructions/PG.md",
            "現在のディレクトリのChangeLog.md",
            "Agent-shared/ChangeLog_format.md",
            "Agent-shared/ChangeLog_format_PM_override.md（存在する場合）"
        ],
        "CD": [
            "instructions/CD.md"
        ],
        "ID": [
            "instructions/ID.md"
        ]
    }
    
    files = common_files.copy()
    if role in role_files:
        files.extend(role_files[role])
    
    return files


def generate_context(source, agent_id, agent_type):
    """セッション開始時のコンテキストを生成"""
    context_parts = []
    
    if source in ['startup', 'clear']:
        context_parts.append("## ⚠️ セッション開始")
        context_parts.append("")
        context_parts.append("OpenCodeATエージェントとして起動しました。")
        context_parts.append("以下の手順で必須ファイルを読み込んでください：")
        context_parts.append("")
        
        # 必須ファイルリスト
        files = get_required_files(agent_id)
        context_parts.append("### 1. 必須ファイルの再読み込み")
        for file in files:
            context_parts.append(f"- {file}")
        
        context_parts.append("")
        context_parts.append("### 2. ディレクトリ構造の確認")
        context_parts.append("```bash")
        context_parts.append("pwd  # 現在位置確認")
        context_parts.append("ls -R ../../../../Agent-shared/")
        context_parts.append("ls -R ../../../../instructions/")
        context_parts.append("```")
        
        if agent_type == 'polling':
            context_parts.append("")
            context_parts.append("### 3. ポーリング型エージェントとしての再開")
            context_parts.append("あなたはポーリング型エージェントです。")
            context_parts.append("待機状態に入らず、定期的にタスクを確認してください。")
    
    return "\n".join(context_parts) if context_parts else None


def main():
    try:
        # 入力を読み込み
        input_data = json.load(sys.stdin)
        session_id = input_data.get('session_id')
        source = input_data.get('source', 'startup')  # startup(新規起動), resume(--continue), clear(/clear)
        
        # テーブルを更新してエージェント情報を取得
        agent_id, agent_type = update_agent_table(session_id, source)
        
        # コンテキストを生成
        context = generate_context(source, agent_id, agent_type)
        
        if context:
            # コンテキストを追加
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": context
                }
            }
            print(json.dumps(output, ensure_ascii=False))
        
        sys.exit(0)
        
    except Exception:
        # エラーは静かに処理
        sys.exit(0)


if __name__ == "__main__":
    main()