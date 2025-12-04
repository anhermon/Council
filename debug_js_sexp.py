from council.core.parser import get_code_parser


def inspect_js():
    parser = get_code_parser()
    js_code = "import React from 'react';"
    tree, _ = parser.parse(js_code, ".js")
    print(f"JS Root: {tree.root_node.sexp()}")


if __name__ == "__main__":
    inspect_js()
