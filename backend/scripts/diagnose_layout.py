
import argparse
import json
from pathlib import Path

import fitz


def extract_page_layout(page):
    data = page.get_text("dict", sort=True)
    blocks = []

    for block in data["blocks"]:
        if block.get("type") != 0:
            continue

        lines = []

        for line in block.get("lines", []):
            spans = []

            for span in line.get("spans", []):
                text = span.get("text", "").strip()

                if text:
                    spans.append({
                        "text": text,
                        "font": span.get("font"),
                        "size": round(span.get("size", 0), 2),
                        "bbox": [
                            round(value, 2)
                            for value in span.get("bbox", [])
                        ]
                    })

            if spans:
                lines.append(spans)

        if lines:
            blocks.append({
                "bbox": [
                    round(value, 2)
                    for value in block.get("bbox", [])
                ],
                "lines": lines
            })

    return blocks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--start", type=int, default=3)
    parser.add_argument("--end", type=int, default=13)
    args = parser.parse_args()

    if not args.pdf.exists():
        raise FileNotFoundError(args.pdf)

    document = fitz.open(args.pdf)

    if args.start < 1 or args.end > len(document):
        raise ValueError("Page range is outside the PDF.")

    results = []

    for page_number in range(args.start, args.end + 1):
        page = document[page_number - 1]

        results.append({
            "page": page_number,
            "width": page.rect.width,
            "height": page.rect.height,
            "blocks": extract_page_layout(page)
        })

        print(
            f"Processed page {page_number}: "
            f"{len(results[-1]['blocks'])} text blocks"
        )

    output_path = args.pdf.parent / "physics_layout_diagnostic.json"

    output_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    document.close()

    print(f"\nLayout report saved: {output_path}")


if __name__ == "__main__":
    main()
