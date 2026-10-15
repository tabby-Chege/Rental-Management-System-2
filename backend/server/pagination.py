from flask import request


DEFAULT_PER_PAGE = 10
MAX_PER_PAGE = 100


def get_pagination():
    """Return validated page parameters or a JSON-ready error message."""
    raw_page = request.args.get("page", "1")
    raw_per_page = request.args.get("per_page", str(DEFAULT_PER_PAGE))

    try:
        page = int(raw_page)
        per_page = int(raw_per_page)
    except (TypeError, ValueError):
        return None, "page and per_page must be positive integers"

    if page < 1 or per_page < 1:
        return None, "page and per_page must be positive integers"

    return (page, min(per_page, MAX_PER_PAGE)), None


def pagination_metadata(result):
    return {
        "page": result.page,
        "per_page": result.per_page,
        "total": result.total,
        "pages": result.pages,
        "has_next": result.has_next,
        "has_prev": result.has_prev,
    }
