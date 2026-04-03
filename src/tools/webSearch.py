from __future__ import annotations

from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlencode, urlparse
from urllib.request import Request, urlopen

from langchain.tools import tool

from utils.truncate import truncate_tool_output

from .registry import register_tool
from .webFetch import (
    DEFAULT_TIMEOUT_SECONDS,
    USER_AGENT,
    _decode_payload,
    _extract_charset,
    _normalize_whitespace,
    _sanitize_attr,
)

DEFAULT_MAX_RESULTS = 5
SEARCH_ENDPOINT = "https://html.duckduckgo.com/html/"

tool_schema = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "Natural-language web search query.",
        },
        "max_results": {
            "type": "integer",
            "description": "Maximum number of results to return.",
        },
        "timeout_seconds": {
            "type": "integer",
            "description": "Network timeout in seconds.",
        },
    },
    "required": ["query"],
}


def _unwrap_result_url(raw_url: str) -> str:
    if not raw_url:
        return ""
    if raw_url.startswith("//"):
        raw_url = f"https:{raw_url}"

    parsed = urlparse(raw_url)
    if "duckduckgo.com" not in parsed.netloc:
        return raw_url

    redirected = parse_qs(parsed.query).get("uddg")
    if redirected:
        return unquote(redirected[0])
    return raw_url


class _DuckDuckGoResultParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, str]] = []
        self._pending_url = ""
        self._pending_title_parts: list[str] = []
        self._in_title = False
        self._active_snippet: dict[str, str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        attr_map = dict(attrs)
        class_names = set(attr_map.get("class", "").split())

        if tag == "a" and "result__a" in class_names:
            self._pending_url = _unwrap_result_url(attr_map.get("href", ""))
            self._pending_title_parts = []
            self._in_title = True
            return

        if class_names and any("snippet" in name for name in class_names) and self.results:
            self._active_snippet = self.results[-1]

    def handle_endtag(self, tag: str) -> None:
        if self._in_title and tag == "a":
            title = _normalize_whitespace("".join(self._pending_title_parts))
            if title:
                self.results.append(
                    {
                        "title": title,
                        "url": self._pending_url,
                        "snippet": "",
                    }
                )
            self._pending_url = ""
            self._pending_title_parts = []
            self._in_title = False
            return

        if self._active_snippet is not None and tag in {"a", "div", "span"}:
            self._active_snippet = None

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._pending_title_parts.append(data)
            return

        if self._active_snippet is not None:
            combined = f"{self._active_snippet['snippet']} {data}"
            self._active_snippet["snippet"] = _normalize_whitespace(combined)


def _perform_search(query: str, timeout_seconds: int) -> list[dict[str, str]]:
    request_url = f"{SEARCH_ENDPOINT}?{urlencode({'q': query})}"
    request = Request(
        request_url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml;q=0.9,text/html;q=0.8,*/*;q=0.1",
        },
    )

    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            content_type = response.headers.get("Content-Type", "text/html; charset=utf-8")
            payload = response.read()
    except HTTPError as exc:
        raise ValueError(f"Error: web search failed - HTTP {exc.code} {exc.reason}.") from exc
    except URLError as exc:
        raise ValueError(f"Error: web search failed - {exc.reason}.") from exc
    except Exception as exc:
        raise ValueError(f"Error: web search failed - {exc}.") from exc

    html = _decode_payload(payload, _extract_charset(content_type))
    parser = _DuckDuckGoResultParser()
    parser.feed(html)
    parser.close()
    return [result for result in parser.results if result.get("title") and result.get("url")]


@register_tool
@tool(
    "web_search",
    description=(
        "Search the public web for a query and return a compact result list with titles, "
        "URLs, and snippets."
    ),
    args_schema=tool_schema,
)
def web_search(
    query: str,
    max_results: int = DEFAULT_MAX_RESULTS,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> str:
    normalized_query = query.strip()
    if not normalized_query:
        return "Error: query must not be empty."
    if max_results <= 0:
        return "Error: max_results must be greater than 0."
    if timeout_seconds <= 0:
        return "Error: timeout_seconds must be greater than 0."

    try:
        results = _perform_search(normalized_query, timeout_seconds=timeout_seconds)
    except ValueError as exc:
        return str(exc)

    visible_results = results[:max_results]
    metadata = (
        f'<system_hint type="web_search" query="{_sanitize_attr(normalized_query)}" '
        f'provider="duckduckgo_html" result_count="{len(visible_results)}" />\n'
    )

    if not visible_results:
        return metadata + f"No web results found for query: {normalized_query}"

    lines = []
    for index, result in enumerate(visible_results, start=1):
        lines.append(f"{index}. {result['title']}")
        lines.append(f"URL: {result['url']}")
        if result.get("snippet"):
            lines.append(f"Snippet: {result['snippet']}")
        lines.append("")

    return truncate_tool_output("web_search", metadata + "\n".join(lines).rstrip())
