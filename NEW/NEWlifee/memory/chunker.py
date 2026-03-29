"""
文档分块模块

策略：优先按 Markdown 标题（##）切分章节，章节过长按段落切，过短则合并。
最终兜底按字符数硬切。
"""

import hashlib
import re
from dataclasses import dataclass


@dataclass
class Chunk:
    """文档分块"""
    text: str
    start_line: int
    end_line: int
    hash: str

    @staticmethod
    def compute_hash(text: str) -> str:
        """计算文本的 SHA256 哈希"""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# 标题正则：Markdown（# ~ ######）+ 中文章节标记
_HEADING_RE = re.compile(
    r"^#{1,6}\s+"           # Markdown: # Title
    r"|^【.+】\s*$"          # 中文卷标：【第一卷 事实与神话】
    r"|^第[一二三四五六七八九十\d]+[部章节篇卷]\s"  # 第X章/部/节/篇/卷
    r"|^Part\s+\w+"          # Part One / Part 1
    r"|^Chapter\s+\w+"       # Chapter One / Chapter 1
)


def chunk_markdown(
    content: str,
    max_tokens: int = 400,
    overlap_tokens: int = 80,
) -> list[Chunk]:
    """
    将 Markdown 文档分块

    策略优先级：
    1. 按 Markdown 标题切分章节
    2. 章节过长 → 按空行（段落）再切
    3. 段落仍然过长 → 按字符数硬切（兜底）
    4. 相邻小章节合并（不超过 max_tokens）

    Args:
        content: 文档内容
        max_tokens: 每块最大 token 数（估算 4 chars/token）
        overlap_tokens: 块之间重叠的 token 数（仅硬切时使用）

    Returns:
        分块列表
    """
    max_chars = max(32, max_tokens * 4)
    overlap_chars = max(0, overlap_tokens * 4)

    lines = content.split("\n")
    if not lines:
        return []

    # ── 第一步：按标题切分成章节 ──
    sections = _split_by_headings(lines)

    # ── 第二步：大章节按段落再切，段落过长兜底硬切 ──
    pieces: list[tuple[int, int, str]] = []  # (start_line, end_line, text)
    for start, end, text in sections:
        if len(text) <= max_chars:
            pieces.append((start, end, text))
        else:
            pieces.extend(_split_by_paragraphs(lines, start, end, max_chars, overlap_chars))

    # ── 第三步：合并过小的相邻块 ──
    merged = _merge_small_pieces(pieces, max_chars)

    # ── 生成 Chunk 对象 ──
    chunks = []
    for start, end, text in merged:
        text = text.strip()
        if text:
            chunks.append(Chunk(
                text=text,
                start_line=start,
                end_line=end,
                hash=Chunk.compute_hash(text),
            ))

    return chunks


def _split_by_headings(lines: list[str]) -> list[tuple[int, int, str]]:
    """按 Markdown 标题切分，返回 (start_line, end_line, text) 列表"""
    sections: list[tuple[int, int, str]] = []
    current_start = 0
    current_lines: list[str] = []

    for i, line in enumerate(lines):
        if _HEADING_RE.match(line) and current_lines:
            # 遇到新标题，保存之前的章节
            text = "\n".join(current_lines)
            sections.append((current_start, i - 1, text))
            current_start = i
            current_lines = [line]
        else:
            current_lines.append(line)

    # 最后一个章节
    if current_lines:
        text = "\n".join(current_lines)
        sections.append((current_start, len(lines) - 1, text))

    return sections


def _split_by_paragraphs(
    lines: list[str], start: int, end: int,
    max_chars: int, overlap_chars: int,
) -> list[tuple[int, int, str]]:
    """将一个过长章节按段落（空行）切分，段落过长则硬切"""
    pieces: list[tuple[int, int, str]] = []
    current_lines: list[str] = []
    current_chars = 0
    block_start = start

    for i in range(start, end + 1):
        line = lines[i]
        line_chars = len(line) + 1
        is_blank = not line.strip()

        # 在空行处尝试断开（当前块已有内容且接近上限）
        if is_blank and current_lines and current_chars > max_chars * 0.3:
            if current_chars + line_chars > max_chars:
                text = "\n".join(current_lines)
                pieces.append((block_start, i - 1, text))
                current_lines = []
                current_chars = 0
                block_start = i + 1
                continue

        # 硬切兜底：当前块超过上限
        if current_chars + line_chars > max_chars and current_lines:
            text = "\n".join(current_lines)
            pieces.append((block_start, i - 1, text))

            # 重叠
            overlap_lines = []
            overlap_total = 0
            for prev_line in reversed(current_lines):
                prev_chars = len(prev_line) + 1
                if overlap_total + prev_chars <= overlap_chars:
                    overlap_lines.insert(0, prev_line)
                    overlap_total += prev_chars
                else:
                    break

            current_lines = overlap_lines
            current_chars = overlap_total
            block_start = i - len(overlap_lines)

        current_lines.append(line)
        current_chars += line_chars

    # 剩余部分
    if current_lines:
        text = "\n".join(current_lines)
        pieces.append((block_start, end, text))

    return pieces


def _merge_small_pieces(
    pieces: list[tuple[int, int, str]], max_chars: int,
    min_chars: int = 200,
) -> list[tuple[int, int, str]]:
    """合并过小的相邻块（小于 min_chars 的尝试与下一块合并）"""
    if not pieces:
        return []

    merged: list[tuple[int, int, str]] = []
    current_start, current_end, current_text = pieces[0]

    for start, end, text in pieces[1:]:
        combined_len = len(current_text) + len(text) + 1  # +1 for newline
        if len(current_text) < min_chars and combined_len <= max_chars:
            # 合并
            current_text = current_text + "\n" + text
            current_end = end
        else:
            merged.append((current_start, current_end, current_text))
            current_start, current_end, current_text = start, end, text

    merged.append((current_start, current_end, current_text))
    return merged


def chunk_file(
    path: str,
    max_tokens: int = 400,
    overlap_tokens: int = 80,
) -> list[Chunk]:
    """
    读取文件并分块

    Args:
        path: 文件路径
        max_tokens: 每块最大 token 数
        overlap_tokens: 重叠 token 数

    Returns:
        分块列表
    """
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    return chunk_markdown(content, max_tokens, overlap_tokens)
