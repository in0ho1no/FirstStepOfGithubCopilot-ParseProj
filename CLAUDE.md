# CLAUDE.md — プロジェクト指示書

## フォルダ構成

```
prj/
├── src/              # すべてのソースコード・スクリプトを配置
│   ├── main.py
│   └── tests/        # テストコードはここに配置
├── documents/        # 仕様書・ドキュメント類
├── pyproject.toml    # プロジェクト設定（uv / ruff / mypy）
├── uv.lock           # uvのロックファイル
└── CLAUDE.md         # 本ファイル
```

## ソースコード配置ルール

- すべてのソースファイルは `src/` に配置する
- テストコードは `src/tests/` に配置する
- リポジトリルートにスクリプトやソースファイルを置かない

## Python 環境

本プロジェクトは **uv** で Python 環境を管理している。

### スクリプト実行

```bash
uv run src/main.py
```

### パッケージ追加

```bash
uv add <パッケージ名>
```

### 開発用パッケージ追加

```bash
uv add --dev <パッケージ名>
```

> **注意: `pip` コマンドは使用しない。**
> パッケージのインストール・管理はすべて `uv` 経由で行うこと。
> `pip install` / `pip uninstall` 等を直接実行してはならない。

## コード品質ツール

### Lint / Format（ruff）

```bash
uv run ruff check src/
uv run ruff format src/
```

### 型チェック（mypy）

```bash
uv run mypy src/
```

### テスト実行（pytest）

```bash
uv run pytest src/tests/
```

## コーディング規約

- Python バージョン: 3.12 以上
- 文字列はシングルクォート優先（ruff format 設定に準拠）
- 1行の最大文字数: 150文字
- 関数には型ヒントを付与する（mypy: `disallow_untyped_defs = true`）
- docstring は Google スタイル

## OSS ライセンスポリシー

本プロジェクトのコードに OSS ライセンス汚染を持ち込まないこと。

### 禁止事項

- OSS リポジトリ（GitHub 等）からコードをコピー・移植すること
- StackOverflow 等の投稿コードをそのまま貼り付けること（CC BY-SA ライセンスが付随する）
- GPL / LGPL / AGPL ライセンスのライブラリを `uv add` で追加すること
  （コピーレフトにより本プロジェクト全体への感染リスクがある）

### 外部ライブラリを追加する際の手順

1. `uv add` する前にライセンスを確認する
2. 許容できるライセンス: MIT / BSD / Apache-2.0 / PSF / ISC など Permissive 系
3. 不明・要確認の場合はユーザーに許可を取ってから追加する

### 推奨アプローチ

- **Python 標準ライブラリのみ**での実装を第一選択とする
- アルゴリズムを自前実装する場合は、特定 OSS のコードを参照せず、
  仕様・原理から独自に実装すること
- 生成したコードに外部由来の断片が含まれないことを自己確認すること
