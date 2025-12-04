from council.core.parser import get_code_parser


def test_parser():
    parser = get_code_parser()

    # Test Python
    code_py = "def foo(): pass"
    tree, lang = parser.parse(code_py, ".py")
    print(f"Python: {lang}, {tree.root_node.type}")
    assert tree is not None
    assert tree.root_node.type == "module"

    # Test TS
    code_ts = "function foo() { return 1; }"
    tree, lang = parser.parse(code_ts, ".ts")
    print(f"TS: {lang}, {tree.root_node.type}")
    assert tree is not None
    assert tree.root_node.type == "program"

    print("Parser test passed!")


if __name__ == "__main__":
    test_parser()
