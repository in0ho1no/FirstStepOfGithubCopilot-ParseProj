"""サンプルのエントリポイント。"""

def function_example(arg1: str, arg2: int) -> None:
    """文字列と整数の引数を表示する。"""
    print(f'arg1: {arg1}, arg2: {arg2}')


def main() -> None:
    """メイン処理を実行する。"""
    print('Hello, World!')
    function_example('hello world', 42)


if __name__ == '__main__':
    main()
