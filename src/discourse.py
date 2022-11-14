# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Interface for Discourse interactions."""

import os
import typing
from urllib import parse

import pydiscourse
import pydiscourse.exceptions

from .exceptions import DiscourseError, InputError


class _DiscourseTopicInfo(typing.NamedTuple):
    """Information about a discourse topic.

    Attrs:
        slug: The URL slug generated by Discourse based on the title of the topic.
        id: The identifier generated by Discourse of the topic.

    """

    slug: str
    id_: str


class _ValidationResultValid(typing.NamedTuple):
    """The validation result is valid.

    Attrs:
        value: The validation result, always True.
        message: The validation message, always None.

    """

    value: typing.Literal[True] = True
    message: None = None


class _ValidationResultInvalid(typing.NamedTuple):
    """The validation result is invalid.

    Attrs:
        value: The validation result, always False.
        message: The validation message as the reason the validation failed.

    """

    message: str
    value: typing.Literal[False] = False


_ValidationResult = _ValidationResultValid | _ValidationResultInvalid
KeyT = typing.TypeVar("KeyT")


class Discourse:
    """Interact with a discourse server."""

    tags = ("docs",)

    def __init__(self, base_path: str, api_username: str, api_key: str, category_id: int) -> None:
        """Constructor.

        Args:
            base_path: The HTTP protocol and hostname for discourse (e.g., https://discourse).
            api_username: The username to use for API requests.
            api_key: The API key for requests.
            category_id: The category identifier to put the topics into.

        """
        self._client = pydiscourse.DiscourseClient(
            host=base_path, api_username=api_username, api_key=api_key
        )
        self._category_id = category_id
        self._base_path = base_path

    def topic_url_valid(self, url: str) -> _ValidationResult:
        """Check whether a url to a topic is valid. Assume the url is well formatted.

        Validations:
            1. The URL must start with the base path configured during construction.
            2. The URL must have 3 components in its path.
            3. The first component in the path must be the literal 't'.
            4. The second component in the path must be the slug to the topic which must have at
                least 1 character.
            5. The third component must the the topic id as an integer.

        Args:
            url: The URL to check.

        Returns:
            Whether the URL is a valid topic URL.

        """
        if not url.startswith(self._base_path):
            return _ValidationResultInvalid(
                "The base path is different to the expected base path, "
                f"expected: {self._base_path}, {url=}"
            )

        parsed_url = parse.urlparse(url=url)
        # Remove trailing / and ignore first element which is always empty
        path_components = parsed_url.path.rstrip("/").split("/")[1:]

        if not len(path_components) == 3:
            return _ValidationResultInvalid(
                "Unexpected number of path components, "
                f"expected: 3, got: {len(path_components)}, {url=}"
            )

        if not path_components[0] == "t":
            return _ValidationResultInvalid(
                "Unexpected first path component, "
                f"expected: {'t'!r}, got: {path_components[0]!r}, {url=}"
            )

        if not path_components[1]:
            return _ValidationResultInvalid(
                f"Empty second path component topic slug, got: {path_components[1]!r}, {url=}"
            )

        if not path_components[2].isnumeric():
            return _ValidationResultInvalid(
                "unexpected third path component topic id, "
                "expected: a string that can be converted to an integer, "
                f"got: {path_components[2]!r}, {url=}"
            )

        return _ValidationResultValid()

    def _retrieve_topic_info_from_url(self, url: str) -> _DiscourseTopicInfo:
        """Retrieve the topic information from the url to the topic.

        Raises DiscourseError if the url is not valid.

        Args:
            url: The URL to the topic.

        Returns:
            The topic information.

        """
        result = self.topic_url_valid(url=url)
        if not result.value:
            raise DiscourseError(result.message)

        path_components = parse.urlparse(url=url).path.split("/")
        return _DiscourseTopicInfo(slug=path_components[-2], id_=path_components[-1])

    def _retrieve_topic_first_post(self, url: str) -> dict:
        """Retrieve the first post from a topic based on the URL to the topic.

        Raises DiscourseError is pydiscourse raises an error or if the topic has been deleted.

        Args:
            usl: The URL to the topic.

        Returns:
            The first post from the topic.

        """
        topic_info = self._retrieve_topic_info_from_url(url=url)
        try:
            topic = self._client.topic(slug=topic_info.slug, topic_id=topic_info.id_)
        except pydiscourse.exceptions.DiscourseError as discourse_error:
            raise DiscourseError(f"Error retrieving topic, {url=!r}") from discourse_error

        try:
            first_post = next(
                filter(lambda post: post["post_number"] == 1, topic["post_stream"]["posts"])
            )
        except (TypeError, KeyError, StopIteration) as exc:
            raise DiscourseError(
                f"The documentation server returned unexpected data, {topic=!r}"
            ) from exc

        # Check for deleted topic
        user_deleted = self._get_post_value(
            post=first_post, key="user_deleted", expected_type=bool
        )
        if user_deleted:
            raise DiscourseError(f"topic has been deleted, {url=}")

        return first_post

    @staticmethod
    def _get_post_value(post: dict, key: str, expected_type: typing.Type[KeyT]) -> KeyT:
        """Get a value by key from the first post checking the value is the correct type.

        Raises DiscourseError if the key is missing or is not of the correct type.

        Args:
            post: The first post to retrieve the value from.
            key: The key to the value.
            expected_type: The expected type of the value.

        Returns:
            The value pointed to by the key.

        """
        try:
            value = post[key]
            # It is ok for optimised code to ignore this
            assert isinstance(value, expected_type)  # nosec
            return value
        except (TypeError, KeyError, AssertionError) as exc:
            raise DiscourseError(
                f"The documentation server returned unexpected data, {post=!r}"
            ) from exc

    def check_topic_write_permission(self, url: str) -> bool:
        """Check whether the credentials have write permission on a topic.

        Raises DiscourseError if authentication fails or if the topic is not found.

        Args:
            url: The URL to the topic. Assume it includes the slug and id of the topic as the last
                2 elements of the url.

        Returns:
            Whether the credentials have write permissions to the topic.

        """
        first_post = self._retrieve_topic_first_post(url=url)
        return self._get_post_value(post=first_post, key="can_edit", expected_type=bool)

    def check_topic_read_permission(self, url: str) -> bool:
        """Check whether the credentials have read permission on a topic.

        Uses whether retrieve topic succeeds as indication whether the read permission is
        available.

        Raises DiscourseError if authentication fails or if the topic is not found.

        Args:
            url: The URL to the topic. Assume it includes the slug and id of the topic as the last
                2 elements of the url.

        Returns:
            Whether the credentials have read permissions to the topic.

        """
        self._retrieve_topic_first_post(url=url)
        return True

    def retrieve_topic(self, url: str) -> str:
        """Retrieve the topic content.

        Raises DiscourseError if authentication fails, if the server refuses to return the
        requested topic or if the topic is not found.

        Args:
            url: The URL to the topic. Assume it includes the slug and id of the topic as the last
                2 elements of the url.

        Returns:
            The content of the first post in the topic.

        """
        first_post = self._retrieve_topic_first_post(url=url)
        return self._get_post_value(post=first_post, key="cooked", expected_type=str)

    def create_topic(self, title: str, content: str) -> str:
        """Create a new topic.

        Raises DiscourseError if anything goes wrong during topic creation.

        Args:
            title: The title of the topic.
            content: The content for the first post in the topic.

        Returns:
            The URL to the topic.

        """
        try:
            post = self._client.create_post(
                title=title, category_id=self._category_id, tags=self.tags, content=content
            )
        except pydiscourse.exceptions.DiscourseError as discourse_error:
            raise DiscourseError(
                f"Error creating the topic, {title=!r}, {content=!r}"
            ) from discourse_error

        topic_slug = self._get_post_value(post=post, key="topic_slug", expected_type=str)
        topic_id = self._get_post_value(post=post, key="topic_id", expected_type=int)
        return f"{self._base_path}/t/{topic_slug}/{topic_id}"

    def delete_topic(self, url: str) -> None:
        """Delete a topic.

        Raises DiscourseError if authentication fails if the server refuses to delete the topic,
        if the topic is not found or if anything else has gone wrong.

        Args:
            url: The URL to the topic.

        """
        topic_info = self._retrieve_topic_info_from_url(url=url)
        try:
            self._client.delete_topic(topic_id=topic_info.id_)
        except pydiscourse.exceptions.DiscourseError as discourse_error:
            raise DiscourseError(f"Error deleting the topic, {url=!r}") from discourse_error

    def update_topic(
        self, url: str, content: str, edit_reason: str = "Charm documentation updated"
    ) -> None:
        """Update the first post of a topic.

        Raises DiscourseError if authentication fails, if the server refuses to update the first
        post in the topic or if the topic is not found.

        Args:
            url: The URL to the topic.
            content: The content for the first post in the topic.
            edit_reason: The reason the edit was made.

        """
        first_post = self._retrieve_topic_first_post(url=url)

        post_id = self._get_post_value(post=first_post, key="id", expected_type=int)
        try:
            self._client.update_post(post_id=post_id, content=content, edit_reason=edit_reason)
        except pydiscourse.exceptions.DiscourseError as discourse_error:
            raise DiscourseError(
                f"Error updating the topic, {url=!r}, {content=!r}"
            ) from discourse_error


def create_discourse(hostname: str, category_id: int) -> Discourse:
    """Create discourse client.

    Raises InputError if the DISCOURSE_API_USERNAME and DISCOURSE_API_KEY environment variables are
    not defined, if the protocol has been included in the hostname, the hostname is not a string or
    the category_id is not an integer.

    Args:
        hostname: The Discourse server hostname.

    Returns:
        A discourse client that is connected to the server.

    """
    if not isinstance(hostname, str):
        raise InputError(f"Invalid discourse_host input, it must be a string, got {hostname=!r}")
    if not hostname:
        raise InputError(f"Invalid discourse_host input, it must be non-empty, got {hostname=!r}")
    hostname = hostname.lower()
    if hostname.startswith("http://") or hostname.startswith("https://"):
        raise InputError(
            f"Invalid discourse_host input, it should not include the protocol, got {hostname=!r}"
        )

    if not isinstance(category_id, int):
        raise InputError(
            f"Invalid discourse_category_id input, it must be an integer, got {category_id=!r}"
        )

    api_username = os.getenv("DISCOURSE_API_USERNAME")
    if api_username is None:
        raise InputError(
            "The DISCOURSE_API_USERNAME is missing but is required to be able to interact with "
            "the documentation server"
        )
    api_key = os.getenv("DISCOURSE_API_KEY")
    if api_key is None:
        raise InputError(
            "The DISCOURSE_API_KEY is missing but is required to be able to interact with "
            "the documentation server"
        )

    return Discourse(
        base_path=f"https://{hostname}",
        api_username=api_username,
        api_key=api_key,
        category_id=category_id,
    )
