# mtpj_deps

Renesas CS+ プロジェクトファイル (`.mtpj`) を解析して、
GitHub Copilot 用プロジェクト構造リファレンス Markdown を生成するツールです。

## 利用フロー

```text
.mtpj ──[mtpj_deps.py]──► copilot-project-structure.md ◄──参照── .github/copilot-instructions.md
                                                                        │
                                                                        ▼
                                                                  GitHub Copilot
```

## 使い方

### 基本フロー

```bash
# 1. ビルドモード一覧を確認
uv run src/mtpj_deps.py ./proj/Sample.mtpj --list-modes

# 2. ビルドモードを明示して生成（推奨運用）
uv run src/mtpj_deps.py ./proj/Sample.mtpj -m DefaultBuild \
    -o .github/copilot-project-structure.md

# 3. プリプロセスを有効にして、非アクティブ include を除外
uv run src/mtpj_deps.py ./proj/Sample.mtpj -m DefaultBuild --preprocess \
    -o .github/copilot-project-structure.md
```

### マクロ定義の確認

`--dump-macros` を使うと、指定したビルドモードのマクロ定義とインクルードパスを
Markdown を生成せずに標準出力で確認できます。

```bash
uv run src/mtpj_deps.py ./proj/Sample.mtpj -m DefaultBuild --dump-macros
```

出力例：

```
Build mode : DefaultBuild (index 0)
Macros     : 3

  TRCBUFMODE=1
  TRCBUFSZ=01000H
  TRCMODE=2

Include paths: 9

  r_config
  r_bsp\mcu\rx65n
  appli\include
  ...
```

### オプション一覧

| オプション          | 必須 | 説明 |
|---------------------|------|------|
| `<project.mtpj>`    | 必須 | 解析対象の .mtpj パス |
| `-m`, `--mode MODE` | 推奨 | 対象ビルドモード名。省略時は `CurrentBuildMode` |
| `-o`, `--out PATH`  | 任意 | 出力先。省略時は `<mtpj名>_<mode>_deps.md` |
| `--no-scan`         | 任意 | `#include` スキャンをスキップ |
| `--list-modes`      | 任意 | ビルドモード一覧を表示して終了 |
| `--preprocess`      | 任意 | マクロ定義に基づく条件ディレクティブ評価を有効化 |
| `--dump-macros`     | 任意 | 指定ビルドモードのマクロ定義とインクルードパスを表示して終了 |

> **推奨**: `-m` でビルドモードを明示指定してください。
> `CurrentBuildMode` は CS+ で最後に開いた環境に依存するため、結果が環境によって変わる可能性があります。

## 対応コンパイラ

| コンパイラ | 対象シリーズ | Cマクロタグ | インクルードパスタグ |
|------------|-------------|-------------|----------------------|
| CC-RL      | RL78        | `COptionD-<N>` | `COptionIncludePath-<N>` |
| CC-RX      | RX          | `COptionDefine-<N>` | `COptionInclude-<N>` |

アセンブラマクロ（`AsmOptionDefine-<N>`）は両系共通です。

また、RX 系では BuildTool の設定情報が同一 `<Class>` 内の複数の `<Instance>` に
分散して格納されています。本ツールはこの構造を自動で認識します。

## 出力形式

生成される Markdown は3セクション構成です：

1. **Registered files (by category)** — カテゴリ別ファイル一覧。ビルド対象は `[B]` でマーク。
2. **Include dependencies** — 実ソースをスキャンして抽出した `#include` 依存関係。プロジェクト内ファイルへの解決は `→ (project)` で明示。
3. **Summary** — 登録ファイル数 / ビルド対象数 / カテゴリ数。

`--preprocess` 有効時は追加で：
- Section 1 直下に **「Active defines」** サブセクション（マクロ定義一覧）
- Section 2 見出しに `(preprocessed)` 付記
- Section 3 末尾に **「Preprocessing notes」**（保守的フォールバック件数等）

## コンパイラ組み込みマクロ (`compiler_builtins.json`)

`src/compiler_builtins.json` にコンパイラ組み込みマクロを定義できます。
`--preprocess` 有効時に `.mtpj` のマクロ定義とマージして評価に使用されます。
優先順は `.mtpj` > `compiler_builtins.json`（同名キーは `.mtpj` が優先）。

使用するコンパイラに合わせて編集してください。

CC-RL (RL78) 向けサンプル：

```json
{
  "__CCRL__": "1",
  "__RL78__": "1",
  "__K0R__": "1",
  "__RENESAS__": "1",
  "__RENESAS_VERSION__": "0x01000000"
}
```

CC-RX (RX) 向けサンプル：

```json
{
  "__CCRX__": "1",
  "__RX__": "1",
  "__RENESAS__": "1",
  "__RENESAS_VERSION__": "0x03000000"
}
```

## 出力先フォルダについて

`.github/` フォルダは `.gitkeep` で Git 追跡されています。
このフォルダ内に生成される `*.md` ファイルは `.gitignore` で除外されています。
出力ファイルを Git 管理したい場合は `.gitignore` から除外ルールを取り除いてください。

## CI 連携例（GitHub Actions）

```yaml
- name: Regenerate Copilot project structure
  run: |
    uv run src/mtpj_deps.py ./proj/Sample.mtpj -m DefaultBuild --preprocess \
      -o .github/copilot-project-structure.md
```

## `.github/copilot-instructions.md` からの参照例

```markdown
## Project structure reference

See [`copilot-project-structure.md`](./copilot-project-structure.md) for:
- registered source/header files,
- build participation for `DefaultBuild` (marked `[B]`),
- active macro definitions and per-file `#include` dependencies
  (preprocessed for this build mode).

When proposing changes:
- Only modify files marked `[B]` or headers they include.
- Keep `#include` paths consistent with the dependency list.
- Do not add new source files without also registering them in the `.mtpj`.
```

## テスト実行

```bash
uv run pytest src/tests/
```

## 制限事項

1. **ファイル単位のビルド除外**: CS+ のファイルプロパティによるビルドモード別ファイル除外は未サポート。全ビルドモード共通ソースリストとして扱います。
2. **マクロの完全展開**: `--preprocess` 有効時も、`#include` ファイル側の `#define` は追いません。`.mtpj` のマクロ定義と組み込みマクロのみで評価します。
3. **再帰的 include 展開**: 行いません（Copilot 用途では過剰なため）。
4. **同名ファイル**: 異なるフォルダに同名ファイルがある場合、`#include` の解決はベース名一致のため複数候補が列挙されます。
5. **システムヘッダ**: `<stdint.h>` 等は未解決のまま表示します（解決不要）。
6. **マクロ経由 include**: `#include INC_FILE` のようなマクロ経由の include は解析対象外です（無視されます）。

## セキュリティ

信頼できる `.mtpj` とソースツリーのみを対象として使用してください。
生成物にはプロジェクトの内部構造情報が含まれます。公開リポジトリへのコミット前に
内容を確認してください。詳細は [SECURITY.md](SECURITY.md) を参照してください。

## 必要環境

- Python 3.12+
- 追加ライブラリ不要（標準ライブラリのみ使用）
