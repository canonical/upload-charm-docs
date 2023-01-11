# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Integration tests for running the migrate action."""

# This test is fairly complex as it simulates sequential action runs
# pylint: disable=too-many-arguments,too-many-locals,too-many-statements

import logging
from itertools import chain
from pathlib import Path

import pytest
from git.repo import Repo
from github.PullRequest import PullRequest

from src import index, metadata, migration, pull_request, run
from src.discourse import Discourse

from .. import factories
from ..unit.helpers import assert_substrings_in_string, create_metadata_yaml

pytestmark = pytest.mark.migrate


@pytest.mark.asyncio
@pytest.mark.usefixtures("patch_create_repository_client")
async def test_run_migrate(
    discourse_hostname: str,
    discourse_api: Discourse,
    caplog: pytest.LogCaptureFixture,
    repository: Repo,
    repository_path: Path,
    upstream_repository: Repo,
    upstream_repository_path: Path,
    mock_pull_request: PullRequest,
):
    """
    arrange: given running discourse server
    act: when run is called with:
        1. with no docs dir and no custom branchname provided
        2. with no docs dir and custom branchname provided
        3. with no changes applied after migration
    assert: then:
        1. the documentation files are pushed to default branch
        2. the documentation files are pushed to custom branch
        3. no operations are taken place
    """
    caplog.set_level(logging.INFO)
    document_name = "migration name 1"
    discourse_prefix = f"http://{discourse_hostname}"
    content_page_1 = factories.ContentPageFactory()
    content_page_1_url = discourse_api.create_topic(
        title=content_page_1.title,
        content=content_page_1.content,
    ).removeprefix(discourse_prefix)
    content_page_2 = factories.ContentPageFactory()
    content_page_2_url = discourse_api.create_topic(
        title=content_page_2.title,
        content=content_page_2.content,
    ).removeprefix(discourse_prefix)
    content_page_3 = factories.ContentPageFactory()
    content_page_3_url = discourse_api.create_topic(
        title=content_page_3.title,
        content=content_page_3.content,
    ).removeprefix(discourse_prefix)
    content_page_4 = factories.ContentPageFactory()
    content_page_4_url = discourse_api.create_topic(
        title=content_page_4.title,
        content=content_page_4.content,
    ).removeprefix(discourse_prefix)
    index_page_content = f"""Testing index page.

    Testing index page content.

    # Navigation

    | Level | Path | Navlink |
    | -- | -- | -- |
    | 1 | group-1 | [Group 1]() |
    | 1 | group-2 | [Group 2]() |
    | 2 | group-2-content-1 | [Content Link 1]({content_page_1_url}) |
    | 2 | group-2-content-2 | [Content Link 2]({content_page_2_url}) |
    | 1 | group-3 | [Group 3]() |
    | 2 | group-3-group-4 | [Group 4]() |
    | 3 | group-3-group-4-content-3 | [Content Link 3]({content_page_3_url}) |
    | 2 | group-3-content-4 | [Content Link 4]({content_page_4_url}) |
    | 1 | group-5 | [Group 5]() |"""
    index_url = discourse_api.create_topic(
        title=f"{document_name.replace('-', ' ').title()} Documentation Overview",
        content=index_page_content,
    )

    # 1. with no docs dir and a metadata.yaml with docs key
    caplog.clear()
    create_metadata_yaml(
        content=f"{metadata.METADATA_NAME_KEY}: name 1\n{metadata.METADATA_DOCS_KEY}: {index_url}",
        path=repository_path,
    )

    urls_with_actions = run(
        base_path=repository_path,
        discourse=discourse_api,
        user_inputs=factories.UserInputFactory(),
    )

    upstream_repository.git.checkout(pull_request.DEFAULT_BRANCH_NAME)
    upstream_doc_dir = upstream_repository_path / index.DOCUMENTATION_FOLDER_NAME
    assert tuple(urls_with_actions) == (mock_pull_request.html_url,)
    assert (group_1_path := upstream_doc_dir / "group-1").is_dir()
    assert (group_1_path / migration.GITKEEP_FILENAME).is_file()
    assert (group_2_path := upstream_doc_dir / "group-2").is_dir()
    assert (group_2_path / "content-1.md").read_text(encoding="utf-8") == content_page_1.content
    assert (group_2_path / "content-2.md").read_text(encoding="utf-8") == content_page_2.content
    assert (group_3_path := upstream_doc_dir / "group-3").is_dir()
    assert (group_4_path := group_3_path / "group-4").is_dir()
    assert (group_4_path / "content-3.md").read_text(encoding="utf-8") == content_page_3.content
    assert (group_3_path / "content-4.md").read_text(encoding="utf-8") == content_page_4.content
    assert (group_5_path := upstream_doc_dir / "group-5").is_dir()
    assert group_5_path.is_dir()

    # 2. with no changes applied after migration
    caplog.clear()
    repository.git.checkout(pull_request.DEFAULT_BRANCH_NAME)

    urls_with_actions = run(
        base_path=repository_path,
        discourse=discourse_api,
        user_inputs=factories.UserInputFactory(),
    )

    assert_substrings_in_string(
        chain(urls_with_actions, ("Noop", "Noop", "Noop", "'success'")), caplog.text
    )
