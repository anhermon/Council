from tree_sitter import Query, QueryCursor

from council.core.parser import get_code_parser


def debug_cursor_usage():
    parser = get_code_parser()
    js_code = "import React from 'react';"
    tree, lang_name = parser.parse(js_code, ".js")
    lang = parser.get_language(lang_name)

    query_str = "(import_statement source: (string) @source)"
    query = Query(lang, query_str)

    try:
        print("Trying QueryCursor(query)...")
        cursor = QueryCursor(query)
        captures = cursor.captures(tree.root_node)
        print(f"Captures: {captures}")
    except Exception as e:
        print(f"QueryCursor(query) failed: {e}")


if __name__ == "__main__":
    debug_cursor_usage()
