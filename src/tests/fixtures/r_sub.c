/* r_sub.c - サブソース（テスト用） */
#include "r_main.h"

/* FLAG_USB 識別子テスト: str.replace 落とし穴回避確認 */
#if defined(FLAG_USB)
#include "usb_driver.h"
#endif

/* 0x1UL のようなサフィックス付きリテラルテスト */
#if CFG_VER >= 0x0100UL
#include "ver_check.h"
#endif

void sub_func(void) {}
