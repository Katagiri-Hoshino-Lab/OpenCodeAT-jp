#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "matplotlib",
#     "numpy",
# ]
# ///

"""
OpenCodeAT コンテキスト使用率監視システム
Claude Code JSONLログからトークン使用状況を解析し、各種グラフで可視化

機能:
1. ~/.claude/projects/ 以下のJSONLログを監視
2. usage情報を抽出して累積トークン数を計算
3. 多様なグラフ形式で可視化（積み上げ棒、折れ線、概要）
4. auto-compact（160K前後）の予測
5. 軽量キャッシュシステム（オプション）
6. クイックステータス確認機能
"""

import json
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
import argparse
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from collections import defaultdict, OrderedDict
from typing import Dict, List, Tuple, Optional
import numpy as np
import pickle
import gzip

# グラフスタイル設定
plt.style.use('seaborn-v0_8-darkgrid')
plt.rcParams['figure.figsize'] = (14, 10)
plt.rcParams['font.size'] = 10

class ContextUsageMonitor:
    """コンテキスト使用率監視クラス"""
    
    # Claude Codeのコンテキスト制限
    CONTEXT_LIMIT = 200000  # 200Kトークン（表示用）
    AUTO_COMPACT_THRESHOLD = 160000  # 実際のauto-compact発生点（推定）
    WARNING_THRESHOLD = 140000  # 警告閾値
    
    def __init__(self, project_root: Path, use_cache: bool = True):
        self.project_root = project_root
        self.claude_projects_dir = Path.home() / ".claude" / "projects"
        self.output_dir = project_root / "User-shared" / "visualizations"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # キャッシュ設定
        self.use_cache = use_cache
        self.cache_dir = project_root / ".cache" / "context_monitor"
        if self.use_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def get_cache_path(self, agent_id: str, jsonl_file: Path) -> Path:
        """キャッシュファイルパスを生成"""
        cache_name = f"{agent_id}_{jsonl_file.stem}.pkl.gz"
        return self.cache_dir / cache_name
    
    def load_from_cache(self, cache_path: Path, jsonl_file: Path) -> Optional[List[Dict]]:
        """キャッシュからデータを読み込み"""
        if not self.use_cache or not cache_path.exists():
            return None
            
        # ファイルの更新時刻を比較
        cache_mtime = cache_path.stat().st_mtime
        jsonl_mtime = jsonl_file.stat().st_mtime
        
        if jsonl_mtime > cache_mtime:
            return None  # JSONLの方が新しい
            
        try:
            with gzip.open(cache_path, 'rb') as f:
                return pickle.load(f)
        except:
            return None
    
    def save_to_cache(self, cache_path: Path, data: List[Dict]):
        """データをキャッシュに保存"""
        if not self.use_cache:
            return
            
        try:
            with gzip.open(cache_path, 'wb') as f:
                pickle.dump(data, f)
        except:
            pass  # キャッシュ失敗は無視
    
    def find_project_jsonl_files(self) -> Dict[str, List[Path]]:
        """プロジェクトディレクトリからJSONLファイルを検索"""
        jsonl_files = {}
        
        # プロジェクトディレクトリ名を生成（パスの / を - に変換）
        # Claude projectsディレクトリの命名規則: /mnt/... → -mnt-...
        project_dir_name = str(self.project_root).replace('/', '-')
            
        project_claude_dir = self.claude_projects_dir / project_dir_name
        
        if not project_claude_dir.exists():
            print(f"⚠️  Warning: Project directory not found: {project_claude_dir}")
            return jsonl_files
            
        # session_idとエージェントの対応を取得
        agent_sessions = self.get_agent_sessions()
        
        # JSONLファイルを検索
        for jsonl_file in project_claude_dir.glob("*.jsonl"):
            session_id = jsonl_file.stem
            
            # session_idからエージェントを特定
            agent_id = agent_sessions.get(session_id, f"Unknown_{session_id[:8]}")
            
            if agent_id not in jsonl_files:
                jsonl_files[agent_id] = []
            jsonl_files[agent_id].append(jsonl_file)
            
        return jsonl_files
    
    def get_agent_sessions(self) -> Dict[str, str]:
        """agent_and_pane_id_table.jsonlからsession_idとagent_idの対応を取得"""
        sessions = {}
        
        agent_table_path = self.project_root / "Agent-shared" / "agent_and_pane_id_table.jsonl"
        if agent_table_path.exists():
            with open(agent_table_path, 'r') as f:
                for line in f:
                    if line.strip() and not line.startswith('#'):
                        try:
                            data = json.loads(line)
                            session_id = data.get('claude_session_id')
                            agent_id = data.get('agent_id')
                            if session_id and agent_id:
                                sessions[session_id] = agent_id
                        except json.JSONDecodeError:
                            continue
                            
        return sessions
    
    def parse_usage_data(self, jsonl_file: Path, agent_id: str, last_n: Optional[int] = None) -> List[Dict]:
        """JSONLファイルからusage情報を抽出（キャッシュ対応）"""
        
        # キャッシュチェック
        cache_path = self.get_cache_path(agent_id, jsonl_file)
        cached_data = self.load_from_cache(cache_path, jsonl_file)
        if cached_data is not None:
            # last_n適用
            if last_n and len(cached_data) > last_n:
                return cached_data[-last_n:]
            return cached_data
        
        # 通常の解析処理
        all_entries = []
        with open(jsonl_file, 'r') as f:
            for line in f:
                if line.strip():
                    try:
                        entry = json.loads(line)
                        # usageフィールドを持つエントリのみ
                        if 'message' in entry and isinstance(entry['message'], dict):
                            msg = entry['message']
                            if 'usage' in msg and isinstance(msg['usage'], dict) and 'timestamp' in entry:
                                all_entries.append({
                                    'timestamp': entry['timestamp'],
                                    'usage': msg['usage']
                                })
                    except (json.JSONDecodeError, KeyError, TypeError):
                        continue
        
        # キャッシュに保存
        self.save_to_cache(cache_path, all_entries)
        
        # last_n適用
        if last_n and len(all_entries) > last_n:
            return all_entries[-last_n:]
        return all_entries
    
    def calculate_cumulative_tokens(self, usage_entries: List[Dict], cumulative: bool = False) -> List[Tuple[datetime, Dict[str, int]]]:
        """トークン数を計算（累積またはスナップショット）"""
        token_data = []
        total_input = 0
        total_cache_creation = 0
        total_cache_read = 0
        total_output = 0
        
        for entry in usage_entries:
            # タイムスタンプ変換
            ts = datetime.fromisoformat(entry['timestamp'].replace('Z', '+00:00'))
            
            usage = entry['usage']
            
            if cumulative:
                # 累積モード（従来の動作）
                total_input += usage.get('input_tokens', 0)
                total_cache_creation += usage.get('cache_creation_input_tokens', 0)
                total_cache_read += usage.get('cache_read_input_tokens', 0)
                total_output += usage.get('output_tokens', 0)
                
                token_data.append((ts, {
                    'input': total_input,
                    'cache_creation': total_cache_creation,
                    'cache_read': total_cache_read,
                    'output': total_output,
                    'total': total_input + total_cache_creation + total_cache_read + total_output
                }))
            else:
                # スナップショットモード（各時点のコンテキスト使用量）
                input_tokens = usage.get('input_tokens', 0)
                cache_creation = usage.get('cache_creation_input_tokens', 0)
                cache_read = usage.get('cache_read_input_tokens', 0)
                output = usage.get('output_tokens', 0)
                
                token_data.append((ts, {
                    'input': input_tokens,
                    'cache_creation': cache_creation,
                    'cache_read': cache_read,
                    'output': output,
                    'total': input_tokens + cache_creation + cache_read + output
                }))
            
        return token_data
    
    def generate_all_graphs(self, all_agent_data: Dict[str, List[Tuple[datetime, Dict[str, int]]]],
                           graph_type: str = 'all', time_unit: str = 'minutes', cumulative: bool = False):
        """指定されたタイプのグラフを生成"""
        self.is_cumulative = cumulative
        
        if graph_type in ['all', 'overview']:
            self.generate_overview_line_graph(all_agent_data, time_unit)
            
        if graph_type in ['all', 'stacked']:
            # デフォルトはカウントベース（トークン数の明記があるログ）
            self.generate_stacked_bar_chart(all_agent_data, x_axis='count')
            self.generate_stacked_bar_chart(all_agent_data, x_axis='time')
            
        if graph_type in ['all', 'timeline']:
            self.generate_timeline_graph(all_agent_data)
            
        if graph_type in ['all', 'individual']:
            # 各エージェントの個別グラフを生成
            for agent_id, cumulative_data in all_agent_data.items():
                if cumulative_data:
                    self.generate_agent_detail_graphs(agent_id, cumulative_data)
    
    def generate_overview_line_graph(self, all_agent_data: Dict[str, List[Tuple[datetime, Dict[str, int]]]], 
                                    time_unit: str = 'minutes'):
        """概要用の軽量な折れ線グラフ（ステップスタイル）
        
        Args:
            time_unit: 'seconds', 'minutes', 'hours' のいずれか（デフォルト: 'minutes'）
        """
        plt.figure(figsize=(12, 8))
        
        # プロジェクト開始時刻を取得
        start_time_file = self.project_root / "Agent-shared" / "project_start_time.txt"
        project_start = None
        
        if start_time_file.exists():
            try:
                with open(start_time_file, 'r') as f:
                    time_str = f.read().strip()
                    project_start = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
            except:
                pass
        
        # ファイルがない場合は全データの最も古いタイムスタンプを使用
        if project_start is None:
            print("⚠️  Warning: project_start_time.txt not found. Using earliest log timestamp.")
            for agent_data in all_agent_data.values():
                if agent_data and (project_start is None or agent_data[0][0] < project_start):
                    project_start = agent_data[0][0]
        
        # プロジェクト開始時刻以降のデータのみをフィルタリング
        filtered_agent_data = {}
        for agent_id, cumulative_data in all_agent_data.items():
            filtered_data = [(t, tokens) for t, tokens in cumulative_data if t >= project_start]
            if filtered_data:
                filtered_agent_data[agent_id] = filtered_data
        
        # 各エージェントの総トークン数の推移
        for agent_id, cumulative_data in filtered_agent_data.items():
            if not cumulative_data:
                continue
                
            # 相対時間に変換（デフォルトは分単位）
            time_divisor = {'seconds': 1, 'minutes': 60, 'hours': 3600}[time_unit]
            times = [(t - project_start).total_seconds() / time_divisor for t, _ in cumulative_data]
            totals = [tokens['total'] for _, tokens in cumulative_data]
            
            # ステップスタイル（階段状）の折れ線グラフ
            plt.step(times, totals, where='post', marker='o', markersize=3, 
                    label=agent_id, alpha=0.8)
        
        # 閾値ライン
        plt.axhline(y=self.AUTO_COMPACT_THRESHOLD, color='red', 
                   linestyle='--', linewidth=2, label='Auto-compact (~160K)')
        plt.axhline(y=self.WARNING_THRESHOLD, color='orange', 
                   linestyle='--', linewidth=1, label='Warning (140K)')
        
        # X軸ラベル（単位に応じて変更）
        unit_labels = {'seconds': 'Seconds', 'minutes': 'Minutes', 'hours': 'Hours'}
        plt.xlabel(f'{unit_labels[time_unit]} from Project Start')
        
        # Y軸ラベル（累積モードで変更）
        if hasattr(self, 'is_cumulative') and self.is_cumulative:
            plt.ylabel('Cumulative Token Usage')
            plt.title('Cumulative Token Usage Over Time')
        else:
            plt.ylabel('Current Context Usage [tokens]')
            plt.title('Context Usage Monitor')
        plt.legend(loc='upper left', bbox_to_anchor=(1.02, 1))
        plt.grid(True, alpha=0.3)
        plt.gca().yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{int(x/1000)}K'))
        
        plt.tight_layout()
        output_path = self.output_dir / "context_usage_overview.png"
        plt.savefig(output_path, dpi=120, bbox_inches='tight')
        plt.close()
        
        print(f"✅ 概要グラフ生成: {output_path}")
    
    def generate_stacked_bar_chart(self, all_agent_data: Dict[str, List[Tuple[datetime, Dict[str, int]]]],
                                  x_axis: str = 'count'):
        """積み上げ棒グラフ（静的なものを下に配置）"""
        fig, ax = plt.subplots(figsize=(16, 10))
        
        # カラーマップ（静的→動的の順）
        token_types = ['cache_read', 'cache_creation', 'input', 'output']
        token_colors = {
            'cache_read': '#f39c12',     # オレンジ（最も静的）
            'cache_creation': '#2ecc71',  # 緑
            'input': '#3498db',          # 青
            'output': '#e74c3c'          # 赤（最も動的）
        }
        
        if x_axis == 'count':
            # ログ回数ベースの棒グラフ
            bar_width = 0.8
            agent_positions = {}
            
            for idx, (agent_id, cumulative_data) in enumerate(all_agent_data.items()):
                if not cumulative_data:
                    continue
                    
                # 最新のデータポイントを使用
                latest_time, latest_tokens = cumulative_data[-1]
                
                # X軸の位置
                x_pos = idx
                agent_positions[agent_id] = x_pos
                
                # 積み上げ棒グラフ（静的なものから）
                bottom = 0
                for token_type in token_types:
                    value = latest_tokens[token_type]
                    ax.bar(x_pos, value, bar_width, bottom=bottom,
                          color=token_colors[token_type], 
                          label=token_type if idx == 0 else "")
                    bottom += value
                
                # 合計値をバーの上に表示
                total = latest_tokens['total']
                percentage = (total / self.AUTO_COMPACT_THRESHOLD) * 100
                ax.text(x_pos, total + 2000, f'{total:,}\n({percentage:.1f}%)', 
                       ha='center', va='bottom', fontsize=9)
            
            ax.set_xticks(list(agent_positions.values()))
            ax.set_xticklabels(list(agent_positions.keys()))
            ax.set_xlabel('Agents')
            
        else:  # x_axis == 'time'
            # 時間ベースの積み上げ面グラフ
            # 最もトークン数が多いエージェントを選択
            max_agent = max(all_agent_data.items(), 
                          key=lambda x: x[1][-1][1]['total'] if x[1] else 0)[0]
            
            if all_agent_data[max_agent]:
                data = all_agent_data[max_agent]
                times = [t for t, _ in data]
                
                # 各トークンタイプの値を取得
                token_values = {tt: [tokens[tt] for _, tokens in data] for tt in token_types}
                
                # 積み上げ面グラフ
                bottom = np.zeros(len(times))
                for token_type in token_types:
                    values = np.array(token_values[token_type])
                    ax.fill_between(times, bottom, bottom + values, 
                                   color=token_colors[token_type],
                                   label=token_type, alpha=0.8)
                    bottom += values
                
                ax.set_xlabel('Time')
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %H:%M'))
                plt.xticks(rotation=45)
                ax.set_title(f'Token Usage Timeline - {max_agent}')
        
        # 共通設定
        ax.axhline(y=self.AUTO_COMPACT_THRESHOLD, color='red', 
                  linestyle='--', linewidth=2, label='Auto-compact (~160K)')
        ax.axhline(y=self.WARNING_THRESHOLD, color='orange', 
                  linestyle='--', linewidth=1, label='Warning (140K)')
        
        ax.set_ylabel('Cumulative Tokens')
        ax.set_title(f'OpenCodeAT Token Usage (X-axis: {x_axis})')
        ax.legend(loc='upper left', bbox_to_anchor=(1.02, 1))
        ax.grid(True, alpha=0.3, axis='y')
        ax.set_ylim(0, self.CONTEXT_LIMIT * 1.05)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{int(x/1000)}K'))
        
        plt.tight_layout()
        output_path = self.output_dir / f"context_usage_stacked_{x_axis}.png"
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        print(f"✅ 積み上げグラフ生成（{x_axis}軸）: {output_path}")
    
    def generate_timeline_graph(self, all_agent_data: Dict[str, List[Tuple[datetime, Dict[str, int]]]]):
        """auto-compact予測に特化したタイムライングラフ"""
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), 
                                       gridspec_kw={'height_ratios': [2, 1]})
        
        # 上段: 全エージェントの推移
        for agent_id, cumulative_data in all_agent_data.items():
            if not cumulative_data:
                continue
                
            times = [t for t, _ in cumulative_data]
            totals = [tokens['total'] for _, tokens in cumulative_data]
            
            # 現在の使用率に応じて色を変える
            current_usage = totals[-1] if totals else 0
            if current_usage >= self.AUTO_COMPACT_THRESHOLD * 0.95:
                color = 'red'
                alpha = 1.0
            elif current_usage >= self.WARNING_THRESHOLD:
                color = 'orange'
                alpha = 0.8
            else:
                color = 'blue'
                alpha = 0.6
                
            ax1.step(times, totals, where='post', marker='o', markersize=3, 
                    label=f'{agent_id} ({current_usage/1000:.0f}K)', 
                    color=color, alpha=alpha)
        
        ax1.axhline(y=self.AUTO_COMPACT_THRESHOLD, color='red', 
                   linestyle='--', linewidth=2)
        ax1.set_ylabel('Total Tokens')
        ax1.set_title('Context Usage Timeline & Auto-compact Prediction')
        ax1.legend(loc='upper left', bbox_to_anchor=(1.02, 1))
        ax1.grid(True, alpha=0.3)
        ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{int(x/1000)}K'))
        
        # 下段: 増加率の可視化
        self._plot_growth_rates(ax2, all_agent_data)
        
        plt.tight_layout()
        output_path = self.output_dir / "context_usage_timeline.png"
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        print(f"✅ タイムライングラフ生成: {output_path}")
    
    def generate_agent_detail_graphs(self, agent_id: str, cumulative_data: List[Tuple[datetime, Dict[str, int]]]):
        """個別エージェントの詳細グラフ（2種類）"""
        
        # 1. 時系列積み上げ面グラフ
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), 
                                       gridspec_kw={'height_ratios': [2, 1]})
        
        times = [t for t, _ in cumulative_data]
        
        # カラーマップ（静的→動的の順）
        token_types = ['cache_read', 'cache_creation', 'input', 'output']
        token_colors = {
            'cache_read': '#f39c12',     # オレンジ
            'cache_creation': '#2ecc71',  # 緑
            'input': '#3498db',          # 青
            'output': '#e74c3c'          # 赤
        }
        
        # 上段: 積み上げ面グラフ
        token_values = {tt: [tokens[tt] for _, tokens in cumulative_data] for tt in token_types}
        bottom = np.zeros(len(times))
        
        for token_type in token_types:
            values = np.array(token_values[token_type])
            ax1.fill_between(times, bottom, bottom + values, 
                           color=token_colors[token_type],
                           label=token_type, alpha=0.8)
            bottom += values
        
        # 最新の統計情報
        latest_tokens = cumulative_data[-1][1]
        total = latest_tokens['total']
        percentage = (total / self.AUTO_COMPACT_THRESHOLD) * 100
        
        # 閾値ライン
        ax1.axhline(y=self.AUTO_COMPACT_THRESHOLD, color='red', 
                   linestyle='--', linewidth=2, label='Auto-compact')
        ax1.axhline(y=self.WARNING_THRESHOLD, color='orange', 
                   linestyle='--', linewidth=1, label='Warning')
        
        ax1.set_ylabel('Cumulative Tokens')
        ax1.set_title(f'{agent_id} - Token Usage Detail ({total:,} tokens, {percentage:.1f}%)')
        ax1.legend(loc='upper left')
        ax1.grid(True, alpha=0.3)
        ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{int(x/1000)}K'))
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %H:%M'))
        
        # 下段: 各トークンタイプの割合推移
        self._plot_token_ratios(ax2, cumulative_data, token_types)
        
        plt.tight_layout()
        output_path = self.output_dir / f"context_usage_{agent_id}_detail.png"
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        # 2. ログ回数ベースのグラフ
        self._generate_count_based_graph(agent_id, cumulative_data)
        
        print(f"✅ {agent_id} の個別グラフ生成完了")
    
    def _plot_token_ratios(self, ax, cumulative_data: List[Tuple[datetime, Dict[str, int]]], 
                          token_types: List[str]):
        """トークンタイプの割合推移をプロット"""
        times = [t for t, _ in cumulative_data]
        
        # 各時点での割合を計算
        ratios = {tt: [] for tt in token_types}
        
        for _, tokens in cumulative_data:
            total = tokens['total']
            if total > 0:
                for tt in token_types:
                    ratios[tt].append(100 * tokens[tt] / total)
            else:
                for tt in token_types:
                    ratios[tt].append(0)
        
        # 割合の推移をプロット
        for token_type in token_types:
            ax.plot(times, ratios[token_type], marker='o', markersize=3, 
                   label=f'{token_type} %', alpha=0.7)
        
        ax.set_xlabel('Time')
        ax.set_ylabel('Token Type Ratio (%)')
        ax.set_title('Token Type Distribution Over Time')
        ax.legend(loc='upper left', bbox_to_anchor=(1.02, 1))
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %H:%M'))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)
        ax.set_ylim(0, 100)
    
    def _generate_count_based_graph(self, agent_id: str, cumulative_data: List[Tuple[datetime, Dict[str, int]]]):
        """ログ回数ベースのグラフ"""
        fig, ax = plt.subplots(figsize=(12, 8))
        
        # X軸: ログエントリ番号
        log_counts = list(range(1, len(cumulative_data) + 1))
        totals = [tokens['total'] for _, tokens in cumulative_data]
        
        # 色分け（使用率に応じて）
        colors = []
        for total in totals:
            if total >= self.AUTO_COMPACT_THRESHOLD * 0.95:
                colors.append('red')
            elif total >= self.WARNING_THRESHOLD:
                colors.append('orange')
            else:
                colors.append('blue')
        
        # 散布図と線
        ax.scatter(log_counts, totals, c=colors, s=50, alpha=0.7, edgecolors='black')
        ax.plot(log_counts, totals, 'b-', alpha=0.3)
        
        # 閾値ライン
        ax.axhline(y=self.AUTO_COMPACT_THRESHOLD, color='red', 
                  linestyle='--', linewidth=2, label='Auto-compact')
        ax.axhline(y=self.WARNING_THRESHOLD, color='orange', 
                  linestyle='--', linewidth=1, label='Warning')
        
        ax.set_xlabel('Log Entry Count')
        ax.set_ylabel('Total Tokens')
        ax.set_title(f'{agent_id} - Token Usage by Log Count')
        ax.legend()
        ax.grid(True, alpha=0.3)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{int(x/1000)}K'))
        
        plt.tight_layout()
        output_path = self.output_dir / f"context_usage_{agent_id}_count.png"
        plt.savefig(output_path, dpi=120, bbox_inches='tight')
        plt.close()
    
    def _plot_growth_rates(self, ax, all_agent_data: Dict[str, List[Tuple[datetime, Dict[str, int]]]]):
        """トークン増加率を可視化"""
        
        for agent_id, cumulative_data in all_agent_data.items():
            if len(cumulative_data) < 2:
                continue
                
            times = [t for t, _ in cumulative_data]
            totals = [tokens['total'] for _, tokens in cumulative_data]
            
            # 増加率を計算（トークン/時間）
            growth_rates = []
            growth_times = []
            
            for i in range(1, len(times)):
                time_diff = (times[i] - times[i-1]).total_seconds() / 3600  # 時間単位
                if time_diff > 0:
                    token_diff = totals[i] - totals[i-1]
                    rate = token_diff / time_diff
                    growth_rates.append(rate)
                    growth_times.append(times[i])
            
            if growth_rates:
                ax.plot(growth_times, growth_rates, marker='o', markersize=3, 
                       label=agent_id, alpha=0.7)
        
        ax.set_xlabel('Time')
        ax.set_ylabel('Growth Rate (tokens/hour)')
        ax.set_title('Token Growth Rate Analysis')
        ax.legend(loc='upper left', bbox_to_anchor=(1.02, 1))
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %H:%M'))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)
    
    def generate_summary_report(self, all_agent_data: Dict[str, List[Tuple[datetime, Dict[str, int]]]]):
        """サマリーレポートをMarkdown形式で生成"""
        report_path = self.output_dir / "context_usage_report.md"
        
        with open(report_path, 'w') as f:
            # タイトル（累積モードで変更）
            if hasattr(self, 'is_cumulative') and self.is_cumulative:
                f.write("# 累積トークン使用量レポート\n\n")
            else:
                f.write("# コンテキスト使用状況レポート\n\n")
            
            f.write(f"生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            f.write("## サマリー\n\n")
            f.write("| エージェント | 合計 [トークン] | 使用率 | Cache Read | Cache Create | Input | Output | 推定時間 |\n")
            f.write("|-------------|----------------|--------|------------|--------------|-------|--------|----------|\n")
            
            # エージェントデータを整理
            agent_summaries = []
            
            for agent_id, cumulative_data in all_agent_data.items():
                if not cumulative_data:
                    continue
                    
                latest_time, latest_tokens = cumulative_data[-1]
                total = latest_tokens['total']
                percentage = (total / self.AUTO_COMPACT_THRESHOLD) * 100
                
                # auto-compactまでの推定時間
                est_hours = "N/A"
                if len(cumulative_data) >= 2:
                    # 直近の増加率から推定
                    recent_data = cumulative_data[-min(10, len(cumulative_data)):]
                    time_span = (recent_data[-1][0] - recent_data[0][0]).total_seconds() / 3600
                    token_increase = recent_data[-1][1]['total'] - recent_data[0][1]['total']
                    
                    if time_span > 0 and token_increase > 0:
                        rate = token_increase / time_span
                        remaining_tokens = self.AUTO_COMPACT_THRESHOLD - total
                        if remaining_tokens > 0:
                            est_hours = f"{remaining_tokens / rate:.1f}h"
                
                # 状態アイコン（累積モードでは常に緑）
                if hasattr(self, 'is_cumulative') and self.is_cumulative:
                    status = "🟢"  # 累積モードでは閾値判定なし
                else:
                    if total >= self.AUTO_COMPACT_THRESHOLD * 0.95:
                        status = "🔴"
                    elif total >= self.WARNING_THRESHOLD:
                        status = "🟡"
                    else:
                        status = "🟢"
                
                agent_summaries.append({
                    'agent_id': agent_id,
                    'status': status,
                    'total': total,
                    'percentage': percentage,
                    'tokens': latest_tokens,
                    'est_hours': est_hours
                })
            
            # トークン数でソート
            agent_summaries.sort(key=lambda x: x['total'], reverse=True)
            
            for summary in agent_summaries:
                f.write(f"| {summary['status']} {summary['agent_id']} | "
                       f"{summary['total']:,} | "
                       f"{summary['percentage']:.1f}% | "
                       f"{summary['tokens']['cache_read']:,} | "
                       f"{summary['tokens']['cache_creation']:,} | "
                       f"{summary['tokens']['input']:,} | "
                       f"{summary['tokens']['output']:,} | "
                       f"{summary['est_hours']} |\n")
            
            f.write("\n## Visualizations\n\n")
            f.write("### Global Views\n")
            f.write("- [Overview](context_usage_overview.png) - 軽量な折れ線グラフ\n")
            f.write("- [Stacked by Count](context_usage_stacked_count.png) - エージェント別積み上げ\n")
            f.write("- [Stacked by Time](context_usage_stacked_time.png) - 時系列積み上げ\n")
            f.write("- [Timeline](context_usage_timeline.png) - 予測とトレンド分析\n\n")
            
            f.write("### Individual Agent Details\n")
            for agent_id in sorted(all_agent_data.keys()):
                f.write(f"- {agent_id}: [Detail](context_usage_{agent_id}_detail.png) | "
                       f"[Count](context_usage_{agent_id}_count.png)\n")
            
            f.write("\n## Quick Access Commands\n\n")
            f.write("```bash\n")
            f.write("# 最新状態の確認（テキスト出力）\n")
            f.write("python telemetry/context_usage_monitor.py --status\n\n")
            f.write("# 特定エージェントの状態確認\n")
            f.write("python telemetry/context_usage_monitor.py --status --agent PG1.1.1\n\n")
            f.write("# 概要グラフのみ生成（軽量）\n")
            f.write("python telemetry/context_usage_monitor.py --graph-type overview\n")
            f.write("```\n\n")
            
            f.write("## Cache Status\n\n")
            if self.use_cache and self.cache_dir.exists():
                cache_size = sum(f.stat().st_size for f in self.cache_dir.glob('*.pkl.gz'))
                f.write(f"- Cache directory: `.cache/context_monitor/`\n")
                f.write(f"- Total cache size: {cache_size / 1024 / 1024:.1f} MB\n")
                f.write(f"- Cache files: {len(list(self.cache_dir.glob('*.pkl.gz')))}\n")
            else:
                f.write("- Cache: Disabled\n")
        
        print(f"✅ レポート生成完了: {report_path}")
    
    def print_quick_status(self, all_agent_data: Dict[str, List[Tuple[datetime, Dict[str, int]]]], 
                          target_agent: Optional[str] = None):
        """コンソールに現在の状態を出力（クイックアクセス用）"""
        
        print("\n" + "="*60)
        print(f"OpenCodeAT Context Usage Status - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60)
        
        # エージェントをフィルタリング
        if target_agent:
            filtered_data = {k: v for k, v in all_agent_data.items() 
                           if target_agent.upper() in k.upper()}
        else:
            filtered_data = all_agent_data
        
        if not filtered_data:
            print(f"❌ Agent '{target_agent}' not found")
            return
        
        # テーブル形式で出力
        print(f"{'Agent':<10} {'Total':>10} {'%':>6} {'Status':<8} {'Est.Time':<10}")
        print("-"*50)
        
        # データを整理してソート
        agent_infos = []
        for agent_id, cumulative_data in filtered_data.items():
            if not cumulative_data:
                continue
                
            latest_time, latest_tokens = cumulative_data[-1]
            total = latest_tokens['total']
            percentage = (total / self.AUTO_COMPACT_THRESHOLD) * 100
            
            # 状態判定
            if total >= self.AUTO_COMPACT_THRESHOLD * 0.95:
                status = "🔴 CRITICAL"
            elif total >= self.WARNING_THRESHOLD:
                status = "🟡 WARNING"
            else:
                status = "🟢 OK"
            
            # 推定時間
            est_time = "N/A"
            if len(cumulative_data) >= 2:
                recent_data = cumulative_data[-min(10, len(cumulative_data)):]
                time_span = (recent_data[-1][0] - recent_data[0][0]).total_seconds() / 3600
                token_increase = recent_data[-1][1]['total'] - recent_data[0][1]['total']
                
                if time_span > 0 and token_increase > 0:
                    rate = token_increase / time_span
                    remaining_tokens = self.AUTO_COMPACT_THRESHOLD - total
                    if remaining_tokens > 0:
                        hours = remaining_tokens / rate
                        if hours < 1:
                            est_time = f"{int(hours*60)}min"
                        else:
                            est_time = f"{hours:.1f}h"
            
            agent_infos.append({
                'agent_id': agent_id,
                'total': total,
                'percentage': percentage,
                'status': status,
                'est_time': est_time
            })
        
        # トークン数でソート
        agent_infos.sort(key=lambda x: x['total'], reverse=True)
        
        # 出力
        for info in agent_infos:
            print(f"{info['agent_id']:<10} {info['total']:>10,} {info['percentage']:>5.1f}% "
                  f"{info['status']:<8} {info['est_time']:<10}")
        
        print("\n" + "="*60)

def main():
    """メイン処理"""
    parser = argparse.ArgumentParser(description='Monitor Claude Code context usage')
    parser.add_argument('--last-n', type=int, default=None,
                       help='Analyze only the last N log entries per agent')
    parser.add_argument('--graph-type', choices=['all', 'overview', 'stacked', 'timeline', 'individual'],
                       default='all', help='Type of graphs to generate')
    parser.add_argument('--time-unit', choices=['seconds', 'minutes', 'hours'],
                       default='minutes', help='Time unit for X-axis (default: minutes)')
    parser.add_argument('--cumulative', action='store_true',
                       help='Show cumulative token usage instead of per-request context size')
    parser.add_argument('--no-cache', action='store_true',
                       help='Disable caching')
    parser.add_argument('--clear-cache', action='store_true',
                       help='Clear cache before running')
    parser.add_argument('--watch', action='store_true', 
                       help='Continue monitoring (update every 5 minutes)')
    parser.add_argument('--interval', type=int, default=300,
                       help='Update interval in seconds (default: 300)')
    parser.add_argument('--status', action='store_true',
                       help='Show quick status in console (no graphs)')
    parser.add_argument('--agent', type=str, default=None,
                       help='Show status for specific agent only')
    
    args = parser.parse_args()
    
    # プロジェクトルートを取得
    project_root = Path(__file__).parent.parent
    monitor = ContextUsageMonitor(project_root, use_cache=not args.no_cache)
    
    # キャッシュクリア
    if args.clear_cache and monitor.cache_dir.exists():
        import shutil
        shutil.rmtree(monitor.cache_dir)
        monitor.cache_dir.mkdir(parents=True, exist_ok=True)
        print("✅ Cache cleared")
    
    def update_once():
        """一度だけ更新"""
        print("🔍 Scanning JSONL files...")
        jsonl_files = monitor.find_project_jsonl_files()
        
        if not jsonl_files:
            print("❌ No JSONL files found in project directory")
            print(f"   Expected location: {monitor.claude_projects_dir}")
            return
        
        print(f"📊 Found {len(jsonl_files)} agents with logs")
        
        # 各エージェントのデータを収集
        all_agent_data = {}
        for agent_id, files in jsonl_files.items():
            if not args.status:  # ステータス表示時は進捗を省略
                print(f"  - Processing {agent_id}...")
            
            # 複数ファイルがある場合は結合
            all_usage_entries = []
            for jsonl_file in sorted(files):
                entries = monitor.parse_usage_data(jsonl_file, agent_id, args.last_n)
                all_usage_entries.extend(entries)
            
            if all_usage_entries:
                # 時系列でソート
                all_usage_entries.sort(key=lambda x: x['timestamp'])
                cumulative_data = monitor.calculate_cumulative_tokens(all_usage_entries, args.cumulative)
                all_agent_data[agent_id] = cumulative_data
        
        if all_agent_data:
            if args.status:
                # クイックステータス表示
                monitor.print_quick_status(all_agent_data, args.agent)
            else:
                # グラフとレポート生成
                monitor.generate_all_graphs(all_agent_data, args.graph_type, args.time_unit, args.cumulative)
                monitor.generate_summary_report(all_agent_data)
                print("✅ Context usage monitoring complete")
        else:
            print("❌ No usage data found in JSONL files")
    
    # 実行
    if args.watch:
        import time
        print(f"👁️  Watching mode enabled (interval: {args.interval}s)")
        while True:
            update_once()
            print(f"💤 Waiting {args.interval}s...")
            time.sleep(args.interval)
    else:
        update_once()

if __name__ == "__main__":
    # pandas import（予測機能で使用）
    try:
        import pandas as pd
    except ImportError:
        # datetimeで代替
        pd = None
    
    main()