/* r_main.c - メインソースファイル（テスト用） */

#include "r_main.h"
#include "r_config.h"
#include <stdint.h>

// #include "dummy.h"    <- コメントなので無視されること

/* #include "legacy.h" */ /* これも無視 */

int x = 1; // #include "x.h"   <- 行コメントなので無視

#if MacroA && MacroB
#include "DDDD.h"   /* アクティブ: 出力に含める */
#endif

#if MacroA && MacroC
#include "EEEE.h"   /* 非アクティブ: 除外 */
#endif

#if MacroA && MacroB\
&& MacroC
#include "FFFF.h"   /* 非アクティブ: バックスラッシュ改行テスト */
#endif

#if MacroA && MacroB\
&& MacroB
#include "GGGG.h"   /* アクティブ: バックスラッシュ改行テスト */
#endif

/* & (単一) テスト */
#if MacroA & MacroB
#include "HHHH.h"   /* アクティブ: 単一& */
#endif

#if MacroA & MacroC
#include "IIII.h"   /* 非アクティブ: 単一& */
#endif

/* #elif チェーンテスト */
#if MacroA
#include "CHAIN_A.h"  /* アクティブ */
#elif MacroB
#include "CHAIN_B.h"  /* 非アクティブ (branch_taken=true) */
#elif MacroA
#include "CHAIN_C.h"  /* 非アクティブ (branch_taken=true) */
#else
#include "CHAIN_D.h"  /* 非アクティブ (branch_taken=true) */
#endif

/* defined() テスト */
#if defined(MacroA)
#include "DEF_PAREN.h"  /* アクティブ */
#endif

#if defined MacroC
#include "DEF_BARE_UNDEF.h"  /* 非アクティブ */
#endif

/* 整数除算テスト */
#if 5/2 == 2
#include "INT_DIV.h"  /* アクティブ: C整数除算 */
#endif

void main_func(void) {
    /* 何もしない */
    char url[] = "http://example.com";  /* 文字列内の // はコメントではない */
}
