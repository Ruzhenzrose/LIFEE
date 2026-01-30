#!/usr/bin/env python3
"""
扫描版 PDF OCR 识别工具
使用 PaddleOCR 将扫描版 PDF 转换为文本文件
"""

import sys
import fitz  # PyMuPDF
from pathlib import Path
from paddleocr import PaddleOCR


def pdf_to_images(pdf_path: Path):
    """将 PDF 每页转换为图片"""
    doc = fitz.open(pdf_path)
    images = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        # 放大 2 倍以提高 OCR 精度
        mat = fitz.Matrix(2, 2)
        pix = page.get_pixmap(matrix=mat)
        img_data = pix.tobytes("png")
        images.append((page_num + 1, img_data))
    doc.close()
    return images


def ocr_images(images: list, ocr: PaddleOCR) -> str:
    """对图片列表进行 OCR"""
    import tempfile
    import os

    all_text = []
    total = len(images)

    for page_num, img_data in images:
        print(f"\r  OCR 进度: {page_num}/{total}", end="", flush=True)

        # 保存临时图片
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(img_data)
            temp_path = f.name

        try:
            # OCR 识别
            result = ocr.ocr(temp_path)

            # 提取文本（适配新版 PaddleOCR API）
            page_text = []
            if result:
                for item in result:
                    if isinstance(item, dict) and "rec_texts" in item:
                        # 新版 API 格式
                        page_text.extend(item["rec_texts"])
                    elif isinstance(item, list):
                        # 旧版 API 格式
                        for line in item:
                            if line and len(line) >= 2 and line[1]:
                                text = line[1][0] if isinstance(line[1], tuple) else line[1]
                                page_text.append(str(text))

            if page_text:
                all_text.append(f"--- 第 {page_num} 页 ---\n")
                all_text.append("\n".join(page_text))
                all_text.append("\n\n")
        finally:
            os.unlink(temp_path)

    print()  # 换行
    return "".join(all_text)


def process_pdf(pdf_path: str, output_path: str = None):
    """处理单个 PDF 文件"""
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        print(f"错误: 文件不存在 - {pdf_path}")
        return

    if output_path:
        output_path = Path(output_path)
    else:
        output_path = pdf_path.with_suffix(".txt")

    print(f"处理: {pdf_path.name}")
    print("  初始化 PaddleOCR...")

    # 初始化 OCR，使用中文模型
    ocr = PaddleOCR(
        use_angle_cls=True,
        lang="ch"
    )

    print("  转换 PDF 为图片...")
    images = pdf_to_images(pdf_path)
    print(f"  共 {len(images)} 页")

    print("  开始 OCR 识别...")
    text = ocr_images(images, ocr)

    # 保存结果
    output_path.write_text(text, encoding="utf-8")
    print(f"  保存到: {output_path}")
    print(f"  文本长度: {len(text)} 字符")


def main():
    if len(sys.argv) < 2:
        print("用法: python ocr_pdf.py <pdf_file> [output_file]")
        print("示例: python ocr_pdf.py 拉康选集.pdf")
        print("      python ocr_pdf.py 拉康选集.pdf output.txt")
        sys.exit(1)

    pdf_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None

    process_pdf(pdf_path, output_path)


if __name__ == "__main__":
    main()
