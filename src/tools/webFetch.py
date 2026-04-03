from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from langchain.tools import tool

from utils.truncate import truncate_tool_output

from .registry import register_tool

USER_AGENT = "red-code/0.1 (+local-agent)"
DEFAULT_TIMEOUT_SECONDS = 10
DEFAULT_MAX_CHARS = 4000

tool_schema = {
    "type": "object",
    "properties": {
        "url": {
            "type": "string",
            "description": "Absolute http(s) URL to fetch.",
        },
        "max_chars": {
            "type": "integer",
            "description": "Maximum number of extracted characters to return.",
        },
        "timeout_seconds": {
            "type": "integer",
            "description": "Network timeout in seconds.",
        },
    },
    "required": ["url"],
}


def _normalize_whitespace(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _sanitize_attr(value: str) -> str:
    return value.replace('"', "'")


def _extract_charset(content_type: str) -> str | None:
    match = re.search(r"charset=([^\s;]+)", content_type, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1).strip("\"'")


def _decode_payload(payload: bytes, charset: str | None = None) -> str:
    candidates = []
    if charset:
        candidates.append(charset)
    candidates.extend(["utf-8", "utf-8-sig", "gb18030"])

    seen: set[str] = set()
    for encoding in candidates:
        normalized = encoding.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        try:
            return payload.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue

    return payload.decode("utf-8", errors="replace")


def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Error: only absolute http(s) URLs are supported.")


def _is_supported_text_content_type(content_type: str) -> bool:
    normalized = (content_type or "").lower()
    return (
        normalized.startswith("text/")
        or "html" in normalized
        or "json" in normalized
        or "xml" in normalized
    )


class _HTMLTextExtractor(HTMLParser):
    _BLOCK_TAGS = {
        "article",
        "blockquote",
        "br",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "footer",
        "li",
        "main",
        "p",
        "pre",
        "section",
        "tr",
    }
    _IGNORED_TAGS = {"script", "style", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self._in_title = False
        self._title_parts: list[str] = []
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self._IGNORED_TAGS:
            self._ignored_depth += 1
            return
        if tag == "title":
            self._in_title = True
        if tag in self._BLOCK_TAGS:
            self._text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._IGNORED_TAGS and self._ignored_depth > 0:
            self._ignored_depth -= 1
            return
        if tag == "title":
            self._in_title = False
        if tag in self._BLOCK_TAGS:
            self._text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._ignored_depth > 0:
            return

        if self._in_title:
            self._title_parts.append(data)
            return

        text = _normalize_whitespace(data)
        if not text:
            return
        self._text_parts.append(text)
        self._text_parts.append(" ")

    def get_title(self) -> str | None:
        title = _normalize_whitespace("".join(self._title_parts))
        return title or None

    def get_text(self) -> str:
        return _normalize_whitespace("".join(self._text_parts))


@dataclass(slots=True)
class _FetchedDocument:
    requested_url: str
    final_url: str
    status_code: int
    content_type: str
    text: str
    title: str | None = None


def _extract_readable_text(body_text: str, content_type: str) -> tuple[str, str | None]:
    normalized_content_type = content_type.lower()
    if "html" in normalized_content_type:
        parser = _HTMLTextExtractor()
        parser.feed(body_text)
        parser.close()
        return parser.get_text(), parser.get_title()

    if "json" in normalized_content_type:
        try:
            parsed = json.loads(body_text)
        except json.JSONDecodeError:
            return _normalize_whitespace(body_text), None
        return json.dumps(parsed, ensure_ascii=False, indent=2), None

    return _normalize_whitespace(body_text), None


def fetch_web_document(url: str, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> _FetchedDocument:
    _validate_url(url)

    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/json,text/plain;q=0.9,*/*;q=0.1",
        },
    )

    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            final_url = response.geturl()
            status_code = getattr(response, "status", None) or getattr(response, "code", None) or 200
            content_type = response.headers.get("Content-Type", "application/octet-stream")
            payload = response.read()
    except HTTPError as exc:
        raise ValueError(f"Error: failed to fetch URL - HTTP {exc.code} {exc.reason}.") from exc
    except URLError as exc:
        raise ValueError(f"Error: failed to reach URL - {exc.reason}.") from exc
    except Exception as exc:
        raise ValueError(f"Error: failed to fetch URL - {exc}.") from exc

    if not _is_supported_text_content_type(content_type):
        raise ValueError(f"Error: unsupported content type - {content_type}.")

    decoded_text = _decode_payload(payload, _extract_charset(content_type))
    extracted_text, title = _extract_readable_text(decoded_text, content_type)
    if not extracted_text:
        raise ValueError(f"Error: fetched URL but extracted no readable text - {final_url}.")

    return _FetchedDocument(
        requested_url=url,
        final_url=final_url,
        status_code=status_code,
        content_type=content_type,
        text=extracted_text,
        title=title,
    )


@register_tool
@tool(
    "web_fetch",
    description=(
        "Fetch an http(s) page and extract readable text. Use this to inspect a known URL "
        "without relying on local shell tools."
    ),
    args_schema=tool_schema,
)
def web_fetch(
    url: str,
    max_chars: int = DEFAULT_MAX_CHARS,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> str:
    if max_chars <= 0:
        return "Error: max_chars must be greater than 0."
    if timeout_seconds <= 0:
        return "Error: timeout_seconds must be greater than 0."

    try:
        document = fetch_web_document(url, timeout_seconds=timeout_seconds)
    except ValueError as exc:
        return str(exc)

    visible_text = document.text[:max_chars].rstrip()
    title_attr = f' title="{_sanitize_attr(document.title)}"' if document.title else ""
    metadata = (
        f'<system_hint type="web_fetch" url="{_sanitize_attr(document.requested_url)}" '
        f'final_url="{_sanitize_attr(document.final_url)}" status_code="{document.status_code}" '
        f'content_type="{_sanitize_attr(document.content_type)}"{title_attr} '
        f'extracted_chars="{len(document.text)}" shown_chars="{len(visible_text)}" />\n'
    )

    header_lines = [
        f"URL: {document.final_url}",
        f"Status: {document.status_code}",
        f"Content-Type: {document.content_type}",
    ]
    if document.title:
        header_lines.insert(0, f"Title: {document.title}")

    return truncate_tool_output(
        "web_fetch",
        metadata + "\n".join(header_lines) + "\n\n" + visible_text,
    )
