# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Execute the uploading of documentation."""

from pathlib import Path

from .discourse import Discourse
from .exceptions import DiscourseError, ServerError
from .reconcile import NAVIGATION_TABLE_START
from .types_ import Index, IndexFile, Metadata, Page

DOCUMENTATION_FOLDER_NAME = "docs"
DOCUMENTATION_INDEX_FILENAME = "index.md"


def _read_docs_index(base_path: Path) -> str | None:
    """Read the content of the index file.

    Args:
        base_path: The starting path to look for the index content.

    Returns:
        The content of the index file if it exists, otherwise return None.

    """
    if not (docs_directory := base_path / DOCUMENTATION_FOLDER_NAME).is_dir():
        return None
    if not (index_file := docs_directory / DOCUMENTATION_INDEX_FILENAME).is_file():
        return None

    return index_file.read_text()


def get(metadata: Metadata, base_path: Path, server_client: Discourse) -> Index:
    """Retrieve the local and server index information.

    Args:
        metadata: Information about the charm.
        base_path: The base path to look for the metadata file in.
        server_client: A client to the documentation server.

    Returns:
        The index page.

    Raises:
        ServerError: if interactions with the documentation server occurs.

    """
    if metadata.docs is not None:
        index_url = metadata.docs
        try:
            server_content = server_client.retrieve_topic(url=index_url)
        except DiscourseError as exc:
            raise ServerError("Index page retrieval failed") from exc
        server = Page(url=index_url, content=server_content)
    else:
        server = None

    name_value = metadata.name
    local_content = _read_docs_index(base_path=base_path)
    local = IndexFile(
        title=f"{name_value.replace('-', ' ').title()} Documentation Overview",
        content=local_content,
    )

    return Index(server=server, local=local, name=name_value)


def contents_from_page(page: str) -> str:
    """Get index file contents from server page.

    Args:
        page: Page contents from server.

    Returns:
        Index file contents.
    """
    contents = page.split(NAVIGATION_TABLE_START)
    return contents[0]
