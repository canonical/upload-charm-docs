# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for run module."""

# Need access to protected functions for testing
# pylint: disable=protected-access

from pathlib import Path
from unittest import mock

import pytest

from src import discourse, index, types_
from src.exceptions import DiscourseError, ServerError

from .helpers import assert_substrings_in_string


def test__read_docs_index_docs_directory_missing(tmp_path: Path):
    """
    arrange: given empty directory
    act: when _read_docs_index is called with the directory
    assert: then None is returned.
    """
    returned_content = index._read_docs_index(base_path=tmp_path)

    assert returned_content is None


def test__read_docs_index_index_file_missing(tmp_path: Path):
    """
    arrange: given directory with the docs folder
    act: when _read_docs_index is called with the directory
    assert: then None is returned.
    """
    docs_directory = tmp_path / index.DOCUMENTATION_FOLDER_NAME
    docs_directory.mkdir()

    returned_content = index._read_docs_index(base_path=tmp_path)

    assert returned_content is None


def test__read_docs_index_index_file(index_file_content: str, tmp_path: Path):
    """
    arrange: given directory with the docs folder and index file
    act: when _read_docs_index is called with the directory
    assert: then the index file content is returned.
    """
    returned_content = index._read_docs_index(base_path=tmp_path)

    assert returned_content == index_file_content


def test_get_metadata_yaml_retrieve_discourse_error(tmp_path: Path):
    """
    arrange: given directory with metadata.yaml with docs defined and discourse client that
        raises DiscourseError
    act: when get is called with that directory
    assert: then ServerError is raised.
    """
    meta = types_.Metadata(name="name", docs="http://server/index-page")
    mocked_server_client = mock.MagicMock(spec=discourse.Discourse)
    mocked_server_client.retrieve_topic.side_effect = DiscourseError

    with pytest.raises(ServerError) as exc_info:
        index.get(metadata=meta, base_path=tmp_path, server_client=mocked_server_client)

    assert_substrings_in_string(("index page", "retrieval", "failed"), str(exc_info.value).lower())


def test_get_metadata_yaml_retrieve_local_and_server(tmp_path: Path, index_file_content: str):
    """
    arrange: given directory with metadata.yaml with docs defined and discourse client that
        returns the index page content and local index file
    act: when get is called with that directory
    assert: then retrieve topic is called with the docs key value and the content returned by the
        client, docs key and local file information is returned.
    """
    url = "http://server/index-page"
    name = "name 1"
    meta = types_.Metadata(name=name, docs=url)
    mocked_server_client = mock.MagicMock(spec=discourse.Discourse)
    mocked_server_client.retrieve_topic.return_value = (content := "content 2")

    returned_index = index.get(
        metadata=meta, base_path=tmp_path, server_client=mocked_server_client
    )

    assert returned_index.server is not None
    assert returned_index.server.url == url
    assert returned_index.server.content == content
    assert returned_index.local.title == "Name 1 Documentation Overview"
    assert returned_index.local.content == index_file_content
    assert returned_index.name == name
    mocked_server_client.retrieve_topic.assert_called_once_with(url=url)


def test_get_metadata_yaml_retrieve_empty(tmp_path: Path):
    """
    arrange: given directory with metadata.yaml without docs defined and empty local documentation
    act: when get is called with that directory
    assert: then all information is None except the title.
    """
    name = "name 1"
    meta = types_.Metadata(name=name, docs=None)
    mocked_server_client = mock.MagicMock(spec=discourse.Discourse)

    returned_index = index.get(
        metadata=meta, base_path=tmp_path, server_client=mocked_server_client
    )

    assert returned_index.server is None
    assert returned_index.local.title == "Name 1 Documentation Overview"
    assert returned_index.local.content is None
    assert returned_index.name == name


# Pylint doesn't understand how the walrus operator works
# pylint: disable=undefined-variable,unused-variable
@pytest.mark.parametrize(
    "page, expected_content",
    [
        pytest.param(
            index.NAVIGATION_TABLE_START,
            "",
            id="navigation table only",
        ),
        pytest.param(
            (content := "Page content"),
            content,
            id="page content only",
        ),
        pytest.param(
            (multiline_content := "Page content\nWithMultiline"),
            multiline_content,
            id="multiline content only",
        ),
        pytest.param(
            f"{(content := 'Page content')}{index.NAVIGATION_TABLE_START}",
            content,
            id="page with content and navigation table",
        ),
        pytest.param(
            f"{(content := 'page content')}{index.NAVIGATION_TABLE_START}\ncontent-afterwards",
            content,
            id="page with content after the navigation table",
        ),
    ],
)
# pylint: enable=undefined-variable,unused-variable
def test_get_contents_from_page(page: str, expected_content: str):
    """
    arrange: given an index page from server
    act: when contents_from_page is called
    assert: contents without navigation table is returned.
    """
    assert index.contents_from_page(page=page) == expected_content
