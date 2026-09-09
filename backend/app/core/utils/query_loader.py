from pathlib import Path

# Path(__file__).parent is 'utils/', so .parent goes up to 'my_project/'
BASE_DIR = Path(__file__).resolve().parent.parent
QUERIES_DIR = BASE_DIR / "queries"


def get_query(filename: str, **kwargs) -> str:
    """Reads a SQL template file from the queries/ directory and injects dynamic parameters.

    Args:
        filename: Name of the .sql file (e.g., 'performance_query.sql').
        **kwargs: Key-value parameters to inject into the template placeholders.

    Returns:
        Formatted SQL query string.
    """
    file_path = QUERIES_DIR / filename

    if not file_path.exists():
        raise FileNotFoundError(f"SQL file not found at: {file_path}")

    with open(file_path, "r", encoding="utf-8") as file:
        query_template = file.read()

    if kwargs:
        return query_template.format(**kwargs)
    return query_template