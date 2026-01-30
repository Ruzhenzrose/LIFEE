#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OCR using Gemini Vision API
Convert scanned PDF to text file
"""

import sys
import os
import time
import base64
import fitz  # PyMuPDF
from pathlib import Path

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

import google.generativeai as genai

# Configure Gemini API
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    print("Error: Please set GOOGLE_API_KEY environment variable")
    sys.exit(1)

genai.configure(api_key=GOOGLE_API_KEY)


def pdf_to_images(pdf_path: Path):
    """Convert PDF pages to images"""
    doc = fitz.open(pdf_path)
    images = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        mat = fitz.Matrix(1.5, 1.5)
        pix = page.get_pixmap(matrix=mat)
        img_data = pix.tobytes("png")
        images.append((page_num + 1, img_data))
    doc.close()
    return images


def ocr_with_gemini(images: list, output_path: Path, start_page: int = 1) -> str:
    """OCR using Gemini Vision"""
    model = genai.GenerativeModel("gemini-2.0-flash")

    all_text = []
    total = len(images)

    # Check for existing progress
    if output_path.exists():
        existing_text = output_path.read_text(encoding="utf-8")
        all_text.append(existing_text)
        import re
        matches = re.findall(r"--- Page (\d+) ---", existing_text)
        if matches:
            start_page = int(matches[-1]) + 1
            print(f"  Resuming from page {start_page}...")

    for page_num, img_data in images:
        if page_num < start_page:
            continue

        print(f"\r  OCR progress: {page_num}/{total}", end="", flush=True)

        img_base64 = base64.b64encode(img_data).decode("utf-8")

        try:
            response = model.generate_content([
                {
                    "mime_type": "image/png",
                    "data": img_base64
                },
                "Extract all text from this image. Keep the original paragraph format. Output only the recognized text without any explanation. If no text found, output [NO TEXT]."
            ])

            text = response.text.strip()

            if text and text != "[NO TEXT]":
                all_text.append(f"--- Page {page_num} ---\n")
                all_text.append(text)
                all_text.append("\n\n")

                # Save progress every 10 pages
                if page_num % 10 == 0:
                    output_path.write_text("".join(all_text), encoding="utf-8")

        except Exception as e:
            print(f"\n  Error on page {page_num}: {e}")
            output_path.write_text("".join(all_text), encoding="utf-8")

            if "429" in str(e) or "quota" in str(e).lower():
                print("  Rate limit hit, waiting 60s...")
                time.sleep(60)
                continue
            else:
                raise

        # Rate limit: max 15 requests per minute
        time.sleep(4.5)

    print()
    return "".join(all_text)


def process_pdf(pdf_path: str, output_path: str = None):
    """Process a single PDF file"""
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        print(f"Error: File not found - {pdf_path}")
        return

    if output_path:
        output_path = Path(output_path)
    else:
        output_path = pdf_path.with_suffix(".txt")

    print(f"Processing: {pdf_path.name}")
    print("  Converting PDF to images...")
    images = pdf_to_images(pdf_path)
    print(f"  Total pages: {len(images)}")

    print("  Starting OCR (Gemini Vision)...")
    print(f"  Estimated time: ~{len(images) * 4.5 / 60:.0f} minutes")

    text = ocr_with_gemini(images, output_path)

    output_path.write_text(text, encoding="utf-8")
    print(f"  Saved to: {output_path}")
    print(f"  Text length: {len(text)} chars")


def main():
    if len(sys.argv) < 2:
        print("Usage: python ocr_gemini.py <pdf_file> [output_file]")
        print("Supports resume: if interrupted, run again to continue.")
        sys.exit(1)

    pdf_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None

    process_pdf(pdf_path, output_path)


if __name__ == "__main__":
    main()
