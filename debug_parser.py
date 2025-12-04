from council.core.parser import get_code_parser


def debug_parser():
    parser = get_code_parser()
    js_code = "import React from 'react';"
    tree, lang_name = parser.parse(js_code, ".js")

    if tree:
        print(f"Tree methods: {dir(tree)}")
        print(f"Node methods: {dir(tree.root_node)}")


if __name__ == "__main__":
    debug_parser()
