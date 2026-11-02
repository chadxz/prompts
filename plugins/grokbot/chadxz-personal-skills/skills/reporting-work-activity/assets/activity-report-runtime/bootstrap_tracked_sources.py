from __future__ import annotations

from report_sources import TRACKED_SOURCES_FILE, bootstrap_tracked_sources


def main() -> None:
    path = bootstrap_tracked_sources()
    if path is None:
        raise SystemExit(
            "Could not bootstrap tracked source config from local artifacts.\n"
            "- checked data/slack_channels.json + data/notion_pages.json\n"
            "- checked dist/summary.json\n"
            "Copy tracked_sources.template.json to tracked_sources.json, fill "
            "in your tracked Slack channels and Notion pages, and then rerun "
            "$reporting-work-activity."
        )

    print(f"Tracked source config ready at {TRACKED_SOURCES_FILE.name}.")


if __name__ == "__main__":
    main()
