
import argparse
import tempfile
from pathlib import Path

from app.services.engine import extract_pdf
from app.services.layout import detect_page_layout


def diagnose(pdf_path: Path):
    print(f"\n{'=' * 90}")
    print(f"PDF: {pdf_path.name}")
    print(f"{'=' * 90}")

    with tempfile.TemporaryDirectory(prefix="layout_diagnostic_") as temp_dir:
        extracted = extract_pdf(pdf_path, Path(temp_dir))
        pages = extracted["pages"]

        for page in pages:
            result = detect_page_layout(
                lines=page["lines"],
                page_width=page["width"],
                page_height=page["height"],
            )

            print(
                f"\nPage {page['page']}: "
                f"{result['layout_type']} | "
                f"columns={len(result['columns'])} | "
                f"regions={len(result['regions'])} | "
                f"confidence={result['confidence']}"
            )

            if result["warnings"]:
                print("Warnings:", "; ".join(result["warnings"]))

            for region in result["regions"]:
                indexes = region["line_indices"]
                preview = [
                    page["lines"][i][2].strip()
                    for i in indexes[:3]
                ]

                print(
                    f"  Region {region['region_id']} "
                    f"[{region['region_type']}] "
                    f"bbox={region['bbox']} "
                    f"lines={len(indexes)}"
                )

                for line in preview:
                    print(f"    {line[:130]}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pdfs", nargs="+", type=Path)
    args = parser.parse_args()

    for pdf_path in args.pdfs:
        if not pdf_path.is_file():
            print(f"\nFile not found: {pdf_path}")
            continue

        diagnose(pdf_path)


if __name__ == "__main__":
    main()
