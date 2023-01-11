#!/usr/bin/env python

# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Main execution for the action."""

import json
import logging
import os
import pathlib
from functools import partial

from src import GETTING_STARTED, exceptions, run, types_
from src.discourse import create_discourse


def _parse_env_vars() -> types_.UserInputs:
    """Instantiate user inputs from environment variables.

    Returns:
        Wrapped user input variables.
    """
    discourse_host = os.getenv("INPUT_DISCOURSE_HOST", "")
    discourse_category_id = os.getenv("INPUT_DISCOURSE_CATEGORY_ID", "")
    discourse_api_username = os.getenv("INPUT_DISCOURSE_API_USERNAME", "")
    discourse_api_key = os.getenv("INPUT_DISCOURSE_API_KEY", "")
    delete_topics = os.getenv("INPUT_DELETE_TOPICS") == "true"
    dry_run = os.getenv("INPUT_DRY_RUN") == "true"
    github_access_token = os.getenv("INPUT_GITHUB_TOKEN")

    return types_.UserInputs(
        discourse_hostname=discourse_host,
        discourse_category_id=discourse_category_id,
        discourse_api_username=discourse_api_username,
        discourse_api_key=discourse_api_key,
        delete_pages=delete_topics,
        dry_run=dry_run,
        github_access_token=github_access_token,
    )


def _write_github_output(
    urls_with_actions_dict: dict[str, str], user_inputs: types_.UserInputs
) -> None:
    """Writes results produced by the action to github_output.

    Args:
        urls_with_actions_dict: key value pairs of link to result of action.
        user_inputs: parsed input variables used to run the action.

    Raises:
        InputError: if not running inside a github actions environment.
    """
    github_output = os.getenv("GITHUB_OUTPUT")
    if not github_output:
        raise exceptions.InputError(
            f"Invalid 'GITHUB_OUTPUT' input, it must be non-empty, got {github_output=!r}"
            f"This action is intended to run inside github-actions. {GETTING_STARTED}"
        )

    github_output_path = pathlib.Path(github_output)
    compact_json = partial(json.dumps, separators=(",", ":"))
    urls_with_actions = compact_json(urls_with_actions_dict)
    if urls_with_actions_dict:
        *_, index_url = urls_with_actions_dict.keys()
    else:
        index_url = ""
    discourse_config = compact_json(
        {
            "hostname": user_inputs.discourse_hostname,
            "category_id": user_inputs.discourse_category_id,
            "api_username": user_inputs.discourse_api_username,
            "api_key": user_inputs.discourse_api_key,
        }
    )
    github_output_path.write_text(
        f"urls_with_actions={urls_with_actions}\n"
        f"index_url={index_url}\n"
        f"discourse_config={discourse_config}\n",
        encoding="utf-8",
    )


def main() -> None:
    """Execute the action."""
    logging.basicConfig(level=logging.INFO)

    # Read input
    user_inputs = _parse_env_vars()

    # Execute action
    discourse = create_discourse(
        hostname=user_inputs.discourse_hostname,
        category_id=user_inputs.discourse_category_id,
        api_username=user_inputs.discourse_api_username,
        api_key=user_inputs.discourse_api_key,
    )
    urls_with_actions_dict = run(
        base_path=pathlib.Path(),
        discourse=discourse,
        user_inputs=user_inputs,
    )

    # Write output
    _write_github_output(urls_with_actions_dict=urls_with_actions_dict, user_inputs=user_inputs)


if __name__ == "__main__":
    main()
