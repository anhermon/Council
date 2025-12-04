from tree_sitter import Query

from council.core.parser import get_code_parser


def test_query_validity():
    parser = get_code_parser()
    lang = parser.get_language("javascript")  # JS Grammar

    # This contains import_require which might be TS only?
    query_str = """
        (import_statement source: (string) @source)
        (import_require source: (string) @source)
    """

    try:
        Query(lang, query_str)
        print("Query creation successful")
    except Exception as e:
        print(f"Query creation failed: {e}")


if __name__ == "__main__":
    test_query_validity()
