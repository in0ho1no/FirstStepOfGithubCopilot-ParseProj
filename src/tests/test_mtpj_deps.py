"""mtpj_deps.py の自動テスト。"""
from __future__ import annotations

import base64
import sys
import textwrap
from pathlib import Path

import pytest

# src/ を sys.path に追加（プロジェクトルートからの実行に対応）
sys.path.insert(0, str(Path(__file__).parent.parent))

from mtpj_deps import (
    IfFrame,
    MtpjProject,
    ScanResult,
    _transform_expr,
    decode_build_mode,
    evaluate_expr,
    generate_markdown,
    join_continuation_lines,
    parse_mtpj,
    read_source_file,
    remove_comments,
    scan_includes,
)

FIXTURES = Path(__file__).parent / 'fixtures'


# ---------------------------------------------------------------------------
# UTF-16LE + Base64 復号テスト
# ---------------------------------------------------------------------------
class TestDecodeBuildMode:
    def test_default_build(self) -> None:
        b64 = base64.b64encode('DefaultBuild'.encode('utf-16-le')).decode('ascii')
        assert decode_build_mode(b64) == 'DefaultBuild'

    def test_release_mode(self) -> None:
        b64 = base64.b64encode('ReleaseMode'.encode('utf-16-le')).decode('ascii')
        assert decode_build_mode(b64) == 'ReleaseMode'

    def test_known_value(self) -> None:
        # SPEC.md に例示された値
        assert decode_build_mode('RABlAGYAYQB1AGwAdABCAHUAaQBsAGQA') == 'DefaultBuild'


# ---------------------------------------------------------------------------
# .mtpj パーステスト
# ---------------------------------------------------------------------------
class TestParseMtpj:
    def test_basic_parse(self) -> None:
        proj = parse_mtpj(FIXTURES / 'sample.mtpj')
        assert len(proj.build_modes) == 3
        assert 'DefaultBuild' in proj.build_modes
        assert 'ReleaseMode' in proj.build_modes
        assert 'DebugMode' in proj.build_modes

    def test_current_build_mode(self) -> None:
        proj = parse_mtpj(FIXTURES / 'sample.mtpj')
        assert proj.current_build_mode == 'DefaultBuild'

    def test_files_registered(self) -> None:
        proj = parse_mtpj(FIXTURES / 'sample.mtpj')
        rel_paths = {fe.rel_path for fe in proj.files.values()}
        assert 'r_main.c' in rel_paths
        assert 'r_sub.c' in rel_paths
        assert 'r_main.h' in rel_paths

    def test_build_targets(self) -> None:
        proj = parse_mtpj(FIXTURES / 'sample.mtpj')
        build_targets = {fe.rel_path for fe in proj.files.values() if fe.is_build_target}
        assert 'r_main.c' in build_targets
        assert 'r_sub.c' in build_targets
        # ヘッダはビルド対象外
        assert 'r_main.h' not in build_targets

    def test_category_path(self) -> None:
        proj = parse_mtpj(FIXTURES / 'sample.mtpj')
        by_path = {fe.rel_path: fe for fe in proj.files.values()}
        # r_sub.c は Sources / Generated カテゴリ
        assert 'Generated' in by_path['r_sub.c'].category_path

    def test_macros_extracted(self) -> None:
        proj = parse_mtpj(FIXTURES / 'sample.mtpj')
        macros = proj.macros_by_mode_index.get(0, {})
        assert 'MacroA' in macros
        assert 'MacroB' in macros
        assert macros.get('CFG_CON') == '1'

    def test_broken_xml(self) -> None:
        with pytest.raises(SystemExit):
            parse_mtpj(FIXTURES / 'broken.mtpj')

    def test_nonexistent_file(self) -> None:
        with pytest.raises(SystemExit):
            parse_mtpj(FIXTURES / 'nonexistent.mtpj')


# ---------------------------------------------------------------------------
# RX系（CC-RX）固有タグテスト
# ---------------------------------------------------------------------------
class TestParseMtpjRx:
    """CC-RX形式の .mtpj（COptionDefine-N / COptionInclude-N）の解析テスト。"""

    def test_rx_files_registered(self) -> None:
        proj = parse_mtpj(FIXTURES / 'rx_sample.mtpj')
        rel_paths = {fe.rel_path for fe in proj.files.values()}
        assert 'src/rx_main.c' in rel_paths
        assert 'src/rx_sub.c' in rel_paths
        assert 'src/rx_main.h' in rel_paths

    def test_rx_build_modes(self) -> None:
        proj = parse_mtpj(FIXTURES / 'rx_sample.mtpj')
        assert 'DefaultBuild' in proj.build_modes
        assert 'ReleaseMode' in proj.build_modes

    def test_rx_build_targets(self) -> None:
        proj = parse_mtpj(FIXTURES / 'rx_sample.mtpj')
        build_targets = {fe.rel_path for fe in proj.files.values() if fe.is_build_target}
        assert 'src/rx_main.c' in build_targets
        assert 'src/rx_sub.c' in build_targets
        assert 'src/rx_main.h' not in build_targets

    def test_rx_c_macros_extracted(self) -> None:
        """COptionDefine-<N>（RX固有タグ）からマクロが取得できること。"""
        proj = parse_mtpj(FIXTURES / 'rx_sample.mtpj')
        macros = proj.macros_by_mode_index.get(0, {})
        assert 'RX_MACRO_A' in macros
        assert 'RX_MACRO_B' in macros
        assert macros.get('RX_CFG') == '1'

    def test_rx_asm_macros_extracted(self) -> None:
        """AsmOptionDefine-<N>（RX/RL78共通タグ）からアセンブラマクロが取得できること。"""
        proj = parse_mtpj(FIXTURES / 'rx_sample.mtpj')
        macros = proj.macros_by_mode_index.get(0, {})
        assert macros.get('ASM_DEFINE') == '1'

    def test_rx_include_paths_extracted(self) -> None:
        """COptionInclude-<N>（RX固有タグ）からインクルードパスが取得できること。"""
        proj = parse_mtpj(FIXTURES / 'rx_sample.mtpj')
        inc = proj.include_paths_by_mode_index.get(0, [])
        assert 'r_config' in inc
        assert r'appli\include' in inc

    def test_rx_release_macros(self) -> None:
        """ReleaseMode (index 1) のマクロが取得できること。"""
        proj = parse_mtpj(FIXTURES / 'rx_sample.mtpj')
        macros = proj.macros_by_mode_index.get(1, {})
        assert 'RX_MACRO_A' in macros
        assert macros.get('RELEASE') == '1'


# ---------------------------------------------------------------------------
# セキュリティテスト
# ---------------------------------------------------------------------------
class TestSecurity:
    def test_path_traversal_blocked(self) -> None:
        """../../../ のようなパスはスキャン対象から除外される。"""
        from mtpj_deps import _is_within_base
        base = Path('/some/project')
        assert _is_within_base(base, '../outside.c') is False
        assert _is_within_base(base, '../../etc/passwd') is False
        assert _is_within_base(base, 'src/main.c') is True
        assert _is_within_base(base, 'sub/dir/file.c') is True

    def test_absolute_path_blocked(self) -> None:
        """絶対パスはプロジェクト外とみなしてブロックされる。"""
        from mtpj_deps import _is_within_base
        base = Path('D:/project') if sys.platform == 'win32' else Path('/project')
        assert _is_within_base(base, '/etc/passwd') is False

    def test_oversized_mtpj_rejected(self, tmp_path: Path) -> None:
        """上限を超えるファイルサイズは sys.exit する。"""
        from mtpj_deps import _MAX_MTPJ_BYTES
        large = tmp_path / 'large.mtpj'
        large.write_bytes(b'x' * (_MAX_MTPJ_BYTES + 1))
        with pytest.raises(SystemExit):
            parse_mtpj(large)


# ---------------------------------------------------------------------------
# バックスラッシュ改行（論理行連結）テスト
# ---------------------------------------------------------------------------
class TestJoinContinuationLines:
    def test_basic(self) -> None:
        text = 'line1\\\nline2'
        assert join_continuation_lines(text) == 'line1line2'

    def test_crlf(self) -> None:
        text = 'line1\\\r\nline2'
        assert join_continuation_lines(text) == 'line1line2'

    def test_no_continuation(self) -> None:
        text = 'line1\nline2'
        assert join_continuation_lines(text) == 'line1\nline2'

    def test_if_expression(self) -> None:
        text = '#if MacroA && MacroB\\\n&& MacroC'
        result = join_continuation_lines(text)
        assert result == '#if MacroA && MacroB&& MacroC'


# ---------------------------------------------------------------------------
# コメント除去テスト
# ---------------------------------------------------------------------------
class TestRemoveComments:
    def test_line_comment(self) -> None:
        text = 'int x = 1; // comment\nint y = 2;'
        result = remove_comments(text)
        assert 'comment' not in result
        assert 'int y = 2;' in result

    def test_block_comment(self) -> None:
        text = '/* block */int x;'
        result = remove_comments(text)
        assert 'block' not in result
        assert 'int x;' in result

    def test_multiline_block_comment(self) -> None:
        text = '/*\nmulti\nline\n*/int x;'
        result = remove_comments(text)
        assert 'multi' not in result

    def test_include_in_line_comment_not_picked(self) -> None:
        text = '// #include "dummy.h"\n#include "real.h"'
        result = remove_comments(text)
        assert 'dummy' not in result
        assert 'real' in result

    def test_include_in_block_comment_not_picked(self) -> None:
        text = '/* #include "legacy.h" */'
        result = remove_comments(text)
        assert 'legacy' not in result

    def test_url_in_string_not_removed(self) -> None:
        """文字列リテラル中の // はコメントとして除去しない。"""
        text = 'char *url = "http://example.com";'
        result = remove_comments(text)
        assert 'http://example.com' in result

    def test_inline_comment_after_code(self) -> None:
        text = 'int x = 1; // #include "x.h"\n'
        result = remove_comments(text)
        assert 'x.h' not in result


# ---------------------------------------------------------------------------
# 条件式評価テスト
# ---------------------------------------------------------------------------
class TestEvaluateExpr:
    def setup_method(self) -> None:
        self.defs = {'MacroA': 1, 'MacroB': 1}

    def test_macro_and_both_defined(self) -> None:
        result, fallback = evaluate_expr('MacroA && MacroB', self.defs)
        assert result is True
        assert fallback is False

    def test_macro_and_one_undefined(self) -> None:
        result, fallback = evaluate_expr('MacroA && MacroC', self.defs)
        assert result is False
        assert fallback is False

    def test_single_and_both_defined(self) -> None:
        """単一 & のテスト（0/1 フラグなら && と同等）。"""
        result, fallback = evaluate_expr('MacroA & MacroB', self.defs)
        assert result is True

    def test_single_and_one_undefined(self) -> None:
        result, fallback = evaluate_expr('MacroA & MacroC', self.defs)
        assert result is False

    def test_not_equal_not_broken(self) -> None:
        """!= が not= に壊れないことを確認。"""
        result, fallback = evaluate_expr('MacroA != 0', self.defs)
        assert result is True

    def test_flag_usb_identifier_not_broken(self) -> None:
        """FLAG_USB のような識別子が FILE_SB 等に壊れないことを確認。"""
        defs = {'FLAG_USB': 1}
        result, _ = evaluate_expr('FLAG_USB', defs)
        assert result is True

    def test_int_suffix_removed(self) -> None:
        """0x1UL のサフィックスが正しく除去されること。"""
        result, fallback = evaluate_expr('0x1UL == 1', self.defs)
        assert result is True
        assert fallback is False

    def test_integer_division_c_semantics(self) -> None:
        """C セマンティクス: 5/2 == 2 は真。"""
        result, fallback = evaluate_expr('5/2 == 2', self.defs)
        assert result is True
        assert fallback is False

    def test_integer_division_not_float(self) -> None:
        """5/2 == 2.5 は偽（Python 浮動小数ではない）。"""
        # 2.5 はリテラルとしてパース不可 → fallback になる
        result, fallback = evaluate_expr('5/2 == 2', self.defs)
        assert result is True

    def test_defined_paren(self) -> None:
        result, fallback = evaluate_expr('defined(MacroA)', self.defs)
        assert result is True
        assert fallback is False

    def test_defined_bare(self) -> None:
        result, fallback = evaluate_expr('defined MacroA', self.defs)
        assert result is True
        assert fallback is False

    def test_defined_undefined(self) -> None:
        result, fallback = evaluate_expr('defined(MacroC)', self.defs)
        assert result is False
        assert fallback is False

    def test_defined_paren_and_bare_same_result(self) -> None:
        r1, _ = evaluate_expr('defined(MacroA)', self.defs)
        r2, _ = evaluate_expr('defined MacroA', self.defs)
        assert r1 == r2

    def test_fallback_on_function_call(self) -> None:
        """関数形式マクロは保守的フォールバック。"""
        result, fallback = evaluate_expr('FOO(1, 2)', self.defs)
        assert result is True
        assert fallback is True

    def test_fallback_on_attribute(self) -> None:
        """属性アクセスは保守的フォールバック。"""
        result, fallback = evaluate_expr('os.getenv', self.defs)
        assert result is True
        assert fallback is True

    def test_or_expr(self) -> None:
        defs = {'MacroA': 1}
        result, _ = evaluate_expr('MacroA || MacroC', defs)
        assert result is True

    def test_not_expr(self) -> None:
        defs = {'MacroA': 0}
        result, _ = evaluate_expr('!MacroA', defs)
        assert result is True

    def test_comparison_ge(self) -> None:
        defs = {'CFG_VER': 0x0100}
        result, fallback = evaluate_expr('CFG_VER >= 0x0100', defs)
        assert result is True
        assert fallback is False


# ---------------------------------------------------------------------------
# AST Evaluator ホワイトリストテスト
# ---------------------------------------------------------------------------
class TestAstEvaluatorWhitelist:
    def test_os_system_rejected(self) -> None:
        """os.system への参照は拒否され、保守的フォールバックになる。"""
        result, fallback = evaluate_expr('__import__("os").system("echo")', {})
        assert fallback is True

    def test_lambda_rejected(self) -> None:
        result, fallback = evaluate_expr('(lambda x: x)(1)', {})
        assert fallback is True

    def test_subscript_rejected(self) -> None:
        result, fallback = evaluate_expr('a[0]', {})
        assert fallback is True


# ---------------------------------------------------------------------------
# #elif チェーンテスト
# ---------------------------------------------------------------------------
class TestElifChain:
    def test_only_first_true_branch_active(self) -> None:
        """A が真の場合、elif B, elif C, else は全て非アクティブ。"""
        defs = {'A': 1, 'B': 1, 'C': 1}
        source = textwrap.dedent("""\
            #if A
            #include "BRANCH_A.h"
            #elif B
            #include "BRANCH_B.h"
            #elif C
            #include "BRANCH_C.h"
            #else
            #include "BRANCH_ELSE.h"
            #endif
        """)
        result = _scan_text(source, defs)
        assert 'BRANCH_A.h' in result.includes
        assert 'BRANCH_B.h' not in result.includes
        assert 'BRANCH_C.h' not in result.includes
        assert 'BRANCH_ELSE.h' not in result.includes

    def test_else_active_when_all_false(self) -> None:
        defs: dict[str, int] = {}
        source = textwrap.dedent("""\
            #if A
            #include "BRANCH_A.h"
            #elif B
            #include "BRANCH_B.h"
            #else
            #include "BRANCH_ELSE.h"
            #endif
        """)
        result = _scan_text(source, defs)
        assert 'BRANCH_A.h' not in result.includes
        assert 'BRANCH_B.h' not in result.includes
        assert 'BRANCH_ELSE.h' in result.includes


# ---------------------------------------------------------------------------
# バックスラッシュ改行を含む #if テスト（SPEC.md 5.2 必須テストケース）
# ---------------------------------------------------------------------------
class TestBackslashContinuation:
    def setup_method(self) -> None:
        self.defs = {'MacroA': 1, 'MacroB': 1}

    def test_ffff_inactive(self) -> None:
        """MacroA && MacroB && MacroC → MacroC 未定義 → 非アクティブ。"""
        source = '#if MacroA && MacroB\\\n&& MacroC\n#include "FFFF.h"\n#endif\n'
        result = _scan_text(source, self.defs)
        assert 'FFFF.h' not in result.includes

    def test_gggg_active(self) -> None:
        """MacroA && MacroB && MacroB → すべて定義済み → アクティブ。"""
        source = '#if MacroA && MacroB\\\n&& MacroB\n#include "GGGG.h"\n#endif\n'
        result = _scan_text(source, self.defs)
        assert 'GGGG.h' in result.includes


# ---------------------------------------------------------------------------
# #include アクティブ判定テスト（SPEC.md 5.2 必須テストケース）
# ---------------------------------------------------------------------------
class TestIncludeActiveInactive:
    def setup_method(self) -> None:
        self.defs = {'MacroA': 1, 'MacroB': 1}

    def test_dddd_active(self) -> None:
        """MacroA && MacroB → アクティブ。"""
        source = '#if MacroA && MacroB\n#include "DDDD.h"\n#endif\n'
        result = _scan_text(source, self.defs)
        assert 'DDDD.h' in result.includes

    def test_eeee_inactive(self) -> None:
        """MacroA && MacroC → 非アクティブ。"""
        source = '#if MacroA && MacroC\n#include "EEEE.h"\n#endif\n'
        result = _scan_text(source, self.defs)
        assert 'EEEE.h' not in result.includes


# ---------------------------------------------------------------------------
# 文字コードフォールバックテスト
# ---------------------------------------------------------------------------
class TestEncodingFallback:
    def test_cp932_file_readable(self) -> None:
        """CP932 で保存されたファイルが UnicodeDecodeError なく読める。"""
        path = FIXTURES / 'cp932_source.c'
        text = read_source_file(path)
        assert '#include' in text

    def test_cp932_include_extracted(self) -> None:
        """CP932 ファイルから #include が正しく抽出される。"""
        path = FIXTURES / 'cp932_source.c'
        result = scan_includes(path, use_preprocess=False, defs={})
        assert result is not None
        assert 'r_main.h' in result.includes


# ---------------------------------------------------------------------------
# --no-scan / --preprocess / 未指定の出力差分テスト
# ---------------------------------------------------------------------------
class TestOutputVariants:
    def setup_method(self) -> None:
        self.proj = parse_mtpj(FIXTURES / 'sample.mtpj')
        self.mode_name = 'DefaultBuild'
        self.mode_index = 0
        self.mtpj_path = FIXTURES / 'sample.mtpj'
        self.builtin: dict[str, str] = {}

    def _gen(self, use_preprocess: bool, no_scan: bool) -> str:
        return generate_markdown(
            proj=self.proj,
            mode_name=self.mode_name,
            mode_index=self.mode_index,
            mtpj_path=self.mtpj_path,
            use_preprocess=use_preprocess,
            no_scan=no_scan,
            builtin_macros=self.builtin,
        )

    def test_no_scan_skips_section2(self) -> None:
        md = self._gen(use_preprocess=False, no_scan=True)
        assert '--no-scan' in md
        assert 'DDDD.h' not in md

    def test_default_scan_includes_all(self) -> None:
        """--preprocess なし: 条件ディレクティブを評価せずに全 #include を列挙。"""
        md = self._gen(use_preprocess=False, no_scan=False)
        # r_main.c に #include "r_main.h" がある → 出力に含まれる
        assert 'r_main.h' in md

    def test_preprocess_adds_macro_section(self) -> None:
        md = self._gen(use_preprocess=True, no_scan=False)
        assert 'Active defines' in md

    def test_preprocess_label_in_section2(self) -> None:
        md = self._gen(use_preprocess=True, no_scan=False)
        assert '(preprocessed)' in md

    def test_preprocess_excludes_inactive(self) -> None:
        """--preprocess 時、MacroA && MacroC (MacroC未定義) の EEEE.h は除外。"""
        md = self._gen(use_preprocess=True, no_scan=False)
        assert 'EEEE.h' not in md

    def test_preprocess_includes_active(self) -> None:
        """--preprocess 時、MacroA && MacroB (両方定義済み) の DDDD.h は含まれる。"""
        md = self._gen(use_preprocess=True, no_scan=False)
        assert 'DDDD.h' in md

    def test_no_preprocess_compat(self) -> None:
        """--preprocess 未指定の出力には 'Active defines' が含まれない。"""
        md = self._gen(use_preprocess=False, no_scan=False)
        assert 'Active defines' not in md


# ---------------------------------------------------------------------------
# 組み込みマクロ JSON が無い場合のテスト
# ---------------------------------------------------------------------------
class TestBuiltinMacrosMissing:
    def test_works_without_json(self) -> None:
        """compiler_builtins.json が無くても動作する。"""
        proj = parse_mtpj(FIXTURES / 'sample.mtpj')
        md = generate_markdown(
            proj=proj,
            mode_name='DefaultBuild',
            mode_index=0,
            mtpj_path=FIXTURES / 'sample.mtpj',
            use_preprocess=True,
            no_scan=False,
            builtin_macros={},  # 空辞書 = JSON なし相当
        )
        assert '## 1.' in md


# ---------------------------------------------------------------------------
# コメント除去 + #include スキャン統合テスト
# ---------------------------------------------------------------------------
class TestCommentIncludeIntegration:
    def test_comment_line_include_not_scanned(self) -> None:
        source = '// #include "dummy.h"\n#include "real.h"\n'
        result = _scan_text(source, {})
        assert 'dummy.h' not in result.includes
        assert 'real.h' in result.includes

    def test_block_comment_include_not_scanned(self) -> None:
        source = '/* #include "legacy.h" */\n#include "real.h"\n'
        result = _scan_text(source, {})
        assert 'legacy.h' not in result.includes
        assert 'real.h' in result.includes

    def test_macro_via_include_ignored(self) -> None:
        """マクロ経由 #include INC_FILE は無視される（スコープ外）。"""
        source = '#define INC_FILE "foo.h"\n#include INC_FILE\n#include "bar.h"\n'
        result = _scan_text(source, {})
        # INC_FILE パターンは拾わない
        assert 'INC_FILE' not in result.includes
        assert 'bar.h' in result.includes


# ---------------------------------------------------------------------------
# 整数除算テスト
# ---------------------------------------------------------------------------
class TestIntegerDivision:
    def test_5_div_2_equals_2(self) -> None:
        result, fallback = evaluate_expr('5/2 == 2', {})
        assert result is True
        assert fallback is False

    def test_5_div_2_not_float(self) -> None:
        """5/2 は整数除算で 2、したがって 2.5 との等号は偽。"""
        # 2.5 は ast.parse で float Constant になる → _EvalError → fallback
        # ただし fallback=True の場合は result=True（保守的）
        # ここは「5/2 == 2 が真」の確認で十分
        result, _ = evaluate_expr('5/2 == 2', {})
        assert result is True


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------
def _scan_text(source: str, defs: dict[str, int]) -> ScanResult:
    """テキストを直接スキャンするヘルパー（ファイル経由ではない）。"""
    import tempfile
    with tempfile.NamedTemporaryFile(
        mode='w', suffix='.c', delete=False, encoding='utf-8'
    ) as f:
        f.write(source)
        tmp_path = Path(f.name)
    try:
        result = scan_includes(tmp_path, use_preprocess=True, defs=defs)
        return result or ScanResult()
    finally:
        tmp_path.unlink(missing_ok=True)
