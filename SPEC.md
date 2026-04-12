本ドキュメントは、Renesas CS+ プロジェクトファイル (.mtpj) を解析して

GitHub Copilot 用プロジェクト構造リファレンス Markdown を生成する

ツール mtpj_deps.py の完全な要件定義です。

Claude Code にはこのドキュメントを読んだうえで、mtpj_deps.py および周辺ファイル一式を実装してもらうことを想定しています。

1. 背景と目的

1.1 なぜ作るのか

Renesas CS+ の .mtpj はプロジェクト構造とビルド構成を持つが、GitHub Copilot は直接読み取れない。

Copilot に「どのファイルがどのビルドモードに参加しているか」「どのヘッダに依存するか」を正しく伝えるため、.github/copilot-instructions.md から参照するプロジェクト構造 Markdown が必要。

手書き・手更新では保守できないため、.mtpj から自動生成するツールを作る。

1.2 利用フロー

.mtpj ──[mtpj_deps.py]──► copilot-project-structure.md ◄──参照── .github/copilot-instructions.md

│

▼

GitHub Copilot

2. 入力 / 出力仕様

2.1 入力

必須: .mtpj ファイル（CS+ プロジェクトファイル、XML 形式）

必須（推奨運用）: ビルドモード名（-m オプション）

任意: スキャン対象のソースファイル（.mtpj からの相対パスで解決）

2.2 出力

単一の Markdown ファイル。以下3セクション構成：



Registered files (by category) — カテゴリ別ファイル一覧。ビルド対象は [B] でマーク。

Include dependencies — 実ソースをスキャンして抽出した #include 依存関係。プロジェクト内ファイルに解決できたものは → (project) で明示。

Summary — 登録ファイル数 / ビルド対象数 / カテゴリ数。

2.3 CLI 仕様

python mtpj_deps.py <project.mtpj> [options]

オプション必須説明<project.mtpj>✅解析対象の .mtpj パス-m, --mode MODE推奨対象ビルドモード名。省略時は CurrentBuildMode-o, --out PATH任意出力先。省略時は <mtpj名>_<mode>_deps.md--no-scan任意#include スキャンをスキップ--list-modes任意ビルドモード一覧を表示して終了--preprocess任意（新規追加）COptionD-<N> 等のマクロ定義に基づく条件ディレクティブ評価を有効化-h, --help任意ヘルプ3. .mtpj フォーマット仕様（解析対象）

.mtpj は UTF-8 の XML。以下の要素を抽出対象とする。



3.1 ファイル登録

<Instance Guid="...">

<n>r_main.c</n>

<Type>File</Type>

<RelativePath>src\r_main.c</RelativePath>

<ParentItem>633ddd13-...</ParentItem>

</Instance>

<RelativePath> の区切り文字は \（Windows 形式）。内部処理では / に正規化。

<ParentItem> は親 Category の Guid。

3.2 カテゴリ階層

<Instance Guid="633ddd13-...">

<n>コード生成</n>

<Type>Category</Type>

<ParentItem>4ae340d5-...</ParentItem>

</Instance>

ルートまで ParentItem を辿って "コード生成 / Platform / driver" のようなパス表記にする。

3.3 ビルドモード定義

BuildTool Instance 内に以下が格納される：



<BuildModeCount>3</BuildModeCount>

<BuildMode0>RABlAGYAYQB1AGwAdABCAHUAaQBsAGQA</BuildMode0>

<BuildMode1>...</BuildMode1>

<CurrentBuildMode>DefaultBuild</CurrentBuildMode>

重要: BuildMode<N> は UTF-16LE + Base64 でエンコードされている。base64.b64decode(v).decode('utf-16-le').rstrip('\x00')

インデックス <N> と復号後のビルドモード名は 1:1 対応。以降の各種オプション要素は -<N> サフィックスで識別される。

3.4 ビルド対象ソースリスト

<SourceItemGuid0>3c8caaf3-...</SourceItemGuid0>

<SourceItemType0>AsmSource</SourceItemType0>

<SourceItemGuid1>a4a26ac0-...</SourceItemGuid1>

<SourceItemType1>CSource</SourceItemType1>

SourceItemGuid<N> の値集合が「ビルド対象ファイル GUID 集合」。

現状の .mtpj ではソースリストは全ビルドモード共通で保持されている。ファイル単位のビルド除外は本ツールでは対象外（制限事項として README に明記済み）。

ここに載らない .h 等は「登録されているがビルド対象外」として扱う。

3.5 マクロ定義 / インクルードパス（プリプロセス機能で使用）

各ビルドモード index <N> に対し：



<COptionD-0>_USE_CCRL_RL78

USE_VUART_PROFILE

CFG_CON=1

CFG_SECLIB_BOND_NUM=1

</COptionD-0>



<AsmOptionDefine-0 />



<COptionIncludePath-0>...</COptionIncludePath-0>

COptionD-<N> : C コンパイラ -D 相当。改行区切り、NAME または NAME=VALUE。

AsmOptionDefine-<N> : アセンブラ向け -D 相当。同形式。

値なし定義は 1 として扱う（プリプロセッサ慣例）。

未定義識別子は #if 文脈で 0 に置換（C プリプロセッサ仕様通り）。

4. 既存実装（保持すべき動作）

現行 mtpj_deps.py（リポジトリにコミット済み）は以下を実装済み：



.mtpj の XML パース（xml.etree.ElementTree、名前空間に頑健）

BuildMode 名の UTF-16LE+Base64 復号

ファイル/カテゴリ/ビルドモード/ソースリスト抽出

カテゴリパス再帰構築

実ソースの #include 正規表現スキャン（#include "..." / #include <...> 両対応）

ベース名マッチで登録ファイルへの解決

3セクション構成の Markdown 出力

--list-modes / --no-scan / -m / -o

これらの動作は維持すること。拡張（5章）は追加機能として実装する。

5. 追加機能：条件ディレクティブ評価（--preprocess）

5.1 目的

.mtpj の COptionD-<N> / AsmOptionDefine-<N> から得たマクロ集合を使い、

各ソースファイルの 条件ディレクティブを評価して、非アクティブブロック内の #include を出力から除外する。

再帰的な include 展開やマクロ本体の完全展開は行わない（スコープ外）。



5.2 サポート範囲

必ずサポートする条件ディレクティブ

#if <expr>

#ifdef NAME / #ifndef NAME

#elif <expr>

#else

#endif

<expr> 内で必ずサポートする構文

defined(NAME) / defined NAME

論理: &&, ||, !

比較: ==, !=, <, <=, >, >=

算術: +, -, *, /, %

ビット: &, |, ^, ~, <<, >>

括弧 ( )

整数リテラル（10進・16進 0x...・8進 0...、サフィックス u/U/l/L は除去）

識別子: 定義済みなら値、未定義なら 0

必須テストケース（ユーザー要求）

定義済みマクロ: MacroA, MacroB（MacroC は未定義）



#if MacroA && MacroB

#include "DDDD.h" // ← アクティブ。出力に含める

#endif



#if MacroA && MacroC

#include "EEEE.h" // ← 非アクティブ。出力から除外

#endif

この例が --preprocess 有効時に正しく区別されること（自動テストで検証）。

なお &（単一）・&&（論理）どちらで書かれても 0/1 フラグなら同一結果になるため、両方テストを含める。



5.3 保守的フォールバック

以下のケースは「判定不能 → アクティブとみなす（include を拾う）」

という False Negative 回避方針をとる：



関数形式マクロ使用（#if FOO(1,2)）

他ファイルの #define に依存する識別子（解決不能）

パース/評価で例外発生

未サポート構文（三項演算子 ? : 等）

保守的判定を行った箇所は出力 Markdown に注記する（例：「1 件の #if を保守的にアクティブ扱いとした」）。



5.4 実装指針

条件式 → Python 式への変換：&&→and, ||→or, !→not , defined(X)→(1 if 'X' in _defs else 0), 識別子→値 or 0

制限された namespace（__builtins__: {}）で eval

#if/#elif/#else/#endif をスタックで追跡。各ブロックに「active/inactive/skip(親が非アクティブ)」状態を持たせる

include 行はアクティブなブロック内のもののみ採用

式評価はファイル単位。#define による動的なマクロ追加は追わない（スコープ外）

5.5 CC-RL 組み込みマクロ allow-list

.mtpj に載らないコンパイラ組み込みマクロを外部 JSON で持つ。

ファイル名: ccrl_builtins.json（mtpj_deps.py と同階層に配置。存在しなければ空辞書扱い）

形式:



{

"__CCRL__": "1",

"__RL78__": "1",

"__K0R__": "1",

"__RENESAS__": "1",

"__RENESAS_VERSION__": "0x01000000"

}

利用者が自プロジェクトの CC-RL バージョンに合わせて編集できる。

--preprocess 有効時、COptionD-<N> / AsmOptionDefine-<N> の内容にマージして評価用マクロ辞書を作る。優先順は .mtpj の値 > 組み込み（同名キーは .mtpj を優先）。

5.6 出力の変更点

--preprocess 有効時、Markdown に以下を追加：



セクション 1 の直下に 「Active defines (build-mode macros)」 サブセクションCOptionD-<N> 由来と組み込み由来を区別して列挙

セクション 2 の見出しに (preprocessed) を付記

セクション 3 の末尾に「Preprocessing notes」を追加保守的にアクティブ扱いとした #if の件数

スキャン対象ファイル数 / 評価成功ファイル数
