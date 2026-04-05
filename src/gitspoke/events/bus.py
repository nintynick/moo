"""Event bus — webhook dispatch and event streaming."""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from gitspoke.models import Event, EventType, Webhook


class EventBus:
    """Manages events, webhooks, and event streaming for real-time notifications."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self._subscribers: list[Any] = []  # In-memory streaming subscribers

    # ── Events ──

    def emit(self, repo_id: str, event_type: EventType, payload: dict) -> Event:
        """Record an event and dispatch to webhooks."""
        event = Event(
            repo_id=repo_id,
            event_type=event_type,
            payload=payload,
        )
        self.conn.execute(
            "INSERT INTO events (id, repo_id, event_type, payload, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                event.id,
                event.repo_id,
                event.event_type.value,
                json.dumps(event.payload),
                event.created_at.isoformat(),
            ),
        )
        self.conn.commit()

        # Dispatch to webhooks
        self._dispatch_webhooks(event)

        # Notify in-memory subscribers
        for sub in self._subscribers:
            sub(event)

        return event

    def list_events(
        self,
        repo_id: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[Event]:
        query = "SELECT * FROM events WHERE 1=1"
        params: list = []
        if repo_id:
            query += " AND repo_id = ?"
            params.append(repo_id)
        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(query, params).fetchall()
        return [self._row_to_event(r) for r in rows]

    def subscribe(self, callback: Any) -> None:
        """Register an in-memory event subscriber for streaming."""
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Any) -> None:
        self._subscribers = [s for s in self._subscribers if s is not callback]

    # ── Webhooks ──

    def register_webhook(
        self,
        repo_id: str,
        url: str,
        events: list[str],
        created_by: str,
        secret: str | None = None,
    ) -> Webhook:
        webhook = Webhook(
            repo_id=repo_id,
            url=url,
            events=events,
            secret=secret,
            created_by=created_by,
        )
        self.conn.execute(
            "INSERT INTO webhooks (id, repo_id, url, events, secret, active, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                webhook.id,
                webhook.repo_id,
                webhook.url,
                json.dumps(webhook.events),
                webhook.secret,
                int(webhook.active),
                webhook.created_by,
                webhook.created_at.isoformat(),
            ),
        )
        self.conn.commit()
        return webhook

    def list_webhooks(self, repo_id: str) -> list[Webhook]:
        rows = self.conn.execute(
            "SELECT * FROM webhooks WHERE repo_id = ? AND active = 1",
            (repo_id,),
        ).fetchall()
        return [self._row_to_webhook(r) for r in rows]

    def delete_webhook(self, webhook_id: str) -> None:
        self.conn.execute(
            "UPDATE webhooks SET active = 0 WHERE id = ?", (webhook_id,)
        )
        self.conn.commit()

    def _dispatch_webhooks(self, event: Event) -> None:
        """Dispatch event to matching webhooks. In a real system this would be async HTTP."""
        webhooks = self.list_webhooks(event.repo_id)
        for wh in webhooks:
            if not wh.events or event.event_type.value in wh.events:
                # In production: async HTTP POST to wh.url with signature
                # For MVP: we just record the dispatch attempt
                payload = {
                    "event_id": event.id,
                    "event_type": event.event_type.value,
                    "repo_id": event.repo_id,
                    "payload": event.payload,
                    "timestamp": event.created_at.isoformat(),
                }
                if wh.secret:
                    sig = hmac.new(
                        wh.secret.encode(),
                        json.dumps(payload).encode(),
                        hashlib.sha256,
                    ).hexdigest()
                    payload["signature"] = sig

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> Event:
        return Event(
            id=row["id"],
            repo_id=row["repo_id"],
            event_type=EventType(row["event_type"]),
            payload=json.loads(row["payload"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _row_to_webhook(row: sqlite3.Row) -> Webhook:
        return Webhook(
            id=row["id"],
            repo_id=row["repo_id"],
            url=row["url"],
            events=json.loads(row["events"]),
            secret=row["secret"],
            active=bool(row["active"]),
            created_by=row["created_by"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
