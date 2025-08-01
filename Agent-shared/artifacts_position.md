#　📋 OpenCodeAT 設計成果物・ドキュメント一覧

## 核心原則
- ChangeLog.md中心設計: 情報の集約化（分散させるのは本当に必要な場合のみ）
- 階層配置の明確化: Agent-shared vs 各エージェント直下

## 必須ドキュメント

### プロジェクトルート直下
```
OpenCodeAT/
├── CLAUDE.md                    # 共通ルール（writer:PM, reader:all）
├── assign_history.txt           # PM管理（writer:PM, reader:all）
├── resource_allocation.md       # リソース割り当て（writer:PM, reader:CI）
├── sota_project.txt             # Project階層SOTA（writer:PG, reader:all）
├── history/
│   └── sota_project_history.txt # Project SOTA履歴（writer:PG, reader:PM）
├── GitHub/                      # CD管理（writer:CD, reader:all）
│   ├── changelog_public.md      # 統合・匿名化版
│   └── repository_name
└── User-shared/                 # ユーザ向け成果物（writer:SE/PM, reader:User）
    ├── final_report.md          # 最終報告書
    ├── reports/                 # 統合レポート
    └── visualizations/          # グラフ・図表
```

## Agent-shared階層

### Agent-shared/ (全エージェント参照)
```
Agent-shared/
├── directory_map.txt            # エージェント配置（writer:PM, reader:all）
├── budget_history.md            # 予算履歴（writer:PM, reader:CI）
├── ChangeLog_format.md          # ChangeLog.md基本フォーマット（writer:PM, reader:all）
├── ChangeLog_format_PM_override_template.md # PMオーバーライドテンプレート（writer:運営, reader:PM）
├── ChangeLog_format_PM_override.md # PMオーバーライド仕様（writer:PM, reader:all）※PMがテンプレートから生成
├── sota_management.md           # SOTA管理システム仕様（writer:PM, reader:all）
├── changelog_query/             # ChangeLog.md解析ツール群（writer:all）
│   ├── query_changelog.py       # SQLライクなChangeLog.md検索
│   ├── [その他解析コード自由配置]
│   └── README.md                # 使用方法・クエリ例
├── tools/                       # 共通ツール群
│   ├── changelog_analysis_template.py  # ChangeLog解析テンプレート
│   └── report_generator.py      # レポート生成補助ツール
└── SE-shared/                   # SE専用ツール（writer:SE, reader:SE/PM）
    ├── log_analyzer.py          # ログ解析ツール
    └── performance_trends.png   # 統計グラフ
```

### _remote_info/ (スパコン・ユーザ固有)
```
_remote_info/
├── user_id.txt                  # 秘匿情報（writer:PM, reader:CD）
├── Flow/command.md              # 実行コマンド
└── [スパコン環境設定]
```

### communication/ (通信システム)
```
communication/
├── hpc_agent_send.sh            # メッセージ送信
├── setup_hpc.sh                 # エージェント起動
└── logs/send_log.txt            # 送信履歴
```

## 各エージェント直下

### ハードウェア階層直下
```
Flow/TypeII/single-node/
├── hardware_info.txt           # ハードウェア情報集約（writer:CI, reader:all）
│   ├── CPU: lscpu結果
│   ├── Memory: lsmem結果  
│   ├── Network: 通信バンド幅、レイテンシ
│   ├── Storage: ディスクI/O性能
│   └── Accelerator: GPU/FPGA情報
├── sota_hardware.txt           # Hardware階層SOTA（writer:PG, reader:all）
├── intel2024/
└── gcc11.3.0/
```

### CI階層
```
CI1.1/
├── setup.md                    # 環境構築手順
└── job_list_CI1.1.txt          # ジョブ管理
```

### PG階層
```
PG1.1.1/
├── ChangeLog.md                 # 【必須】全情報統合（→Agent-shared/ChangeLog_format.md参照）
├── visible_paths.txt            # 参照許可パス一覧（SE管理）
├── sota_local.txt               # Local階層SOTA（writer:PG, reader:all）
└── results/                     # 実行結果ファイル
    ├── job_12345.out
    └── job_12345.err
```

## 情報統合の考え方

### ChangeLog.md統合項目（一部）
- code_versions: バージョン履歴
- optimization_notes: 最適化メモ
- performance_data: 性能データ
- sota_candidates: SOTA候補情報

### 分離する理由があるもの
- 実行結果ファイル: サイズが大きい（results/）
- 環境構築手順: CI固有情報（setup.md）
- 予算管理: PM集約必要（budget_history.md）

## 取得・解析方法

### ChangeLog.md解析
```bash
# バージョン一覧取得例
grep "^### v" ChangeLog.md | sed 's/### //'

# 性能データ抽出例
grep "performance:" ChangeLog.md | grep -o '`[^`]*`' | tr -d '`'

# SOTA履歴取得例
grep -A1 "\*\*sota\*\*" ChangeLog.md | grep "scope: \`project\`"
```

### SOTA情報取得
```bash
# Local SOTA確認
cat PG1.1.1/sota_local.txt

# Hardware SOTA確認  
cat Flow/TypeII/single-node/sota_hardware.txt

# Project SOTA確認
cat OpenCodeAT/sota_project.txt
```

### 統合クエリ例
```bash
# Agent-shared/changelog_query/内の解析ツール活用
python3 Agent-shared/changelog_query/query_changelog.py --performance-trend
python3 Agent-shared/changelog_query/query_changelog.py --sota-comparison
```

要点: ChangeLog.mdのフォーマットがしっかりしていれば、エージェントが必要に応じて正規表現やPythonでパースして部分的に取得できる。加えて、SOTA情報は専用ファイルで高速アクセス可能。