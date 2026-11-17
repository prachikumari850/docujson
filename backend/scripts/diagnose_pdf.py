
import argparse
import json
from pathlib import Path

import fitz


def diagnose_pdf(pdf_path: Path):
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    document = fitz.open(pdf_path)
    results = []

    for index, page in enumerate(document):
        text = page.get_text("text").strip()
        images = page.get_images(full=True)
        drawings = page.get_drawings()

        text_length = len(text)

        if text_length >= 100:
            page_type = "digital_text"
        elif text_length > 0:
            page_type = "limited_text"
        else:
            page_type = "ocr_candidate"

        results.append({
            "page": index + 1,
            "type": page_type,
            "text_characters": text_length,
            "embedded_images": len(images),
            "vector_drawings": len(drawings),
            "text_preview": text[:250]
        })

    document.close()

    report = {
        "pdf": str(pdf_path.resolve()),
        "total_pages": len(results),
        "digital_text_pages": sum(
            page["type"] == "digital_text" for page in results
        ),
        "limited_text_pages": sum(
            page["type"] == "limited_text" for page in results
        ),
        "ocr_candidate_pages": sum(
            page["type"] == "ocr_candidate" for page in results
        ),
        "pages": results
    }

    output_path = pdf_path.parent / f"{pdf_path.stem}_diagnostic.json"
    output_path.write_text(
        json.dumps(report, indent=4, ensure_ascii=False),
        encoding="utf-8"
    )

    print(f"\nPDF: {pdf_path.name}")
    print(f"Total pages: {report['total_pages']}")
    print(f"Digital text pages: {report['digital_text_pages']}")
    print(f"Limited text pages: {report['limited_text_pages']}")
    print(f"OCR candidate pages: {report['ocr_candidate_pages']}")
    print("\nPage-wise results:")

    for page in results:
        print(
            f"Page {page['page']:>3}: "
            f"{page['type']:<15} "
            f"Characters: {page['text_characters']:<5} "
            f"Images: {page['embedded_images']:<3} "
            f"Drawings: {page['vector_drawings']}"
        )

    print(f"\nDetailed report saved to: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    args = parser.parse_args()

    diagnose_pdf(args.pdf)
