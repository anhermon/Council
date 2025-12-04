from tree_sitter import Query, QueryCursor

from council.core.parser import get_code_parser


def debug_ts():
    parser = get_code_parser()
    ts_code = "import { Component } from '@angular/core';"
    tree, lang_name = parser.parse(ts_code, ".ts")
    print(f"TS Lang: {lang_name}")

    lang = parser.get_language(lang_name)

    query_str = """
        (import_statement source: (string) @source)
        (import_require source: (string) @source)
    """

    try:
        query = Query(lang, query_str)
        cursor = QueryCursor(query)
        captures = cursor.captures(tree.root_node)
        print(f"Captures: {captures}")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    debug_ts()
