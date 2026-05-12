from __future__ import annotations

import json
import os
from pathlib import Path

from report_config import ROOT

TRACKED_SOURCES_TEMPLATE_FILE = ROOT / "tracked_sources.template.json"
TRACKED_SOURCES_FILE = Path(
    os.environ.get("REPORT_TRACKED_SOURCES_FILE", ROOT / "tracked_sources.json")
)


def _missing_config_message() -> str:
    return "\n".join(
        [
            "Missing private tracked source config.",
            f"- {TRACKED_SOURCES_FILE.name}",
            (
                f"Copy {TRACKED_SOURCES_TEMPLATE_FILE.name} to "
                f"{TRACKED_SOURCES_FILE.name}, fill in the tracked Slack "
                "channels and Notion pages, and then rerun "
                "$reporting-work-activity."
            ),
        ]
    )


def _invalid_config_message(reason: str) -> str:
    return "\n".join(
        [
            "Invalid private tracked source config.",
            f"- {TRACKED_SOURCES_FILE.name}",
            reason,
            (
                f"Use {TRACKED_SOURCES_TEMPLATE_FILE.name} as the schema "
                "reference, fix the local config, and rerun "
                "$reporting-work-activity."
            ),
        ]
    )


def _normalize_source_list(
    value: object,
    *,
    field_name: str,
    required_fields: tuple[str, ...],
    optional_fields: tuple[str, ...],
) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise SystemExit(_invalid_config_message(f"`{field_name}` must be a JSON list."))

    normalized: list[dict[str, str]] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise SystemExit(
                _invalid_config_message(f"`{field_name}[{index}]` must be a JSON object.")
            )

        normalized_item: dict[str, str] = {}
        for key in required_fields:
            raw = item.get(key)
            if not isinstance(raw, str) or not raw.strip():
                raise SystemExit(
                    _invalid_config_message(
                        f"`{field_name}[{index}].{key}` must be a non-empty string."
                    )
                )
            normalized_item[key] = raw.strip()

        for key in optional_fields:
            raw = item.get(key)
            if isinstance(raw, str) and raw.strip():
                normalized_item[key] = raw.strip()

        normalized.append(normalized_item)

    if not normalized:
        raise SystemExit(
            _invalid_config_message(f"`{field_name}` must include at least one tracked entry.")
        )

    return normalized


def _load_tracked_sources() -> dict[str, list[dict[str, str]]]:
    if not TRACKED_SOURCES_FILE.exists():
        raise SystemExit(_missing_config_message())

    try:
        data = json.loads(TRACKED_SOURCES_FILE.read_text())
    except json.JSONDecodeError:
        raise SystemExit(_invalid_config_message("The file must contain valid JSON.")) from None

    if not isinstance(data, dict):
        raise SystemExit(_invalid_config_message("The top-level value must be a JSON object."))

    slack_channels = _normalize_source_list(
        data.get("slack_channels"),
        field_name="slack_channels",
        required_fields=("channel",),
        optional_fields=("url", "focus"),
    )
    notion_pages = _normalize_source_list(
        data.get("notion_pages"),
        field_name="notion_pages",
        required_fields=("title", "url"),
        optional_fields=("focus",),
    )

    return {
        "slack_channels": slack_channels,
        "notion_pages": notion_pages,
    }


TRACKED_SOURCES = _load_tracked_sources()
TRACKED_SLACK_CHANNELS = TRACKED_SOURCES["slack_channels"]
TRACKED_NOTION_PAGES = TRACKED_SOURCES["notion_pages"]
