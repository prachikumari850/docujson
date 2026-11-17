import sys
import argparse
import tempfile
from pathlib import Path

from app.services.engine import extract_pdf

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def inspect(pdf_path: Path, page_number: int):
    with tempfile.TemporaryDirectory(prefix="layout_geometry_") as temp_dir:
        extracted = extract_pdf(pdf_path, Path(temp_dir))
        pages = extracted["pages"]

        page = next(
            (item for item in pages if item["page"] == page_number),
            None,
        )

        if page is None:
            print(f"Page {page_number} not found")
            return

        print(f"\nPDF: {pdf_path.name}")
        print(f"Page: {page_number}")
        print(f"Page dimensions: {page['width']} x {page['height']}")
        print(f"Total lines: {len(page['lines'])}")

        for index, line in enumerate(page["lines"]):
            _, _, text, bbox, spans = line

            x0, y0, x1, y1 = bbox

            print(
                f"{index:03} | "
                f"x={x0:7.2f}-{x1:7.2f} | "
                f"y={y0:7.2f}-{y1:7.2f} | "
                f"w={x1 - x0:7.2f} | "
                f"spans={len(spans):2} | "
                f"{text[:110]}"
            )

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--page", type=int, default=3)
    args = parser.parse_args()

    inspect(args.pdf, args.page)


if __name__ == "__main__":
    main()
