# レポート階層構造ガイド

## 概要
OpenCodeATでは、技術的詳細から経営層向けまで、3段階のレポート体系を採用します。

## レポート階層

### 1. 一次レポート（現場レベル）
- **形式**: ChangeLog.md
- **作成者**: PG（リアルタイム自動記録）
- **配置**: 各PGの作業ディレクトリ
- **特徴**: 
  - 技術的詳細をすべて記録
  - バージョンごとの試行錯誤
  - 実行ログへのパス

### 2. 二次レポート（統合レベル）
- **形式**: Markdown + 画像
- **作成者**: SE（Pythonで半自動生成）
- **配置**: User-shared/reports/
- **特徴**:
  - 複数PGの成果を統合
  - グラフによる可視化
  - 人間が読みやすい形式
  - 日本語で記述

### 3. 最終レポート（経営レベル）
- **形式**: エグゼクティブサマリー
- **作成者**: PM
- **配置**: User-shared/final_report.md
- **特徴**:
  - 投資対効果の明示
  - 予算消費と成果
  - 今後の推奨事項

## ディレクトリ構造

```
OpenCodeAT/
├── Agent-shared/                # エージェント用（技術的）
│   ├── tools/
│   │   ├── changelog_analyzer.py
│   │   └── report_generator.py
│   └── templates/
│       └── report_template.md
└── User-shared/                 # ユーザ用（成果物）
    ├── final_report.md          # 最終報告書
    ├── reports/
    │   └── performance_summary.md
    └── visualizations/
        ├── sota_trends.png
        ├── efficiency_radar.png
        └── cost_performance.png
```

## 二次レポート生成スクリプト例

```python
# Agent-shared/tools/generate_user_report.py
import matplotlib.pyplot as plt
import pandas as pd
from pathlib import Path
import datetime

class UserReportGenerator:
    def __init__(self):
        self.output_dir = Path('User-shared/reports')
        self.viz_dir = Path('User-shared/visualizations')
        
    def generate_summary_report(self):
        # ChangeLog.mdからデータ収集
        data = self.collect_performance_data()
        
        # グラフ生成（日本語ラベル）
        self.create_performance_graph(data)
        
        # レポート生成
        report = self.format_report(data)
        
        # 保存
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        report_path = self.output_dir / f'summary_{timestamp}.md'
        report_path.write_text(report, encoding='utf-8')
```

## レポート作成のタイミング

### 短期集中型プロジェクトでの運用
- **一次**: PGがコード生成時に即座に記録（ChangeLog.md）
- **二次**: SEが必要に応じて統合レポート生成
- **最終**: PMがプロジェクト終了時に作成

### 作成タイミング
- **統合レポート**: 重要なマイルストーン達成時
- **中間報告**: 予算50%消費時点（推奨）
- **最終報告**: プロジェクト完了時

## 言語使用の指針

| レポート種別 | 言語 | 理由 |
|------------|------|------|
| ChangeLog.md | 日本語 | 技術用語は英語OK |
| 二次レポート | 日本語 | ユーザ向け |
| グラフラベル | 日本語 | 視認性向上 |
| 最終報告書 | 日本語 | 経営層向け |

## User-sharedの利点

1. **アクセス性**: ユーザはここだけ見ればよい
2. **整理**: 技術詳細と成果物の分離
3. **共有**: プレゼン資料として即座に使用可能
4. **保守**: エージェント用ツールと分離

## 注意事項

- Agent-shared/には解析ツールやテンプレートを配置
- User-shared/には最終成果物のみを配置
- 機密情報の扱いに注意（特に最終報告書）