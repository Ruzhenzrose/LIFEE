"""
流式过滤器 - 参考 clawdbot 的 stripBlockTags 机制

在流式输出时过滤格式泄露（如 <msg from="...">、</msg>、--- 等）
"""
import re
from typing import List


class StreamingFilter:
    """
    有状态的流式过滤器

    策略：
    1. 遇到 '<' 时开始缓冲，直到看到 '>' 或确定不是标签
    2. 完整标签匹配过滤模式时丢弃
    3. 在代码块内不过滤（保护代码中的 <msg> 等）
    4. 检测 --- 分隔线并丢弃
    """

    # 需要过滤的标签模式
    FILTER_PATTERNS = [
        re.compile(r'^<msg from="[^"]*">\s*'),  # <msg from="拉康">
        re.compile(r'^\s*</msg>\s*$'),           # </msg>
    ]

    # 需要过滤的特殊令牌
    SKIP_TOKEN = "[[PASS]]"

    def __init__(self):
        self.buffer = ""           # 缓冲未完成的内容
        self.in_code_block = False # 是否在代码块内
        self.pending_newlines = 0  # 待输出的换行数（用于处理 --- 前后的换行）

    def process(self, chunk: str) -> str:
        """
        处理一个 chunk，返回可以安全输出的内容

        Args:
            chunk: LLM 输出的一个片段

        Returns:
            过滤后可以显示的内容
        """
        self.buffer += chunk
        output = ""

        while self.buffer:
            # 检测代码块边界
            if self._at_code_fence():
                # 输出代码块标记，切换状态
                fence_end = self.buffer.find('\n')
                if fence_end == -1:
                    # 代码块标记不完整，等待更多输入
                    break
                fence_line = self.buffer[:fence_end + 1]
                self.buffer = self.buffer[fence_end + 1:]
                self.in_code_block = not self.in_code_block
                output += fence_line
                continue

            # 在代码块内，直接输出所有内容
            if self.in_code_block:
                output += self.buffer
                self.buffer = ""
                break

            # 检测 --- 分隔线（可能在换行后）
            separator_match = self._find_separator_line()
            if separator_match is not None:
                start, end = separator_match
                # 输出分隔线之前的内容（不含紧邻的换行）
                before = self.buffer[:start].rstrip('\n')
                if before:
                    output += before
                # 跳过分隔线
                self.buffer = self.buffer[end:]
                continue

            # 检测 [[PASS]] 跳过令牌
            skip_match = self._find_skip_token()
            if skip_match is not None:
                start, end = skip_match
                # 输出令牌之前的内容
                before = self.buffer[:start]
                if before:
                    output += before
                # 跳过令牌
                self.buffer = self.buffer[end:]
                continue

            # 检查是否有未完成的 [[ 可能是 [[PASS]] 的开头
            double_bracket = self.buffer.find('[[')
            if double_bracket >= 0:
                # 检查 [[ 之后是否有 ]]
                close_bracket = self.buffer.find(']]', double_bracket)
                if close_bracket == -1:
                    # 未完成，输出 [[ 之前的内容，等待更多输入
                    if double_bracket > 0:
                        output += self.buffer[:double_bracket]
                        self.buffer = self.buffer[double_bracket:]
                    break

            # 查找 < 的位置
            lt_pos = self.buffer.find('<')

            if lt_pos == -1:
                # 没有 <，检查是否可能有未完成的 ---
                # 如果 buffer 以换行结尾且可能有 --- 在下一个 chunk
                if self.buffer.endswith('\n') or self.buffer.endswith('-'):
                    # 保守起见，检查最后是否可能是 --- 的开头
                    last_newline = self.buffer.rfind('\n')
                    if last_newline >= 0:
                        after_newline = self.buffer[last_newline + 1:]
                        if after_newline.strip() in ('', '-', '--', '---'):
                            # 输出换行前的内容，保留可能的 --- 在缓冲区
                            output += self.buffer[:last_newline + 1]
                            self.buffer = after_newline
                            break
                # 全部输出
                output += self.buffer
                self.buffer = ""
            elif lt_pos > 0:
                # < 之前的内容可以输出
                output += self.buffer[:lt_pos]
                self.buffer = self.buffer[lt_pos:]
            else:
                # buffer 以 < 开头
                gt_pos = self.buffer.find('>')
                if gt_pos == -1:
                    # 标签未完成，等待更多输入
                    # 但如果缓冲太长（>50字符），可能不是标签
                    if len(self.buffer) > 50:
                        output += self.buffer[0]
                        self.buffer = self.buffer[1:]
                    else:
                        break
                else:
                    # 完整的标签
                    tag = self.buffer[:gt_pos + 1]
                    rest = self.buffer[gt_pos + 1:]

                    # 检查是否需要过滤
                    if self._should_filter(tag):
                        # 丢弃标签，保留后面的内容
                        self.buffer = rest.lstrip()  # 移除标签后的前导空白
                    else:
                        # 不过滤，输出标签
                        output += tag
                        self.buffer = rest

        return output

    def _should_filter(self, text: str) -> bool:
        """检查文本是否应该被过滤"""
        for pattern in self.FILTER_PATTERNS:
            if pattern.match(text):
                return True
        return False

    def _find_skip_token(self) -> tuple[int, int] | None:
        """
        查找 buffer 中的 [[PASS]] 跳过令牌

        Returns:
            (start, end) 如果找到，返回其位置
            None 如果没有找到
        """
        pos = self.buffer.find(self.SKIP_TOKEN)
        if pos >= 0:
            return pos, pos + len(self.SKIP_TOKEN)
        return None

    def _find_separator_line(self) -> tuple[int, int] | None:
        """
        查找 buffer 中的 --- 分隔线

        Returns:
            (start, end) 如果找到分隔线，返回其位置（包含前后换行）
            None 如果没有找到
        """
        # 使用正则匹配 --- 分隔线（单独一行，可能有前后换行）
        match = re.search(r'(\n\s*---\s*\n|\n\s*---\s*$|^\s*---\s*\n|^\s*---\s*$)', self.buffer)
        if match:
            return match.start(), match.end()
        return None

    def _at_code_fence(self) -> bool:
        """检查是否在代码块边界"""
        return self.buffer.startswith('```')

    def flush(self) -> str:
        """
        刷新缓冲区（流结束时调用）

        Returns:
            剩余的可输出内容
        """
        result = self.buffer
        self.buffer = ""

        # 最后检查一次是否需要过滤
        if self._should_filter(result):
            return ""
        if result.strip() == '---':
            return ""
        # 过滤 [[PASS]] 令牌
        if self.SKIP_TOKEN in result:
            result = result.replace(self.SKIP_TOKEN, "")

        return result


class SimpleStreamingFilter:
    """
    简化版流式过滤器 - 只处理开头和结尾的标签

    延迟更小，适合大多数场景。
    """

    def __init__(self):
        self.buffer = ""
        self.header_checked = False
        self.header_size = 35  # 检查前 35 个字符（足够容纳 <msg from="长名字">）
        self.tail_buffer = ""  # 用于检测结尾的 </msg>

    def process(self, chunk: str) -> str:
        """处理一个 chunk"""
        if self.header_checked:
            # 已经检查过开头
            # 累积最后 10 个字符用于检测 </msg>
            combined = self.tail_buffer + chunk
            self.tail_buffer = combined[-10:] if len(combined) >= 10 else combined
            return chunk

        self.buffer += chunk

        if len(self.buffer) < self.header_size:
            # 继续缓冲
            return ""

        # 检查开头是否有 <msg from="...">
        self.header_checked = True
        cleaned = re.sub(r'^<msg from="[^"]*">\s*', '', self.buffer)
        # 也检查 --- 开头
        cleaned = re.sub(r'^---\s*\n?', '', cleaned)
        self.tail_buffer = cleaned[-10:] if len(cleaned) >= 10 else cleaned
        return cleaned

    def flush(self) -> str:
        """刷新缓冲区"""
        if not self.header_checked:
            self.header_checked = True
            cleaned = re.sub(r'^<msg from="[^"]*">\s*', '', self.buffer)
            cleaned = re.sub(r'^---\s*\n?', '', cleaned)
        else:
            cleaned = ""

        # 检查结尾是否有 </msg>
        # 注意：这里不能直接修改已输出的内容，只能处理最后的缓冲
        if self.tail_buffer.rstrip().endswith('</msg>'):
            # 返回空，因为 </msg> 已经在之前的 chunk 中输出了
            # 这是简化版的限制
            pass

        return cleaned


# 导出默认使用的过滤器
DefaultStreamingFilter = StreamingFilter
