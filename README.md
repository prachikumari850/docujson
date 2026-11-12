# DocuJSON

DocuJSON is a local React/Vite and FastAPI application that extracts educational questions and answer keys from PDF, DOCX, and TXT uploads. It retains source locations and review evidence, exports confirmed multiple-choice questions as UTF-8 JSON, and packages referenced media in a ZIP.

Extraction is deterministic by default. Ollama is optional and disabled by default; basic conversion does not require a model, network service, GPU, or model download.

## Architecture

1. The React uploader validates selected file roles and sends repeated `files` multipart fields plus a JSON `roles` field.
2. FastAPI validates names, formats, combined upload size, and roles, then queues `app.services.engine.run_conversion`.
3. The active engine dispatches PDF, DOCX, and TXT extraction. PDF processing uses PyMuPDF structured text and drawing data, optional Tesseract OCR, atom/math-unit and reading-order stages, question/option parsing, MCQ classification, answer-key matching, and media ownership.
4. Pydantic result models validate the output. The same conversion result supplies the status API, standalone JSON download, ZIP's `document.json`, and React preview.
5. ZIP media paths are relative under `media/`; the archive includes a media manifest and available extraction/classification diagnostics.

The extraction stages preserve ambiguous evidence for review. Successful parsing does not establish source accuracy; inspect review flags and compare important content with its source pages.

## Windows prerequisites

- Python 3.11 or newer.
- Node.js 20 or newer and npm.
- Tesseract OCR for scanned pages. Install it separately if OCR is needed. English (`eng`) data is recommended; Hindi (`hin`) data is optional and must be installed separately.
- No GPU or Ollama installation is required.

## Setup

From PowerShell at the project root:

```powershell
python -m venv .\backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools
.\backend\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
Set-Location .\frontend
npm ci
Set-Location ..
```

Configure `backend/.env` without overwriting an existing file. For a new checkout only:

```powershell
if (-not (Test-Path backend\.env)) {
    Copy-Item backend\.env.example backend\.env
}
```

Set `TESSERACT_CMD` and `TESSDATA_PREFIX` to the local installation only if they are needed. Leave them empty to let Tesseract use its normal system configuration. `OCR_LANGUAGES=eng+hin` falls back to installed OCR languages when a requested language pack is missing and records a warning. Keep `OLLAMA_ENABLED=false` for deterministic local extraction without model requests.

Configuration is read by `backend/app/config.py`. Storage paths are resolved relative to the backend directory unless absolute. Upload size applies to the combined request. Supported formats are `.pdf`, `.docx`, and `.txt`.

## Start the application

From the repository root, start the backend in one PowerShell window:

```powershell
Set-Location .\backend
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

From the repository root in a second window, start the frontend:

```powershell
Set-Location .\frontend
npm.cmd run dev -- --host 127.0.0.1
```

Open `http://localhost:5173`. The API health endpoint is `http://127.0.0.1:8000/api/health`.

## Conversion and exports

Choose one question paper and, optionally, one answer key. Assign each role in the uploader and start conversion. The API accepts repeated multipart `files` fields and `roles` as a JSON object mapping each uploaded filename to `question_paper` or `answer_key`; the legacy single `file` field is also accepted.

The JSON result contains document metadata, confirmed MCQs, options, answer provenance, source locations, math evidence, media references, and review warnings. The ZIP contains:

```text
document.json
media/manifest.json
media/<referenced raster and SVG assets>
debug/extraction_debug.json       (when available)
debug/classification_debug.json   (when available)
```

SVG vector assets are generated only when source PDF drawing geometry can be reconstructed. Raster wrappers are labelled as wrappers, and original raster assets remain available. Media references use export-relative paths rather than temporary filesystem paths.

## Tests and build

```powershell
Set-Location .\backend
.venv\Scripts\python.exe -m pytest -q

Set-Location .\frontend
npm.cmd test
npm.cmd run build
```

To require the SRG real-document fixture instead of allowing a fixture-dependent skip:

```powershell
$env:DOCUJSON_REGRESSION = '1'
.venv\Scripts\python.exe -m pytest tests/test_srg_source_regression.py -q
Remove-Item Env:DOCUJSON_REGRESSION
```

If the source PDF is outside the repository, set `DOCUJSON_PHYSICS_QP_PDF` to its path for that test run. Keep original documents and generated storage data out of commits.

## Troubleshooting

- **OCR unavailable:** verify Tesseract is on `PATH` or configure `TESSERACT_CMD`; check that the requested trained data is installed.
- **Hindi OCR warning:** install the Hindi Tesseract trained data and configure `TESSDATA_PREFIX`, or accept English-only OCR with review warnings.
- **Backend connection failure:** start FastAPI on `127.0.0.1:8000` and check the health endpoint.
- **Upload rejected:** verify supported extension, non-empty files, unique filenames, exactly one question paper, and combined size under `MAX_UPLOAD_MB`.
- **Question or math uncertainty:** inspect review reasons and source-page evidence. The system does not guarantee exact reconstruction of every scanned, legacy-font, or complex mathematical layout.

## Known validation limits

The preserved SRG Physics and Chemistry papers are from the same publisher family. They are useful regression sources, not evidence of universal or cross-publisher compatibility. Other-publisher physics, mathematics, chemistry, Hindi/bilingual, multi-column, image-option, and genuine scanned MCQ exam samples are still needed for broader accuracy claims. OCR performance depends on image quality and installed language data. Review flags and source comparison remain important for ambiguous content.
