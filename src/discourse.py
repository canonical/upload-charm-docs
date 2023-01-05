# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Interface for Discourse interactions."""

import typing
from urllib import parse

import pydiscourse
import pydiscourse.exceptions
import requests
from requests.adapters import HTTPAdapter
from urllib3 import Retry

from .exceptions import DiscourseError, InputError

_URL_PATH_PREFIX = "/t/"


class _DiscourseTopicInfo(typing.NamedTuple):
    """Information about a discourse topic.

    Attrs:
        slug: The URL slug generated by Discourse based on the title of the topic.
        id: The identifier generated by Discourse of the topic.

    """

    slug: str
    id_: int


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
        """Construct.

        Args:
            base_path: The HTTP protocol and hostname for discourse (e.g., https://discourse).
            api_username: The username to use for API requests.
            api_key: The API key for requests.
            category_id: The category identifier to put the topics into.

        """
        self._client = pydiscourse.DiscourseClient(
            host=base_path, api_username=api_username, api_key=api_key, timeout=10 * 60
        )
        self._category_id = category_id
        self._base_path = base_path
        self._api_username = api_username
        self._api_key = api_key

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
        if not url.startswith((self._base_path, _URL_PATH_PREFIX)):
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

    def _url_to_topic_info(self, url: str) -> _DiscourseTopicInfo:
        """Retrieve the topic information from the url to the topic.

        Args:
            url: The URL to the topic.

        Returns:
            The topic information.

        Raises:
            DiscourseError: if the url is not valid.

        """
        result = self.topic_url_valid(url=url)
        if not result.value:
            raise DiscourseError(result.message)

        path_components = parse.urlparse(url=url).path.split("/")
        return _DiscourseTopicInfo(slug=path_components[-2], id_=int(path_components[-1]))

    def _topic_info_to_absolute_url(self, topic_info: _DiscourseTopicInfo) -> str:
        """Retrieve the url from the topic information.

        Args:
            url: The topic information.

        Returns:
            The URL to the topic.

        """
        return f"{self._base_path}{_URL_PATH_PREFIX}{topic_info.slug}/{topic_info.id_}"

    def _ensure_topic_default_config(
        self, topic: dict, topic_info: _DiscourseTopicInfo, url: str
    ) -> None:
        """Check the topic configuration and apply defaults if not already applied.

        Args:
            topic: The pydiscourse dictionary representing the topic.
            topic_info: The information about the topic.
            url: The URL to the topic, used for the error message.
        """
        visible = self._get_record_value(record=topic, key="visible", expected_type=bool)
        if visible:
            try:
                self._client.update_topic_status(
                    topic_id=topic_info.id_, status="visible", enabled=False
                )
            except pydiscourse.exceptions.DiscourseError as discourse_error:
                raise DiscourseError(
                    f"Error updating topic configuration, {url=!r}, {discourse_error=}"
                ) from discourse_error

    def _retrieve_topic(self, topic_info: _DiscourseTopicInfo, url: str) -> dict:
        """Retrieve the topic based on the information about the topic.

        Args:
            topic_info: The information about the topic.
            url: The URL to the topic, used for the error message.

        Returns:
            The the topic.

        Raises:
            DiscourseError: if pydiscourse raises an error or if it returns invalid data.

        """
        try:
            topic = self._client.topic(
                slug=topic_info.slug,
                topic_id=topic_info.id_,
                override_request_kwargs={"allow_redirects": True},
            )
        except pydiscourse.exceptions.DiscourseError as discourse_error:
            raise DiscourseError(
                f"Error retrieving topic, {url=!r}, {discourse_error=}"
            ) from discourse_error

        if not isinstance(topic, dict):
            raise DiscourseError(
                "Error retrieving topic, the documentation server returned unexpected data, "
                f"{url=!r}, {topic=}"
            )

        return topic

    def _get_topic_first_post(self, topic: dict, url: str) -> dict:
        """Get the first post from a topic.

        Args:
            topic: The topic information.
            url: The URL to the topic, used for the error message.

        Returns:
            The first post from the topic.

        Raises:
            DiscourseError: if the topic has been deleted.

        """
        try:
            first_post = next(
                filter(lambda post: post["post_number"] == 1, topic["post_stream"]["posts"])
            )
        except (TypeError, KeyError, StopIteration) as exc:
            raise DiscourseError(
                f"The documentation server returned unexpected data, {topic=!r}"
            ) from exc

        # Check for deleted topic
        user_deleted = self._get_record_value(
            record=first_post, key="user_deleted", expected_type=bool
        )
        if user_deleted:
            raise DiscourseError(f"topic has been deleted, {url=}")

        return first_post

    def _retrieve_topic_first_post(self, url: str) -> dict:
        """Retrieve the first post from a topic based on the URL to the topic.

        Args:
            url: The URL to the topic.

        Returns:
            The first post from the topic.

        Raises:
            DiscourseError: if pydiscourse raises an error or if the topic has been deleted.

        """
        topic_info = self._url_to_topic_info(url=url)
        topic = self._retrieve_topic(topic_info=topic_info, url=url)
        return self._get_topic_first_post(topic=topic, url=url)

    @staticmethod
    def _get_record_value(record: dict, key: str, expected_type: type[KeyT]) -> KeyT:
        """Get a value by key from the record checking the value is the correct type.

        Args:
            record: The record to retrieve the value from.
            key: The key to the value.
            expected_type: The expected type of the value.

        Returns:
            The value pointed to by the key.

        Raises:
            DiscourseError: if the key is missing or is not of the correct type.

        """
        try:
            value = record[key]
            # It is ok for optimised code to ignore this
            assert isinstance(value, expected_type)  # nosec
            return value
        except (TypeError, KeyError, AssertionError) as exc:
            raise DiscourseError(
                f"The documentation server returned unexpected data, {record=!r}"
            ) from exc

    def absolute_url(self, url: str) -> str:
        """Get the URL including base path for a topic.

        Args:
            url: The relative or absolute URL.

        Returns:
            The url with the base path.
        """
        topic_info = self._url_to_topic_info(url=url)
        return self._topic_info_to_absolute_url(topic_info=topic_info)

    def check_topic_write_permission(self, url: str) -> bool:
        """Check whether the credentials have write permission on a topic.

        Args:
            url: The URL to the topic. Assume it includes the slug and id of the topic as the last
                2 elements of the url.

        Returns:
            Whether the credentials have write permissions to the topic.

        Raises:
            DiscourseError: if authentication fails or if the topic is not found.

        """
        first_post = self._retrieve_topic_first_post(url=url)
        return self._get_record_value(record=first_post, key="can_edit", expected_type=bool)

    def check_topic_read_permission(self, url: str) -> bool:
        """Check whether the credentials have read permission on a topic.

        Uses whether retrieve topic succeeds as indication whether the read permission is
        available.

        Args:
            url: The URL to the topic. Assume it includes the slug and id of the topic as the last
                2 elements of the url.

        Returns:
            Whether the credentials have read permissions to the topic.

        Raises:
            DiscourseError: if authentication fails or if the topic is not found.

        """
        self._retrieve_topic_first_post(url=url)
        return True

    # Tested in integration tests
    @staticmethod
    def _get_requests_session() -> requests.Session:  # pragma: no cover
        """Get a requests session.

        Returns:
            A session with retries enabled.
        """
        session = requests.Session()
        adapter = HTTPAdapter(
            max_retries=Retry(
                total=5,
                backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504],
            )
        )
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def retrieve_topic(self, url: str) -> str:
        """Retrieve the topic content.

        Args:
            url: The URL to the topic. Assume it includes the slug and id of the topic as the last
                2 elements of the url.

        Returns:
            The content of the first post in the topic.

        Raises:
            DiscourseError: if authentication fails, if the server refuses to return the requested
                topic or if the topic is not found.

        """
        # Check for any read issues
        if not self.check_topic_read_permission(url=url):
            raise DiscourseError(f"Error retrieving the topic, could not read the topic, {url=!r}")

        topic_info = self._url_to_topic_info(url=url)
        headers = {"Api-Key": self._api_key, "Api-Username": self._api_username}
        response = self._get_requests_session().get(
            f"{self._base_path}/raw/{topic_info.id_}", headers=headers, timeout=60
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise DiscourseError(f"Error retrieving the topic, {url=!r}") from exc

        return response.content.decode("utf-8")

    def create_topic(self, title: str, content: str) -> str:
        """Create a new topic.

        Args:
            title: The title of the topic.
            content: The content for the first post in the topic.

        Returns:
            The URL to the topic.

        Raises:
            DiscourseError: if anything goes wrong during topic creation.

        """
        try:
            post = self._client.create_post(
                title=title,
                category_id=self._category_id,
                tags=self.tags,
                content=content,
                unlist_topic=True,
            )
        except pydiscourse.exceptions.DiscourseError as discourse_error:
            raise DiscourseError(
                f"Error creating the topic, {title=!r}, {content=!r}, {discourse_error=}"
            ) from discourse_error

        if not isinstance(post, dict):
            raise DiscourseError(
                "Error creating topic, the documentation server returned unexpected data, "
                f"{title=!r}, {content=!r}, {post=}"
            )

        topic_slug = self._get_record_value(record=post, key="topic_slug", expected_type=str)
        topic_id = self._get_record_value(record=post, key="topic_id", expected_type=int)
        return self._topic_info_to_absolute_url(_DiscourseTopicInfo(slug=topic_slug, id_=topic_id))

    def delete_topic(self, url: str) -> str:
        """Delete a topic.

        Args:
            url: The URL to the topic.

        Raises:
            DiscourseError: if authentication fails if the server refuses to delete the topic, if
                the topic is not found or if anything else has gone wrong.

        """
        topic_info = self._url_to_topic_info(url=url)
        try:
            self._client.delete_topic(topic_id=topic_info.id_)
        except pydiscourse.exceptions.DiscourseError as discourse_error:
            raise DiscourseError(
                f"Error deleting the topic, {url=!r}, {discourse_error=}"
            ) from discourse_error
        return self._topic_info_to_absolute_url(topic_info)

    def update_topic(
        self, url: str, content: str, edit_reason: str = "Charm documentation updated"
    ) -> str:
        """Update the first post of a topic.

        Args:
            url: The URL to the topic.
            content: The content for the first post in the topic.
            edit_reason: The reason the edit was made.

        Raises:
            DiscourseError: if authentication fails, if the server refuses to update the first post
                in the topic or if the topic is not found.

        """
        topic_info = self._url_to_topic_info(url=url)
        topic = self._retrieve_topic(topic_info=topic_info, url=url)
        self._ensure_topic_default_config(topic=topic, topic_info=topic_info, url=url)
        first_post = self._get_topic_first_post(topic=topic, url=url)

        post_id = self._get_record_value(record=first_post, key="id", expected_type=int)
        try:
            self._client.update_post(post_id=post_id, content=content, edit_reason=edit_reason)
        except pydiscourse.exceptions.DiscourseError as discourse_error:
            raise DiscourseError(
                f"Error updating the topic, {url=!r}, {content=!r}, {discourse_error=}"
            ) from discourse_error

        return self.absolute_url(url=url)


def create_discourse(
    hostname: typing.Any, category_id: typing.Any, api_username: typing.Any, api_key: typing.Any
) -> Discourse:
    """Create discourse client.

    Args:
        hostname: The Discourse server hostname.
        category_id: The category to use for topics.
        api_username: The discourse API username to use for interactions with the server.
        api_key: The discourse API key to use for interactions with the server.

    Returns:
        A discourse client that is connected to the server.

    Raises:
    InputError: if the api_username and api_key arguments are not strings or empty, if the
        protocol has been included in the hostname, the hostname is not a string or the category_id
        is not an integer or a string that can be converted to an integer.

    """
    if not isinstance(hostname, str):
        raise InputError(f"Invalid 'discourse_host' input, it must be a string, got {hostname=!r}")
    if not hostname:
        raise InputError(
            f"Invalid 'discourse_host' input, it must be non-empty, got {hostname=!r}"
        )
    hostname = hostname.lower()
    if hostname.startswith(("http://", "https://")):
        raise InputError(
            "Invalid 'discourse_host' input, it should not include the protocol, "
            f"got {hostname=!r}"
        )

    if not isinstance(category_id, int) and not (
        isinstance(category_id, str) and category_id.isdigit()
    ):
        raise InputError(
            "Invalid 'discourse_category_id' input, it must be an integer or a string that can be "
            f"converted to an integer, got {category_id=!r}"
        )
    if isinstance(category_id, str):
        category_id_int = int(category_id)
    else:
        category_id_int = category_id

    if not isinstance(api_username, str):
        raise InputError(
            f"Invalid 'discourse_api_username' input, it must be a string, got {api_username=!r}"
        )
    if not api_username:
        raise InputError(
            f"Invalid 'discourse_api_username' input, it must be non-empty, got {api_username=!r}"
        )

    if not isinstance(api_key, str):
        raise InputError(
            f"Invalid 'discourse_api_key' input, it must be a string, got {api_key=!r}"
        )
    if not api_key:
        raise InputError(
            f"Invalid 'discourse_api_key' input, it must be non-empty, got {api_key=!r}"
        )

    return Discourse(
        base_path=f"https://{hostname}",
        api_username=api_username,
        api_key=api_key,
        category_id=category_id_int,
    )
