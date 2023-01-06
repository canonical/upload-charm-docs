# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for migration module."""

# Need access to protected functions for testing
# pylint: disable=protected-access

from collections.abc import Iterable
from pathlib import Path
from unittest import mock

import pytest

from src import discourse, exceptions, migration, types_

from .. import factories
from .helpers import assert_substrings_in_string


@pytest.mark.parametrize(
    "path, table_path, expected",
    [
        pytest.param(Path(""), types_.TablePath("test"), "test", id="table path only"),
        pytest.param(
            Path("group-1"), types_.TablePath("group-1-test"), "test", id="test in group"
        ),
        pytest.param(
            Path("group-1/nested/path"),
            types_.TablePath("group-1-nested-path-test"),
            "test",
            id="test in group",
        ),
        pytest.param(
            Path("not/matching/group"), types_.TablePath("test"), "test", id="non-prefix path"
        ),
    ],
)
def test__extract_name_from_paths(path: Path, table_path: types_.TablePath, expected: str):
    """
    arrange: given a path and table path composed from groups
    act: when _extract_name_from_paths is called
    assert: the name part is extracted from table path.
    """
    assert migration._extract_name_from_paths(current_path=path, table_path=table_path) == expected


@pytest.mark.parametrize(
    "depth, row, is_first_row, expected_message_contents",
    [
        pytest.param(
            0,
            factories.TableRowFactory(level=2),
            True,
            (
                "invalid starting row level",
                "a table row must start with level value 1",
                "please fix the upstream first and re-run",
            ),
            id="Invalid starting row",
        ),
        pytest.param(
            1,
            factories.TableRowFactory(level=0),
            False,
            ("invalid row level", "zero or negative level value is invalid."),
            id="Invalid level(0)",
        ),
        pytest.param(
            1,
            factories.TableRowFactory(level=-1),
            False,
            ("invalid row level", "zero or negative level value is invalid."),
            id="Invalid level(negative value)",
        ),
        pytest.param(
            1,
            factories.TableRowFactory(level=3),
            False,
            (
                "invalid row level value sequence",
                "level sequence jumps of more than 1 is invalid.",
            ),
            id="Invalid level sequence jump",
        ),
    ],
)
def test__assert_valid_row_error(
    depth: int, row: types_.TableRow, is_first_row: bool, expected_message_contents: Iterable[str]
):
    """
    arrange: given an invalid group depth(level), table row and is_first_row combinations
    act: when _assert_valid_row is called
    assert: InputError is raised with expected error message contents.
    """
    with pytest.raises(exceptions.InputError) as exc:
        migration._assert_valid_row(group_level=depth, row=row, is_first_row=is_first_row)

    assert_substrings_in_string(expected_message_contents, str(exc.value).lower())


@pytest.mark.parametrize(
    "depth, row, is_first_row",
    [
        pytest.param(
            0,
            factories.TableRowFactory(level=1),
            True,
            id="Valid starting row",
        ),
        pytest.param(
            1,
            factories.TableRowFactory(level=2),
            False,
            id="Valid row sequence(increase)",
        ),
        pytest.param(
            3,
            factories.TableRowFactory(level=2),
            False,
            id="Valid row sequence(decrease)",
        ),
        pytest.param(
            3,
            factories.TableRowFactory(level=1),
            False,
            id="Valid row sequence(decrease multi)",
        ),
    ],
)
def test__assert_valid_row(depth: int, row: types_.TableRow, is_first_row: bool):
    """
    arrange: given a valid group depth(level), table row and is_first_row combinations
    act: when _assert_valid_row is called
    assert: No exceptions are raised.
    """
    migration._assert_valid_row(group_level=depth, row=row, is_first_row=is_first_row)


@pytest.mark.parametrize(
    "table_rows",
    [
        pytest.param(
            (
                factories.TableRowFactory(level=1, is_document=True),
                factories.TableRowFactory(level=2, is_document=True),
            ),
            id="document sequence level increase(no group)",
        ),
        pytest.param(
            (
                factories.TableRowFactory(level=1, is_document=True),
                factories.TableRowFactory(level=3, is_document=True),
            ),
            id="document sequence level increase(skip level)",
        ),
        pytest.param(
            (
                factories.TableRowFactory(level=1, is_group=True),
                factories.TableRowFactory(level=3, is_group=True),
            ),
            id="group sequence level increase(skip level)",
        ),
        pytest.param(
            (
                factories.TableRowFactory(level=1, is_document=True),
                factories.TableRowFactory(level=2, is_group=True),
            ),
            id="document group sequence level increase(no group)",
        ),
        pytest.param(
            (
                factories.TableRowFactory(level=1, is_group=True),
                factories.TableRowFactory(level=2, is_document=True),
                factories.TableRowFactory(level=3, is_group=True),
            ),
            id="document group sequence level increase(doc doesn't increase group depth)",
        ),
    ],
)
def test__extract_docs_from_table_rows_invalid_sequence(table_rows: Iterable[types_.TableRow]):
    """
    arrange: given an invalid table row sequence
    act: when _extract_docs_from_table_rows is called
    assert: InputError is raised with invalid level value sequence error message.
    """
    with pytest.raises(exceptions.InputError) as exc:
        all(migration._extract_docs_from_table_rows(table_rows=table_rows))

    assert_substrings_in_string(
        ("invalid row level value sequence", "level sequence jumps of more than 1 is invalid"),
        str(exc.value).lower(),
    )


# Pylint doesn't understand how the walrus operator works
# pylint: disable=undefined-variable,unused-variable
@pytest.mark.parametrize(
    "table_rows, expected_metas",
    [
        pytest.param(
            (doc_row_1 := factories.TableRowFactory(level=1, path="doc-1", is_document=True),),
            (
                types_.DocumentMeta(
                    path=Path("doc-1.md"), link=doc_row_1.navlink.link, table_row=doc_row_1
                ),
            ),
            id="single initial document",
        ),
        pytest.param(
            (group_row_1 := factories.TableRowFactory(level=1, path="group-1", is_group=True),),
            (types_.GitkeepMeta(path=Path("group-1/.gitkeep"), table_row=group_row_1),),
            id="single initial group",
        ),
        pytest.param(
            (
                doc_row_1 := factories.TableRowFactory(level=1, path="doc-1", is_document=True),
                doc_row_2 := factories.TableRowFactory(level=1, path="doc-2", is_document=True),
            ),
            (
                types_.DocumentMeta(
                    path=Path("doc-1.md"), link=doc_row_1.navlink.link, table_row=doc_row_1
                ),
                types_.DocumentMeta(
                    path=Path("doc-2.md"), link=doc_row_2.navlink.link, table_row=doc_row_2
                ),
            ),
            id="two documents",
        ),
        pytest.param(
            (
                group_row_1 := factories.TableRowFactory(level=1, path="group-1", is_group=True),
                group_row_2 := factories.TableRowFactory(level=1, path="group-2", is_group=True),
            ),
            (
                types_.GitkeepMeta(path=Path("group-1/.gitkeep"), table_row=group_row_1),
                types_.GitkeepMeta(path=Path("group-2/.gitkeep"), table_row=group_row_2),
            ),
            id="distinct two groups",
        ),
        pytest.param(
            (
                doc_row_1 := factories.TableRowFactory(level=1, path="doc-1", is_document=True),
                group_row_1 := factories.TableRowFactory(level=1, path="group-1", is_group=True),
            ),
            (
                types_.DocumentMeta(
                    path=Path("doc-1.md"), link=doc_row_1.navlink.link, table_row=doc_row_1
                ),
                types_.GitkeepMeta(path=Path("group-1/.gitkeep"), table_row=group_row_1),
            ),
            id="distinct document and group",
        ),
        pytest.param(
            (
                group_row_1 := factories.TableRowFactory(level=1, path="group-1", is_group=True),
                doc_row_1 := factories.TableRowFactory(level=1, path="doc-1", is_document=True),
            ),
            (
                types_.GitkeepMeta(path=Path("group-1/.gitkeep"), table_row=group_row_1),
                types_.DocumentMeta(
                    path=Path("doc-1.md"), link=doc_row_1.navlink.link, table_row=doc_row_1
                ),
            ),
            id="distinct group and document",
        ),
        pytest.param(
            (
                group_row_1 := factories.TableRowFactory(level=1, path="group-1", is_group=True),
                doc_row_1 := factories.TableRowFactory(level=2, path="doc-1", is_document=True),
            ),
            (
                types_.DocumentMeta(
                    path=Path("group-1/doc-1.md"),
                    link=doc_row_1.navlink.link,
                    table_row=doc_row_1,
                ),
            ),
            id="nested document in group",
        ),
        pytest.param(
            (
                group_row_1 := factories.TableRowFactory(level=1, path="group-1", is_group=True),
                group_row_2 := factories.TableRowFactory(level=2, path="group-2", is_group=True),
            ),
            (types_.GitkeepMeta(path=Path("group-1/group-2/.gitkeep"), table_row=group_row_2),),
            id="nested group in group",
        ),
        pytest.param(
            (
                group_row_1 := factories.TableRowFactory(level=1, path="group-1", is_group=True),
                group_row_2 := factories.TableRowFactory(level=1, path="group-2", is_group=True),
                group_row_3 := factories.TableRowFactory(level=1, path="group-3", is_group=True),
            ),
            (
                types_.GitkeepMeta(path=Path("group-1/.gitkeep"), table_row=group_row_1),
                types_.GitkeepMeta(path=Path("group-2/.gitkeep"), table_row=group_row_2),
                types_.GitkeepMeta(path=Path("group-3/.gitkeep"), table_row=group_row_3),
            ),
            id="distinct rows(group, group, group)",
        ),
        pytest.param(
            (
                group_row_1 := factories.TableRowFactory(level=1, path="group-1", is_group=True),
                doc_row_1 := factories.TableRowFactory(level=1, path="doc-1", is_document=True),
                group_row_2 := factories.TableRowFactory(level=1, path="group-2", is_group=True),
            ),
            (
                types_.GitkeepMeta(path=Path("group-1/.gitkeep"), table_row=group_row_1),
                types_.DocumentMeta(
                    path=Path("doc-1.md"),
                    link=doc_row_1.navlink.link,
                    table_row=doc_row_1,
                ),
                types_.GitkeepMeta(path=Path("group-2/.gitkeep"), table_row=group_row_2),
            ),
            id="distinct rows(group, doc, group)",
        ),
        pytest.param(
            (
                group_row_1 := factories.TableRowFactory(level=1, path="group-1", is_group=True),
                nested_doc_row_1 := factories.TableRowFactory(
                    level=2, path="group-1-doc-1", is_document=True
                ),
                group_row_2 := factories.TableRowFactory(level=1, path="group-2", is_group=True),
            ),
            (
                types_.DocumentMeta(
                    path=Path("group-1/doc-1.md"),
                    link=nested_doc_row_1.navlink.link,
                    table_row=nested_doc_row_1,
                ),
                types_.GitkeepMeta(path=Path("group-2/.gitkeep"), table_row=group_row_2),
            ),
            id="multi rows 1 nested(group, nested-doc, group)",
        ),
        pytest.param(
            (
                group_row_1 := factories.TableRowFactory(level=1, path="group-1", is_group=True),
                nested_doc_row_1 := factories.TableRowFactory(
                    level=2, path="group-1-doc-1", is_document=True
                ),
                nested_group_row_1 := factories.TableRowFactory(
                    level=2, path="group-1-group-2", is_group=True
                ),
            ),
            (
                types_.DocumentMeta(
                    path=Path("group-1/doc-1.md"),
                    link=nested_doc_row_1.navlink.link,
                    table_row=nested_doc_row_1,
                ),
                types_.GitkeepMeta(
                    path=Path("group-1/group-2/.gitkeep"), table_row=nested_group_row_1
                ),
            ),
            id="multi rows 2 separately nested(group, nested-group, nested-doc)",
        ),
        pytest.param(
            (
                group_row_1 := factories.TableRowFactory(level=1, path="group-1", is_group=True),
                nested_group_row_1 := factories.TableRowFactory(
                    level=2, path="group-1-group-2", is_group=True
                ),
                nested_doc_row_1 := factories.TableRowFactory(
                    level=3, path="group-1-group-2-doc-1", is_document=True
                ),
            ),
            (
                types_.DocumentMeta(
                    path=Path("group-1/group-2/doc-1.md"),
                    link=nested_doc_row_1.navlink.link,
                    table_row=nested_doc_row_1,
                ),
            ),
            id="multi rows nested(group, nested-group, nested-group-nested-doc)",
        ),
    ],
)
def test__extract_docs_from_table_rows(
    table_rows: Iterable[types_.TableRow], expected_metas: Iterable[types_.DocumentMeta]
):
    """
    arrange: given an valid table row sequences
    act: when _extract_docs_from_table_rows is called
    assert: expected document metadatas are yielded.
    """
    assert (
        tuple(row for row in migration._extract_docs_from_table_rows(table_rows=table_rows))
        == expected_metas
    )


@pytest.mark.parametrize(
    "row, group_path, group_level, expected_path_depth_pair",
    [
        pytest.param(
            factories.TableRowFactory(level=1, path="test-1", is_document=True),
            Path(),
            0,
            (Path(), 0),
            id="single initial document",
        ),
        pytest.param(
            factories.TableRowFactory(level=1, path="group-1", is_group=True),
            Path(),
            0,
            (Path("group-1"), 1),
            id="single initial group",
        ),
        pytest.param(
            factories.TableRowFactory(level=2, path="group-1-test-1", is_document=True),
            Path("group-1"),
            1,
            (Path("group-1"), 1),
            id="document in group",
        ),
        pytest.param(
            factories.TableRowFactory(level=2, path="group-1-group-2", is_group=True),
            Path("group-1"),
            1,
            (Path("group-1/group-2"), 2),
            id="group in group",
        ),
        pytest.param(
            factories.TableRowFactory(level=2, path="group-1-test-1", is_document=True),
            Path("group-1/group-2"),
            2,
            (Path("group-1"), 1),
            id="document in same level group",
        ),
        pytest.param(
            factories.TableRowFactory(level=2, path="group-1-group-4", is_group=True),
            Path("group-1/group-2"),
            2,
            (Path("group-1/group-4"), 2),
            id="group in same level group",
        ),
        pytest.param(
            factories.TableRowFactory(level=2, path="group-1-test-1", is_document=True),
            Path("group-1/group-2/group-3"),
            3,
            (Path("group-1"), 1),
            id="document in lower level group",
        ),
        pytest.param(
            factories.TableRowFactory(level=2, path="group-1-group-4", is_group=True),
            Path("group-1/group-2/group-3"),
            3,
            (Path("group-1/group-4"), 2),
            id="group in lower level group",
        ),
    ],
)
def test__get_next_group_info(
    row: types_.TableRow,
    group_path: Path,
    group_level: int,
    expected_path_depth_pair: tuple[Path, int],
):
    """
    arrange: given table row, group path and group depth
    act: when _get_next_group_info is called
    assert: expected path with corresponding depth is returned.
    """
    assert (
        migration._get_next_group_info(row=row, group_path=group_path, group_level=group_level)
        == expected_path_depth_pair
    )


@pytest.mark.parametrize(
    "row, path, expected_meta",
    [
        pytest.param(
            doc_row := factories.TableRowFactory(is_document=True, path="doc-1"),
            Path(),
            types_.DocumentMeta(
                path=Path("doc-1.md"), link=doc_row.navlink.link, table_row=doc_row
            ),
            id="single doc file",
        ),
        pytest.param(
            doc_row := factories.TableRowFactory(is_document=True, path="group-1-doc-1"),
            Path("group-1"),
            types_.DocumentMeta(
                path=Path("group-1/doc-1.md"), link=doc_row.navlink.link, table_row=doc_row
            ),
            id="nested doc file",
        ),
        pytest.param(
            doc_row := factories.TableRowFactory(is_document=True, path="group-2-doc-1"),
            Path("group-1"),
            types_.DocumentMeta(
                path=Path("group-1/group-2-doc-1.md"), link=doc_row.navlink.link, table_row=doc_row
            ),
            id="typo in nested doc file path",
        ),
    ],
)
def test__create_document_meta(
    row: types_.TableRow, path: Path, expected_meta: types_.DocumentMeta
):
    """
    arrange: given a document table row
    act: when _create_document_meta is called
    assert: document meta with path to file is returned.
    """
    assert migration._create_document_meta(row=row, path=path) == expected_meta


@pytest.mark.parametrize(
    "row, path, expected_meta",
    [
        pytest.param(
            group_row := factories.TableRowFactory(is_group=True, path="group-1"),
            Path("group-1"),
            types_.GitkeepMeta(path=Path("group-1/.gitkeep"), table_row=group_row),
            id="single group row",
        ),
        pytest.param(
            group_row := factories.TableRowFactory(is_group=True, path="group-1-group-2"),
            Path("group-1/group-2"),
            types_.GitkeepMeta(path=Path("group-1/group-2/.gitkeep"), table_row=group_row),
            id="nested group row with correct current path",
        ),
    ],
)
def test__create_gitkeep_meta(row: types_.TableRow, path: Path, expected_meta: types_.GitkeepMeta):
    """
    arrange: given a empty group table row
    act: when _create_gitkeep_meta is called
    assert: gitkeep meta denoting empty group is returned.
    """
    assert migration._create_gitkeep_meta(row=row, path=path) == expected_meta


@pytest.mark.parametrize(
    "content, expected_meta",
    [
        pytest.param(
            content := "content-1",
            types_.IndexDocumentMeta(path=Path("index.md"), content=content),
        ),
    ],
)
def test__index_file_from_content(content: str, expected_meta: types_.IndexDocumentMeta):
    """
    arrange: given an index file content
    act: when _index_file_from_content is called
    assert: expected index document metadata is returned.
    """
    assert migration._index_file_from_content(content) == expected_meta


@pytest.mark.parametrize(
    "meta",
    [
        pytest.param(
            types_.GitkeepMeta(path=Path(".gitkeep"), table_row=factories.TableRowFactory()),
            id="single .gitkeep",
        ),
        pytest.param(
            types_.GitkeepMeta(
                path=Path("nested-dir/.gitkeep"), table_row=factories.TableRowFactory()
            ),
            id="nested .gitkeep",
        ),
    ],
)
def test__migrate_gitkeep(meta: types_.GitkeepMeta, tmp_path: Path):
    """
    arrange: given a gitkeep file metadata and a temporary path denoting docs directory
    act: when _migrate_gitkeep is called
    assert: Successful action report is returned and gitkeep file is created.
    """
    returned_report = migration._migrate_gitkeep(gitkeep_meta=meta, docs_path=tmp_path)
    assert returned_report.table_row == meta.table_row
    assert returned_report.result == types_.ActionResult.SUCCESS
    assert returned_report.location == tmp_path / meta.path
    assert returned_report.reason == migration.EMPTY_DIR_REASON
    assert (tmp_path / meta.path).is_file()


def test__migrate_document_fail(tmp_path: Path):
    """
    arrange: given valid document metadata and mocked discourse that raises an error
    act: when _migrate_document is called
    assert: failed migration report is returned.
    """
    mocked_discourse = mock.MagicMock(spec=discourse.Discourse)
    mocked_discourse.retrieve_topic.side_effect = (error := exceptions.DiscourseError("fail"))
    table_row = types_.TableRow(
        level=(level := 1),
        path=(path_str := "empty-group-path"),
        navlink=types_.Navlink(title=(navlink_title := "title 1"), link=(link_str := "link 1")),
    )
    document_meta = types_.DocumentMeta(
        path=(path := Path(path_str)), table_row=table_row, link=link_str
    )

    returned_report = migration._migrate_document(
        document_meta=document_meta, discourse=mocked_discourse, docs_path=tmp_path
    )

    assert not (tmp_path / path).exists()
    mocked_discourse.retrieve_topic.assert_called_once_with(url=link_str)
    assert returned_report.table_row is not None
    assert returned_report.table_row.level == level
    assert returned_report.table_row.path == path_str
    assert returned_report.table_row.navlink.title == navlink_title
    assert returned_report.table_row.navlink.link == link_str
    assert returned_report.result == types_.ActionResult.FAIL
    assert returned_report.reason == str(error)


def test__migrate_document(tmp_path: Path):
    """
    arrange: given valid document metadata
    act: when _migrate_document is called
    assert: document is created and migration report is returned.
    """
    mocked_discourse = mock.MagicMock(spec=discourse.Discourse)
    mocked_discourse.retrieve_topic.return_value = (content := "content")
    table_row = types_.TableRow(
        level=(level := 1),
        path=(path_str := "empty-directory"),
        navlink=types_.Navlink(title=(navlink_title := "title 1"), link=(link_str := "link 1")),
    )
    document_meta = types_.DocumentMeta(
        path=(path := Path(path_str)), table_row=table_row, link=link_str
    )

    returned_report = migration._migrate_document(
        document_meta=document_meta, discourse=mocked_discourse, docs_path=tmp_path
    )

    assert (file_path := (tmp_path / path)).is_file()
    assert file_path.read_text(encoding="utf-8") == content
    mocked_discourse.retrieve_topic.assert_called_once_with(url=link_str)
    assert returned_report.table_row is not None
    assert returned_report.table_row.level == level
    assert returned_report.table_row.path == path_str
    assert returned_report.table_row.navlink.title == navlink_title
    assert returned_report.table_row.navlink.link == link_str
    assert returned_report.result == types_.ActionResult.SUCCESS


def test__migrate_index(tmp_path: Path):
    """
    arrange: given valid index document metadata
    act: when _migrate_index is called
    assert: index file is created and migration report is returned.
    """
    document_meta = types_.IndexDocumentMeta(
        path=(path := Path("index.md")), content=(content := "content 1")
    )

    returned_report = migration._migrate_index(index_meta=document_meta, docs_path=tmp_path)

    assert (file_path := (tmp_path / path)).is_file()
    assert file_path.read_text(encoding="utf-8") == content
    assert returned_report.table_row is None
    assert returned_report.result == types_.ActionResult.SUCCESS
    assert returned_report.location == tmp_path / path
    assert returned_report.reason is None


@pytest.mark.parametrize(
    "file_meta, expected_report",
    [
        pytest.param(
            gitkeep_meta := types_.GitkeepMeta(
                path=(gitkeep_path := Path(".gitkeep")),
                table_row=(
                    table_row_sample := types_.TableRow(
                        level=1,
                        path="tablepath",
                        navlink=types_.Navlink(title="navlink", link=None),
                    )
                ),
            ),
            gitkeep_report := types_.ActionReport(
                table_row=table_row_sample,
                location=gitkeep_path,
                result=types_.ActionResult.SUCCESS,
                reason=migration.EMPTY_DIR_REASON,
            ),
            id="gitkeep file",
        ),
        pytest.param(
            document_meta := types_.DocumentMeta(
                path=(document_path := Path("document.md")),
                table_row=table_row_sample,
                link="samplelink",
            ),
            document_report := types_.ActionReport(
                table_row=table_row_sample,
                location=document_path,
                result=types_.ActionResult.SUCCESS,
                reason=None,
            ),
            id="document file",
        ),
        pytest.param(
            types_.IndexDocumentMeta(
                path=(index_path := Path("index.md")), content="index content"
            ),
            types_.ActionReport(
                table_row=None,
                location=index_path,
                result=types_.ActionResult.SUCCESS,
                reason=None,
            ),
            id="index file",
        ),
    ],
)
def test__run_one(
    file_meta: types_.MigrationFileMeta, expected_report: types_.ActionReport, tmp_path: Path
):
    """
    arrange: given a migration metadata and mocked discourse
    act: when _run_one is called
    assert: a valid migration report is returned and a file is created.
    """
    mocked_discourse = mock.MagicMock(spec=discourse.Discourse)
    mocked_discourse.retrieve_topic.side_effect = "content"

    returned_report = migration._run_one(
        file_meta=file_meta, discourse=mocked_discourse, docs_path=tmp_path
    )

    assert isinstance(returned_report.location, Path)
    assert returned_report.location.is_file()
    assert isinstance(expected_report.location, Path)
    assert returned_report.location == tmp_path / expected_report.location
    assert returned_report.result == expected_report.result
    assert returned_report.reason == expected_report.reason
    assert returned_report.table_row == expected_report.table_row


def test__get_docs_metadata():
    """
    arrange: given table rows from index table and the index_content from index file
    act: when _get_docs_metadata is called
    assert: an iterable starting with index migration metadata is returned.
    """
    table_rows = (factories.TableRowFactory(level=1),)
    index_content = "index-content-1"

    returned_docs_metadata = tuple(
        meta
        for meta in migration._get_docs_metadata(
            table_rows=table_rows,
            index_content=index_content,
        )
    )

    assert len(returned_docs_metadata) == 2
    assert isinstance(returned_docs_metadata[0], types_.IndexDocumentMeta)
    assert isinstance(returned_docs_metadata[1], types_.MigrationFileMeta)


@pytest.mark.parametrize(
    "migration_results",
    [
        pytest.param(
            (factories.ActionReportFactory(is_failed=True, is_migrate=True),),
            id="single failed result",
        ),
        pytest.param(
            (
                factories.ActionReportFactory(is_success=True, is_migrate=True),
                factories.ActionReportFactory(is_failed=True, is_migrate=True),
            ),
            id="single failed result in successful result",
        ),
        pytest.param(
            (
                factories.ActionReportFactory(is_skipped=True, is_migrate=True),
                factories.ActionReportFactory(is_failed=True, is_migrate=True),
            ),
            id="single failed result in skipped result",
        ),
        pytest.param(
            (
                factories.ActionReportFactory(is_success=True, is_migrate=True),
                factories.ActionReportFactory(is_failed=True, is_migrate=True),
                factories.ActionReportFactory(is_skipped=True, is_migrate=True),
                factories.ActionReportFactory(is_failed=True, is_migrate=True),
            ),
            id="multiple failed results in multiple result types",
        ),
    ],
)
def test__assert_migration_success_failed_result(migration_results: Iterable[types_.ActionReport]):
    """
    arrange: given an migration results iterable with a failed result
    act: when _assert_migration_success is called
    assert: Migration error is raised.
    """
    with pytest.raises(exceptions.MigrationError):
        migration._assert_migration_success(migration_results=migration_results)


@pytest.mark.parametrize(
    "migration_results",
    [
        pytest.param(
            (factories.ActionReportFactory(is_success=True, is_migrate=True),),
            id="successful result",
        ),
        pytest.param(
            (factories.ActionReportFactory(is_skipped=True, is_migrate=True),), id="skipped result"
        ),
        pytest.param(
            (
                factories.ActionReportFactory(is_success=True, is_migrate=True),
                factories.ActionReportFactory(is_skipped=True, is_migrate=True),
            ),
            id="non-failed results",
        ),
    ],
)
def test__assert_migration_success(migration_results: Iterable[types_.ActionReport]):
    """
    arrange: given an migration results iterable with no failed result
    act: when _assert_migration_success is called
    assert: No exceptions are raised.
    """
    migration._assert_migration_success(migration_results=migration_results)


@pytest.mark.parametrize(
    "table_rows, index_content, expected_files",
    [
        pytest.param(
            (factories.TableRowFactory(is_document=True, path="doc-1", level=1),),
            "content-1",
            (Path("doc-1.md"),),
            id="single doc",
        ),
        pytest.param(
            (
                factories.TableRowFactory(is_group=True, path="group-1", level=1),
                factories.TableRowFactory(is_document=True, path="doc-1", level=2),
            ),
            "content-1",
            (Path("group-1/doc-1.md"),),
            id="nested doc",
        ),
        pytest.param(
            (
                factories.TableRowFactory(is_group=True, path="group-1", level=1),
                factories.TableRowFactory(is_group=True, path="group-2", level=2),
            ),
            "content-1",
            (Path("group-1/group-2/.gitkeep"),),
            id="nested group no docs",
        ),
    ],
)
def test_run(
    table_rows: Iterable[types_.TableRow],
    index_content: str,
    tmp_path: Path,
    expected_files: Iterable[Path],
):
    """
    arrange: given table rows, index content, mocked discourse and a temporary docs path
    act: when run is called
    assert: table rows are successfully migrated
    """
    mocked_discourse = mock.MagicMock(spec=discourse.Discourse)
    mocked_discourse.retrieve_topic.return_value = "document-content"

    migration.run(
        table_rows=table_rows,
        index_content=index_content,
        discourse=mocked_discourse,
        docs_path=tmp_path,
    )

    assert (tmp_path / "index.md").read_text() == index_content
    for path in expected_files:
        assert (tmp_path / path).is_file()
