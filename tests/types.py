# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Useful types for tests."""

from typing import NamedTuple


class DiscoursePageMeta(NamedTuple):
    """Metadata for creating a discourse page.

    Attrs:
        title: Page title.
        content: Page content.
    """

    title: str
    content: str
