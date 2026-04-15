"""mtpj_deps.py — Renesas CS+ .mtpj を解析して GitHub Copilot 用 Markdown を生成する。"""
from __future__ import annotations

import ast
import base64
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import xml.etree.ElementTree as ET
import xml.parsers.expat as expat


# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------
ENCODING_FALLBACKS = ['utf-8', 'cp932', 'shift_jis']
INCLUDE_RE = re.compile(r'^\s*#\s*include\s*[<"]([^">]+)[">]', re.MULTILINE)

# .mtpj ファイルの最大許容サイズ（DoS 軽減: 10 MB）
_MAX_MTPJ_BYTES = 10 * 1024 * 1024

# ---------------------------------------------------------------------------
# データクラス
# ---------------------------------------------------------------------------
@dataclass
class FileEntry:
    """プロジェクトに登録されたファイル1件。"""
    guid: str
    name: str
    rel_path: str          # '/' 正規化済み
    category_path: str     # "Cat / Sub / ..." 形式
    is_build_target: bool = False


@dataclass
class IfFrame:
    """条件ディレクティブのスタックフレーム。"""
    parent_active: bool    # 親ブロックがアクティブか
    branch_taken: bool     # この if〜endif チェーンで既に真ブランチに入ったか
    current_active: bool   # 現在アクティブなブランチ内か


# ---------------------------------------------------------------------------
# ユーティリティ
# ---------------------------------------------------------------------------
def read_source_file(path: Path) -> str:
    """ソースファイルを文字コードフォールバック付きで読む。"""
    for enc in ENCODING_FALLBACKS:
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return path.read_text(encoding='utf-8', errors='replace')


def join_continuation_lines(text: str) -> str:
    """バックスラッシュ改行（翻訳フェーズ2）を除去して論理行に連結する。"""
    return re.sub(r'\\\r?\n', '', text)


def remove_comments(text: str) -> str:
    """行コメント・ブロックコメントを除去する。文字列リテラル内は保護する。"""
    result: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        # 文字列リテラル（ダブルクォート）を読み飛ばす
        if text[i] == '"':
            result.append(text[i])
            i += 1
            while i < n:
                ch = text[i]
                result.append(ch)
                if ch == '\\' and i + 1 < n:
                    i += 1
                    result.append(text[i])
                elif ch == '"':
                    break
                i += 1
            i += 1
        # 文字リテラル（シングルクォート）を読み飛ばす
        elif text[i] == "'":
            result.append(text[i])
            i += 1
            while i < n:
                ch = text[i]
                result.append(ch)
                if ch == '\\' and i + 1 < n:
                    i += 1
                    result.append(text[i])
                elif ch == "'":
                    break
                i += 1
            i += 1
        # ブロックコメント
        elif text[i:i+2] == '/*':
            i += 2
            while i < n and text[i:i+2] != '*/':
                if text[i] == '\n':
                    result.append('\n')
                i += 1
            i += 2  # '*/' をスキップ
        # 行コメント
        elif text[i:i+2] == '//':
            i += 2
            while i < n and text[i] != '\n':
                i += 1
        else:
            result.append(text[i])
            i += 1
    return ''.join(result)


def decode_build_mode(b64: str) -> str:
    """UTF-16LE + Base64 エンコードされたビルドモード名を復号する。"""
    raw = base64.b64decode(b64)
    return raw.decode('utf-16-le').rstrip('\x00')


def _md_code(s: str) -> str:
    """Markdown のバッククォートコードスパン内に埋め込む文字列をサニタイズする。

    改行・制御文字（コードスパンを壊す）とバッククォート（スパンを脱出できる）を
    除去または置換する。
    """
    s = re.sub(r'[\x00-\x1f\x7f]', '', s)   # 制御文字を除去
    s = s.replace('`', '\u02cb')              # バッククォートを類似文字 ˋ に置換
    return s


def _md_heading(s: str) -> str:
    """Markdown の見出し行（# / ## / ### ...）に埋め込む文字列をサニタイズする。

    改行（見出しを終わらせ偽の行を挿入できる）と
    バッククォート（インラインコードの誤生成）を除去または置換する。
    """
    s = re.sub(r'[\x00-\x1f\x7f]', '', s)   # 制御文字・改行を除去
    s = s.replace('`', '\u02cb')              # バッククォートを置換
    return s


def _plain(s: str) -> str:
    """標準出力・標準エラー出力の 1 行として出力する文字列をサニタイズする。

    改行・制御文字（ログ行注入）と ANSI エスケープシーケンス（端末操作）を除去する。
    """
    s = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', s)   # ANSI エスケープを除去
    s = re.sub(r'[\x00-\x1f\x7f]', '', s)          # 制御文字・改行を除去
    return s


def _is_within_base(base_dir: Path, rel_path: str) -> bool:
    """
    rel_path を base_dir に結合して解決したパスが base_dir の外を指していないか検証する。
    パストラバーサル（../../../ 等）を防ぐために使用する。
    """
    try:
        resolved = (base_dir / rel_path).resolve()
        resolved.relative_to(base_dir.resolve())
        return True
    except (ValueError, OSError):
        return False


def _parse_xml_safe(path: Path) -> ET.ElementTree:
    """
    エンティティ系 XML 攻撃を遮断した安全な XML パーサ。

    Python 標準の ET.parse は内部エンティティ展開（billion laughs 等）を防がない。
    xml.parsers.expat を直接使い、EntityDeclHandler / StartDoctypeDeclHandler で
    宣言を検知した時点で ParseError を送出することで展開処理に到達させない。
    """
    builder = ET.TreeBuilder()

    def _block(*_: object) -> None:
        raise ET.ParseError('XML エンティティ定義・DOCTYPE 宣言は許可されていません')

    p = expat.ParserCreate()
    p.StartElementHandler = lambda name, attrs: builder.start(name, attrs)
    p.EndElementHandler = lambda name: builder.end(name)
    p.CharacterDataHandler = lambda data: builder.data(data)
    p.EntityDeclHandler = _block
    p.StartDoctypeDeclHandler = _block

    with path.open('rb') as f:
        data = f.read()
    try:
        p.Parse(data, True)
    except expat.ExpatError as e:
        raise ET.ParseError(str(e)) from e

    return ET.ElementTree(builder.close())


# ---------------------------------------------------------------------------
# .mtpj パーサ
# ---------------------------------------------------------------------------
@dataclass
class MtpjProject:
    """パース結果を保持する。"""
    files: dict[str, FileEntry] = field(default_factory=dict)   # guid → FileEntry
    build_modes: list[str] = field(default_factory=list)
    current_build_mode: str = ''
    build_target_guids: set[str] = field(default_factory=set)
    macros_by_mode_index: dict[int, dict[str, str]] = field(default_factory=dict)
    include_paths_by_mode_index: dict[int, list[str]] = field(default_factory=dict)


def _parse_macros(raw: str) -> dict[str, str]:
    """改行区切りの NAME または NAME=VALUE をパースする。"""
    result: dict[str, str] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if '=' in line:
            k, _, v = line.partition('=')
            result[k.strip()] = v.strip()
        else:
            result[line] = '1'
    return result


def parse_mtpj(mtpj_path: Path) -> MtpjProject:
    """
    .mtpj XML を解析して MtpjProject を返す。
    名前空間に依存しないよう、タグのローカル名で比較する。
    """
    proj = MtpjProject()

    if not mtpj_path.exists():
        sys.exit(f'[ERROR] ファイルが見つかりません: {mtpj_path}')

    file_size = mtpj_path.stat().st_size
    if file_size > _MAX_MTPJ_BYTES:
        sys.exit(f'[ERROR] .mtpj ファイルが大きすぎます ({file_size:,} bytes)。上限: {_MAX_MTPJ_BYTES:,} bytes')

    try:
        tree = _parse_xml_safe(mtpj_path)
    except ET.ParseError as e:
        sys.exit(f'[ERROR] .mtpj の XML パースに失敗しました: {e}')

    root = tree.getroot()

    # すべての Instance 要素を収集
    # 名前空間を無視するため、ローカル名で検索
    def local(tag: str) -> str:
        return tag.split('}', 1)[-1] if '}' in tag else tag

    def find_text(elem: ET.Element, tag: str) -> str:
        """深さ優先でタグを探す。ネストした Instance 要素の内部には立ち入らない。
        再帰を使わずスタックで実装し、深いネストによる RecursionError を防ぐ。
        """
        stack = list(reversed(list(elem)))
        while stack:
            child = stack.pop()
            child_local = local(child.tag)
            if child_local == 'Instance':
                continue  # このサブツリー全体をスキップ
            if child_local == tag:
                return (child.text or '').strip()
            stack.extend(reversed(list(child)))
        return ''

    instances: list[ET.Element] = []
    # RL78系: Instance の親は <Instances>
    # RX系  : Instance の親は <Class>（同一 Class 内に複数の兄弟 Instance がある）
    # parent_map を使って BuildTool Instance の親要素を特定し、
    # マクロ・インクルードパスを親スコープから検索できるようにする。
    parent_map: dict[ET.Element, ET.Element] = {}
    for elem in root.iter():
        if local(elem.tag) == 'Instance':
            instances.append(elem)
        for child in elem:
            parent_map[child] = elem

    # guid → name / type / rel_path / parent_guid のマッピング
    raw_items: dict[str, dict] = {}
    for inst in instances:
        guid = inst.get('Guid', '')
        if not guid:
            continue
        item_type = find_text(inst, 'Type')
        # CS+ RX系では同一 GUID の Instance が複数存在する場合がある。
        # 後から現れるビルド設定専用 Instance（Type が空）で
        # File / Category エントリを上書きしないよう保護する。
        existing = raw_items.get(guid)
        if existing and existing['type'] in ('File', 'Category') and item_type not in ('File', 'Category'):
            continue
        # 名前タグは CS+ RL78 系では <n>、RX 系では <Name> を使う
        name = find_text(inst, 'n') or find_text(inst, 'Name')
        rel_path = find_text(inst, 'RelativePath').replace('\\', '/')
        parent = find_text(inst, 'ParentItem')
        raw_items[guid] = {
            'type': item_type,
            'name': name,
            'rel_path': rel_path,
            'parent': parent,
        }

    # カテゴリパスを再帰的に構築
    def build_category_path(guid: str, depth: int = 0) -> str:
        if depth > 50 or guid not in raw_items:
            return ''
        item = raw_items[guid]
        if item['type'] != 'Category':
            return ''
        parent_path = build_category_path(item['parent'], depth + 1)
        if parent_path:
            return parent_path + ' / ' + item['name']
        return item['name']

    # File エントリを構築
    for guid, item in raw_items.items():
        if item['type'] == 'File':
            cat_path = build_category_path(item['parent'])
            proj.files[guid] = FileEntry(
                guid=guid,
                name=item['name'],
                rel_path=item['rel_path'],
                category_path=cat_path,
            )

    # BuildTool Instance からビルドモードとソースリストを抽出
    for inst in instances:
        # BuildModeCount があれば BuildTool Instance
        bmc_elem = None
        for elem in inst.iter():
            if local(elem.tag) == 'BuildModeCount':
                bmc_elem = elem
                break
        if bmc_elem is None:
            continue

        # ビルドモード名を復号
        try:
            count = int((bmc_elem.text or '0').strip())
        except ValueError:
            count = 0

        modes: list[str] = []
        for idx in range(count):
            for elem in inst.iter():
                if local(elem.tag) == f'BuildMode{idx}':
                    raw_b64 = (elem.text or '').strip()
                    try:
                        modes.append(decode_build_mode(raw_b64))
                    except Exception:
                        modes.append(raw_b64)
                    break

        proj.build_modes = modes

        # CurrentBuildMode
        proj.current_build_mode = ''
        for elem in inst.iter():
            if local(elem.tag) == 'CurrentBuildMode':
                proj.current_build_mode = (elem.text or '').strip()
                break

        # ソースリスト（SourceItemGuid<N>）
        # BuildTool Instance 内のどの階層にあっても拾えるよう iter() で再帰検索する
        src_guids: set[str] = set()
        for elem in inst.iter():
            tag = local(elem.tag)
            if tag.startswith('SourceItemGuid'):
                val = (elem.text or '').strip()
                if val:
                    src_guids.add(val)
        proj.build_target_guids = src_guids

        # マクロ・インクルードパスを検索する。
        # RL78(CC-RL): COptionD-<N> / RX(CC-RX): COptionDefine-<N>
        # アセンブラ define は両系で AsmOptionDefine-<N> 共通。
        # インクルードパス: RL78 は COptionIncludePath-<N> / RX は COptionInclude-<N>
        #
        # RX系では BuildTool Instance とオプション Instance が同一 Class 内の
        # 兄弟要素に分かれているため、親要素（Class / Instances）を起点に検索する。
        # RL78系では BuildTool Instance の内部にすべてのオプションがあるが、
        # 親要素を起点にしても同じ結果が得られる。
        opt_scope = parent_map.get(inst, inst)

        for idx in range(count):
            macros: dict[str, str] = {}
            for elem in opt_scope.iter():
                tag = local(elem.tag)
                if tag in (f'COptionD-{idx}', f'COptionDefine-{idx}', f'AsmOptionDefine-{idx}'):
                    raw = (elem.text or '').strip()
                    if raw:
                        macros.update(_parse_macros(raw))
            proj.macros_by_mode_index[idx] = macros

            inc_paths: list[str] = []
            for elem in opt_scope.iter():
                tag = local(elem.tag)
                if tag in (f'COptionIncludePath-{idx}', f'COptionInclude-{idx}'):
                    raw = (elem.text or '').strip()
                    if raw:
                        inc_paths = [p.strip() for p in raw.splitlines() if p.strip()]
                    break
            proj.include_paths_by_mode_index[idx] = inc_paths

        # 最初の BuildTool Instance だけ見る
        break

    # ビルド対象フラグをセット
    for guid, fe in proj.files.items():
        fe.is_build_target = guid in proj.build_target_guids

    return proj


# ---------------------------------------------------------------------------
# AST Evaluator（eval 禁止）
# ---------------------------------------------------------------------------
class _EvalError(Exception):
    """評価不能な構文に遭遇したことを示す。"""


def _eval_node(node: ast.AST, defs: dict[str, int]) -> int:
    """ホワイトリスト方式の AST ノード評価器。整数値を返す。"""
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, defs)

    # 数値リテラル
    if isinstance(node, ast.Constant):
        if isinstance(node.value, int):
            return node.value
        if isinstance(node.value, float):
            # 整数除算の結果として float が来た場合（本来は発生しないが念のため）
            return int(node.value)
        raise _EvalError(f'非整数リテラル: {node.value!r}')

    # 識別子: 定義済みなら値、未定義なら 0
    if isinstance(node, ast.Name):
        return defs.get(node.id, 0)

    # 単項演算子
    if isinstance(node, ast.UnaryOp):
        val = _eval_node(node.operand, defs)
        if isinstance(node.op, ast.Not):
            return 0 if val else 1
        if isinstance(node.op, ast.USub):
            return -val
        if isinstance(node.op, ast.UAdd):
            return val
        if isinstance(node.op, ast.Invert):
            return ~val
        raise _EvalError(f'未サポート単項演算子: {type(node.op).__name__}')

    # 論理演算子
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            result = 1
            for v in node.values:
                ev = _eval_node(v, defs)
                if not ev:
                    return 0
                result = ev
            return result
        if isinstance(node.op, ast.Or):
            for v in node.values:
                ev = _eval_node(v, defs)
                if ev:
                    return ev
            return 0
        raise _EvalError(f'未サポート論理演算子: {type(node.op).__name__}')

    # 二項演算子
    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left, defs)
        right = _eval_node(node.right, defs)
        op = node.op
        if isinstance(op, ast.Add):
            return left + right
        if isinstance(op, ast.Sub):
            return left - right
        if isinstance(op, ast.Mult):
            return left * right
        if isinstance(op, ast.Div):
            # C セマンティクス: 整数除算
            if right == 0:
                raise _EvalError('ゼロ除算')
            return int(left / right)
        if isinstance(op, ast.FloorDiv):
            if right == 0:
                raise _EvalError('ゼロ除算')
            return left // right
        if isinstance(op, ast.Mod):
            if right == 0:
                raise _EvalError('ゼロ除算')
            return left % right
        if isinstance(op, ast.BitAnd):
            return left & right
        if isinstance(op, ast.BitOr):
            return left | right
        if isinstance(op, ast.BitXor):
            return left ^ right
        if isinstance(op, ast.LShift):
            return left << right
        if isinstance(op, ast.RShift):
            return left >> right
        raise _EvalError(f'未サポート二項演算子: {type(op).__name__}')

    # 比較演算子
    if isinstance(node, ast.Compare):
        left = _eval_node(node.left, defs)
        for op, comparator in zip(node.ops, node.comparators):
            right = _eval_node(comparator, defs)
            if isinstance(op, ast.Eq):
                result = left == right
            elif isinstance(op, ast.NotEq):
                result = left != right
            elif isinstance(op, ast.Lt):
                result = left < right
            elif isinstance(op, ast.LtE):
                result = left <= right
            elif isinstance(op, ast.Gt):
                result = left > right
            elif isinstance(op, ast.GtE):
                result = left >= right
            else:
                raise _EvalError(f'未サポート比較演算子: {type(op).__name__}')
            if not result:
                return 0
            left = right
        return 1

    raise _EvalError(f'ホワイトリスト外の AST ノード: {type(node).__name__}')


# ---------------------------------------------------------------------------
# 条件式変換（C → Python AST に変換できる形式へ）
# ---------------------------------------------------------------------------

# defined(X) または defined X → __defined_X__ という一時名に変換し、
# 後段で defs 辞書をもとに 0/1 に置換する
_DEFINED_PAREN_RE = re.compile(r'\bdefined\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)')
_DEFINED_BARE_RE = re.compile(r'\bdefined\s+([A-Za-z_][A-Za-z0-9_]*)')

# 整数リテラルのサフィックス除去: 0x1UL, 3ul など
# ※ 識別子の末尾は触らない（[A-Za-z_] が先行しないもの）
_INT_SUFFIX_RE = re.compile(r'\b(0[xX][0-9a-fA-F]+|[0-9]+)[uUlL]+\b')

# C 演算子 → Python に変換するトークン単位の置換（長いものを先に）
# 順序: &&, ||, !=, ==, <=, >=, !, & (単独), | (単独)
_OP_REPLACEMENTS = [
    (re.compile(r'&&'),  ' and '),
    (re.compile(r'\|\|'), ' or '),
    # ! は != の後に処理
    (re.compile(r'!='),  ' != '),
    (re.compile(r'=='),  ' == '),
    (re.compile(r'<='),  ' <= '),
    (re.compile(r'>='),  ' >= '),
    # 単独の ! (直後が = でない位置)
    (re.compile(r'!(?!=)'), ' not '),
]


def _transform_expr(expr: str, defs: dict[str, int]) -> tuple[str, dict[str, int]]:
    """
    C プリプロセッサ条件式を Python の ast.parse が受け付ける形に変換する。
    返り値: (変換後の式文字列, 評価用名前辞書)
    """
    # defined(X) → __D_X__ 形式の一時識別子に変換
    # defs に __D_X__ = (1 if X in defs else 0) を追加
    eval_defs = dict(defs)

    def replace_defined_paren(m: re.Match) -> str:
        name = m.group(1)
        tmp = f'__D_{name}__'
        eval_defs[tmp] = 1 if name in defs else 0
        return tmp

    def replace_defined_bare(m: re.Match) -> str:
        name = m.group(1)
        tmp = f'__D_{name}__'
        eval_defs[tmp] = 1 if name in defs else 0
        return tmp

    expr = _DEFINED_PAREN_RE.sub(replace_defined_paren, expr)
    expr = _DEFINED_BARE_RE.sub(replace_defined_bare, expr)

    # 整数リテラルのサフィックス除去
    expr = _INT_SUFFIX_RE.sub(lambda m: m.group(1), expr)

    # C演算子 → Python演算子
    for pattern, repl in _OP_REPLACEMENTS:
        expr = pattern.sub(repl, expr)

    return expr, eval_defs


def evaluate_expr(expr: str, defs: dict[str, int]) -> tuple[bool, bool]:
    """
    C プリプロセッサ条件式を評価する。
    返り値: (評価結果, 保守的フォールバックが必要だったか)
    """
    try:
        py_expr, eval_defs = _transform_expr(expr.strip(), defs)
        tree = ast.parse(py_expr, mode='eval')
        val = _eval_node(tree, eval_defs)
        return bool(val), False
    except Exception:
        return True, True  # 保守的フォールバック: アクティブとみなす


# ---------------------------------------------------------------------------
# #include スキャナ（条件ディレクティブ評価付き）
# ---------------------------------------------------------------------------
@dataclass
class ScanResult:
    """1ファイルのスキャン結果。"""
    includes: list[str] = field(default_factory=list)
    fallback_count: int = 0   # 保守的フォールバック件数
    cond_eval_count: int = 0  # 評価した条件式の数


def scan_includes(
    source_path: Path,
    use_preprocess: bool,
    defs: dict[str, int],
) -> Optional[ScanResult]:
    """
    ソースファイルを読み込み、#include を抽出する。
    use_preprocess=True の場合は条件ディレクティブを評価する。
    ファイルが存在しない場合は None を返す。
    """
    if not source_path.exists():
        return None

    text = read_source_file(source_path)
    text = join_continuation_lines(text)
    text = remove_comments(text)

    result = ScanResult()

    if not use_preprocess:
        for m in INCLUDE_RE.finditer(text):
            result.includes.append(m.group(1))
        return result

    # 条件ディレクティブを追跡しながらスキャン
    stack: list[IfFrame] = []

    def is_active() -> bool:
        if not stack:
            return True
        return stack[-1].current_active and stack[-1].parent_active

    for line in text.splitlines():
        stripped = line.strip()

        # ディレクティブ判定
        directive_m = re.match(r'^\s*#\s*(\w+)(.*)', stripped)
        if directive_m:
            directive = directive_m.group(1)
            rest = directive_m.group(2).strip()

            if directive == 'if':
                parent = is_active()
                active, fallback = evaluate_expr(rest, defs) if parent else (False, False)
                if parent and fallback:
                    result.fallback_count += 1
                if parent:
                    result.cond_eval_count += 1
                stack.append(IfFrame(
                    parent_active=parent,
                    branch_taken=active,
                    current_active=active,
                ))

            elif directive == 'ifdef':
                name = rest.split()[0] if rest.split() else ''
                parent = is_active()
                active = parent and (name in defs)
                stack.append(IfFrame(
                    parent_active=parent,
                    branch_taken=active,
                    current_active=active,
                ))
                if parent:
                    result.cond_eval_count += 1

            elif directive == 'ifndef':
                name = rest.split()[0] if rest.split() else ''
                parent = is_active()
                active = parent and (name not in defs)
                stack.append(IfFrame(
                    parent_active=parent,
                    branch_taken=active,
                    current_active=active,
                ))
                if parent:
                    result.cond_eval_count += 1

            elif directive == 'elif':
                if stack:
                    frame = stack[-1]
                    if frame.branch_taken:
                        # 既に真ブランチに入っていた → このブランチは非アクティブ
                        frame.current_active = False
                    else:
                        active, fallback = (
                            evaluate_expr(rest, defs) if frame.parent_active else (False, False)
                        )
                        if frame.parent_active and fallback:
                            result.fallback_count += 1
                        if frame.parent_active:
                            result.cond_eval_count += 1
                        frame.current_active = frame.parent_active and active
                        if frame.current_active:
                            frame.branch_taken = True

            elif directive == 'else':
                if stack:
                    frame = stack[-1]
                    frame.current_active = frame.parent_active and not frame.branch_taken

            elif directive == 'endif':
                if stack:
                    stack.pop()

            elif directive == 'include':
                if is_active():
                    # マクロ経由（識別子のみ）は無視
                    inc_m = re.match(r'^[<"]([^">]+)[">]', rest)
                    if inc_m:
                        result.includes.append(inc_m.group(1))
                continue

        # ディレクティブでない通常行の #include チェック
        # （上で directive=='include' を処理済みだが、行全体での正規表現も走らせる）
        if not directive_m and is_active():
            for m in INCLUDE_RE.finditer(line):
                result.includes.append(m.group(1))

    return result


# ---------------------------------------------------------------------------
# Markdown 生成
# ---------------------------------------------------------------------------
def resolve_include(header: str, files: dict[str, FileEntry]) -> list[FileEntry]:
    """ヘッダ名をプロジェクト登録ファイルにベース名マッチで解決する。"""
    base = Path(header).name
    return [fe for fe in files.values() if Path(fe.rel_path).name == base]


def generate_markdown(
    proj: MtpjProject,
    mode_name: str,
    mode_index: int,
    mtpj_path: Path,
    use_preprocess: bool,
    no_scan: bool,
    builtin_macros: dict[str, str],
) -> str:
    """出力 Markdown を生成する。"""
    lines: list[str] = []

    # ヘッダ
    lines.append(f'# Project structure: {_md_heading(mtpj_path.name)} / {_md_heading(mode_name)}')
    lines.append('')

    # -----------------------------------------------------------------------
    # Section 1: Registered files (by category)
    # -----------------------------------------------------------------------
    lines.append('## 1. Registered files (by category)')
    lines.append('')
    lines.append('`[B]` = build target for this mode')
    lines.append('')

    # カテゴリ別に整理
    from collections import defaultdict
    by_cat: dict[str, list[FileEntry]] = defaultdict(list)
    for fe in proj.files.values():
        by_cat[fe.category_path].append(fe)

    for cat in sorted(by_cat.keys()):
        lines.append(f'### {_md_heading(cat) if cat else "(root)"}')
        for fe in sorted(by_cat[cat], key=lambda x: x.rel_path):
            mark = '[B] ' if fe.is_build_target else '     '
            lines.append(f'- {mark}`{_md_code(fe.rel_path)}`')
        lines.append('')

    # Section 1 サブセクション: --preprocess 時のマクロ一覧
    if use_preprocess:
        lines.append('### Active defines (build-mode macros)')
        lines.append('')
        mode_macros = proj.macros_by_mode_index.get(mode_index, {})
        if mode_macros:
            lines.append('**From project (compiler defines):**')
            lines.append('')
            for k, v in sorted(mode_macros.items()):
                lines.append(f'- `{_md_code(k)}` = `{_md_code(v)}`')
            lines.append('')
        if builtin_macros:
            lines.append('**From compiler built-ins:**')
            lines.append('')
            for k, v in sorted(builtin_macros.items()):
                lines.append(f'- `{_md_code(k)}` = `{_md_code(v)}`')
            lines.append('')

    # -----------------------------------------------------------------------
    # Section 2: Include dependencies
    # -----------------------------------------------------------------------
    preprocess_label = ' (preprocessed)' if use_preprocess else ''
    lines.append(f'## 2. Include dependencies{preprocess_label}')
    lines.append('')

    total_fallbacks = 0
    files_scanned = 0
    files_eval_ok = 0
    total_cond_evals = 0

    if no_scan:
        lines.append('_(#include scan skipped: `--no-scan`)_')
        lines.append('')
    else:
        # 評価用マクロ辞書の構築（--preprocess 時）
        eval_defs: dict[str, int] = {}
        if use_preprocess:
            # 組み込みマクロを先に入れ、.mtpj の値で上書き（優先順: .mtpj > 組み込み）
            for k, v in builtin_macros.items():
                try:
                    eval_defs[k] = int(v, 0)
                except ValueError:
                    eval_defs[k] = 1
            mode_macros = proj.macros_by_mode_index.get(mode_index, {})
            for k, v in mode_macros.items():
                try:
                    eval_defs[k] = int(v, 0)
                except ValueError:
                    eval_defs[k] = 1

            # 進捗ログ（stderr）
            n_mtpj = len(proj.macros_by_mode_index.get(mode_index, {}))
            n_builtin = len(builtin_macros)
            print(
                f'[INFO] macros loaded: {len(eval_defs)} '
                f'(from mtpj: {n_mtpj}, from builtins: {n_builtin})',
                file=sys.stderr,
            )

        # ソースファイルをスキャン（ビルド対象ファイルのみ）
        mtpj_dir = mtpj_path.parent
        scan_entries = [fe for fe in proj.files.values() if fe.is_build_target]

        for fe in sorted(scan_entries, key=lambda x: x.rel_path):
            if not _is_within_base(mtpj_dir, fe.rel_path):
                print(f'[WARN] プロジェクト外パスをスキップ: {_plain(fe.rel_path)}', file=sys.stderr)
                continue
            src_path = mtpj_dir / fe.rel_path
            scan = scan_includes(src_path, use_preprocess, eval_defs)
            if scan is None:
                continue

            files_scanned += 1
            if scan.fallback_count == 0 or not use_preprocess:
                files_eval_ok += 1
            total_fallbacks += scan.fallback_count
            total_cond_evals += scan.cond_eval_count

            if not scan.includes:
                continue

            lines.append(f'### `{_md_code(fe.rel_path)}`')
            for inc in scan.includes:
                resolved = resolve_include(inc, proj.files)
                if resolved:
                    targets = ', '.join(f'`{_md_code(r.rel_path)}`' for r in resolved)
                    lines.append(f'- `{_md_code(inc)}` → (project) {targets}')
                else:
                    lines.append(f'- `{_md_code(inc)}`')
            lines.append('')

        if use_preprocess:
            print(f'[INFO] files scanned: {files_scanned}', file=sys.stderr)
            print(f'[INFO] conditional blocks evaluated: {total_cond_evals}', file=sys.stderr)
            print(f'[INFO] conservative fallbacks: {total_fallbacks}', file=sys.stderr)

    # -----------------------------------------------------------------------
    # Section 3: Summary
    # -----------------------------------------------------------------------
    lines.append('## 3. Summary')
    lines.append('')
    total_files = len(proj.files)
    build_files = sum(1 for fe in proj.files.values() if fe.is_build_target)
    categories = len({fe.category_path for fe in proj.files.values()})
    lines.append(f'| Item | Count |')
    lines.append(f'|------|-------|')
    lines.append(f'| Registered files | {total_files} |')
    lines.append(f'| Build targets (`[B]`) | {build_files} |')
    lines.append(f'| Categories | {categories} |')
    lines.append('')

    if use_preprocess and not no_scan:
        lines.append('### Preprocessing notes')
        lines.append('')
        lines.append(f'- Files scanned: {files_scanned}')
        lines.append(f'- Evaluation OK: {files_eval_ok}')
        lines.append(f'- Conservative fallbacks (treated as active): {total_fallbacks}')
        lines.append('')

    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# CLI エントリポイント
# ---------------------------------------------------------------------------
def load_builtin_macros(script_dir: Path) -> dict[str, str]:
    """compiler_builtins.json を読み込む。存在しなければ空辞書。"""
    json_path = script_dir / 'compiler_builtins.json'
    if not json_path.exists():
        return {}
    try:
        with json_path.open(encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def main() -> None:
    """CLI エントリポイント。"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Renesas CS+ .mtpj を解析して GitHub Copilot 用 Markdown を生成する',
    )
    parser.add_argument('mtpj', help='解析対象の .mtpj ファイルパス')
    parser.add_argument('-m', '--mode', help='ビルドモード名（省略時は CurrentBuildMode）')
    parser.add_argument('-o', '--out', help='出力先 Markdown パス')
    parser.add_argument('--no-scan', action='store_true', help='#include スキャンをスキップ')
    parser.add_argument('--list-modes', action='store_true', help='ビルドモード一覧を表示して終了')
    parser.add_argument('--preprocess', action='store_true', help='条件ディレクティブ評価を有効化')
    parser.add_argument('--dump-macros', action='store_true', help='指定ビルドモードのマクロ定義を標準出力に表示して終了')

    args = parser.parse_args()

    mtpj_path = Path(args.mtpj)
    proj = parse_mtpj(mtpj_path)

    if args.list_modes:
        if not proj.build_modes:
            print('ビルドモードが見つかりませんでした。')
        else:
            for i, m in enumerate(proj.build_modes):
                marker = ' ← current' if m == proj.current_build_mode else ''
                print(f'  [{i}] {_plain(m)}{marker}')
        return

    # ビルドモード選択
    mode_name = args.mode or proj.current_build_mode
    if not mode_name:
        sys.exit('[ERROR] ビルドモードを -m で指定するか、.mtpj に CurrentBuildMode が必要です。')

    if mode_name not in proj.build_modes:
        available = ', '.join(_plain(m) for m in proj.build_modes) or '(なし)'
        sys.exit(
            f'[ERROR] 指定されたビルドモードが見つかりません。\n'
            f'利用可能: {available}'
        )

    mode_index = proj.build_modes.index(mode_name)

    # --dump-macros: マクロ定義を標準出力に表示して終了
    if args.dump_macros:
        macros = proj.macros_by_mode_index.get(mode_index, {})
        inc_paths = proj.include_paths_by_mode_index.get(mode_index, [])
        print(f'Build mode : {_plain(mode_name)} (index {mode_index})')
        print(f'Macros     : {len(macros)}')
        if macros:
            print()
            for k, v in sorted(macros.items()):
                print(f'  {_plain(k)}={_plain(v)}')
        print()
        print(f'Include paths: {len(inc_paths)}')
        if inc_paths:
            print()
            for p in inc_paths:
                print(f'  {_plain(p)}')
        return

    # 出力パス
    if args.out:
        out_path = Path(args.out)
    else:
        stem = mtpj_path.stem
        safe_mode = re.sub(r'[^A-Za-z0-9_\-]', '_', mode_name)
        out_path = mtpj_path.parent / f'{stem}_{safe_mode}_deps.md'

    # 組み込みマクロ読み込み
    script_dir = Path(__file__).parent
    builtin_macros = load_builtin_macros(script_dir)

    # Markdown 生成
    md = generate_markdown(
        proj=proj,
        mode_name=mode_name,
        mode_index=mode_index,
        mtpj_path=mtpj_path,
        use_preprocess=args.preprocess,
        no_scan=args.no_scan,
        builtin_macros=builtin_macros,
    )

    out_path.write_text(md, encoding='utf-8')
    print(f'[INFO] 出力: {out_path}')


if __name__ == '__main__':
    main()
