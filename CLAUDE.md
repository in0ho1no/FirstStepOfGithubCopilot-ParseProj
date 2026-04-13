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
