from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from typing import Any
from urllib.parse import urlencode

from sqlalchemy import or_

_DATE_FORMAT = "%Y-%m-%dT%H:%M"
_DEFAULT_RANGE_DAYS = 7


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.strptime(value, _DATE_FORMAT).replace(tzinfo=timezone.utc)


def effective_range(date_from: str | None, date_to: str | None) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    parsed_from = parse_datetime(date_from)
    parsed_to = parse_datetime(date_to)
    return parsed_from or now - timedelta(days=_DEFAULT_RANGE_DAYS), parsed_to or now


@dataclass(frozen=True)
class CategoryFilter:
    """One toggleable list filter (e.g. Decision or Profile tags)."""

    query_param: str
    context_key: str
    column: Any


@dataclass(frozen=True)
class ListingSpec:
    """Static shape of one filterable/sortable/paginated listing (a Logs tab)."""

    prefix: str
    base_path: str
    tab_suffix: str
    items_key: str
    query: Any
    search_columns: Sequence[Any]
    category_filters: Sequence[CategoryFilter]
    date_column: Any
    sort_columns: dict[str, Any]
    default_sort: str
    page_size: int


def build_context(
    spec: ListingSpec,
    q: str,
    category_values: dict[str, list[str]],
    date_from: str | None,
    date_to: str | None,
    sort: str,
    direction: str,
    page: int,
) -> dict:
    """Filters, sorts, and paginates `spec.query`, returning the full template context for its listing."""
    prefix = spec.prefix
    effective_from, effective_to = effective_range(date_from, date_to)
    sort = sort if sort in spec.sort_columns else spec.default_sort
    direction = direction if direction in ("asc", "desc") else "desc"
    page = max(page, 1)

    query = spec.query
    if q and spec.search_columns:
        like = f"%{q}%"
        query = query.filter(or_(*(column.ilike(like) for column in spec.search_columns)))
    for category_filter in spec.category_filters:
        values = category_values.get(category_filter.query_param, [])
        if values:
            query = query.filter(category_filter.column.in_(values))
    query = query.filter(spec.date_column >= effective_from, spec.date_column <= effective_to)
    total = query.count()
    order_column = spec.sort_columns[sort]
    ordered = order_column.asc() if direction == "asc" else order_column.desc()
    items = query.order_by(ordered).offset((page - 1) * spec.page_size).limit(spec.page_size).all()

    total_pages = max((total + spec.page_size - 1) // spec.page_size, 1)
    query_string = filter_query_string(spec, q, category_values, effective_from, effective_to)
    page_link_base = f"{spec.base_path}?{query_string}&{prefix}sort={sort}&{prefix}dir={direction}{spec.tab_suffix}"

    context = {
        spec.items_key: items,
        f"{prefix}q": q,
        f"{prefix}date_from": effective_from,
        f"{prefix}date_to": effective_to,
        f"{prefix}sort": sort,
        f"{prefix}dir": direction,
        f"{prefix}page": page,
        f"{prefix}total_pages": total_pages,
        f"{prefix}total_count": total,
        f"{prefix}range_start": (page - 1) * spec.page_size + 1 if total > 0 else 0,
        f"{prefix}range_end": min(page * spec.page_size, total),
        f"{prefix}sort_links": _sort_links(spec, query_string, sort, direction),
        f"{prefix}prev_page_link": f"{page_link_base}&{prefix}page={max(page - 1, 1)}",
        f"{prefix}next_page_link": f"{page_link_base}&{prefix}page={min(page + 1, total_pages)}",
    }
    for category_filter in spec.category_filters:
        context[category_filter.context_key] = category_values.get(category_filter.query_param, [])
    return context


def filter_query_string(
    spec: ListingSpec, q: str, category_values: dict[str, list[str]], date_from: datetime, date_to: datetime
) -> str:
    """Query string for the current filters only (no sort/dir/page) — used to build HX-Push-Url values."""
    prefix = spec.prefix
    params = [(f"{prefix}q", q)] if q else []
    for category_filter in spec.category_filters:
        params += [(category_filter.query_param, value) for value in category_values.get(category_filter.query_param, [])]
    params += [(f"{prefix}from", date_from.strftime(_DATE_FORMAT)), (f"{prefix}to", date_to.strftime(_DATE_FORMAT))]
    return urlencode(params)


def _sort_links(spec: ListingSpec, query_string: str, sort: str, direction: str) -> dict[str, str]:
    prefix = spec.prefix
    links = {}
    for column in spec.sort_columns:
        next_dir = "desc" if sort == column and direction == "asc" else "asc"
        links[column] = f"{spec.base_path}?{query_string}&{prefix}sort={column}&{prefix}dir={next_dir}{spec.tab_suffix}"
    return links
