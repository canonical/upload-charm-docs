#!/usr/bin/env python

# # Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Cleanup and checking utility after running the action, primarily for testing purposes."""

import argparse
import contextlib
import json
import logging
import sys
from enum import Enum

from src.discourse import Discourse, create_discourse
from src.exceptions import DiscourseError


class Action(str, Enum):
    """The actions the utility can take.

    Attrs:
        CHECK_DRAFT: Check that the draft integration test succeeded.
        CHECK_CREATE: Check that the create integration test succeeded.
        CHECK_DELETE_TOPICS: Check that the delete_topics integration test succeeded.
        CHECK_DELETE: Check that the delete integration test succeeded.
        CLEANUP: Discourse cleanup after the testing.
    """

    CHECK_DRAFT = "check-draft"
    CHECK_CREATE = "check-create"
    CHECK_DELETE_TOPICS = "check-delete-topics"
    CHECK_DELETE = "check-delete"
    CLEANUP = "cleanup"


def main() -> None:
    """Clean up created Discourse pages.

    Raises:
        NotImplementedError: if an action was received for which there is no imlpementation.
    """
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(
        prog="DiscourseCleanup",
        description="Delete posts created on discourse during an action execution.",
    )
    parser.add_argument("urls_with_actions", help="The pages that were created during execution")
    parser.add_argument(
        "discourse_config", help="The discourse configuration used to create the pages"
    )
    parser.add_argument(
        "--action", help="Action to run", choices=tuple(action.value for action in Action)
    )
    parser.add_argument(
        "--action-kwargs", help="Arguments for the action as a JSON mapping", default="{}"
    )
    args = parser.parse_args()
    urls_with_actions = json.loads(args.urls_with_actions)
    discourse_config = json.loads(args.discourse_config)
    action_kwargs = json.loads(args.action_kwargs)

    discourse = create_discourse(**discourse_config)

    match args.action:
        case Action.CHECK_DRAFT.value:
            _exit_with_result(check_draft(urls_with_actions=urls_with_actions, **action_kwargs))
        case Action.CHECK_CREATE.value:
            _exit_with_result(
                check_create(
                    urls_with_actions=urls_with_actions, discourse=discourse, **action_kwargs
                )
            )
        case Action.CHECK_DELETE_TOPICS.value:
            _exit_with_result(
                check_delete_topics(
                    urls_with_actions=urls_with_actions, discourse=discourse, **action_kwargs
                )
            )
        case Action.CHECK_DELETE.value:
            _exit_with_result(
                check_delete(
                    urls_with_actions=urls_with_actions, discourse=discourse, **action_kwargs
                )
            )
        case Action.CLEANUP.value:
            cleanup(urls_with_actions=urls_with_actions, discourse=discourse, **action_kwargs)
            sys.exit(0)
        case _:
            raise NotImplementedError(f"{args.action} has not been implemented")


def _exit_with_result(check_result: bool) -> None:
    """Exit and set exit code based on the check result.

    Args:
        check_result: The outcome of a check.
    """
    sys.exit(0 if check_result else 1)


def _check_url_count(
    urls_with_actions: dict[str, str], expected_count: int, test_name: str
) -> bool:
    """Perform the check for the number of URLs.

    Success is if the number of urls in urls_with_actions matches the expected count.

    Args:
        urls_with_actions: The URLs that had any actions against them.
        expected_count: The expected number of URLs.
        test_name: The name of the test to include in the logging message.

    Returns:
        Whether the test succeeded.
    """
    if (url_count := len(urls_with_actions)) != expected_count:
        logging.error(
            "%s check failed, expected %s URLs with actions, got %s, urls_with_actions=%s",
            test_name,
            expected_count,
            url_count,
            urls_with_actions,
        )
        return False
    return True


def _check_url_retrieve(
    urls_with_actions: dict[str, str], discourse: Discourse, test_name: str
) -> bool:
    """Check that retrieving the URL succeeds.

    Args:
        urls_with_actions: The URLs that had any actions against them.
        discourse: Client to the documentation server.
        test_name: The name of the test to include in the logging message.

    Returns:
        Whether the test succeeded.
    """
    for url in urls_with_actions.keys():
        try:
            discourse.retrieve_topic(url=url)
        except DiscourseError as exc:
            logging.error(
                "%s check failed, URL retrieval failed for %s, error: %s, urls_with_actions=%s",
                test_name,
                url,
                exc,
                urls_with_actions,
            )
            return False
    return True


def _check_url_result(
    urls_with_actions: dict[str, str], expected_result: list[str], test_name: str
) -> bool:
    """Check the results for the URLs.

    Args:
        urls_with_actions: The URLs that had any actions against them.
        expected_result: The expected results.
        test_name: The name of the test to include in the logging message.

    Returns:
        Whether the test succeeded.
    """
    if sorted(results := urls_with_actions.values()) != sorted(expected_result):
        logging.error(
            "%s check failed, the result is not as expected, "
            "expected: %s, got: %s, urls_with_actions=%s",
            test_name,
            results,
            expected_result,
            urls_with_actions,
        )
        return False
    return True


def check_draft(urls_with_actions: dict[str, str], expected_url_results: list[str]) -> bool:
    """Check that the draft test succeeded.

    Success is indicated by that there are the expected number of URLs in urls_with_actions.

    Args:
        urls_with_actions: The URLs that had any actions against them.
        expected_url_results: The expected url results.

    Returns:
        Whether the test succeeded.
    """
    test_name = "draft"
    if not _check_url_count(
        urls_with_actions=urls_with_actions,
        expected_count=len(expected_url_results),
        test_name=test_name,
    ):
        return False

    logging.info("%s check succeeded", test_name)
    return True


def check_create(
    urls_with_actions: dict[str, str], discourse: Discourse, expected_url_results: list[str]
) -> bool:
    """Check that the create test succeeded.

    Success is indicated by that there are the expected number of URLs with the expected result and
    that retrieving the URLs succeeds.

    Args:
        urls_with_actions: The URLs that had any actions against them.
        discourse: Client to the documentation server.
        expected_url_results: The expected url results.

    Returns:
        Whether the test succeeded.
    """
    test_name = "create"
    if not _check_url_count(
        urls_with_actions=urls_with_actions,
        expected_count=len(expected_url_results),
        test_name=test_name,
    ):
        return False

    if not _check_url_result(
        urls_with_actions=urls_with_actions,
        expected_result=expected_url_results,
        test_name=test_name,
    ):
        return False

    if not _check_url_retrieve(
        urls_with_actions=urls_with_actions, discourse=discourse, test_name=test_name
    ):
        return False

    logging.info("%s check succeeded", test_name)
    return True


def check_delete_topics(
    urls_with_actions: dict[str, str], discourse: Discourse, expected_url_results: list[str]
) -> bool:
    """Check that the delete_topics test succeeded.

    Success is indicated by that there are the expected number of URLs and results in
    urls_with_actions and that retrieving the URLs succeeds (none have been deleted).

    Args:
        urls_with_actions: The URLs that had any actions against them.
        discourse: Client to the documentation server.
        expected_url_results: The expected url results.

    Returns:
        Whether the test succeeded.
    """
    test_name = "delete_topics"
    if not _check_url_count(
        urls_with_actions=urls_with_actions,
        expected_count=len(expected_url_results),
        test_name=test_name,
    ):
        return False

    if not _check_url_result(
        urls_with_actions=urls_with_actions,
        expected_result=expected_url_results,
        test_name=test_name,
    ):
        return False

    if not _check_url_retrieve(
        urls_with_actions=urls_with_actions, discourse=discourse, test_name=test_name
    ):
        return False

    logging.info("%s check succeeded", test_name)
    return True


def check_delete(
    urls_with_actions: dict[str, str], discourse: Discourse, expected_url_results: list[str]
) -> bool:
    """Check that the delete test succeeded.

    Success is indicated by that there are the expected number of URLs in urls_with_actions with a
    success result and that retrieving the first URL fails and the second succeeds.

    Args:
        urls_with_actions: The URLs that had any actions against them.
        discourse: Client to the documentation server.
        expected_url_results: The expected url results.

    Returns:
        Whether the test succeeded.
    """
    test_name = "delete"
    if not _check_url_count(
        urls_with_actions=urls_with_actions,
        expected_count=len(expected_url_results),
        test_name=test_name,
    ):
        return False

    if not _check_url_result(
        urls_with_actions=urls_with_actions,
        expected_result=expected_url_results,
        test_name=test_name,
    ):
        return False

    urls = tuple(urls_with_actions.keys())
    if not _check_url_retrieve(
        urls_with_actions={urls[1]: urls_with_actions[urls[1]]},
        discourse=discourse,
        test_name=test_name,
    ):
        return False

    with contextlib.suppress(DiscourseError):
        discourse.retrieve_topic(url=urls[0])
        logging.error(
            "%s check failed, topic not deleted, url: %s, urls_with_actions=%s",
            test_name,
            urls[0],
            urls_with_actions,
        )
        return False

    logging.info("%s check succeeded", test_name)
    return True


def cleanup(urls_with_actions: dict[str, str], discourse: Discourse) -> None:
    """Delete all URLs.

    Args:
        urls_with_actions: The URLs that had any actions against them.
        discourse: Client to the documentation server.
    """
    for url in urls_with_actions.keys():
        with contextlib.suppress(DiscourseError):
            discourse.delete_topic(url=url)


if __name__ == "__main__":
    main()
