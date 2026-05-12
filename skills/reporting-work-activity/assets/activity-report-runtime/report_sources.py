from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from report_config import NOTION_SNAPSHOT_FILE, OUTPUT_DIR, ROOT, SLACK_SNAPSHOT_FILE

TRACKED_SOURCES_TEMPLATE_FILE = ROOT / "tracked_sources.template.json"
TRACKED_SOURCES_FILE = Path(
    os.environ.get("REPORT_TRACKED_SOURCES_FILE", ROOT / "tracked_sources.json")
)
SUMMARY_SNAPSHOT_FILE = OUTPUT_DIR / "summary.json"


def _missing_config_message() -> str:
    return "\n".join(
        [
            "Missing private tracked source config.",
            f"- {TRACKED_SOURCES_FILE.name}",
            (
                "Run `mise run bootstrap-tracked-sources` first. If that "
                "cannot seed the file from local snapshots or "
                "`dist/summary.json`, copy "
                f"{TRACKED_SOURCES_TEMPLATE_FILE.name} to "
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


def _load_json(path: Path) -> object | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def _first_text(item: dict, *keys: str) -> str | None:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _normalize_bootstrap_slack(items: object) -> list[dict[str, str]]:
    if not isinstance(items, list):
        return []

    seen: set[str] = set()
    normalized: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        channel = _first_text(item, "channel")
        if not channel or channel in seen:
            continue
        seen.add(channel)

        entry = {"channel": channel}
        url = _first_text(item, "url")
        focus = _first_text(item, "focus", "theme", "summary")
        if url:
            entry["url"] = url
        if focus:
            entry["focus"] = focus
        normalized.append(entry)

    return normalized


def _normalize_bootstrap_notion(items: object) -> list[dict[str, str]]:
    if not isinstance(items, list):
        return []

    seen: set[tuple[str, str]] = set()
    normalized: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = _first_text(item, "title")
        url = _first_text(item, "url")
        if not title or not url:
            continue
        key = (title, url)
        if key in seen:
            continue
        seen.add(key)

        entry = {"title": title, "url": url}
        focus = _first_text(item, "focus", "summary")
        if focus:
            entry["focus"] = focus
        normalized.append(entry)

    return normalized


def _build_bootstrap_sources(
    slack_items: object, notion_items: object
) -> dict[str, list[dict[str, str]]] | None:
    slack_channels = _normalize_bootstrap_slack(slack_items)
    notion_pages = _normalize_bootstrap_notion(notion_items)
    if not slack_channels or not notion_pages:
        return None
    return {
        "slack_channels": slack_channels,
        "notion_pages": notion_pages,
    }


def _bootstrap_from_snapshots() -> dict[str, list[dict[str, str]]] | None:
    if not SLACK_SNAPSHOT_FILE.exists() or not NOTION_SNAPSHOT_FILE.exists():
        return None
    return _build_bootstrap_sources(
        _load_json(SLACK_SNAPSHOT_FILE),
        _load_json(NOTION_SNAPSHOT_FILE),
    )


def _bootstrap_from_summary() -> dict[str, list[dict[str, str]]] | None:
    summary = _load_json(SUMMARY_SNAPSHOT_FILE)
    if not isinstance(summary, dict):
        return None
    return _build_bootstrap_sources(
        summary.get("slack_highlights"),
        summary.get("notion_highlights"),
    )


def bootstrap_tracked_sources(force: bool = False) -> Path | None:
    if TRACKED_SOURCES_FILE.exists() and not force:
        return TRACKED_SOURCES_FILE

    for builder in (_bootstrap_from_snapshots, _bootstrap_from_summary):
        sources = builder()
        if not sources:
            continue
        TRACKED_SOURCES_FILE.write_text(json.dumps(sources, indent=2) + "\n")
        load_tracked_sources.cache_clear()
        return TRACKED_SOURCES_FILE

    return None


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


@lru_cache(maxsize=1)
def load_tracked_sources() -> dict[str, list[dict[str, str]]]:
    if not TRACKED_SOURCES_FILE.exists():
        bootstrap_tracked_sources()
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


def tracked_slack_channels() -> list[dict[str, str]]:
    return load_tracked_sources()["slack_channels"]


def tracked_notion_pages() -> list[dict[str, str]]:
    return load_tracked_sources()["notion_pages"]
