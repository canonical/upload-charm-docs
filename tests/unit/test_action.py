# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for action."""

# Need access to protected functions for testing
# pylint: disable=protected-access

import logging
from unittest import mock

import pytest

from src import action, discourse, types_, exceptions


@pytest.mark.parametrize(
    "draft_mode",
    [pytest.param(True, id="draft mode enabled"), pytest.param(False, id="draft mode disabled")],
)
def test__create_directory(draft_mode: bool, caplog: pytest.LogCaptureFixture):
    """
    arrange: given create action for a directory, draft mode and mocked discourse
    act: wnen action is passed to _create with draft_mode
    assert: then no topic is created, the action is logged and the expected table row is returned.
    """
    caplog.set_level(logging.INFO)
    mocked_discourse = mock.MagicMock(spec=discourse.Discourse)
    level = 1
    path = "path 1"
    navlink_title = "title 1"
    create_action = types_.CreateAction(
        action=types_.Action.CREATE,
        level=level,
        path=path,
        navlink_title=navlink_title,
        content=None,
    )

    returned_table_row = action._create(
        action=create_action, discourse=mocked_discourse, draft_mode=draft_mode
    )

    assert str(create_action) in caplog.text
    assert f"draft mode: {draft_mode}" in caplog.text
    mocked_discourse.create_topic.assert_not_called()
    assert returned_table_row.level == level
    assert returned_table_row.path == path
    assert returned_table_row.navlink.title == navlink_title
    assert returned_table_row.navlink.link is None


def test__create_file_draft_mode(caplog: pytest.LogCaptureFixture):
    """
    arrange: given create action for a file and mocked discourse
    act: wnen action is passed to _create with draft_mode True
    assert: then no topic is created, the action is logged and the expected table row is returned.
    """
    caplog.set_level(logging.INFO)
    mocked_discourse = mock.MagicMock(spec=discourse.Discourse)
    level = 1
    path = "path 1"
    navlink_title = "title 1"
    create_action = types_.CreateAction(
        action=types_.Action.CREATE,
        level=level,
        path=path,
        navlink_title=navlink_title,
        content="content 1",
    )

    returned_table_row = action._create(
        action=create_action, discourse=mocked_discourse, draft_mode=True
    )

    assert str(create_action) in caplog.text
    assert f"draft mode: {True}" in caplog.text
    mocked_discourse.create_topic.assert_not_called()
    assert returned_table_row.level == level
    assert returned_table_row.path == path
    assert returned_table_row.navlink.title == navlink_title
    assert returned_table_row.navlink.link == action.DRAFT_NAVLINK_LINK


def test__create_file(caplog: pytest.LogCaptureFixture):
    """
    arrange: given create action for a file and mocked discourse
    act: wnen action is passed to _create with draft_mode False
    assert: then no topic is created, the action is logged and the expected table row is returned.
    """
    caplog.set_level(logging.INFO)
    mocked_discourse = mock.MagicMock(spec=discourse.Discourse)
    url = "url 1"
    mocked_discourse.create_topic.return_value = url
    level = 1
    path = "path 1"
    navlink_title = "title 1"
    content = "content 1"
    create_action = types_.CreateAction(
        action=types_.Action.CREATE,
        level=level,
        path=path,
        navlink_title=navlink_title,
        content=content,
    )

    returned_table_row = action._create(
        action=create_action, discourse=mocked_discourse, draft_mode=False
    )

    assert str(create_action) in caplog.text
    assert f"draft mode: {False}" in caplog.text
    mocked_discourse.create_topic.assert_called_once_with(title=navlink_title, content=content)
    assert returned_table_row.level == level
    assert returned_table_row.path == path
    assert returned_table_row.navlink.title == navlink_title
    assert returned_table_row.navlink.link == url


@pytest.mark.parametrize(
    "noop_action, expected_table_row",
    [
        pytest.param(
            types_.NoopAction(
                action=types_.Action.NOOP,
                level=(level := 1),
                path=(path := "path 1"),
                navlink=(navlink := types_.Navlink(title="title 1", link=None)),
                content=None,
            ),
            types_.TableRow(level=level, path=path, navlink=navlink),
            id="directory",
        ),
        pytest.param(
            types_.NoopAction(
                action=types_.Action.NOOP,
                level=(level := 1),
                path=(path := "path 1"),
                navlink=(navlink := types_.Navlink(title="title 1", link="link 1")),
                content="content 1",
            ),
            types_.TableRow(level=level, path=path, navlink=navlink),
            id="file",
        ),
    ],
)
def test__noop(
    noop_action: types_.NoopAction,
    expected_table_row: types_.TableRow,
    caplog: pytest.LogCaptureFixture,
):
    """
    arrange: given noop action
    act: wnen action is passed to _noop
    assert: then the action is logged and the expected table row is returned.
    """
    caplog.set_level(logging.INFO)

    returned_table_row = action._noop(action=noop_action)

    assert str(noop_action) in caplog.text
    assert returned_table_row == expected_table_row


@pytest.mark.parametrize(
    "draft_mode",
    [pytest.param(True, id="draft mode enabled"), pytest.param(False, id="draft mode disabled")],
)
def test__update_directory(draft_mode: bool, caplog: pytest.LogCaptureFixture):
    """
    arrange: given update action for a directory, draft mode and mocked discourse
    act: wnen action is passed to _update with draft_mode
    assert: then no topic is updated, the action is logged and the expected table row is returned.
    """
    caplog.set_level(logging.INFO)
    mocked_discourse = mock.MagicMock(spec=discourse.Discourse)
    level = 1
    path = "path 1"
    update_action = types_.UpdateAction(
        action=types_.Action.UPDATE,
        level=level,
        path=path,
        navlink_change=types_.NavlinkChange(
            old=types_.Navlink(title="title 1", link=None),
            new=types_.Navlink(title="title 2", link=None),
        ),
        content_change=types_.ContentChange(old=None, new=None),
    )

    returned_table_row = action._update(
        action=update_action, discourse=mocked_discourse, draft_mode=draft_mode
    )

    assert str(update_action) in caplog.text
    assert f"draft mode: {draft_mode}" in caplog.text
    mocked_discourse.update_topic.assert_not_called()
    assert returned_table_row.level == level
    assert returned_table_row.path == path
    assert returned_table_row.navlink == update_action.navlink_change.new


def test__update_file_draft_mode(caplog: pytest.LogCaptureFixture):
    """
    arrange: given update action for a file and mocked discourse
    act: wnen action is passed to _update with draft_mode True
    assert: then no topic is updated, the action is logged and the expected table row is returned.
    """
    caplog.set_level(logging.INFO)
    mocked_discourse = mock.MagicMock(spec=discourse.Discourse)
    level = 1
    path = "path 1"
    update_action = types_.UpdateAction(
        action=types_.Action.UPDATE,
        level=level,
        path=path,
        navlink_change=types_.NavlinkChange(
            old=types_.Navlink(title="title 1", link="link 1"),
            new=types_.Navlink(title="title 2", link="link 2"),
        ),
        content_change=types_.ContentChange(old="content 1", new="content 2"),
    )

    returned_table_row = action._update(
        action=update_action, discourse=mocked_discourse, draft_mode=True
    )

    assert str(update_action) in caplog.text
    assert f"draft mode: {True}" in caplog.text
    mocked_discourse.update_topic.assert_not_called()
    assert returned_table_row.level == level
    assert returned_table_row.path == path
    assert returned_table_row.navlink == update_action.navlink_change.new


def test__update_file_navlink_title_change(caplog: pytest.LogCaptureFixture):
    """
    arrange: given update action for a file where only the navlink title has changed and mocked
        discourse
    act: wnen action is passed to _update with draft_mode False
    assert: then no topic is updated, the action is logged and the expected table row is returned.
    """
    caplog.set_level(logging.INFO)
    mocked_discourse = mock.MagicMock(spec=discourse.Discourse)
    level = 1
    path = "path 1"
    content = "content 1"
    link = "link 1"
    update_action = types_.UpdateAction(
        action=types_.Action.UPDATE,
        level=level,
        path=path,
        navlink_change=types_.NavlinkChange(
            old=types_.Navlink(title="title 1", link=link),
            new=types_.Navlink(title="title 2", link=link),
        ),
        content_change=types_.ContentChange(old=content, new=content),
    )

    returned_table_row = action._update(
        action=update_action, discourse=mocked_discourse, draft_mode=False
    )

    assert str(update_action) in caplog.text
    assert f"draft mode: {False}" in caplog.text
    mocked_discourse.update_topic.assert_not_called()
    assert returned_table_row.level == level
    assert returned_table_row.path == path
    assert returned_table_row.navlink == update_action.navlink_change.new


def test__update_file_navlink_content_change(caplog: pytest.LogCaptureFixture):
    """
    arrange: given update action for a file where content has changed and mocked discourse
    act: wnen action is passed to _update with draft_mode False
    assert: then topic is updated, the action is logged and the expected table row is returned.
    """
    caplog.set_level(logging.INFO)
    mocked_discourse = mock.MagicMock(spec=discourse.Discourse)
    level = 1
    path = "path 1"
    link = "link 1"
    update_action = types_.UpdateAction(
        action=types_.Action.UPDATE,
        level=level,
        path=path,
        navlink_change=types_.NavlinkChange(
            old=types_.Navlink(title="title 1", link=link),
            new=types_.Navlink(title="title 2", link=link),
        ),
        content_change=types_.ContentChange(old="content 1", new="content 2"),
    )

    returned_table_row = action._update(
        action=update_action, discourse=mocked_discourse, draft_mode=False
    )

    assert str(update_action) in caplog.text
    assert f"draft mode: {False}" in caplog.text
    mocked_discourse.update_topic.assert_called_once_with(
        url=link, content=update_action.content_change.new
    )
    assert returned_table_row.level == level
    assert returned_table_row.path == path
    assert returned_table_row.navlink == update_action.navlink_change.new


def test__update_file_navlink_content_change_error():
    """
    arrange: given update action for a file where content has changed to None
    act: wnen action is passed to _update with draft_mode False
    assert: ActionError is raised.
    """
    mocked_discourse = mock.MagicMock(spec=discourse.Discourse)
    link = "link 1"
    update_action = types_.UpdateAction(
        action=types_.Action.UPDATE,
        level=1,
        path="path 1",
        navlink_change=types_.NavlinkChange(
            old=types_.Navlink(title="title 1", link=link),
            new=types_.Navlink(title="title 2", link=link),
        ),
        content_change=types_.ContentChange(old="content 1", new=None),
    )

    with pytest.raises(exceptions.ActionError):
        action._update(action=update_action, discourse=mocked_discourse, draft_mode=False)


@pytest.mark.parametrize(
    "draft_mode, delete_pages, navlink_link",
    [
        pytest.param(True, True, "link 1", id="draft mode enabled"),
        pytest.param(False, False, "link 1", id="delete pages false enabled"),
        pytest.param(False, True, None, id="directory"),
    ],
)
def test__delete_not_delete(
    draft_mode: bool,
    delete_pages: bool,
    navlink_link: str | None,
    caplog: pytest.LogCaptureFixture,
):
    """
    arrange: given delete action with given navlink link, draft mode and whether to delete pages
    act: wnen action is passed to _delete with draft_mode and whether to delete pages
    assert: then no topic is deleted and the action is logged.
    """
    caplog.set_level(logging.INFO)
    mocked_discourse = mock.MagicMock(spec=discourse.Discourse)
    delete_action = types_.DeleteAction(
        action=types_.Action.DELETE,
        level=1,
        path="path 1",
        navlink=types_.Navlink(title="title 1", link=navlink_link),
        content="content 1",
    )

    action._delete(
        action=delete_action,
        discourse=mocked_discourse,
        draft_mode=draft_mode,
        delete_pages=delete_pages,
    )

    assert str(delete_action) in caplog.text
    assert f"draft mode: {draft_mode}" in caplog.text
    assert f"delete pages: {delete_pages}" in caplog.text
    mocked_discourse.delete_topic.assert_not_called()


def test__delete(caplog: pytest.LogCaptureFixture):
    """
    arrange: given delete action for file
    act: wnen action is passed to _delete with draft_mode False and whether to delete pages True
    assert: then topic is deleted and the action is logged.
    """
    caplog.set_level(logging.INFO)
    mocked_discourse = mock.MagicMock(spec=discourse.Discourse)
    link = "link 1"
    delete_action = types_.DeleteAction(
        action=types_.Action.DELETE,
        level=1,
        path="path 1",
        navlink=types_.Navlink(title="title 1", link=link),
        content="content 1",
    )

    action._delete(
        action=delete_action,
        discourse=mocked_discourse,
        draft_mode=False,
        delete_pages=True,
    )

    assert str(delete_action) in caplog.text
    assert f"draft mode: {False}" in caplog.text
    assert f"delete pages: {True}" in caplog.text
    mocked_discourse.delete_topic.assert_called_once_with(url=link)