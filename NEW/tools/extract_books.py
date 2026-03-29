"""
提取 PDF、EPUB、MOBI 书籍内容为文本文件
用于 RAG 知识库索引
"""

import sys
import tempfile
import shutil
from pathlib import Path

# 检查依赖
try:
    import fitz  # PyMuPDF
except ImportError:
    print("请安装 PyMuPDF: pip install PyMuPDF")
    sys.exit(1)

try:
    import ebooklib
    from ebooklib import epub
    from bs4 import BeautifulSoup
except ImportError:
    print("请安装 ebooklib 和 beautifulsoup4: pip install ebooklib beautifulsoup4")
    sys.exit(1)

try:
    import mobi
except ImportError:
    print("请安装 mobi: pip install mobi")
    sys.exit(1)


def extract_pdf(pdf_path: Path) -> str:
    """提取 PDF 文本"""
    doc = fitz.open(pdf_path)
    texts = []
    for page_num, page in enumerate(doc, 1):
        text = page.get_text()
        if text.strip():
            texts.append(f"<!-- 第 {page_num} 页 -->\n{text}")
    doc.close()
    return "\n\n".join(texts)


def extract_epub(epub_path: Path) -> str:
    """提取 EPUB 文本"""
    book = epub.read_epub(str(epub_path))
    texts = []

    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            soup = BeautifulSoup(item.get_content(), 'html.parser')
            text = soup.get_text(separator='\n')
            if text.strip():
                texts.append(text)

    return "\n\n---\n\n".join(texts)


def extract_mobi(mobi_path: Path) -> str:
    """提取 MOBI 文本"""
    # mobi.extract 会解压到临时目录
    tempdir, filepath = mobi.extract(str(mobi_path))

    try:
        # filepath 是解压后的 HTML 文件路径
        html_path = Path(filepath)
        if html_path.exists():
            content = html_path.read_text(encoding='utf-8', errors='ignore')
            soup = BeautifulSoup(content, 'html.parser')
            text = soup.get_text(separator='\n')
            return text
        else:
            # 尝试查找目录中的 HTML 文件
            temp_path = Path(tempdir)
            for html_file in temp_path.rglob("*.html"):
                content = html_file.read_text(encoding='utf-8', errors='ignore')
                soup = BeautifulSoup(content, 'html.parser')
                text = soup.get_text(separator='\n')
                if len(text) > 1000:  # 找到有效内容
                    return text
            return ""
    finally:
        # 清理临时目录
        shutil.rmtree(tempdir, ignore_errors=True)


def clean_filename(name: str) -> str:
    """清理文件名，只保留书名"""
    # 移除作者、ISBN 等信息
    name = name.split(" -- ")[0]
    # 移除繁体标记
    name = name.replace("(繁)", "").replace("（繁）", "")
    return name.strip()


def main():
    # 路径配置
    source_dir = Path(__file__).parent.parent / "lifee" / "roles" / "krishnamurti" / "原文"
    output_dir = Path(__file__).parent.parent / "lifee" / "roles" / "krishnamurti" / "knowledge" / "books"

    if not source_dir.exists():
        print(f"源目录不存在: {source_dir}")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    # 处理所有文件
    files = (
        list(source_dir.glob("*.pdf")) +
        list(source_dir.glob("*.epub")) +
        list(source_dir.glob("*.mobi"))
    )

    if not files:
        print("没有找到 PDF、EPUB 或 MOBI 文件")
        return

    print(f"找到 {len(files)} 个文件\n")

    success_count = 0
    fail_count = 0

    for file_path in files:
        book_name = clean_filename(file_path.stem)
        output_path = output_dir / f"{book_name}.txt"

        print(f"处理: {book_name}")
        print(f"  来源: {file_path.suffix.upper()}")

        try:
            suffix = file_path.suffix.lower()
            if suffix == ".pdf":
                text = extract_pdf(file_path)
            elif suffix == ".epub":
                text = extract_epub(file_path)
            elif suffix == ".mobi":
                text = extract_mobi(file_path)
            else:
                print(f"  跳过: 不支持的格式")
                continue

            # 检查是否有有效内容
            if len(text.strip()) < 500:
                print(f"  警告: 内容过少 ({len(text)} 字符)，可能是扫描版")
                fail_count += 1
                continue

            # 写入文件
            output_path.write_text(text, encoding="utf-8")

            # 统计
            char_count = len(text)
            line_count = text.count('\n')
            print(f"  输出: {output_path.name}")
            print(f"  字符: {char_count:,}, 行数: {line_count:,}")
            print()
            success_count += 1

        except Exception as e:
            print(f"  错误: {e}")
            print()
            fail_count += 1

    print(f"\n完成！成功: {success_count}, 失败: {fail_count}")
    print(f"输出目录: {output_dir}")


if __name__ == "__main__":
    main()
