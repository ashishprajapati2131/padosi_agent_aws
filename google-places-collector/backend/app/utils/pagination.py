"""Offset pagination for our API. Google page tokens never leave the server."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PageWindow:
    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def window(page: int, page_size: int) -> PageWindow:
    safe_page = page if page >= 1 else 1
    safe_size = page_size if page_size >= 1 else 1
    if safe_size > 100:
        safe_size = 100
    return PageWindow(page=safe_page, page_size=safe_size)


def slice_page(items: list, page: int, page_size: int) -> tuple[list, int]:
    current = window(page, page_size)
    total = len(items)
    return items[current.offset : current.offset + current.page_size], total
