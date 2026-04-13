# mtpj_deps.py 仕様書（Claude Code 向け実装指示書）

本ドキュメントは、Renesas CS+ プロジェクトファイル (`.mtpj`) を解析して
GitHub Copilot 用プロジェクト構造リファレンス Markdown を生成する
ツール `mtpj_deps.py` の**完全な要件定義**です。

Claude Code にはこのドキュメントを読んだうえで、
`mtpj_deps.py` および周辺ファイル一式を実装してもらうことを想定しています。

---

## 1. 背景と目的

### 1.1 なぜ作るのか

- Renesas CS+ の `.mtpj` はプロジェクト構造とビルド構成を持つが、**GitHub Copilot は直接読み取れない**。
- Copilot に「どのファイルがどのビルドモードに参加しているか」「どのヘッダに依存するか」を正しく伝えるため、`.github/copilot-instructions.md` から参照する**プロジェクト構造 Markdown** が必要。
- 手書き・手更新では保守できないため、`.mtpj` から自動生成するツールを作る。

### 1.2 利用フロー

```text
.mtpj ──[mtpj_deps.py]──► copilot-project-structure.md ◄──参照── .github/copilot-instructions.md
                                                                         │
                                                                         ▼
                                                                   GitHub Copilot
```

---

## 2. 入力 / 出力仕様

### 2.1 入力

- **必須**: `.mtpj` ファイル（CS+ プロジェクトファイル、XML 形式）
- **必須（推奨運用）**: ビルドモード名（`-m` オプション）
- **任意**: スキャン対象のソースファイル（`.mtpj` からの相対パスで解決）

### 2.2 出力

単一の Markdown ファイル。以下3セクション構成：

1. **Registered files (by category)** — カテゴリ別ファイル一覧。ビルド対象は `[B]` でマーク。
2. **Include dependencies** — 実ソースをスキャンして抽出した `#include` 依存関係。プロジェクト内ファイルに解決できたものは `→ (project)` で明示。
3. **Summary** — 登録ファイル数 / ビルド対象数 / カテゴリ数。

### 2.3 CLI 仕様

```text
python mtpj_deps.py <project.mtpj> [options]
```

| オプション          | 必須                 | 説明                                                                |
| ------------------- | -------------------- | ------------------------------------------------------------------- |
| `<project.mtpj>`    | ✅                   | 解析対象の .mtpj パス                                               |
| `-m`, `--mode MODE` | 推奨                 | 対象ビルドモード名。省略時は `CurrentBuildMode`                     |
| `-o`, `--out PATH`  | 任意                 | 出力先。省略時は `<mtpj名>_<mode>_deps.md`                          |
| `--no-scan`         | 任意                 | `#include` スキャンをスキップ                                       |
| `--list-modes`      | 任意                 | ビルドモード一覧を表示して終了                                      |
| `--preprocess`      | 任意（**新規追加**） | `COptionD-<N>` 等のマクロ定義に基づく条件ディレクティブ評価を有効化 |
| `-h`, `--help`      | 任意                 | ヘルプ                                                              |

---

## 3. `.mtpj` フォーマット仕様（解析対象）

`.mtpj` は UTF-8 の XML。以下の要素を抽出対象とする。

### 3.1 ファイル登録

```xml
<Instance Guid="...">
  <n>r_main.c</n>
  <Type>File</Type>
  <RelativePath>src\r_main.c</RelativePath>
  <ParentItem>633ddd13-...</ParentItem>
</Instance>
```

- `<RelativePath>` の区切り文字は `\`（Windows 形式）。内部処理では `/` に正規化。
- `<ParentItem>` は親 Category の Guid。

### 3.2 カテゴリ階層

```xml
<Instance Guid="633ddd13-...">
  <n>コード生成</n>
  <Type>Category</Type>
  <ParentItem>4ae340d5-...</ParentItem>
</Instance>
```

- ルートまで `ParentItem` を辿って `"コード生成 / Platform / driver"` のようなパス表記にする。

### 3.3 ビルドモード定義

BuildTool Instance 内に以下が格納される：

```xml
<BuildModeCount>3</BuildModeCount>
<BuildMode0>RABlAGYAYQB1AGwAdABCAHUAaQBsAGQA</BuildMode0>
<BuildMode1>...</BuildMode1>
<CurrentBuildMode>DefaultBuild</CurrentBuildMode>
```

- **重要**: `BuildMode<N>` は **UTF-16LE + Base64** でエンコードされている。

  ```python
  base64.b64decode(v).decode('utf-16-le').rstrip('\x00')
  ```

- インデックス `<N>` と復号後のビルドモード名は 1:1 対応。以降の各種オプション要素は `-<N>` サフィックスで識別される。

### 3.4 ビルド対象ソースリスト

```xml
<SourceItemGuid0>3c8caaf3-...</SourceItemGuid0>
<SourceItemType0>AsmSource</SourceItemType0>
<SourceItemGuid1>a4a26ac0-...</SourceItemGuid1>
<SourceItemType1>CSource</SourceItemType1>
```

- `SourceItemGuid<N>` の値集合が「ビルド対象ファイル GUID 集合」。
- **現状の `.mtpj` ではソースリストは全ビルドモード共通**で保持されている。ファイル単位のビルド除外は本ツールでは対象外（制限事項として README に明記済み）。
- ここに載らない `.h` 等は「登録されているがビルド対象外」として扱う。

### 3.5 マクロ定義 / インクルードパス（プリプロセス機能で使用）

各ビルドモード index `<N>` に対し：

```xml
<COptionD-0>_USE_CCRL_RL78
USE_VUART_PROFILE
CFG_CON=1
CFG_SECLIB_BOND_NUM=1
</COptionD-0>

<AsmOptionDefine-0 />

<COptionIncludePath-0>...</COptionIncludePath-0>
```

- `COptionD-<N>` : C コンパイラ `-D` 相当。改行区切り、`NAME` または `NAME=VALUE`。
- `AsmOptionDefine-<N>` : アセンブラ向け `-D` 相当。同形式。
- 値なし定義は `1` として扱う（プリプロセッサ慣例）。
- 未定義識別子は `#if` 文脈で `0` に置換（C プリプロセッサ仕様通り）。

---

## 4. 既存実装（保持すべき動作）

現行 `mtpj_deps.py`（リポジトリにコミット済み）は以下を実装済み：

- `.mtpj` の XML パース（`xml.etree.ElementTree`、名前空間に頑健）
- BuildMode 名の UTF-16LE+Base64 復号
- ファイル/カテゴリ/ビルドモード/ソースリスト抽出
- カテゴリパス再帰構築
- 実ソースの `#include` 正規表現スキャン（`#include "..."` / `#include <...>` 両対応）
- ベース名マッチで登録ファイルへの解決
- 3セクション構成の Markdown 出力
- `--list-modes` / `--no-scan` / `-m` / `-o`

これらの動作は**維持**すること。拡張（5章）は追加機能として実装する。

### 4.1 堅牢化要件（再実装時の必須事項）

現行初版の挙動を再実装する際、以下は退行させず必ず確保すること。

#### (a) ソースファイル読み込みの文字コード堅牢化

CS+ が生成する `.c`/`.h` は CP932 で保存されていることが多いため、
以下の順でフォールバック読み込みを行うこと：

1. `utf-8` で読み込み試行
2. 失敗時は `cp932` で再試行
3. 失敗時は `shift_jis` で再試行
4. すべて失敗した場合は `utf-8` + `errors='replace'` で強制読み込み

`#include` 行自体は ASCII だが、日本語コメントを含むファイルで
`UnicodeDecodeError` によるスクリプト停止を防ぐため必須。

#### (b) 物理行 → 論理行の連結（バックスラッシュ改行対応）

ファイル読み込み直後、**`#include` スキャンおよび条件評価を行う前に**、
バックスラッシュ改行（`\` 直後の LF または CRLF）を除去して論理行に連結する。
これは C 標準の翻訳フェーズ2 相当の処理で、以下のようなケースを正しく扱うために必須：

```c
#if MacroA && MacroB\
&& MacroC
#include "FFFF.h"
#endif
```

上記は `#if MacroA && MacroB && MacroC` として評価されること。
`#include` や `#define` の継続行にも同様に適用する。

実装例：`text = re.sub(r'\\\r?\n', '', text)` を読み込み直後に一度適用。

#### (c) `#include` 正規表現の許容範囲

`#` と `include` の間の空白、および行頭インデントの空白を許容すること。
具体的には `#  include "xxx.h"` や `  #include <yyy.h>` も拾えること。

参考実装：`r'^\s*#\s*include\s*[<"]([^">]+)[">]'`（`re.MULTILINE`）

#### (d) コメントの除去

`#include` スキャンおよび条件評価を行う前に、以下を除去すること：

- 行コメント `// ...`（行末まで）
- ブロックコメント `/* ... */`（複数行にまたがる場合あり）

理由：以下のようなコードで誤マッチを防ぐため。

```c
// #include "dummy.h"           ← 拾ってはいけない
/* #include "legacy.h" */       ← 拾ってはいけない
int x = 1; // #include "x.h"    ← 拾ってはいけない
```

実装上は 4.1(b) の論理行連結後、ディレクティブ解析前に
コメント除去パスを走らせるのが簡潔。文字列リテラル `"..."` 内の `//` や `/*` を
誤って除去しないよう、字句解析的な処理を推奨。

#### (e) 対象外（スコープ外）

以下はプリプロセッサの全機能展開が必要となるため**非対応**とし、
出力しない／無視する扱いとすること。

```c
#define INC_FILE "foo.h"
#include INC_FILE        ← マクロ経由の include は解析しない
```

このパターンに遭遇した場合は警告を出さず、単に無視する（行として拾わない）。

---

## 5. 追加機能：条件ディレクティブ評価（`--preprocess`）

### 5.1 目的

`.mtpj` の `COptionD-<N>` / `AsmOptionDefine-<N>` から得たマクロ集合を使い、
各ソースファイルの **条件ディレクティブを評価**して、
**非アクティブブロック内の `#include` を出力から除外する**。

再帰的な include 展開やマクロ本体の完全展開は**行わない**（スコープ外）。

### 5.2 サポート範囲

#### 必ずサポートする条件ディレクティブ

- `#if <expr>`
- `#ifdef NAME` / `#ifndef NAME`
- `#elif <expr>`
- `#else`
- `#endif`

#### `<expr>` 内で必ずサポートする構文

- `defined(NAME)` / `defined NAME`
- 論理: `&&`, `||`, `!`
- 比較: `==`, `!=`, `<`, `<=`, `>`, `>=`
- 算術: `+`, `-`, `*`, `/`, `%`
- ビット: `&`, `|`, `^`, `~`, `<<`, `>>`
- 括弧 `( )`
- 整数リテラル（10進・16進 `0x...`・8進 `0...`、サフィックス `u`/`U`/`l`/`L` は除去）
- 識別子: 定義済みなら値、未定義なら `0`

#### **必須テストケース（ユーザー要求）**

定義済みマクロ: `MacroA`, `MacroB`（`MacroC` は未定義）

```c
#if MacroA && MacroB
#include "DDDD.h"   // ← アクティブ。出力に含める
#endif

#if MacroA && MacroC
#include "EEEE.h"   // ← 非アクティブ。出力から除外
#endif
```

この例が `--preprocess` 有効時に正しく区別されること（自動テストで検証）。
なお `&`（単一）・`&&`（論理）どちらで書かれても 0/1 フラグなら同一結果になるため、両方テストを含める。

#### **必須テストケース（バックスラッシュ改行）**

定義済みマクロ: `MacroA`, `MacroB`（`MacroC` は未定義）

```c
#if MacroA && MacroB\
&& MacroC
#include "FFFF.h"   // ← 非アクティブ。除外されること
#endif

#if MacroA && MacroB\
&& MacroB
#include "GGGG.h"   // ← アクティブ。含まれること
#endif
```

論理行連結（4.1(b)）後に条件評価が行われ、上記が期待通りに区別されること。

### 5.3 保守的フォールバック

以下のケースは「判定不能 → **アクティブとみなす**（include を拾う）」
という **False Negative 回避**方針をとる：

- 関数形式マクロ使用（`#if FOO(1,2)`）
- 他ファイルの `#define` に依存する識別子（解決不能）
- パース/評価で例外発生
- 未サポート構文（三項演算子 `? :` 等）

保守的判定を行った箇所は出力 Markdown に注記する（例：「1 件の `#if` を保守的にアクティブ扱いとした」）。

### 5.4 実装指針

#### (a) 条件式 → 評価可能形式への変換

- 対応マッピング：`&&`→`and`, `||`→`or`, `!`→`not `, `defined(X)`→`(1 if 'X' in _defs else 0)`,
  識別子→定義値 or `0`、整数リテラルのサフィックス `u/U/l/L/ul/UL/...` は除去。
- **重要：単純な `str.replace` を使用しないこと**。以下の理由による：
  - `!` → `not ` の単純置換は `!=` を `not =` に壊す
  - `|` → `or` の単純置換は `||` や `|=` を破壊する
  - サフィックス除去を無条件で行うと識別子 `FLAG_USB` が `FLAG_SB` に化ける
- **正規表現による安全なトークン単位変換**を行うこと。具体策の例：
  - 演算子は長いものから順にマッチ（`&&`, `||`, `!=`, `==`, `<=`, `>=` を先に、`!` `&` `|` を後に）
  - 識別子は `\b[A-Za-z_][A-Za-z0-9_]*\b` で単語境界マッチ
  - 数値リテラル内のサフィックスのみを `\b(0[xX][0-9a-fA-F]+|[0-9]+)[uUlL]+\b` でマッチして除去
- あるいは C の条件式トークナイザを自前実装して、トークン列ベースで変換する方式も可（より堅牢）。

#### (b) 式の評価 — `eval` は使用禁止

セキュリティ上の理由により、Python `eval` / `exec` / `compile` の
動的実行系は**一切使用しないこと**。

代わりに `ast.parse(expr, mode='eval')` で AST を生成し、
**ホワイトリスト方式の AST Evaluator** を実装する。許可するノード：

| AST ノード                                           | 用途                                                                                                        |
| ---------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `ast.Expression`                                     | ルート                                                                                                      |
| `ast.Constant` (`int` のみ) / `ast.Num` (Py<3.8互換) | 数値リテラル                                                                                                |
| `ast.Name`                                           | 識別子（評価時に `_defs` 辞書から引く）                                                                     |
| `ast.BoolOp`                                         | `and` / `or`                                                                                                |
| `ast.UnaryOp`                                        | `not` / `-` / `+` / `~`                                                                                     |
| `ast.BinOp`                                          | `+ - * / % & \| ^ << >>`（`Add`/`Sub`/`Mult`/`FloorDiv`/`Mod`/`BitAnd`/`BitOr`/`BitXor`/`LShift`/`RShift`） |
| `ast.Compare`                                        | `== != < <= > >=`（`Eq`/`NotEq`/`Lt`/`LtE`/`Gt`/`GtE`）                                                     |

上記以外のノード（`Call`, `Attribute`, `Subscript`, `Lambda`, `Import` 等）に
遭遇した時点で例外を投げ、5.3 の保守的フォールバック（アクティブ扱い）に回すこと。

未定義識別子は `ast.Name` の evaluator 内で `0` を返す。

#### (c) ディレクティブ追跡

`#if` / `#ifdef` / `#ifndef` / `#elif` / `#else` / `#endif` をスタックで追跡する。
**`#elif` の評価には `branch_taken` 状態の管理が必須**。以下の3状態を各スタックフレームに持たせること：

```python
@dataclass
class IfFrame:
    parent_active: bool   # 親ブロックがアクティブか
    branch_taken: bool    # この #if〜#endif チェーン内で既に真ブランチに入ったか
    current_active: bool  # 今まさにアクティブなブランチ内か
```

- `#elif` 評価時は **`branch_taken=True` なら式を評価せず強制的に False** にする。
  これをやらないと以下で全ブランチが評価されてしまう：

  ```c
  #if A      // A=true → branch_taken=true
  ...
  #elif B    // branch_taken=true なので評価スキップ、current_active=false
  #elif C    // 同上
  #endif
  ```

- `#else` も同様に `branch_taken` を見て分岐する。
- 真ブランチに入った時点で `branch_taken=True` をセットする。

`#include` は `current_active=True` のブロック内のもののみ採用。

なお 4.1(b) の論理行連結は、ディレクティブ解析**より前**に適用済みであること。

#### (d) `defined` 演算子

`defined(NAME)` と `defined NAME`（括弧なし）の**両形式を必ずサポート**。
正規表現で両方を `(1 if 'NAME' in _defs else 0)` 相当に変換すること。

#### (e) C と Python の除算セマンティクス差異

C の `/` は整数同士なら整数除算（`5/2 → 2`）だが、
Python の `/` は浮動小数除算（`5/2 → 2.5`）。
AST Evaluator では **`ast.Div` を Python の `//`（整数除算）として評価**すること。
`%`（`ast.Mod`）は C/Python で一致するのでそのままでよい。

#### (f) 演算子優先順位差異の扱い（免責）

`--preprocess` における `#if` 式評価は、`#include` の有効/無効判定を
補助するための簡易評価である。C プリプロセッサの演算子優先順位を
完全再現することは目的としない。

特にビット演算子（`&`, `|`, `^`, `<<`, `>>`）と比較演算子を混在させた
複雑な式については、C 処理系と完全には一致しない可能性がある
（例：C では `a & b == c` が `a & (b == c)`、Python AST では `(a & b) == c`）。
そのような式は**括弧付きで記述されていることを前提**とし、
判定不能時は 5.3 の保守的フォールバック（アクティブ扱い）に回す。

### 5.5 CC-RL 組み込みマクロ allow-list

`.mtpj` に載らないコンパイラ組み込みマクロを外部 JSON で持つ。

**ファイル名**: `ccrl_builtins.json`（`mtpj_deps.py` と同階層に配置。存在しなければ空辞書扱い）

**形式**:

```json
{
  "__CCRL__": "1",
  "__RL78__": "1",
  "__K0R__": "1",
  "__RENESAS__": "1",
  "__RENESAS_VERSION__": "0x01000000"
}
```

- 利用者が自プロジェクトの CC-RL バージョンに合わせて編集できる。
- `--preprocess` 有効時、`COptionD-<N>` / `AsmOptionDefine-<N>` の内容に**マージ**して評価用マクロ辞書を作る。優先順は `.mtpj` の値 > 組み込み（同名キーは `.mtpj` を優先）。

### 5.6 出力の変更点

`--preprocess` 有効時、Markdown に以下を追加：

- セクション 1 の直下に **「Active defines (build-mode macros)」** サブセクション
  - `COptionD-<N>` 由来と組み込み由来を区別して列挙
- セクション 2 の見出しに `(preprocessed)` を付記
- セクション 3 の末尾に「Preprocessing notes」を追加
  - 保守的にアクティブ扱いとした `#if` の件数
  - スキャン対象ファイル数 / 評価成功ファイル数

`--preprocess` 未指定時の出力は現行と完全互換であること。

### 5.7 `--preprocess` 時の進捗ログ（stderr）

デバッグ性のため、`--preprocess` 有効時は stderr に以下のような
簡易ログを出力すること。標準出力（Markdown 本体）は汚染しない。

```text
[INFO] macros loaded: 24 (from mtpj: 19, from builtins: 5)
[INFO] files scanned: 68
[INFO] conditional blocks evaluated: 183
[INFO] conservative fallbacks: 2
```

内訳：

- `macros loaded` : 評価用マクロ辞書のサイズ。内訳（`.mtpj` 由来 / 組み込み由来）も表示
- `files scanned` : `#include` スキャン対象となったソースファイル数
- `conditional blocks evaluated` : 評価した `#if` / `#elif` の総数
- `conservative fallbacks` : 判定不能で保守的にアクティブ扱いとした件数

実装は `print(..., file=sys.stderr)` で十分。ロギングライブラリは不要。

---

## 6. 制限事項（README に記載すること）

1. **ファイル単位のビルド除外**: CS+ のファイルプロパティによるビルドモード別ファイル除外は未サポート。全ビルドモード共通ソースリストとして扱う。
2. **マクロの完全展開**: `--preprocess` 有効時も、`#include` ファイル側の `#define` は追わない。`COptionD` と組み込みマクロのみで評価。
3. **再帰的 include 展開**: 行わない（Copilot 用途では過剰）。
4. **同名ファイル**: 異なるフォルダに同名ファイルがある場合、`#include` の解決はベース名一致のため複数候補が列挙される。
5. **システムヘッダ**: `<stdint.h>` 等は未解決のまま表示（解決不要）。

---

## 7. 成果物一覧

Claude Code に実装してもらう成果物：

| ファイル                  | 内容                                                       |
| ------------------------- | ---------------------------------------------------------- |
| `mtpj_deps.py`            | 本体。現行機能 + `--preprocess` 拡張                       |
| `ccrl_builtins.json`      | CC-RL 組み込みマクロ allow-list（最低限のサンプル同梱）    |
| `README.md`               | 利用者向けドキュメント。推奨運用は `.mtpj` + `-m` 明示指定 |
| `tests/test_mtpj_deps.py` | 自動テスト（pytest）。5.2 の必須ケース含む                 |
| `tests/fixtures/`         | テスト用ミニ `.mtpj` + ソース群                            |

### 7.1 テスト要件

- 添付プロジェクト `RL78G14_Fast_Prototyping_Board_HostSample.mtpj` 相当の構造を持つ fixture を用意
- `MacroA && MacroB` / `MacroA && MacroC` の分岐テスト（`&&` と `&` の両方）
- **バックスラッシュ改行を含む `#if` 式のテスト**（5.2 の FFFF/GGGG 例）
- UTF-16LE+Base64 の BuildMode 復号テスト
- `--no-scan` / `--preprocess` / 未指定の3パターンで出力差分テスト
- 不正な `.mtpj`（壊れた XML、存在しないモード名）のエラーハンドリング
- 組み込みマクロ JSON が無い場合でも動作すること
- **CP932 で保存された `.c` ファイル**（日本語コメント入り）が `UnicodeDecodeError` を起こさず読めること
- **AST Evaluator 単体テスト**：許可されていないノード（例：`os.system` への参照、属性アクセス、関数呼び出し）を含む式を入力した際に、例外がキャッチされて保守的にアクティブ扱いになること
- **`str.replace` 落とし穴テスト**：`!=`、`FLAG_USB` のような識別子、`0x1UL` のようなサフィックス付きリテラルが破壊されず正しく評価されること
- **`#elif` チェーンテスト**：`#if A / #elif B / #elif C / #else` で複数ブランチがヒットし得る条件でも、**最初の真ブランチ以降がすべて非アクティブになる**こと
- **`defined` 両形式テスト**：`defined(X)` と `defined X`（括弧なし）が同じ結果になること
- **整数除算テスト**：`#if 5/2 == 2` が真、`#if 5/2 == 2.5` が偽になること（C セマンティクス準拠）
- **コメント除去テスト**：`// #include "dummy.h"` や `/* #include "x.h" */` が拾われないこと、文字列リテラル `"http://..."` 内の `//` がコメントとして誤除去されないこと

### 7.2 コーディング方針

- Python 3.7+ 標準ライブラリのみ（追加依存禁止）
- 型ヒント付与（`from __future__ import annotations` 可）
- docstring は日本語可
- CLI エラーは `sys.exit(...)` でメッセージ付き終了
- Windows / macOS / Linux で動作すること（パス区切り注意）

---

## 8. 運用シナリオ（README に反映）

### 基本フロー

```bash
# 1. ビルドモード一覧を確認
python mtpj_deps.py ./proj/Sample.mtpj --list-modes

# 2. ビルドモードを明示して生成（推奨運用）
python mtpj_deps.py ./proj/Sample.mtpj -m DefaultBuild \
    -o .github/copilot-project-structure.md

# 3. プリプロセスを有効にして、非アクティブ include を除外
python mtpj_deps.py ./proj/Sample.mtpj -m DefaultBuild --preprocess \
    -o .github/copilot-project-structure.md
```

### CI 連携例（GitHub Actions）

```yaml
- name: Regenerate Copilot project structure
  run: |
    python mtpj_deps.py ./proj/Sample.mtpj -m DefaultBuild --preprocess \
      -o .github/copilot-project-structure.md
```

### `.github/copilot-instructions.md` からの参照例

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

---

## 9. 会話履歴サマリ（Claude Code 向け補足）

本仕様は以下の経緯で確定：

1. 初期要件: `.mtpj` からビルドモード別の依存情報を Markdown で出力（`copilot-instructions.md` から参照する目的）
2. 初版実装: カテゴリ別ファイル一覧 + `[B]` マーク + `#include` 正規表現スキャンを実現
3. 運用方針確認: **`.mtpj` とビルドモードの明示指定を推奨**（`CurrentBuildMode` 依存は結果が環境依存になるため）
4. 拡張要望: `COptionD-<N>` のマクロで `#if/#ifdef` を評価し、非アクティブ include を除外したい
5. スコープ確定:
   - `#include` 行の active/inactive 判定のみ行う（再帰展開・完全マクロ展開はしない）
   - 複合条件 `MacroA && MacroB` 等は必須サポート
   - 判定不能は保守的にアクティブ扱い
   - 組み込みマクロは外部 JSON で差し替え可能
6. 堅牢化要件の追加（最終レビュー）:
   - バックスラッシュ改行（論理行連結）を必須サポート
   - 条件式変換は `str.replace` 禁止、正規表現/トークン単位で行う
   - 式評価は `eval` 禁止、`ast.parse` + ホワイトリスト AST Evaluator
   - ソース読み込みは UTF-8 → CP932 → Shift_JIS → `errors='replace'` フォールバック
   - `#include` 正規表現は `#  include` のような空白混在を許容（現行既対応、明文化）
7. 追加の実装地雷対策（最終レビュー2）:
   - `#elif` の `branch_taken` 状態管理を必須化（漏れると全ブランチ評価される）
   - `defined NAME`（括弧なし）の明示的サポート
   - C の整数除算セマンティクス対応（`5/2 → 2`、`ast.Div` を `//` として評価）
   - ビット演算と比較演算の優先順位差異は「括弧前提＋保守的フォールバック」で許容
   - コメント内 `#include` の誤マッチ防止（行・ブロック両コメント除去）
   - マクロ経由 `#include INC_FILE` はスコープ外（明示）
   - `--preprocess` 時に stderr へ進捗ログを出力

この仕様で実装を進めてください。
