# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Module for migrating remote documentation into local git repository."""

import itertools
import logging
import typing
from pathlib import Path

from . import exceptions, types_
from .discourse import Discourse
from .docs_directory import calculate_table_path

EMPTY_DIR_REASON = "<created due to empty directory>"
GITKEEP_FILENAME = ".gitkeep"


def _extract_name(current_group_path: Path, table_path: types_.TablePath) -> str:
    """Extract name given a current working directory and table path.

    If there is a matching prefix in table path's prefix generated from the current group path,
    the prefix is removed and the remaining segment is returned as the extracted name.

    Args:
        current_group_path: current path of the file relative to the group's path directory.
        table_path: table path of the file from the index file, of format path-to-file-filename.

    Returns:
        The filename derived by removing the directory path from given table path of the file.
    """
    return table_path.removeprefix(f"{calculate_table_path(current_group_path)}-")


def _validate_table_rows(
    table_rows: typing.Iterable[types_.TableRow],
) -> typing.Iterable[types_.TableRow]:
    """Check whether a table row is valid in regards to the sequence.

    By tracking the current group level for each row, it validates whether a given row is valid
    among the sequence of rows given.

    Args:
        table_rows: Parsed rows from the index table.

    Raises:
        InputError: if the row is the first row but the value of level is not 1 or
            the level smaller than 1 or
            if the level increment is greater than one.

    Yields:
        Valid table row.
    """
    is_first_row = True
    current_group_level = 0
    for row in table_rows:
        if is_first_row:
            if row.level != 1:
                raise exceptions.InputError(
                    "Invalid starting row level. A table row must start with level value 1. "
                    "Please fix the upstream first and re-run."
                    f"Row: {row.to_markdown()}"
                )
        if row.level < 1:
            raise exceptions.InputError(
                f"Invalid row level: {row.level=!r}."
                "Zero or negative level value is invalid."
                f"Row: {row.to_markdown()}"
            )
        if row.level > current_group_level + 1:
            raise exceptions.InputError(
                "Invalid row level value sequence. Level sequence jumps of more than 1 is invalid."
                f"Did you mean level {current_group_level+1}?"
                f"Row: {row.to_markdown()}"
            )

        yield row

        is_first_row = False
        current_group_level = row.level if row.is_group else row.level - 1


def _get_row_group_path(
    group_path: Path, previous_row: types_.TableRow | None, row: types_.TableRow
) -> Path:
    """Get path to row's working group.

    If given row is a document row, it's working group is the group one level below.
    If given row is a group row, it's working group should be the path to row's group.

    Args:
        group_path: The path of the group in which the previous row was in, it should be the
            equivalent to previous_row's group path.
        previous_row: Previous row in the sequence. None if row is the first in sequence.
        row: Target row to adjust group path to.

    Returns:
        A path to the group where the row belongs.
    """
    # if it's the first row or the row level has increased from group row
    if not previous_row:
        # document belongs in current group path
        if not row.is_group:
            return group_path
        # move one level of nesting into new group path
        return group_path / _extract_name(current_group_path=group_path, table_path=row.path)

    # working group path belongs in the group 1 level above current row's level.
    # i.e. group-1/document-1, group path is group-1
    # group-1/group-2, group-path is group-1/group-2 but both cases require
    # moving to group-1 first to either generate document or group afterwards.
    destination_group_level = row.level - 1
    current_group_level = previous_row.level if previous_row.is_group else previous_row.level - 1

    while current_group_level != destination_group_level:
        current_group_level -= 1
        group_path = group_path.parent

    # current state of group_path is 1 level above current row's level.
    # move working group path to current group
    # i.e. current: group-1, destination: group-1/group-2, row: group-1-group-2
    if row.is_group:
        group_path = group_path / _extract_name(current_group_path=group_path, table_path=row.path)

    return group_path


def _create_document_meta(row: types_.TableRow, path: Path) -> types_.DocumentMeta:
    """Create document meta file for migration from table row.

    Args:
        row: Row containing link to document and path information.
        path: Relative path to where the document should reside.

    Raises:
        MigrationError: if the table row that was passed in does not cantain a link to document.

    Returns:
        Information required to migrate document.
    """
    # this is to help mypy understand that link is not None.
    # this case cannot be possible since this is called for group rows only.
    if not row.navlink.link:  # pragma: no cover
        raise exceptions.MigrationError(
            "Internal error, no implementation for creating document meta with missing link in row."
        )
    name = _extract_name(current_group_path=path, table_path=row.path)
    return types_.DocumentMeta(path=path / f"{name}.md", link=row.navlink.link, table_row=row)


def _create_gitkeep_meta(row: types_.TableRow, path: Path) -> types_.GitkeepMeta:
    """Create a representation of an empty grouping through a .gitkeep file metadata.

    Args:
        row: An empty group row.
        path: Relative path to where the document should reside.

    Returns:
        Information required to migrate empty group.
    """
    return types_.GitkeepMeta(path=path / GITKEEP_FILENAME, table_row=row)


def _extract_docs_from_table_rows(
    table_rows: typing.Iterable[types_.TableRow],
) -> typing.Iterable[types_.MigrationFileMeta]:
    """Extract necessary migration documents to build docs directory.

    Algorithm:
        1. For each row:
            1.1. If previous row was a group and the level is equal to or lower than current
                level, yield gitkeep meta
            1.2. Adjust current group path according to previous row path.
            1.3. If current row is a document, yield document meta.
            1.4. Set previous row as current row since we're done processing it.

    Args:
        table_rows: Table rows from the index file in the order of group hierarchy.

    Yields:
        Migration documents with navlink to content. .gitkeep file if empty group.
    """
    current_group_path = Path()
    previous_row: types_.TableRow | None = None
    previous_path: Path | None = None

    for row in table_rows:
        # if previously processed row was a group and it had nothing in it
        # it should yield a .gitkeep file to denote empty group.
        if (
            previous_row
            and previous_path
            and previous_row.is_group
            and row.level <= previous_row.level
        ):
            yield _create_gitkeep_meta(row=previous_row, path=previous_path)

        current_group_path = _get_row_group_path(
            group_path=current_group_path, previous_row=previous_row, row=row
        )

        if not row.is_group:
            yield _create_document_meta(row=row, path=current_group_path)

        previous_row = row
        previous_path = current_group_path

    # last group without documents yields gitkeep meta.
    if previous_row is not None and previous_row.is_group:
        yield _create_gitkeep_meta(row=previous_row, path=current_group_path)


def _index_file_from_content(content: str) -> types_.IndexDocumentMeta:
    """Get index file document metadata.

    Args:
        content: Index file content.

    Returns:
        Index file document metadata.
    """
    return types_.IndexDocumentMeta(path=Path("index.md"), content=content)


def make_parent(docs_path: Path, document_meta: types_.MigrationFileMeta) -> Path:
    """Construct path leading to document to be created.

    Args:
        docs_path: Path to documentation directory.
        document_meta: Information about document to be migrated.

    Returns:
        Full path to the parent directory of the document to be migrated.
    """
    path = docs_path / document_meta.path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _migrate_gitkeep(gitkeep_meta: types_.GitkeepMeta, docs_path: Path) -> types_.ActionReport:
    """Write gitkeep file to a path inside docs directory.

    Args:
        gitkeep_meta: Information about gitkeep file to be migrated.
        docs_path: Documentation folder path.

    Returns:
        Migration report for gitkeep file creation.
    """
    logging.info("migrate meta: %s", gitkeep_meta)

    full_path = make_parent(docs_path=docs_path, document_meta=gitkeep_meta)
    full_path.touch()
    return types_.ActionReport(
        table_row=gitkeep_meta.table_row,
        result=types_.ActionResult.SUCCESS,
        location=full_path,
        reason=EMPTY_DIR_REASON,
    )


def _migrate_document(
    document_meta: types_.DocumentMeta, discourse: Discourse, docs_path: Path
) -> types_.ActionReport:
    """Write document file with content to docs directory.

    Args:
        document_meta: Information about document file to be migrated.
        discourse: Client to the documentation server.
        docs_path: The path to the docs directory to migrate all the documentation.

    Returns:
        Migration report for document file creation.
    """
    logging.info("migrate meta: %s", document_meta)

    try:
        content = discourse.retrieve_topic(url=document_meta.link)
    except exceptions.DiscourseError as exc:
        return types_.ActionReport(
            table_row=document_meta.table_row,
            result=types_.ActionResult.FAIL,
            location=None,
            reason=str(exc),
        )
    full_path = make_parent(docs_path=docs_path, document_meta=document_meta)
    full_path.write_text(content, encoding="utf-8")
    return types_.ActionReport(
        table_row=document_meta.table_row,
        result=types_.ActionResult.SUCCESS,
        location=full_path,
        reason=None,
    )


def _migrate_index(index_meta: types_.IndexDocumentMeta, docs_path: Path) -> types_.ActionReport:
    """Write index document to docs repository.

    Args:
        index_meta: Information about index file to be migrated.
        docs_path: The path to the docs directory to migrate all the documentation.

    Returns:
        Migration report for index file creation.
    """
    logging.info("migrate meta: %s", index_meta)

    full_path = make_parent(docs_path=docs_path, document_meta=index_meta)
    full_path.write_text(index_meta.content, encoding="utf-8")
    return types_.ActionReport(
        table_row=None,
        result=types_.ActionResult.SUCCESS,
        location=full_path,
        reason=None,
    )


def _run_one(
    file_meta: types_.MigrationFileMeta, discourse: Discourse, docs_path: Path
) -> types_.ActionReport:
    """Write document content inside the docs directory.

    Args:
        file_meta: Information about migration file corresponding to a row in index table.
        discourse: Client to the documentation server.
        docs_path: The path to the docs directory to migrate all the documentation.

    Raises:
        MigrationError: if file_meta is of invalid metadata type.

    Returns:
        Migration report containing migration result.
    """
    match type(file_meta):
        case types_.GitkeepMeta:
            # To help mypy (same for the rest of the asserts), it is ok if the assert does not run
            assert isinstance(file_meta, types_.GitkeepMeta)  # nosec
            report = _migrate_gitkeep(gitkeep_meta=file_meta, docs_path=docs_path)
        case types_.DocumentMeta:
            assert isinstance(file_meta, types_.DocumentMeta)  # nosec
            report = _migrate_document(
                document_meta=file_meta, discourse=discourse, docs_path=docs_path
            )
        case types_.IndexDocumentMeta:
            assert isinstance(file_meta, types_.IndexDocumentMeta)  # nosec
            report = _migrate_index(index_meta=file_meta, docs_path=docs_path)
        # Edge case that should not be possible.
        case _:  # pragma: no cover
            raise exceptions.MigrationError(
                f"Internal error, no implementation for migration file, {file_meta=!r}"
            )

    logging.info("report: %s", report)
    return report


def _get_docs_metadata(
    table_rows: typing.Iterable[types_.TableRow], index_content: str
) -> itertools.chain[types_.MigrationFileMeta]:
    """Get metadata for all documents to be migrated.

    Args:
        table_rows: Table rows from the index table.
        index_content: Index content from index page.

    Returns:
        Metadata of files to be migrated.
    """
    index_doc = _index_file_from_content(content=index_content)
    table_docs = _extract_docs_from_table_rows(table_rows=table_rows)
    return itertools.chain((index_doc,), table_docs)


def run(
    table_rows: typing.Iterable[types_.TableRow],
    index_content: str,
    discourse: Discourse,
    docs_path: Path,
) -> None:
    """Write table contents to the document directory.

    Args:
        table_rows: Iterable sequence of documentation structure to be migrated.
        index_content: Main content describing the charm.
        discourse: Client to the documentation server.
        docs_path: The path to the docs directory containing all the documentation.

    Raises:
        MigrationError: if any migration report has failed.
    """
    valid_table_rows = _validate_table_rows(table_rows=table_rows)
    document_metadata = _get_docs_metadata(
        table_rows=valid_table_rows, index_content=index_content
    )
    migration_reports = (
        _run_one(file_meta=document, discourse=discourse, docs_path=docs_path)
        for document in document_metadata
    )

    if any(result for result in migration_reports if result.result is types_.ActionResult.FAIL):
        raise exceptions.MigrationError(
            "Error migrating the docs, please check the logs for more detail."
        )
