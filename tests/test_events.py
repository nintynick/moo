"""Tests for the Event Bus and Webhook system."""

import pytest

from gitspoke.db import bootstrap, get_connection
from gitspoke.events.bus import EventBus
from gitspoke.models import EventType


@pytest.fixture
def event_bus():
    conn = get_connection(":memory:")
    bootstrap(conn)
    return EventBus(conn)


def test_emit_event(event_bus):
    event = event_bus.emit("repo-1", EventType.COMMIT_PUSHED, {"commit_id": "abc123"})
    assert event.event_type == EventType.COMMIT_PUSHED
    assert event.payload["commit_id"] == "abc123"


def test_list_events(event_bus):
    event_bus.emit("repo-1", EventType.COMMIT_PUSHED, {"id": "1"})
    event_bus.emit("repo-1", EventType.EVAL_COMPLETED, {"id": "2"})
    event_bus.emit("repo-2", EventType.COMMIT_PUSHED, {"id": "3"})

    all_events = event_bus.list_events()
    assert len(all_events) == 3

    repo1 = event_bus.list_events(repo_id="repo-1")
    assert len(repo1) == 2

    eval_events = event_bus.list_events(event_type="eval.completed")
    assert len(eval_events) == 1


def test_register_webhook(event_bus):
    wh = event_bus.register_webhook(
        repo_id="repo-1",
        url="https://example.com/hook",
        events=["commit.pushed", "eval.completed"],
        created_by="alice",
        secret="s3cret",
    )
    assert wh.url == "https://example.com/hook"
    assert len(wh.events) == 2


def test_list_webhooks(event_bus):
    event_bus.register_webhook("repo-1", "https://a.com", [], "alice")
    event_bus.register_webhook("repo-1", "https://b.com", [], "bob")
    event_bus.register_webhook("repo-2", "https://c.com", [], "charlie")

    hooks = event_bus.list_webhooks("repo-1")
    assert len(hooks) == 2


def test_delete_webhook(event_bus):
    wh = event_bus.register_webhook("repo-1", "https://a.com", [], "alice")
    event_bus.delete_webhook(wh.id)
    hooks = event_bus.list_webhooks("repo-1")
    assert len(hooks) == 0


def test_in_memory_subscriber(event_bus):
    received = []
    event_bus.subscribe(lambda e: received.append(e))
    event_bus.emit("repo-1", EventType.SCORE_RECORDED, {"score": 0.95})
    assert len(received) == 1
    assert received[0].event_type == EventType.SCORE_RECORDED


def test_unsubscribe(event_bus):
    received = []
    cb = lambda e: received.append(e)
    event_bus.subscribe(cb)
    event_bus.emit("repo-1", EventType.COMMIT_PUSHED, {})
    assert len(received) == 1

    event_bus.unsubscribe(cb)
    event_bus.emit("repo-1", EventType.COMMIT_PUSHED, {})
    assert len(received) == 1  # No new events
