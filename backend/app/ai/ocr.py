"""OCR / document digitisation (FR14) using Tesseract (English + Hindi) and pdfium.

Digital PDFs use their embedded text layer; scanned pages are rasterised at
300 DPI and OCR'd. Output is later cleaned/structured by the LLM.
"""

from __future__ import annotations

import io
import logging
import shutil
from dataclasses import dataclass

import anyio
import pypdfium2 as pdfium
import pytesseract
from PIL import Image, ImageOps

from app.core.metrics import OCR_PAGES

logger = logging.getLogger(__name__)

MAX_PAGES = 200
_MIN_TEXT_LAYER_CHARS = 40


@dataclass(slots=True)
class OCRResult:
    text: str
    confidence: float | None
    pages: int
    method: str  # text-layer | tesseract | mixed


class OCRUnavailable(RuntimeError):
    pass


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def _available_langs(requested: str) -> str:
    try:
        installed = set(pytesseract.get_languages(config=""))
    except Exception:
        return "eng"
    langs = [lang for lang in requested.split("+") if lang in installed]
    return "+".join(langs) or "eng"


def _ocr_image(img: Image.Image, lang: str) -> tuple[str, float | None]:
    img = ImageOps.exif_transpose(img).convert("L")
    # Upscale small scans; Tesseract works best around 300 DPI.
    if img.width < 1500:
        factor = 1500 / img.width
        img = img.resize((int(img.width * factor), int(img.height * factor)), Image.Resampling.LANCZOS)
    data = pytesseract.image_to_data(img, lang=lang, config="--oem 1 --psm 3", output_type=pytesseract.Output.DICT)
    confs = [float(c) for c, w in zip(data["conf"], data["text"], strict=False) if str(w).strip() and float(c) >= 0]
    text = pytesseract.image_to_string(img, lang=lang, config="--oem 1 --psm 3")
    return text, (sum(confs) / len(confs) / 100.0) if confs else None


def _run(data: bytes, content_type: str, lang: str) -> OCRResult:
    if content_type == "application/pdf" or data[:5] == b"%PDF-":
        pdf = pdfium.PdfDocument(data)
        pages = min(len(pdf), MAX_PAGES)
        texts: list[str] = []
        confs: list[float] = []
        methods: set[str] = set()
        for i in range(pages):
            page = pdf[i]
            layer = page.get_textpage().get_text_range().strip()
            if len(layer) >= _MIN_TEXT_LAYER_CHARS:
                texts.append(layer)
                methods.add("text-layer")
                OCR_PAGES.labels("text_layer").inc()
                continue
            if not tesseract_available():
                raise OCRUnavailable("Tesseract is not installed; scanned PDFs cannot be processed")
            bitmap = page.render(scale=300 / 72).to_pil()
            text, conf = _ocr_image(bitmap, lang)
            texts.append(text)
            if conf is not None:
                confs.append(conf)
            methods.add("tesseract")
            OCR_PAGES.labels("ocr").inc()
        method = "mixed" if len(methods) > 1 else (methods.pop() if methods else "text-layer")
        return OCRResult(
            "\n\n".join(f"--- Page {i + 1} ---\n{t.strip()}" for i, t in enumerate(texts)),
            round(sum(confs) / len(confs), 3) if confs else (1.0 if method == "text-layer" else None),
            pages,
            method,
        )
    if content_type.startswith("image/"):
        if not tesseract_available():
            raise OCRUnavailable("Tesseract is not installed; images cannot be processed")
        with Image.open(io.BytesIO(data)) as img:
            frames = getattr(img, "n_frames", 1)
            texts, confs = [], []
            for frame in range(min(frames, MAX_PAGES)):
                img.seek(frame)
                text, conf = _ocr_image(img.copy(), lang)
                texts.append(text)
                if conf is not None:
                    confs.append(conf)
                OCR_PAGES.labels("ocr").inc()
        return OCRResult(
            "\n\n".join(t.strip() for t in texts),
            round(sum(confs) / len(confs), 3) if confs else None,
            len(texts),
            "tesseract",
        )
    if content_type.startswith("text/"):
        return OCRResult(data.decode("utf-8", errors="replace"), 1.0, 1, "text-layer")
    raise ValueError(f"Unsupported content type for digitisation: {content_type}")


async def extract_text(data: bytes, content_type: str, lang: str = "eng+hin") -> OCRResult:
    resolved = _available_langs(lang) if tesseract_available() else "eng"
    try:
        return await anyio.to_thread.run_sync(_run, data, content_type, resolved)
    except (OCRUnavailable, ValueError):
        OCR_PAGES.labels("failed").inc()
        raise
