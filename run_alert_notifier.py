from __future__ import annotations

import json
import logging
import os
import signal
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from typing import Callable

import config
from core.orchestration.observability import (
    RuntimeAlert,
    RuntimeAlertStore,
    RuntimeHeartbeatStore,
)
from utils.logger import setup_logger


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_ROOT = PROJECT_ROOT / ".atlas_data"
DELIVERY_PATH = (
    DATA_ROOT / "runtime_alert_deliveries.json"
)

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class NotificationResult:
    sent_count: int
    failed_count: int
    heartbeat_notification_sent: bool


MessageSender = Callable[[str], None]


class DeliveryStateStore:
    """
    Persists delivered alert IDs and the last observed heartbeat state.

    The first poll records the heartbeat baseline without sending a fake
    recovery notification.
    """

    def __init__(
        self,
        storage_path: str | Path,
        *,
        max_ids: int = 500,
    ) -> None:
        if max_ids < 1:
            raise ValueError(
                "max_ids must be at least 1."
            )

        self.storage_path = Path(
            storage_path
        )
        self.max_ids = max_ids

        self.storage_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if not self.storage_path.exists():
            self.save(
                {
                    "delivered_alert_ids": [],
                    "heartbeat_state": None,
                }
            )

    def load(self) -> dict[str, object]:
        try:
            payload = json.loads(
                self.storage_path.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            json.JSONDecodeError,
        ):
            return self._default()

        if not isinstance(payload, dict):
            return self._default()

        delivered = payload.get(
            "delivered_alert_ids",
            [],
        )

        if not isinstance(delivered, list):
            delivered = []

        heartbeat_state = payload.get(
            "heartbeat_state"
        )

        return {
            "delivered_alert_ids": [
                str(value)
                for value in delivered
            ][-self.max_ids:],
            "heartbeat_state": (
                str(heartbeat_state)
                if heartbeat_state is not None
                else None
            ),
        }

    def save(
        self,
        payload: dict[str, object],
    ) -> None:
        delivered = payload.get(
            "delivered_alert_ids",
            [],
        )

        if not isinstance(delivered, list):
            delivered = []

        heartbeat_state = payload.get(
            "heartbeat_state"
        )

        normalized = {
            "delivered_alert_ids": [
                str(value)
                for value in delivered
            ][-self.max_ids:],
            "heartbeat_state": (
                str(heartbeat_state)
                if heartbeat_state is not None
                else None
            ),
        }

        temporary_path = (
            self.storage_path.with_suffix(
                self.storage_path.suffix + ".tmp"
            )
        )

        temporary_path.write_text(
            json.dumps(
                normalized,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        temporary_path.replace(
            self.storage_path
        )

    @staticmethod
    def _default() -> dict[str, object]:
        return {
            "delivered_alert_ids": [],
            "heartbeat_state": None,
        }


class DiscordRestSender:
    """Sends runtime notifications through Discord's REST API."""

    def __init__(
        self,
        *,
        bot_token: str,
        channel_id: int,
        timeout_seconds: int = 30,
    ) -> None:
        cleaned_token = bot_token.strip()

        if not cleaned_token:
            raise ValueError(
                "bot_token cannot be empty."
            )

        if channel_id < 1:
            raise ValueError(
                "channel_id must be positive."
            )

        if timeout_seconds < 1:
            raise ValueError(
                "timeout_seconds must be positive."
            )

        self.bot_token = cleaned_token
        self.channel_id = channel_id
        self.timeout_seconds = timeout_seconds

    def send(
        self,
        message: str,
    ) -> None:
        cleaned_message = message.strip()

        if not cleaned_message:
            return

        payload = json.dumps(
            {
                "content": cleaned_message[:1900],
                "allowed_mentions": {
                    "parse": [],
                },
            }
        ).encode("utf-8")

        request = urllib.request.Request(
            (
                "https://discord.com/api/v10/"
                f"channels/{self.channel_id}/messages"
            ),
            data=payload,
            method="POST",
            headers={
                "Authorization": (
                    f"Bot {self.bot_token}"
                ),
                "Content-Type": "application/json",
                "User-Agent": (
                    "Atlas-Lite-Alert-Notifier/1.0"
                ),
            },
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout_seconds,
            ) as response:
                if not 200 <= response.status < 300:
                    raise RuntimeError(
                        "Discord notification failed "
                        f"with HTTP {response.status}."
                    )
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(
                "utf-8",
                errors="replace",
            )

            raise RuntimeError(
                "Discord notification HTTP error: "
                f"{exc.code}: {body}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(
                "Discord notification network error: "
                f"{exc}"
            ) from exc


class RuntimeAlertNotifier:
    """
    Sends each unacknowledged runtime alert once and reports heartbeat
    transitions such as healthy -> stale and stale -> healthy.
    """

    def __init__(
        self,
        *,
        alert_store: RuntimeAlertStore,
        heartbeat_store: RuntimeHeartbeatStore,
        delivery_store: DeliveryStateStore,
        sender: MessageSender,
        heartbeat_stale_seconds: float = 120.0,
    ) -> None:
        if heartbeat_stale_seconds < 1:
            raise ValueError(
                "heartbeat_stale_seconds must be at least 1."
            )

        self.alert_store = alert_store
        self.heartbeat_store = (
            heartbeat_store
        )
        self.delivery_store = delivery_store
        self.sender = sender
        self.heartbeat_stale_seconds = (
            heartbeat_stale_seconds
        )

    def poll_once(
        self,
    ) -> NotificationResult:
        state = self.delivery_store.load()

        delivered_ids = {
            str(value)
            for value in state.get(
                "delivered_alert_ids",
                [],
            )
        }

        sent_count = 0
        failed_count = 0

        for alert in (
            self.alert_store
            .list_unacknowledged()
        ):
            if alert.alert_id in delivered_ids:
                continue

            try:
                self.sender(
                    self._format_alert(alert)
                )
            except Exception:
                logger.exception(
                    "Runtime alert delivery failed."
                )
                failed_count += 1
                continue

            delivered_ids.add(
                alert.alert_id
            )
            sent_count += 1

        previous_heartbeat_state = (
            state.get("heartbeat_state")
        )

        current_heartbeat_state = (
            self._heartbeat_state()
        )

        heartbeat_notification_sent = False

        if previous_heartbeat_state is not None:
            if (
                current_heartbeat_state
                != previous_heartbeat_state
            ):
                message = (
                    self._heartbeat_message(
                        current_heartbeat_state
                    )
                )

                if message is not None:
                    try:
                        self.sender(message)
                        heartbeat_notification_sent = True
                    except Exception:
                        logger.exception(
                            "Heartbeat notification "
                            "delivery failed."
                        )
                        failed_count += 1

        self.delivery_store.save(
            {
                "delivered_alert_ids": sorted(
                    delivered_ids
                ),
                "heartbeat_state": (
                    current_heartbeat_state
                ),
            }
        )

        return NotificationResult(
            sent_count=sent_count,
            failed_count=failed_count,
            heartbeat_notification_sent=(
                heartbeat_notification_sent
            ),
        )

    def _heartbeat_state(self) -> str:
        heartbeat = self.heartbeat_store.load()

        if heartbeat is None:
            return "missing"

        try:
            updated_at = datetime.fromisoformat(
                heartbeat.updated_at
            )
        except ValueError:
            return "invalid"

        now = datetime.now(
            timezone.utc
        )

        age_seconds = (
            now - updated_at
        ).total_seconds()

        if heartbeat.service_status != "running":
            return "stopped"

        if (
            age_seconds
            > self.heartbeat_stale_seconds
        ):
            return "stale"

        return "healthy"

    @staticmethod
    def _format_alert(
        alert: RuntimeAlert,
    ) -> str:
        return (
            "**Atlas Runtime Alert**\n"
            f"Severity: "
            f"`{alert.severity.upper()}`\n"
            f"Status: "
            f"`{alert.cycle_status}`\n"
            f"Task: "
            f"`{alert.task_id or 'None'}`\n"
            f"Message: {alert.message}\n"
            f"Created: `{alert.created_at}`"
        )

    @staticmethod
    def _heartbeat_message(
        state: str,
    ) -> str | None:
        if state == "healthy":
            return (
                "**Atlas Runtime Recovered**\n"
                "Heartbeat is healthy and the continuous "
                "orchestrator is running."
            )

        if state in {
            "missing",
            "invalid",
            "stale",
            "stopped",
        }:
            return (
                "**Atlas Runtime Health Alert**\n"
                f"Heartbeat state: `{state}`\n"
                "Check the AWS runtime service."
            )

        return None


def positive_float(
    name: str,
    default: float,
) -> float:
    raw_value = os.getenv(
        name,
        str(default),
    ).strip()

    try:
        value = float(raw_value)
    except ValueError as exc:
        raise RuntimeError(
            f"{name} must be numeric."
        ) from exc

    if value <= 0:
        raise RuntimeError(
            f"{name} must be greater than zero."
        )

    return value


def build_notifier(
) -> RuntimeAlertNotifier:
    DATA_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not config.DISCORD_BOT_TOKEN:
        raise RuntimeError(
            "DISCORD_BOT_TOKEN is missing."
        )

    if not config.DISCORD_CHANNEL_ID:
        raise RuntimeError(
            "DISCORD_CHANNEL_ID is missing."
        )

    try:
        channel_id = int(
            config.DISCORD_CHANNEL_ID
        )
    except ValueError as exc:
        raise RuntimeError(
            "DISCORD_CHANNEL_ID must be numeric."
        ) from exc

    sender = DiscordRestSender(
        bot_token=config.DISCORD_BOT_TOKEN,
        channel_id=channel_id,
        timeout_seconds=30,
    )

    return RuntimeAlertNotifier(
        alert_store=RuntimeAlertStore(
            DATA_ROOT / "runtime_alerts.json"
        ),
        heartbeat_store=(
            RuntimeHeartbeatStore(
                DATA_ROOT
                / "runtime_heartbeat.json"
            )
        ),
        delivery_store=DeliveryStateStore(
            DELIVERY_PATH
        ),
        sender=sender.send,
        heartbeat_stale_seconds=(
            positive_float(
                "ATLAS_HEARTBEAT_STALE_SECONDS",
                120.0,
            )
        ),
    )


def main() -> None:
    setup_logger(
        "atlas-lite.alerts"
    )

    stop_event = Event()

    def request_stop(
        signum: int,
        frame: object,
    ) -> None:
        logger.info(
            "Alert notifier stop signal: %s",
            signum,
        )
        stop_event.set()

    signal.signal(
        signal.SIGTERM,
        request_stop,
    )
    signal.signal(
        signal.SIGINT,
        request_stop,
    )

    notifier = build_notifier()

    poll_seconds = positive_float(
        "ATLAS_ALERT_POLL_SECONDS",
        30.0,
    )

    logger.info(
        "Atlas runtime alert notifier started."
    )

    while not stop_event.is_set():
        result = notifier.poll_once()

        logger.info(
            "Alert poll sent=%s failed=%s "
            "heartbeat_notification=%s",
            result.sent_count,
            result.failed_count,
            result.heartbeat_notification_sent,
        )

        stop_event.wait(
            poll_seconds
        )

    logger.info(
        "Atlas runtime alert notifier stopped."
    )


if __name__ == "__main__":
    main()
