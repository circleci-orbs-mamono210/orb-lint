## Phase 2-2 delivery / verification record

対象: #5351 — Phase 2-2: lint 結果の Measurement 出力を実装する

この文書は今回の納品・検証記録である。継続参照する契約の正本は
`docs/measurement-contract.md`、実装の説明は `docs/measurement-implementation.md` とする。

### 適用基準と収録ファイル

基準リポジトリ: `circleci-orbs-mamono210/orb-lint`

基準コミット: `d148955ddc9c2cf0886f2f267c48a80703865b5f`

このコミットには、修正版 `docs/measurement-contract.md` が含まれている。
同文書の内容を変更せず実装した。

| ファイル | 操作 |
| --- | --- |
| `orb_lint/_measurement.py` | 新規追加: evaluationとMeasurementの内部型、rule集計、測定失敗の識別 |
| `orb_lint/_execution.py` | 新規追加: 実lint評価と測定結果の生成を接続 |
| `orb_lint/cli.py` | 更新: 共通実行経路を呼び、既存diagnosticと終了コードを維持 |
| `tests/test_measurement.py` | 新規追加: 状態・複数rule・失敗境界の検証 |
| `tests/test_execution.py` | 新規追加: 実入力、対象分離、評価例外の検証 |
| `tests/test_cli.py` | 更新: 実行経路接続と既存CLIの回帰検証 |
| `docs/measurement-implementation.md` | 新規追加: 内部結果の取得方法・公開契約との境界 |
| `docs/phase-2-2-verification.md` | 新規追加: 本納品記録 |

ZIP内のパスはリポジトリroot相対である。追加のラッパーディレクトリはない。
基準コミットまたはそれを含む作業ブランチのrootへ展開して適用する。
`orb_lint/cli.py` / `tests/test_cli.py` に独自変更がある場合は差分を統合する。
ZIPには未変更のリポジトリ全体、`.git`、cache、以前のPhase 2-1 ZIPは含めない。

### ローカル検証結果

実行環境: Python 3.12.13

| 確認 | 結果 |
| --- | --- |
| `python -m unittest discover -s tests -v` | 53 tests成功（既存34、新規19。subTestの組み合わせを含む） |
| `python -m orb_lint tests/fixtures/orb001/pass` | `orb-lint: OK`、exit 0 |
| `python -m orb_lint tests/fixtures/orb001/fail` | 既存ORB-001 diagnostic、exit 1 |
| `git diff --check` | 成功 |
| ORB-001・既存ruleテスト・契約文書・package metadata・Orb・CIとの差分 | 変更なし |

CircleCI のリモート実行、release、Gitへのpushは実施していない。
`pyproject.toml` のversion、依存ライブラリ、公開CLI option・出力形式は変更していない。
CLIから測定artifactを保存する機能はなく、結果はプロセス内で取得する。
テスト成功をもって公開JSON出力やPhase 2-3のbaselineが完成したとは扱わない。

### #5351 完了条件との対応

以下はローカル実装・検証との対応であり、Redmineのチェックボックスやステータスを変更する記録ではない。

| # | 完了条件の要旨 | 実装・検証根拠 |
| --- | --- | --- |
| 1 | #5350契約に準拠 | 正本を変更せず、evaluation / Measurement / enforcementを分離。`test_lint_and_measurement_outcomes_are_independent` |
| 2 | 1実行からMeasurement生成 | `_run_repository()` と `test_existing_zero_and_single_finding_inputs_are_measured` |
| 3 | targetとの関連付け | executionとmeasurementのtargetを同テストで比較 |
| 4 | ORB-001のstable identity | rule側の `RULE_ID` を使用し、0件でも `ORB-001` を明示 |
| 5 | messageを集計キーにしない | `test_message_path_and_line_do_not_define_rule_identity` |
| 6 | ORB-001のcount取得 | `measurement.value.rules` から取得し0/1/複数件を確認 |
| 7 | 評価済み0件 | `test_existing_zero_and_single_finding_inputs_are_measured`、`test_zero_is_explicit_and_not_evaluated_has_no_count` |
| 8 | 0件と未評価の区別 | `None`と0を分離。未評価でもMeasurement成功を確認 |
| 9 | 複数findingの正確な測定 | `test_multiple_files_count_findings_not_placeholder_occurrences` |
| 10 | targetの混同防止 | `test_targets_keep_independent_counts_even_with_same_directory_name` |
| 11 | 測定失敗とlint違反の区別 | `test_lint_and_measurement_outcomes_are_independent` の6組み合わせ |
| 12 | 架空のfindingを生成しない | `test_measurement_failure_keeps_the_original_evaluation` |
| 13 | 3責務の分離 | 元のevaluationを保持し、CLIはそのfindingsを使用する |
| 14 | ORB-001専用集計でない | `test_multiple_rules_keep_counts_and_identity_separate`。他ruleはテスト用の合成データのみ |
| 15 | ORB-001検出条件を維持 | ruleソース無変更、既存ruleテスト成功、複数placeholderの計数確認 |
| 16 | 既存CLIの成否を維持 | `test_measurement_failure_preserves_cli_exit_and_diagnostics` |
| 17 | CLI regressionを維持 | 既存 `tests/test_cli.py` の2テストを残し、接続と例外の3テストを追加 |
| 18 | ORB-001 regressionを維持 | `tests/test_orb001.py` は変更せず成功 |
| 19 | 追加検証を自動化 | 新規19テストが既存unittest discoveryで実行される |
| 20 | baseline / policy / 横断集計を混在させない | 保存baseline、threshold、自動更新、横断集計、CI変更を追加していない |
| 21 | Phase 2-3が再設計なしで検証できる | 内部実行結果から対象・rule状態・count・lint結果・測定成否を取得できる。取得方法を実装文書に記載 |

### チケット粒度の判断

目的は「1回の既存lint evaluationからMeasurement resultを生成する」で統一されている。
内部モデル、集計、CLI接続、互換性テストはこの目的の成立に必要な一連の変更であり、
現状は1チケットとして扱える。21項目は独立機能の数ではなく、同じ契約を複数方向から確認する条件である。

公開JSON / 新しいCLI option / 永続化 / baseline policyまで今回へ加える場合は、
追加の公開契約や独立責務が生じるため分割を検討する。現在のチケットは変更していない。
