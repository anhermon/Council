from council.core.parser import get_code_parser


def inspect_js_children():
    parser = get_code_parser()
    js_code = "import React from 'react';"
    tree, _ = parser.parse(js_code, ".js")
    root = tree.root_node
    import_node = root.children[0]
    print(f"Import Node Type: {import_node.type}")
    print(f"Import Node Children: {[c.type for c in import_node.children]}")
    # Check field names for children
    for child in import_node.children:
        print(f"Child: {child.type}, Field: {import_node.field_name_for_child(child)}")


if __name__ == "__main__":
    inspect_js_children()
