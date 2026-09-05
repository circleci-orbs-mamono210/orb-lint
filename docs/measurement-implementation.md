## Measurement implementation

関連チケット: #5351（Phase 2-2）

意味上の正本は [Measurement Contract / Result Model](measurement-contract.md)。
本書はその実装上の取得経路と検証方法を説明する。

### 結果の取得境界

Measurement の出力は、1回のリポジトリ評価から返すプロセス内の実行結果である。
CLI と後続検証は `orb_lint._execution._run_repository()` と同じ経路を使用する。
CLI はこの結果から既存の診断を表示し、finding の有無で終了コードを決定する。

CLI の標準出力への JSON 追加、結果ファイルの生成、永続化は実装していない。
CLI 終了後に別プロセスから読み取る Measurement artifact は生成されない。
公開出力が必要になった場合は、形式・取得方法・失敗時の扱いを別途明示して契約化する。

以下の module・type・attribute 名は今回の private 実装であり、安定した public
Python API や serialization schema として公開するものではない。

| 責務 | 実装箇所 | 内容 |
| --- | --- | --- |
| ORB-001 evaluation | `orb_lint/rules/orb001.py` | 既存の検出条件で `Finding` を返す。変更なし |
| 実行結果の生成 | `orb_lint/_execution.py` | repository を解決し、ORB-001 を1回評価して Measurement を関連付ける |
| Measurement projection | `orb_lint/_measurement.py` | expected rule ごとの状態・件数を作成し、生成失敗を分離する |
| CLI enforcement | `orb_lint/cli.py` | evaluation の findings から従来の表示・終了コードを決める |

### Private result の利用例

以下はリポジトリ内のテスト・後続処理向けの利用例である。

```python
from pathlib import Path

from orb_lint._execution import _run_repository

execution = _run_repository(Path("tests/fixtures/orb001/pass"))

assert execution.evaluation.lint_outcome == "passed"
assert execution.measurement.outcome == "succeeded"
measurement = execution.measurement.value
assert measurement is not None

rules = {rule.rule_id: rule for rule in measurement.rules}
assert rules["ORB-001"].evaluated is True
assert rules["ORB-001"].finding_count == 0
assert measurement.target == execution.evaluation.target
```

`target` は解決済み repository `Path` であり、その実行環境内で対象を区別する。
同名ディレクトリでも異なるパスなら区別される。別マシンの checkout を同一
repository と判定する識別子ではなく、公開・永続化用の identity に転用しない。

### 状態と件数

- `_RuleEvaluation.findings` が空の tuple: 評価済み・違反なし。
- `_RuleEvaluation.findings` が `None`: 評価未完了。部分的なfindingを完全な件数に扱わない。
- `_RuleMeasurement.finding_count` が整数: 評価済み。その値が finding 数。
- `_RuleMeasurement.finding_count` が `None`: 未評価。`evaluated` は `False`。

expected rule は findings の有無から推測せず、evaluation に明示して保持する。
そのため ORB-001 が0件でも rule result が欠落しない。rule result と全体結果は
frozen dataclass と tuple で保持し、別実行へ共有される可変の集計状態を持たない。

集計処理に ORB-001 固有の分岐はない。rule identity の重複、空の identity、
evaluation と finding の identity 不一致は、Measurement 生成失敗として扱う。
message・path・line で集計キーを作成せず、finding の追加・削除・重複排除もしない。
同じ行にplaceholderが複数あっても、ORB-001が1件と返した診断は1件として数える。

### Failure boundary

`execution.evaluation` は Measurement の成否と独立して保持される。

| lint outcome | Measurement outcome | 取得できる状態 |
| --- | --- | --- |
| `passed` / `violations` / `incomplete` | `succeeded` | `value` に対象・全rule状態・件数・lint outcome、`error` は `None` |
| `passed` / `violations` / `incomplete` | `failed` | `value` は `None`、`error` に測定処理の例外。既知のlint結果はevaluationに保持 |

未評価を正しく記録できた場合は `incomplete` と `succeeded` が共存する。
測定失敗時には成功値や架空の `Finding` を返さない。
元のlint結果が `passed` なら、測定失敗だけを理由にlint結果を変更しない。

`_measure()` が捕捉するのは Measurement 構築中の `Exception` のみである。
`KeyboardInterrupt` / `SystemExit` は捕捉しない。
ORB-001 のファイル読込・decode 等の評価例外は測定処理の外側で発生し、従来どおり伝播する。

現在のCLIにはルールをskipする経路がない。未評価状態は内部の `_Evaluation` と
`_measure()` の境界で検証し、テストのための公開skip optionを追加しない。
評価例外時に `_run_repository()` が正常な実行結果を返すという契約も追加しない。

CLI は Measurement を生成するが、Measurement の成功判定をlint判定に使用しない。
測定失敗の詳細は内部実行結果から取得する。従来のCLI表示に測定用のstdout/stderrや
新しいexit codeを追加せず、公開エラーモデルも新設しない。

### 検証と後続Phase

| 検証対象 | 自動テスト |
| --- | --- |
| 0 / 1 / 複数finding、対象分離、1回のrule評価 | `tests/test_execution.py` |
| 未評価、複数rule、identity検証、lintと測定成否の独立 | `tests/test_measurement.py` |
| 実際のCLI接続、測定失敗時を含む表示・終了コードの維持 | `tests/test_cli.py` |
| 既存ORB-001の検出 | `tests/test_orb001.py`（変更なし） |

既存の検証コマンドで実行する。

```bash
python -m unittest discover -s tests -v
```

新規テストも既存 CircleCI `python-tests` job の discovery 対象である。
Phase 2-3 は同じ内部実行結果を使用して、固定baseline・繰り返し実行・意図したbaseline変更の
レビュー境界を整備できる。今回のテストに保存baseline、自動baseline更新、許容threshold、
repository横断集計、CI Gateやrelease policyの変更は含めない。
