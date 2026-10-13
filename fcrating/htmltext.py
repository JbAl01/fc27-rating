"""Turn HTML into text, links and tables using only the standard library."""
from __future__ import annotations

from html.parser import HTMLParser
from typing import List, Tuple

_BLOCK = {"p", "div", "br", "li", "ul", "ol", "tr", "table", "section", "article", "header",
          "footer", "h1", "h2", "h3", "h4", "h5", "h6", "dl", "dt", "dd"}
_SKIP = {"script", "style", "noscript", "svg", "template"}


class _Extractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self.links: List[Tuple[str, List[str]]] = []  # (href, text parts)
        self._link_stack: List[Tuple[str, List[str]]] = []
        self.tables: List[List[List[str]]] = []
        self._table_stack: List[List[List[str]]] = []
        self._cell: List[str] = []
        self._in_cell = False
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self._skip += 1
            return
        if tag in _BLOCK:
            self.parts.append("\n")
        if tag == "a":
            self._link_stack.append((dict(attrs).get("href") or "", []))
        elif tag == "table":
            self._table_stack.append([])
        elif tag == "tr" and self._table_stack:
            self._table_stack[-1].append([])
        elif tag in ("td", "th") and self._table_stack:
            self._in_cell, self._cell = True, []
        elif tag == "img":
            alt = dict(attrs).get("alt")
            if alt:
                self.handle_data(f" {alt} ")

    def handle_endtag(self, tag):
        if tag in _SKIP:
            self._skip = max(0, self._skip - 1)
            return
        if tag in _BLOCK:
            self.parts.append("\n")
        if tag == "a" and self._link_stack:
            self.links.append(self._link_stack.pop())
        elif tag in ("td", "th") and self._in_cell and self._table_stack:
            row = self._table_stack[-1][-1] if self._table_stack[-1] else None
            if row is None:
                self._table_stack[-1].append([])
                row = self._table_stack[-1][-1]
            row.append(" ".join("".join(self._cell).split()))
            self._in_cell = False
            self.parts.append(" | ")
        elif tag == "table" and self._table_stack:
            self.tables.append([r for r in self._table_stack.pop() if r])

    def handle_data(self, data):
        if self._skip:
            return
        self.parts.append(data)
        for _, parts in self._link_stack:
            parts.append(data)
        if self._in_cell:
            self._cell.append(data)


def extract(html: str):
    """Return (text, links, tables). Links are (href, text); tables are rows of cell strings."""
    ex = _Extractor()
    ex.feed(html)
    ex.close()
    text = "".join(ex.parts)
    lines = [" ".join(line.split()) for line in text.split("\n")]
    text = "\n".join(line for line in lines if line)
    links = [(href, " ".join(" ".join(parts).split())) for href, parts in ex.links]
    return text, links, ex.tables
