# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Integration tests for running the action."""

# This test is fairly complex as it simulates sequential action runs
# pylint: disable=too-many-arguments,too-many-locals,too-many-statements

import logging
from itertools import chain
from pathlib import Path
from urllib.parse import urlparse

import pytest

from src import exceptions, index, metadata, reconcile, run
from src.discourse import Discourse

from .. import factories
from ..unit.helpers import assert_substrings_in_string, create_metadata_yaml

pytestmark = pytest.mark.reconcile


@pytest.mark.asyncio
@pytest.mark.usefixtures("patch_create_repository_client")
async def test_run(
    discourse_api: Discourse,
    caplog: pytest.LogCaptureFixture,
    repository_path: Path,
):
    """
    arrange: given running discourse server
    act: when run is called with:
        1. docs with an index file in dry run mode
        2. docs with an index file
        3. docs with a documentation file added in dry run mode
        4. docs with a documentation file added
        5. docs with a documentation file updated in dry run mode
        6. docs with a documentation file updated
        7. docs with a nested directory added
        8. docs with a documentation file added in the nested directory
        9. docs with the documentation file in the nested directory removed in dry run mode
        10. docs with the documentation file in the nested directory removed with page deletion
            disabled
        11. with the nested directory removed
        12. with the documentation file removed
        13. with the index file removed
    assert: then:
        1. an index page is not updated
        2. an index page is updated
        3. the documentation page is not created
        4. the documentation page is created
        5. the documentation page is not updated
        6. the documentation page is updated
        7. the nested directory is added to the navigation table
        8. the documentation file in the nested directory is created
        9. the documentation file in the nested directory is not removed
        10. the documentation file in the nested directory is not removed
        11. the nested directory is removed from the navigation table
        12. the documentation page is deleted
        13. an index page is not updated
    """
    document_name = "name 1"
    caplog.set_level(logging.INFO)
    create_metadata_yaml(
        content=f"{metadata.METADATA_NAME_KEY}: {document_name}", path=repository_path
    )

    # 1. docs with an index file in dry run mode
    caplog.clear()
    index_url = discourse_api.create_topic(
        title=f"{document_name.replace('-', ' ').title()} Documentation Overview",
        content=f"{reconcile.NAVIGATION_TABLE_START}".strip(),
    )
    create_metadata_yaml(
        content=f"{metadata.METADATA_NAME_KEY}: name 1\n{metadata.METADATA_DOCS_KEY}: {index_url}",
        path=repository_path,
    )
    (docs_dir := repository_path / index.DOCUMENTATION_FOLDER_NAME).mkdir()
    (index_file := docs_dir / "index.md").write_text(index_content := "index content 1")

    urls_with_actions = run(
        base_path=repository_path,
        discourse=discourse_api,
        user_inputs=factories.UserInputFactory(
            dry_run=True,
            delete_pages=True,
        ),
    )

    assert tuple(urls_with_actions) == (index_url,)
    index_topic = discourse_api.retrieve_topic(url=index_url)
    assert index_topic == f"{reconcile.NAVIGATION_TABLE_START}".strip()
    assert_substrings_in_string((index_url, "Update", "'skip'"), caplog.text)

    # 2. docs with an index file
    caplog.clear()

    urls_with_actions = run(
        base_path=repository_path,
        discourse=discourse_api,
        user_inputs=factories.UserInputFactory(
            dry_run=False,
            delete_pages=True,
        ),
    )

    assert tuple(urls_with_actions) == (index_url,)
    index_topic = discourse_api.retrieve_topic(url=index_url)
    assert index_topic == f"{index_content}{reconcile.NAVIGATION_TABLE_START}"
    assert_substrings_in_string((index_url, "Update", "'success'"), caplog.text)

    # 3. docs with a documentation file added in dry run mode
    caplog.clear()
    doc_table_key = "doc"
    (doc_file := docs_dir / f"{doc_table_key}.md").write_text(doc_content_1 := "doc content 1")

    urls_with_actions = run(
        base_path=repository_path,
        discourse=discourse_api,
        user_inputs=factories.UserInputFactory(
            dry_run=True,
            delete_pages=True,
        ),
    )

    assert tuple(urls_with_actions) == (index_url,)
    assert_substrings_in_string(("Create", "'skip'"), caplog.text)
    index_topic = discourse_api.retrieve_topic(url=index_url)
    assert doc_content_1 not in index_topic

    # 4. docs with a documentation file added
    caplog.clear()

    urls_with_actions = run(
        base_path=repository_path,
        discourse=discourse_api,
        user_inputs=factories.UserInputFactory(
            dry_run=False,
            delete_pages=True,
        ),
    )

    assert len(urls_with_actions) == 2
    (doc_url, _) = urls_with_actions.keys()
    assert (urls := tuple(urls_with_actions)) == (doc_url, index_url)
    doc_table_line_1 = f"| 1 | {doc_table_key} | [{doc_content_1}]({urlparse(doc_url).path}) |"
    assert_substrings_in_string(
        chain(urls, (doc_table_line_1, "Create", "Update", "'success'")), caplog.text
    )
    index_topic = discourse_api.retrieve_topic(url=index_url)
    assert doc_table_line_1 in index_topic
    doc_topic = discourse_api.retrieve_topic(url=doc_url)
    assert doc_topic == doc_content_1

    # 5. docs with a documentation file updated in dry run mode
    caplog.clear()
    doc_file.write_text(doc_content_2 := "doc content 2")

    urls_with_actions = run(
        base_path=repository_path,
        discourse=discourse_api,
        user_inputs=factories.UserInputFactory(
            dry_run=True,
            delete_pages=True,
        ),
    )

    assert (urls := tuple(urls_with_actions)) == (doc_url, index_url)
    assert_substrings_in_string(chain(urls, (doc_table_line_1, "Update", "'skip'")), caplog.text)
    index_topic = discourse_api.retrieve_topic(url=index_url)
    assert doc_table_line_1 in index_topic
    doc_topic = discourse_api.retrieve_topic(url=doc_url)
    assert doc_topic == doc_content_1

    # 6. docs with a documentation file updated
    caplog.clear()

    urls_with_actions = run(
        base_path=repository_path,
        discourse=discourse_api,
        user_inputs=factories.UserInputFactory(
            dry_run=False,
            delete_pages=True,
        ),
    )

    assert (urls := tuple(urls_with_actions)) == (doc_url, index_url)
    doc_table_line_2 = f"| 1 | {doc_table_key} | [{doc_content_2}]({urlparse(doc_url).path}) |"
    assert_substrings_in_string(
        chain(urls, (doc_table_line_1, doc_table_line_2, "Update", "'success'")), caplog.text
    )
    index_topic = discourse_api.retrieve_topic(url=index_url)
    assert doc_table_line_2 in index_topic
    doc_topic = discourse_api.retrieve_topic(url=doc_url)
    assert doc_topic == doc_content_2

    # 7. docs with a nested directory added
    caplog.clear()
    nested_dir_table_key = "nested-dir"
    (nested_dir := docs_dir / nested_dir_table_key).mkdir()

    urls_with_actions = run(
        base_path=repository_path,
        discourse=discourse_api,
        user_inputs=factories.UserInputFactory(
            dry_run=False,
            delete_pages=True,
        ),
    )

    assert (urls := tuple(urls_with_actions)) == (doc_url, index_url)
    nested_dir_table_line = f"| 1 | {nested_dir_table_key} | [Nested Dir]() |"
    assert_substrings_in_string(
        chain(urls, (nested_dir_table_line, "Create", "'success'")), caplog.text
    )
    index_topic = discourse_api.retrieve_topic(url=index_url)
    assert nested_dir_table_line in index_topic

    # 8. docs with a documentation file added in the nested directory
    caplog.clear()
    nested_dir_doc_table_key = "nested-dir-doc"
    (nested_dir_doc_file := nested_dir / "doc.md").write_text(
        nested_dir_doc_content := "nested dir doc content 1"
    )

    urls_with_actions = run(
        base_path=repository_path,
        discourse=discourse_api,
        user_inputs=factories.UserInputFactory(
            dry_run=False,
            delete_pages=True,
        ),
    )

    assert len(urls_with_actions) == 3
    (_, nested_dir_doc_url, _) = urls_with_actions.keys()
    assert (urls := tuple(urls_with_actions)) == (doc_url, nested_dir_doc_url, index_url)
    nested_dir_doc_table_line = (
        f"| 2 | {nested_dir_doc_table_key} |"
        f" [{nested_dir_doc_content}]({urlparse(nested_dir_doc_url).path}) |"
    )
    assert_substrings_in_string(
        chain(urls, (nested_dir_doc_table_line, "Create", "'success'")), caplog.text
    )
    index_topic = discourse_api.retrieve_topic(url=index_url)
    assert nested_dir_doc_table_line in index_topic
    nested_dir_doc_topic = discourse_api.retrieve_topic(url=nested_dir_doc_url)
    assert nested_dir_doc_topic == nested_dir_doc_content

    # 9. docs with the documentation file in the nested directory removed in dry run mode
    caplog.clear()
    nested_dir_doc_file.unlink()

    urls_with_actions = run(
        base_path=repository_path,
        discourse=discourse_api,
        user_inputs=factories.UserInputFactory(
            dry_run=True,
            delete_pages=True,
        ),
    )

    assert (urls := tuple(urls_with_actions)) == (doc_url, nested_dir_doc_url, index_url)
    assert_substrings_in_string(
        chain(urls, (nested_dir_doc_table_line, "Delete", "Update", "'skip'")), caplog.text
    )
    index_topic = discourse_api.retrieve_topic(url=index_url)
    assert nested_dir_doc_table_line in index_topic
    nested_dir_doc_topic = discourse_api.retrieve_topic(url=nested_dir_doc_url)
    assert nested_dir_doc_topic == nested_dir_doc_content

    # 10. docs with the documentation file in the nested directory removed with page deletion
    #     disabled
    caplog.clear()

    urls_with_actions = run(
        base_path=repository_path,
        discourse=discourse_api,
        user_inputs=factories.UserInputFactory(
            dry_run=False,
            delete_pages=False,
        ),
    )

    assert (urls := tuple(urls_with_actions)) == (doc_url, nested_dir_doc_url, index_url)
    assert_substrings_in_string(
        chain(urls, (nested_dir_doc_table_line, "Delete", "Update", "'skip'")), caplog.text
    )
    index_topic = discourse_api.retrieve_topic(url=index_url)
    assert nested_dir_doc_table_line not in index_topic
    nested_dir_doc_topic = discourse_api.retrieve_topic(url=nested_dir_doc_url)
    assert nested_dir_doc_topic == nested_dir_doc_content

    # 11. with the nested directory removed
    caplog.clear()
    nested_dir.rmdir()

    urls_with_actions = run(
        base_path=repository_path,
        discourse=discourse_api,
        user_inputs=factories.UserInputFactory(
            dry_run=False,
            delete_pages=True,
        ),
    )

    assert (urls := tuple(urls_with_actions)) == (doc_url, index_url)
    assert_substrings_in_string(
        chain(urls, (nested_dir_table_line, "Delete", "Update", "'success'")), caplog.text
    )
    index_topic = discourse_api.retrieve_topic(url=index_url)
    assert nested_dir_table_line not in index_topic

    # 12. with the documentation file removed
    caplog.clear()
    doc_file.unlink()

    urls_with_actions = run(
        base_path=repository_path,
        discourse=discourse_api,
        user_inputs=factories.UserInputFactory(
            dry_run=False,
            delete_pages=True,
        ),
    )

    assert (urls := tuple(urls_with_actions)) == (doc_url, index_url)
    assert_substrings_in_string(
        chain(urls, (doc_table_line_2, "Delete", "Update", "'success'")), caplog.text
    )
    index_topic = discourse_api.retrieve_topic(url=index_url)
    assert doc_table_line_2 not in index_topic
    with pytest.raises(exceptions.DiscourseError):
        discourse_api.retrieve_topic(url=doc_url)

    # 13. with the index file removed
    caplog.clear()
    index_file.unlink()

    urls_with_actions = run(
        base_path=repository_path,
        discourse=discourse_api,
        user_inputs=factories.UserInputFactory(
            dry_run=False,
            delete_pages=True,
        ),
    )

    assert (urls := tuple(urls_with_actions)) == (index_url,)
    assert_substrings_in_string(chain(urls, ("Update", "'success'")), caplog.text)
    index_topic = discourse_api.retrieve_topic(url=index_url)
    assert index_content not in index_topic
