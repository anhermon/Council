from tree_sitter import Query

from council.core.parser import get_code_parser


def debug_tsx():
    parser = get_code_parser()
    lang = parser.get_language("tsx")

    query_str = "(import_require source: (string) @source)"

    try:
        Query(lang, query_str)
        print("TSX supports import_require")
    except Exception as e:
        print(f"TSX Error: {e}")

    lang_ts = parser.get_language("typescript")
    try:
        Query(lang_ts, query_str)
        print("TS supports import_require")
    except Exception as e:
        print(f"TS Error: {e}")


if __name__ == "__main__":
    debug_tsx()
