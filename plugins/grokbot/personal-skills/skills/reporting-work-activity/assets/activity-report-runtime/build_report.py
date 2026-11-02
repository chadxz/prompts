from __future__ import annotations

import export_single_page_pdf
import generate_report


def main() -> None:
    """Build the HTML report and its required single-page PDF companion."""

    generate_report.main()
    export_single_page_pdf.main()


if __name__ == "__main__":
    main()
