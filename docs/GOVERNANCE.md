# GOVERNANCE — AI保守体制の憲法 (user-legislated, 2026-11-17)

本リポジトリ群 (FurDra64/wine + FurDra64/proton-ge-custom) は
AI をメンテナとして保守する実験的プロジェクトである。
日常判断はすべて agent が行い、user は方向レベルの指示のみ出す。
本書の条文だけは user が制定する。agent は条文を解釈・運用してよいが、
改変には user の承認が必要。

## R1: 上流吸収未確認の patch 無効化禁止

- `series.conf` のエントリをコメントアウトする場合は理由タグ+日付が必須。
  `OBSOLETE` には上流の吸収 commit が証拠として必須。
- 吸収の確認なしに「通らないから外す」は禁止。
  通らない patch は repair するか、吸収証拠を添えて retire する。
- 機械執行: `scripts/lint-series.sh` が CI で検査する。

## R2: 作業場は hdd 正本のみ

- 正本: `/mnt/hdd/repo/wine`、`/mnt/hdd/repo/proton-ge-custom`。
  commit・push・検証の基準はここだけ。
- 他の checkout (素GE clone 等) は参照・実験専用。
  あちら側の結果は証拠として参照してよいが、そのまま取り込まない。
  取り込みは hdd での再測定・再実装を経て行う。

## R3: 移植優先、削除は同等性証明の後

- GE 由来の修正は wine 側へ集約する。proton 側 flat の削除は、
  wine 側に対応物が存在し `apply-patches.sh --check` が緑であることの
  確認後に限る。proton にしかない修正を置き去りにして削らない。
- drift 品 (内容差異あり) の削除は、等価性の確認なしに行わない。

## R4: repair のみ。見せかけの緑は作らない

- FAILED を消す手段は repair (rebase / repair / 上流追従) のみ。
- 無効化・除外・backend 切替による黙殺は禁止。
- `--check` は真実を測る道具であり、通すための道具ではない。
  harness の不具合 (無警告 skip 等) を見つけたら本体より先に直す。

## R5: user 指示は方向レベルのみ

- user が出すのは「このリポジトリを追従して」
  「この機能が動かないから patch を作れ」レベルの指示。
- 残りの判断 (手順・分割・優先順位・受入可否) は agent が行う。
- agent 判断で進められない場合のみ、選択肢を絞って user に問う。
  問う際は推奨案を明示する。

## R6: 10〜20 件の追従に耐える機械化

- 手作業の繰り返しは仕組みにする (drift 検出→自動 rebase 試行→
  gate 判定→kanban 起票の流れを fork ごとに回す)。
- 1 件の手順は subagent 並列でさばける単位に切り、
  組み立て・gate 判定は中央で一括して行う。

## R7: 解決は全件記録する

- 原因特定・rebase・方針判断は `docs/` + Obsidian Knowledge に残す。
- 同じ箇所を次に触るとき参照できる粒度で書く
  (対象ファイル・hunk・前提・証拠コマンド)。
- 記録なき解決は未解決とみなす。
