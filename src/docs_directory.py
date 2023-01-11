# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Class for reading the docs directory."""

import typing
from functools import partial
from itertools import count
from pathlib import Path

from . import types_
from .index import DOCUMENTATION_FOLDER_NAME


def _get_directories_files(docs_path: Path) -> list[Path]:
    """Get all the directories and documentation files recursively in the docs directory.

    Args:
        docs_path: The path to the docs directory containing all the documentation.

    Returns:
        List with all the directories and documentation files in the docs directory.
    """
    return sorted(
        path
        for path in docs_path.rglob("*")
        if path.is_dir() or (path.suffix.lower() == ".md" and not path.stem.lower() == "index")
    )


def _calculate_level(path_relative_to_docs: Path) -> types_.Level:
    """Calculate the level of a path.

    Args:
        path_relative_to_docs: The path to calculate the level for relative to the docs
            directory.

    Returns:
        The number of sub-directories from the path to the docs directory including the docs
        directory.
    """
    return len(path_relative_to_docs.parents)


def calculate_table_path(path_relative_to_docs: Path) -> types_.TablePath:
    """Calculate the table path of a path.

    Args:
        path_relative_to_docs: The path to calculate the table path for relative to the docs
            directory.

    Returns:
        The relative path to the docs directory, replacing / with -, removing the extension and
        converting to lower case.
    """
    return (
        "-".join(part for part in path_relative_to_docs.parts)
        .removesuffix(path_relative_to_docs.suffix)
        .lower()
        .replace(" ", "-")
        .replace("_", "-")
    )


def _calculate_navlink_title(path: Path) -> types_.NavlinkTitle:
    """Calculate the navlink title of a path.

    Args:
        path: The path to calculate the navlink title for.

    Returns:
        The first heading, first line if there is no heading or the file/ directory name excluding
        the extension with - replaced by space and titlelized if the file is empty or it is a
        directory.
    """
    # Check for file with content
    if path.is_file() and path.stat().st_size:
        content_lines = path.read_text(encoding="utf-8").splitlines()
        heading_start = "# "
        try:
            return next(
                line.removeprefix(heading_start)
                for line in content_lines
                if line.startswith(heading_start)
            )
        except StopIteration:
            return content_lines[0]

    return path.stem.replace("-", " ").replace("_", " ").title()


def _get_path_info(path: Path, alphabetical_rank: int, docs_path: Path) -> types_.PathInfo:
    """Get the information for a path.

    Args:
        path: The path to calculate the information for.
        alphabetical_rank: The rank to assign to the path info.
        docs_path: The path to the docs directory.

    Returns:
        The information for the path.
    """
    path_relative_to_docs = path.relative_to(docs_path)
    return types_.PathInfo(
        local_path=path,
        level=_calculate_level(path_relative_to_docs=path_relative_to_docs),
        table_path=calculate_table_path(path_relative_to_docs=path_relative_to_docs),
        navlink_title=_calculate_navlink_title(path=path),
        alphabetical_rank=alphabetical_rank,
    )


def read(docs_path: Path) -> typing.Iterator[types_.PathInfo]:
    """Read the docs directory and return information about each directory and documentation file.

    Algorithm:
        1.  Get a list of all sub directories and .md files in the docs folder.
        2.  For each directory/ file:
            2.1. Calculate the level based on the number of sub-directories to the docs directory
                including the docs directory.
            2.2. Calculate the table path using the relative path to the docs directory, replacing
                / with -, removing the extension and converting to lower case.
            2.3. Calculate the navlink title based on the first heading, first line if there is no
                heading or the file/ directory name excluding the extension with - replaced by
                space and titlelized if the file is empty or it is a directory.

    Args:
        docs_path: The path to the docs directory containing all the documentation.

    Returns:
        Information about each directory and documentation file in the docs folder.
    """
    return map(
        partial(_get_path_info, docs_path=docs_path),
        _get_directories_files(docs_path=docs_path),
        count(),
    )


def has_docs_directory(base_path: Path) -> bool:
    """Return existence of docs directory from base path.

    Args:
        base_path: Base path of the repository to search the docs directory from

    Returns:
        True if documentation folder exists, False otherwise
    """
    return (base_path / DOCUMENTATION_FOLDER_NAME).is_dir()
