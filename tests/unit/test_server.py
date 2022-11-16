# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for src module."""

import json
from unittest import mock
from pathlib import Path

import pytest

from src import server
from src import discourse
from src.exceptions import InputError, DiscourseError, ServerError


def assert_string_contains_substrings(substrings: tuple[str, ...], string: str) -> None:
    """Assert that a string contains substrings.

    Args:
        string: The string to check.
        substrings: The sub strings that must be contained in the string.

    """
    for substring in substrings:
        assert substring in string


def test__get_metadata_metadata_yaml_missing(tmp_path: Path):
    """
    arrange: given empty directory
    act: when _get_metadata is called with that directory
    assert: then InputError is raised.
    """
    with pytest.raises(InputError) as exc_info:
        server._get_metadata(local_base_path=tmp_path)

    assert_string_contains_substrings(("metadata.yaml",), str(exc_info.value).lower())


@pytest.mark.parametrize(
    "metadata_yaml_content, expected_contents",
    [
        pytest.param("", ("empty", "metadata.yaml"), id="malformed"),
        pytest.param("malformed: yaml:", ("malformed", "metadata.yaml"), id="malformed"),
        pytest.param("value 1", ("not", "mapping", "metadata.yaml"), id="not dict"),
    ],
)
def test__get_metadata_metadata_yaml_malformed(
    metadata_yaml_content: str, expected_contents: str, tmp_path: Path
):
    """
    arrange: given directory with metadata.yaml that is malformed
    act: when _get_metadata is called with that directory
    assert: then InputError is raised.
    """
    metadata_yaml_path = tmp_path / "metadata.yaml"
    with metadata_yaml_path.open("w", encoding="utf-8") as metadata_yaml_file:
        metadata_yaml_file.write(metadata_yaml_content)

    with pytest.raises(InputError) as exc_info:
        server._get_metadata(local_base_path=tmp_path)

    assert_string_contains_substrings(expected_contents, str(exc_info.value).lower())


def test__get_metadata_metadata(tmp_path: Path):
    """
    arrange: given directory with metadata.yaml with valid mapping yaml
    act: when _get_metadata is called with that directory
    assert: then file contents are returned as a dictionary.
    """
    metadata_yaml_path = tmp_path / "metadata.yaml"
    with metadata_yaml_path.open("w", encoding="utf-8") as metadata_yaml_file:
        metadata_yaml_file.write("key: value")

    metadata = server._get_metadata(local_base_path=tmp_path)

    assert metadata == {"key": "value"}


@pytest.mark.parametrize(
    "metadata, expected_content",
    [
        pytest.param({}, "not defined", id="empty"),
        pytest.param({"key": "value"}, "not defined", id="docs not defined"),
        pytest.param({"docs": ""}, "empty", id="docs empty"),
        pytest.param({"docs": 5}, "not a string", id="not string"),
    ],
)
def test__get_key_docs_missing_malformed(metadata: dict, expected_content: str):
    """
    arrange: given malformed metadata
    act: when _get_key is called with the metadata
    assert: then InputError is raised.
    """
    with pytest.raises(InputError) as exc_info:
        server._get_key(metadata=metadata, key="docs")

    assert_string_contains_substrings(
        ("'docs'", expected_content, "metadata.yaml", f"{metadata=!r}"),
        str(exc_info.value).lower(),
    )


def test__get_key():
    """
    arrange: given metadata with docs key
    act: when _get_key is called with the metadata
    assert: then teh docs value is returned.
    """
    docs_key = "docs"
    docs_value = "url 1"

    returned_value = server._get_key(metadata={docs_key: docs_value}, key="docs")

    assert returned_value == docs_value


@pytest.mark.parametrize(
    "metadata_yaml_contents, create_if_not_exists, expected_contents",
    [
        pytest.param("", True, ("empty",), id="empty file"),
        pytest.param(
            "key: value",
            True,
            (
                "'name'",
                "not",
                "defined",
            ),
            id="create_if_not_exists True name not defined",
        ),
        pytest.param(
            "key: value",
            False,
            ("'docs'", "not defined", "'create_if_not_exists'", "false"),
            id="create_if_not_exists False docs not defined",
        ),
        pytest.param(
            "docs: ''", False, ("'docs'", "empty"), id="create_if_not_exists False docs malformed"
        ),
    ],
)
def test_retrieve_or_create_index_input_error(
    metadata_yaml_contents: str,
    create_if_not_exists: bool,
    expected_contents: tuple[str, ...],
    tmp_path: Path,
):
    """
    arrange: given directory with metadata.yaml with the given contents and create_if_not_exists
    act: when retrieve_or_create_index is called with that directory and create_if_not_exists
    assert: then InputError is raised.
    """
    metadata_yaml_path = tmp_path / "metadata.yaml"
    with metadata_yaml_path.open("w", encoding="utf-8") as metadata_yaml_file:
        metadata_yaml_file.write(metadata_yaml_contents)

    with pytest.raises(InputError) as exc_info:
        server.retrieve_or_create_index(
            create_if_not_exists=create_if_not_exists,
            local_base_path=tmp_path,
            server_client=mock.MagicMock(),
        )

    assert_string_contains_substrings(
        expected_contents,
        str(exc_info.value).lower(),
    )


def test_retrieve_or_create_index_metadata_yaml_create_discourse_error(tmp_path: Path):
    """
    arrange: given directory with metadata.yaml without docs defined and discourse client that
        raises DiscourseError
    act: when retrieve_or_create_index is called with that directory and with create_if_not_exists
        True
    assert: then ServerError is raised.
    """
    metadata_yaml_path = tmp_path / "metadata.yaml"
    with metadata_yaml_path.open("w", encoding="utf-8") as metadata_yaml_file:
        metadata_yaml_file.write("name: charm-name")
    mocked_server_client = mock.MagicMock(spec=discourse.Discourse)
    mocked_server_client.create_topic.side_effect = DiscourseError

    with pytest.raises(ServerError) as exc_info:
        server.retrieve_or_create_index(
            create_if_not_exists=True, local_base_path=tmp_path, server_client=mocked_server_client
        )

    assert_string_contains_substrings(
        ("index page", "creation", "failed"), str(exc_info.value).lower()
    )


def test_retrieve_or_create_index_metadata_yaml_create(tmp_path: Path):
    """
    arrange: given directory with metadata.yaml without docs defined and discourse client that
        returns url
    act: when retrieve_or_create_index is called with that directory and with create_if_not_exists
        True
    assert: then create topic is called with the titleised charm name and with placeholder content
        and the url returned by the client and placeholder content is returned.
    """
    metadata_yaml_path = tmp_path / "metadata.yaml"
    with metadata_yaml_path.open("w", encoding="utf-8") as metadata_yaml_file:
        metadata_yaml_file.write("name: charm-name")
    mocked_server_client = mock.MagicMock(spec=discourse.Discourse)
    url = "http://server/index-page"
    mocked_server_client.create_topic.return_value = url

    returned_page = server.retrieve_or_create_index(
        create_if_not_exists=True, local_base_path=tmp_path, server_client=mocked_server_client
    )

    assert returned_page.url == url
    assert "placeholder" in returned_page.content.lower()

    mocked_server_client.create_topic.assert_called_once()
    call_kwargs = mocked_server_client.create_topic.call_args.kwargs
    assert "title" in call_kwargs and "Charm Name" in call_kwargs["title"]
    assert "content" in call_kwargs and "placeholder" in call_kwargs["content"]


def test_retrieve_or_create_index_metadata_yaml_retrieve_discourse_error(tmp_path: Path):
    """
    arrange: given directory with metadata.yaml with docs defined and discourse client that
        raises DiscourseError
    act: when retrieve_or_create_index is called with that directory
    assert: then ServerError is raised.
    """
    metadata_yaml_path = tmp_path / "metadata.yaml"
    with metadata_yaml_path.open("w", encoding="utf-8") as metadata_yaml_file:
        metadata_yaml_file.write("docs: http://server/index-page")
    mocked_server_client = mock.MagicMock(spec=discourse.Discourse)
    mocked_server_client.retrieve_topic.side_effect = DiscourseError

    with pytest.raises(ServerError) as exc_info:
        server.retrieve_or_create_index(
            create_if_not_exists=False,
            local_base_path=tmp_path,
            server_client=mocked_server_client,
        )

    assert_string_contains_substrings(
        ("index page", "retrieval", "failed"), str(exc_info.value).lower()
    )


def test_retrieve_or_create_index_metadata_yaml_retrieve(tmp_path: Path):
    """
    arrange: given directory with metadata.yaml with docs defined and discourse client that
        returns the index page content
    act: when retrieve_or_create_index is called with that directory
    assert: then retrieve topic is called with the docs key value and the content returned by the
        client and docs key is returned.
    """
    url = "http://server/index-page"
    content = "content 1"
    metadata_yaml_path = tmp_path / "metadata.yaml"
    with metadata_yaml_path.open("w", encoding="utf-8") as metadata_yaml_file:
        metadata_yaml_file.write(f"docs: {url}")
    mocked_server_client = mock.MagicMock(spec=discourse.Discourse)
    mocked_server_client.retrieve_topic.return_value = content

    returned_page = server.retrieve_or_create_index(
        create_if_not_exists=False,
        local_base_path=tmp_path,
        server_client=mocked_server_client,
    )

    assert returned_page.url == url
    assert returned_page.content == content
    mocked_server_client.retrieve_topic.assert_called_once_with(url=url)
