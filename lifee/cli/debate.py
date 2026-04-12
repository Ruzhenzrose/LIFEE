"""统一对话循环"""
import asyncio
import re
import sys
import unicodedata
import msvcrt
from pathlib import Path
from typing import List, Optional, Tuple

from lifee.config.settings import settings
from lifee.providers import LLMProvider
from lifee.providers.base import MediaItem, Message, MessageRole
from lifee.sessions import Session, DebateSessionStore
from lifee.roles import RoleManager
from lifee.debate import Moderator, Participant, DebateContext, clean_response
from lifee.debate.suggestions import SuggestionGenerator
from lifee.memory import UserMemory
from .i18n import t
from .setup import select_provider_interactive, select_model_for_provider, select_menu_interactive, select_roles_interactive


_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}

SLASH_COMMANDS = [
    ("/help",     "显示帮助"),
    ("/history",  "查看对话历史"),
    ("/clear",    "清除对话历史"),
    ("/sessions", "查看历史会话"),
    ("/memory",   "知识库状态"),
    ("/me",       "查看/编辑我的档案"),
    ("/roles",    "增删角色 / 调整发言人数"),
    ("/config",   "切换 Provider"),
    ("/model",    "切换模型"),
    ("/menu",     "返回主菜单"),
    ("/quit",     "退出程序"),
]


def get_clipboard_image() -> Optional[MediaItem]:
    """从 Windows 剪贴板读取图片

    支持两种剪贴板内容:
    1. 截图 (Image) — Win+Shift+S 等截图工具
    2. 复制的图片文件 (FileDropList) — 资源管理器中 Ctrl+C 复制图片
    """
    import subprocess
    import tempfile

    temp_path = Path(tempfile.gettempdir()) / "lifee_clipboard.png"

    # PowerShell: 先检查 Image，再检查 FileDropList
    ps_script = (
        'Add-Type -Assembly System.Windows.Forms;'
        '$img = [System.Windows.Forms.Clipboard]::GetImage();'
        f'if ($img) {{ $img.Save(\"{temp_path}\"); Write-Output \"IMAGE\" }}'
        ' else {'
        '  $files = [System.Windows.Forms.Clipboard]::GetFileDropList();'
        '  if ($files.Count -gt 0) { Write-Output (\"FILE:\" + $files[0]) }'
        '  else { Write-Output \"NO\" }'
        '}'
    )

    try:
        result = subprocess.run(
            ['powershell', '-NoProfile', '-Command', ps_script],
            capture_output=True, text=True, timeout=5,
        )
        output = result.stdout.strip()

        if output == "IMAGE" and temp_path.exists():
            item = MediaItem.from_file(str(temp_path))
            item.filename = "clipboard.png"
            return item

        if output.startswith("FILE:"):
            filepath = output[5:]
            ext = Path(filepath).suffix.lower()
            if ext in _IMAGE_EXTENSIONS:
                return MediaItem.from_file(filepath)
            # 不是图片文件，忽略

    except Exception:
        pass
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)

    return None


def parse_media_from_input(text: str) -> Tuple[str, List[MediaItem]]:
    """从用户输入中提取图片

    支持三种方式:
        1. @路径:     @photo.jpg  @"C:/path with spaces/img.jpg"
        2. @clipboard: 从剪贴板粘贴截图
        3. 拖入文件:   自动检测图片路径（无需 @ 前缀）

    Returns:
        (清理后的文本, 媒体列表)
    """
    media = []
    errors = []
    has_clipboard = False

    # ── Pass 1: @"path" 和 @path 模式 ──
    def replace_at_match(m):
        nonlocal has_clipboard
        path = m.group(1) or m.group(2)
        if path.lower() == 'clipboard':
            has_clipboard = True
            return ""
        try:
            item = MediaItem.from_file(path)
            media.append(item)
            return ""
        except (FileNotFoundError, ValueError) as e:
            errors.append(str(e))
            return ""

    clean_text = re.sub(r'@"([^"]+)"|@(\S+)', replace_at_match, text)

    # ── Pass 2: 自动检测拖入的图片路径 ──
    def replace_bare_path(m):
        path = m.group(1) or m.group(2)
        if not path or path.startswith(('http://', 'https://')):
            return m.group(0)
        p = Path(path)
        if p.suffix.lower() not in _IMAGE_EXTENSIONS:
            return m.group(0)
        try:
            resolved = p.expanduser().resolve()
            if not resolved.exists():
                return m.group(0)
            item = MediaItem.from_file(str(resolved))
            media.append(item)
            return ""
        except (FileNotFoundError, ValueError):
            return m.group(0)

    clean_text = re.sub(
        r'"([^"]+\.(?:jpg|jpeg|png|gif|webp))"|(\S+\.(?:jpg|jpeg|png|gif|webp))',
        replace_bare_path,
        clean_text,
        flags=re.IGNORECASE,
    )

    # ── Pass 3: @clipboard 剪贴板 ──
    if has_clipboard:
        sys.stdout.write("  ⏳ 读取剪贴板...")
        sys.stdout.flush()
        item = get_clipboard_image()
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()
        if item:
            media.append(item)
        else:
            errors.append("剪贴板中没有图片")

    # 清理多余空格
    clean_text = re.sub(r'  +', ' ', clean_text).strip()

    for err in errors:
        print(f"  ⚠ {err}")

    return clean_text, media


def _char_width(c: str) -> int:
    """获取字符的显示宽度（中文等宽字符为 2）"""
    w = unicodedata.east_asian_width(c)
    return 2 if w in ('F', 'W') else 1


def input_with_clipboard(prompt: str, participants: Optional[list] = None) -> Tuple[str, List[MediaItem]]:
    """带剪贴板粘贴 + slash 命令菜单 + @mention 菜单的自定义输入函数

    功能:
        - Ctrl+V / Alt+V: 粘贴剪贴板图片
        - Backspace: 文本为空时删除最后一张图片
        - /: 触发 slash 命令菜单（方向键导航，继续输入过滤）
        - @: 触发角色 mention 菜单（多角色对话时）
        - ESC: 关闭菜单

    Returns:
        (输入文本, 剪贴板媒体列表)
    """
    sys.stdout.write(prompt)
    sys.stdout.flush()

    import shutil
    chars = []
    cursor_pos = 0  # 光标在 chars 中的位置（0 = 最左）
    prompt_width = sum(_char_width(c) for c in prompt)
    rendered_cursor_tw = prompt_width  # 上次渲染后光标对应的文本宽度（含 prompt）
    media = []
    has_attachment_line = False

    # slash 菜单状态
    in_slash_mode = False
    slash_cursor = 0
    slash_prev_count = 0  # 上次绘制的菜单行数

    # @mention 菜单状态
    in_mention_mode = False
    mention_cursor = 0
    mention_prev_count = 0
    mention_items = []  # [(display, role_name), ...]
    if participants and len(participants) > 1:
        mention_items = [(f"{p.info.emoji} {p.info.display_name}", f"@{p.role_name} ") for p in participants]

    def _tail_width():
        """光标右侧字符的显示宽度（用于回移光标）"""
        return sum(_char_width(c) for c in chars[cursor_pos:])

    def _redraw_line():
        """重绘输入行，光标定位到 cursor_pos（正确处理多行换行）"""
        nonlocal rendered_cursor_tw
        term_width = shutil.get_terminal_size().columns
        cursor_text_width = prompt_width + sum(_char_width(c) for c in chars[:cursor_pos])
        total_width = prompt_width + sum(_char_width(c) for c in chars)

        # 物理光标行 = 上次渲染后记录的文本宽度 // 终端宽度
        phys_row = rendered_cursor_tw // term_width
        if phys_row > 0:
            sys.stdout.write(f"\033[{phys_row}A")
        # 从第一行行首清到屏幕底，重写全部内容
        sys.stdout.write(f"\r\033[J{prompt}{''.join(chars)}")

        # 写完后光标在文本末尾，计算末尾和目标的行列差，回移光标
        end_row = total_width // term_width
        target_row = cursor_text_width // term_width
        target_col = cursor_text_width % term_width
        rows_up = end_row - target_row
        if rows_up > 0:
            sys.stdout.write(f"\033[{rows_up}A")
        sys.stdout.write("\r")
        if target_col > 0:
            sys.stdout.write(f"\033[{target_col}C")

        rendered_cursor_tw = cursor_text_width  # 更新物理光标位置记录
        sys.stdout.flush()

    def _redraw():
        """重绘附件行 + 输入行"""
        nonlocal has_attachment_line, rendered_cursor_tw
        if has_attachment_line:
            sys.stdout.write("\033[1A")
        sys.stdout.write("\r\033[J")
        if media:
            names = ", ".join(m.filename for m in media)
            sys.stdout.write(f"  📎 {names}\n")
            has_attachment_line = True
        else:
            has_attachment_line = False
        sys.stdout.write(f"{prompt}{''.join(chars)}")
        tw = _tail_width()
        if tw > 0:
            sys.stdout.write(f"\033[{tw}D")
        cursor_text_width = prompt_width + sum(_char_width(c) for c in chars[:cursor_pos])
        rendered_cursor_tw = cursor_text_width
        sys.stdout.flush()

    def _do_paste():
        """读取剪贴板图片并重绘"""
        sys.stdout.write(" ⏳")
        sys.stdout.flush()
        item = get_clipboard_image()
        if item:
            media.append(item)
        _redraw()

    def _get_slash_filtered():
        prefix = "".join(chars).lower()
        return [(cmd, desc) for cmd, desc in SLASH_COMMANDS if cmd.startswith(prefix)]

    def _draw_slash_menu():
        """在输入行下方绘制/更新 slash 菜单。光标最终停在输入行末尾。"""
        nonlocal slash_prev_count
        filtered = _get_slash_filtered()
        n = len(filtered)
        # 绘制菜单行（每行以 \n\r 开头，保证从列 0 开始）
        for i, (cmd, desc) in enumerate(filtered):
            pointer = ">" if i == slash_cursor else " "
            hi_start = "\033[7m" if i == slash_cursor else ""
            hi_end   = "\033[0m" if i == slash_cursor else ""
            sys.stdout.write(f"\n\r\033[2K  {hi_start}{pointer} {cmd:<12} {desc}{hi_end}")
        # 清除上次多余的旧行
        for _ in range(slash_prev_count - n):
            sys.stdout.write("\n\r\033[2K")
        total = max(n, slash_prev_count)
        if total > 0:
            # 回到输入行
            sys.stdout.write(f"\033[{total}A\r{prompt}{''.join(chars)}")
        sys.stdout.flush()
        slash_prev_count = n

    def _clear_slash_menu():
        """清除菜单，光标保持在输入行末尾。"""
        nonlocal slash_prev_count
        if slash_prev_count > 0:
            for _ in range(slash_prev_count):
                sys.stdout.write("\n\r\033[2K")
            sys.stdout.write(f"\033[{slash_prev_count}A\r{prompt}{''.join(chars)}")
            sys.stdout.flush()
        slash_prev_count = 0

    def _get_mention_filtered():
        # @后面输入的文字用于过滤
        text = "".join(chars)
        if "@" in text:
            filter_text = text[text.index("@") + 1:].lower()
        else:
            filter_text = ""
        return [(display, value) for display, value in mention_items
                if not filter_text or filter_text in display.lower() or filter_text in value.lower()]

    def _draw_mention_menu():
        """在输入行下方绘制 @mention 菜单。"""
        nonlocal mention_prev_count
        filtered = _get_mention_filtered()
        n = len(filtered)
        for i, (display, _) in enumerate(filtered):
            pointer = ">" if i == mention_cursor else " "
            hi_start = "\033[7m" if i == mention_cursor else ""
            hi_end   = "\033[0m" if i == mention_cursor else ""
            sys.stdout.write(f"\n\r\033[2K  {hi_start}{pointer} {display}{hi_end}")
        for _ in range(mention_prev_count - n):
            sys.stdout.write("\n\r\033[2K")
        total = max(n, mention_prev_count)
        if total > 0:
            sys.stdout.write(f"\033[{total}A\r{prompt}{''.join(chars)}")
        sys.stdout.flush()
        mention_prev_count = n

    def _clear_mention_menu():
        """清除 @mention 菜单。"""
        nonlocal mention_prev_count
        if mention_prev_count > 0:
            for _ in range(mention_prev_count):
                sys.stdout.write("\n\r\033[2K")
            sys.stdout.write(f"\033[{mention_prev_count}A\r{prompt}{''.join(chars)}")
            sys.stdout.flush()
        mention_prev_count = 0

    while True:
        char = msvcrt.getwch()

        if char == "\r":  # Enter
            if in_slash_mode:
                filtered = _get_slash_filtered()
                # 清除菜单行
                for _ in range(slash_prev_count):
                    sys.stdout.write("\n\r\033[2K")
                if slash_prev_count > 0:
                    sys.stdout.write(f"\033[{slash_prev_count}A")
                if filtered:
                    idx = min(slash_cursor, len(filtered) - 1)
                    selected = filtered[idx][0]
                    sys.stdout.write(f"\r\033[K{prompt}{selected}\n")
                    sys.stdout.flush()
                    return selected, media
                else:
                    # 无匹配，直接提交当前输入
                    sys.stdout.write(f"\r\033[K{prompt}{''.join(chars)}\n")
                    sys.stdout.flush()
                    return "".join(chars).strip(), media
            elif in_mention_mode:
                filtered = _get_mention_filtered()
                _clear_mention_menu()
                in_mention_mode = False
                if filtered:
                    idx = min(mention_cursor, len(filtered) - 1)
                    selected_value = filtered[idx][1]  # e.g. "@turing "
                    chars.clear()
                    chars.extend(selected_value)
                    cursor_pos = len(chars)
                    sys.stdout.write(f"\r\033[K{prompt}{''.join(chars)}")
                    rendered_cursor_tw = prompt_width + sum(_char_width(c) for c in chars)
                    sys.stdout.flush()
                    continue
                else:
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    break
            else:
                sys.stdout.write("\n")
                sys.stdout.flush()
                break

        elif char == "\x1b":  # ESC — 关闭菜单
            if in_slash_mode:
                _clear_slash_menu()
                in_slash_mode = False
                slash_cursor = 0
            elif in_mention_mode:
                _clear_mention_menu()
                in_mention_mode = False
                mention_cursor = 0

        elif char == "\x08":  # Backspace
            if in_slash_mode:
                if chars:
                    chars.pop()
                    cursor_pos = len(chars)
                    if not chars:
                        _clear_slash_menu()
                        in_slash_mode = False
                    else:
                        slash_cursor = 0
                        _draw_slash_menu()
                else:
                    _clear_slash_menu()
                    in_slash_mode = False
            elif in_mention_mode:
                if chars:
                    chars.pop()
                    cursor_pos = len(chars)
                    if "@" not in "".join(chars):
                        _clear_mention_menu()
                        in_mention_mode = False
                    else:
                        mention_cursor = 0
                        _draw_mention_menu()
                else:
                    _clear_mention_menu()
                    in_mention_mode = False
            else:
                if cursor_pos > 0:
                    chars.pop(cursor_pos - 1)
                    cursor_pos -= 1
                    _redraw_line()
                elif media:
                    media.pop()
                    _redraw()

        elif char == "\x03":  # Ctrl+C
            if in_slash_mode:
                _clear_slash_menu()
            raise KeyboardInterrupt

        elif char == "\x16":  # Ctrl+V
            if in_slash_mode:
                _clear_slash_menu()
                in_slash_mode = False
            _do_paste()

        elif char == "\x00":  # Special key prefix (Alt+key)
            scan = msvcrt.getwch()
            if ord(scan) == 0x2F:  # Alt+V
                if in_slash_mode:
                    _clear_slash_menu()
                    in_slash_mode = False
                _do_paste()

        elif char == "\xe0":  # Extended key (方向键等)
            arrow = msvcrt.getwch()
            if in_slash_mode:
                filtered = _get_slash_filtered()
                n = max(1, len(filtered))
                if arrow == "\x48":  # 上
                    slash_cursor = (slash_cursor - 1) % n
                    _draw_slash_menu()
                elif arrow == "\x50":  # 下
                    slash_cursor = (slash_cursor + 1) % n
                    _draw_slash_menu()
            elif in_mention_mode:
                filtered = _get_mention_filtered()
                n = max(1, len(filtered))
                if arrow == "\x48":  # 上
                    mention_cursor = (mention_cursor - 1) % n
                    _draw_mention_menu()
                elif arrow == "\x50":  # 下
                    mention_cursor = (mention_cursor + 1) % n
                    _draw_mention_menu()
            else:
                if arrow == "\x4b":  # 左
                    if cursor_pos > 0:
                        cursor_pos -= 1
                        _redraw_line()
                elif arrow == "\x4d":  # 右
                    if cursor_pos < len(chars):
                        cursor_pos += 1
                        _redraw_line()
                elif arrow == "\x47":  # Home
                    if cursor_pos > 0:
                        cursor_pos = 0
                        _redraw_line()
                elif arrow == "\x4f":  # End
                    if cursor_pos < len(chars):
                        cursor_pos = len(chars)
                        _redraw_line()
                elif arrow == "\x53":  # Delete（向前删）
                    if cursor_pos < len(chars):
                        chars.pop(cursor_pos)
                        _redraw_line()

        elif ord(char) >= 32:  # 可打印字符
            chars.insert(cursor_pos, char)
            cursor_pos += 1
            if cursor_pos == len(chars):
                sys.stdout.write(char)
                rendered_cursor_tw += _char_width(char)  # 追踪物理光标位置
                sys.stdout.flush()
            else:
                _redraw_line()

            if char == "/" and len(chars) == 1:
                # 进入 slash 菜单模式
                in_slash_mode = True
                slash_cursor = 0
                _draw_slash_menu()
            elif in_slash_mode:
                # 继续输入 — 更新过滤
                slash_cursor = 0
                filtered = _get_slash_filtered()
                if filtered:
                    _draw_slash_menu()
                else:
                    _clear_slash_menu()
                    in_slash_mode = False
            elif char == "@" and len(chars) == 1 and mention_items:
                # 进入 @mention 菜单模式
                in_mention_mode = True
                mention_cursor = 0
                _draw_mention_menu()
            elif in_mention_mode:
                # 继续输入 — 更新过滤
                mention_cursor = 0
                filtered = _get_mention_filtered()
                if filtered:
                    _draw_mention_menu()
                else:
                    _clear_mention_menu()
                    in_mention_mode = False

    return "".join(chars).strip(), media


async def show_suggestion_menu(
    suggestion_generator,
    session,
) -> tuple[str, bool]:
    """
    显示建议回复菜单（输入框 + 建议列表混合 UI）

    默认处于输入模式，光标在输入框中可直接打字。
    按 ↓ 进入选择模式浏览建议，按 ↑ 回到输入模式。

    Returns:
        (选择的文本, 是否保持沉默)
        - 自由输入: ("输入文本", False)
        - 选择建议: ("建议文本", False)
        - 保持沉默: ("", True)
        - ESC取消: ("", False)
    """
    print(t("thinking_suggestions"), end="", flush=True)
    suggestions = await suggestion_generator.generate(session.get_messages())
    sys.stdout.write("\r\033[K")
    sys.stdout.flush()

    if not suggestions:
        suggestions = []

    # 截断建议文本，防止换行导致重绘错位
    import shutil
    term_width = shutil.get_terminal_size().columns

    def _char_w(ch):
        return 2 if unicodedata.east_asian_width(ch) in ('F', 'W') else 1

    def _str_w(s):
        return sum(_char_w(c) for c in s)

    def _truncate_by_width(s, max_w):
        """按显示宽度截断字符串"""
        w = 0
        for i, ch in enumerate(s):
            cw = _char_w(ch)
            if w + cw > max_w:
                return s[:i]
            w += cw
        return s

    max_opt_w = term_width - 8  # "  > N. " 前缀最宽 ~8 列
    display_suggestions = []
    for s in suggestions:
        if _str_w(s) > max_opt_w:
            display_suggestions.append(_truncate_by_width(s, max_opt_w - 2) + "..")
        else:
            display_suggestions.append(s)

    silence_idx = len(suggestions)  # 沉默选项在建议列表末尾
    select_options = suggestions + [t("silence_option")]
    display_select = display_suggestions + [t("silence_option")]

    # 状态
    mode = "input"  # "input" 或 "select"
    buf = []  # 输入缓冲区
    cursor_pos = 0  # 输入光标位置
    sel_cursor = 0  # 选择模式光标
    input_prefix = t("input_prompt")  # "你: "
    # 固定行数 = 提示行 + 输入行 + 建议行数（输入行不换行，所以行数恒定）
    total_lines = 1 + 1 + len(select_options)

    # 输入行可用的最大显示宽度（减去前缀和光标）
    prefix_str = f"  {input_prefix}"
    prefix_w = _str_w(prefix_str)
    max_input_w = term_width - prefix_w - 1  # -1 给光标方块留位置

    def _visible_slice(text, cursor_pos):
        """计算应该显示的文本范围，确保光标可见且不超过终端宽度。
        返回 (visible_before, visible_after)，都是字符串。"""
        before = text[:cursor_pos]
        after = text[cursor_pos:]
        before_w = _str_w(before)
        after_w = _str_w(after)

        if before_w + after_w <= max_input_w:
            return before, after

        # 优先显示光标左侧，剩余空间给右侧
        if before_w <= max_input_w:
            remaining = max_input_w - before_w
            vis_after = []
            w = 0
            for ch in after:
                cw = _char_w(ch)
                if w + cw > remaining:
                    break
                vis_after.append(ch)
                w += cw
            return before, "".join(vis_after)
        else:
            # 左侧也放不下，从光标往左截取能放下的部分
            vis_before = []
            w = 0
            for ch in reversed(before):
                cw = _char_w(ch)
                if w + cw > max_input_w:
                    break
                vis_before.append(ch)
                w += cw
            vis_before.reverse()
            return "".join(vis_before), ""

    # 截断提示行防止换行
    prompt_text = t('suggestion_prompt')
    if _str_w(prompt_text) >= term_width:
        prompt_text = _truncate_by_width(prompt_text, term_width - 2)

    def render(first_time=False):
        if not first_time:
            # \r 先回到当前行首，再往上跳 total_lines-1 行到菜单起始行
            # 关键：最后一行不写 \n，光标停在非零列，这样即使终端 echo 了
            # backspace（左移一列），光标仍在同一行，不会跳到上一行导致错位
            sys.stdout.write(f"\r\033[{total_lines - 1}A")
        sys.stdout.write(f"\033[2K{prompt_text}\n")
        # 输入行（单行，长文本滚动显示）
        text = "".join(buf)
        if mode == "input":
            vis_before, vis_after = _visible_slice(text, cursor_pos)
            sys.stdout.write(f"\033[2K  {input_prefix}{vis_before}\033[7m \033[27m{vis_after}\n")
        else:
            if _str_w(text) > max_input_w + 1:
                text = _truncate_by_width(text, max_input_w + 1)
            sys.stdout.write(f"\033[2K  {input_prefix}{text}\n")
        for i, opt in enumerate(display_select):
            if mode == "select" and i == sel_cursor:
                line = f"\033[2K  > {i + 1}. {opt}"
            else:
                line = f"\033[2K    {i + 1}. {opt}"
            # 最后一行不加 \n —— 光标留在行末非零列
            sys.stdout.write(line + ("\n" if i < len(display_select) - 1 else ""))
        sys.stdout.flush()

    # 预分配菜单空间（不含最后一行的 \n，所以是 total_lines - 1）
    sys.stdout.write("\n" * (total_lines - 1))
    sys.stdout.write(f"\033[{total_lines - 1}A")
    sys.stdout.write("\033[?25l")  # 隐藏终端光标
    render(first_time=True)

    result = ("", False)
    try:
        while True:
            ch = msvcrt.getwch()  # getwch 直接返回 Unicode 字符，支持中文

            if ch == "\r":  # 回车
                if mode == "input":
                    text = "".join(buf).strip()
                    if text:
                        result = (text, False)
                    # 空输入视同 ESC
                    break
                else:  # select mode
                    if sel_cursor == silence_idx:
                        result = ("", True)
                    else:
                        result = (select_options[sel_cursor], False)
                    break

            elif ch == "\x1b":  # ESC
                break

            elif ch == "\xe0":  # 方向键前缀
                arrow = msvcrt.getwch()
                if arrow == "P":  # ↓
                    if mode == "input":
                        mode = "select"
                        sel_cursor = 0
                    else:
                        sel_cursor = (sel_cursor + 1) % len(select_options)
                    render()
                elif arrow == "H":  # ↑
                    if mode == "select":
                        if sel_cursor == 0:
                            mode = "input"
                        else:
                            sel_cursor -= 1
                    render()
                elif arrow == "K":  # ←
                    if mode == "input" and cursor_pos > 0:
                        cursor_pos -= 1
                        render()
                elif arrow == "M":  # →
                    if mode == "input" and cursor_pos < len(buf):
                        cursor_pos += 1
                        render()

            elif ch == "\x08" or ch == "\x7f":  # Backspace 或 DEL
                if mode == "input" and buf and cursor_pos > 0:
                    buf.pop(cursor_pos - 1)
                    cursor_pos -= 1
                elif mode == "select":
                    mode = "input"
                    if buf and cursor_pos > 0:
                        buf.pop(cursor_pos - 1)
                        cursor_pos -= 1
                # 无论是否删除了字符，都重绘（防止终端 echo 破坏显示）
                render()

            elif ch not in ("\x00", "\xe0") and ord(ch) >= 32 and ch != "\x7f":
                # 可打印字符（包括中文）
                if mode == "select":
                    mode = "input"
                buf.insert(cursor_pos, ch)
                cursor_pos += 1
                render()
    finally:
        # 清理菜单区域，恢复终端光标
        sys.stdout.write(f"\r\033[{total_lines - 1}A\033[J\033[?25h")
        sys.stdout.flush()

    return result


def collect_user_input_nonblocking() -> str:
    """非阻塞收集用户输入（直到按回车）

    在对话过程中，当检测到用户按键时调用此函数。
    用户输入会实时回显到屏幕上。
    """
    chars = []
    sys.stdout.write(t("interject_prompt"))
    sys.stdout.flush()

    while True:
        if msvcrt.kbhit():
            # 使用 getwch 支持 Unicode（中文等）
            char = msvcrt.getwch()
            if char == '\r':  # 回车
                sys.stdout.write("\n")
                sys.stdout.flush()
                break
            elif char == '\x08':  # 退格
                if chars:
                    chars.pop()
                    # 删除屏幕上的字符
                    sys.stdout.write('\b \b')
                    sys.stdout.flush()
            elif char == '\x1b':  # ESC - 取消输入
                sys.stdout.write(f"\n{t('cancel')}\n")
                sys.stdout.flush()
                return ""
            elif ord(char) >= 32:  # 可打印字符
                chars.append(char)
                sys.stdout.write(char)
                sys.stdout.flush()

    return ''.join(chars)


async def _memory_search(km_participants, query):
    """在所有参与者的知识库中搜索并显示结果"""
    max_per_role = 5 if len(km_participants) == 1 else 3
    print(f"\n{t('searching').format(query=query)}")
    any_results = False
    for p in km_participants:
        results = await p.knowledge_manager.search(query, max_results=max_per_role)
        if results:
            any_results = True
            if len(km_participants) > 1:
                print(f"\n{t('knowledge_label').format(emoji=p.info.emoji, name=p.info.display_name)}")
                indent = "  "
            else:
                print()
                indent = ""
            for i, r in enumerate(results, 1):
                print(f"{indent}[{i}] {Path(r.path).name}:{r.start_line}-{r.end_line} (score: {r.score:.2f})")
                for line in r.text.strip().splitlines():
                    print(f"{indent}    {line}")
                print()
    if not any_results:
        print(f"{t('no_results')}")
    print()


async def debate_loop(
    participants: list[Participant],
    session: Session,
    provider: LLMProvider,
    session_store: DebateSessionStore,
    max_speakers_per_round: int = 0,
) -> tuple[str, str]:
    """统一对话循环

    Args:
        participants: 预创建的参与者列表
        session: 预创建或恢复的会话
        provider: LLM Provider
        session_store: 会话存储

    Returns:
        ("menu", "") - 返回主菜单
        ("quit", "") - 退出程序
    """
    role_manager = RoleManager()
    roles = role_manager.list_roles()
    user_memory = UserMemory()
    user_memory._last_extracted_msg_count = len(session.history)  # 跳过已有消息

    # 创建主持者（注入用户记忆上下文）
    memory_context = user_memory.get_context()
    moderator = Moderator(participants, session, user_memory_context=memory_context)

    # 创建建议生成器
    suggestion_generator = SuggestionGenerator(provider)

    # 显示欢迎信息
    print("\n" + "=" * 50)
    if len(participants) == 1:
        print(t("conversation_mode").format(emoji=participants[0].info.emoji, name=participants[0].info.display_name))
    else:
        print(t("discussion_mode"))
    print("=" * 50)
    if len(participants) > 1:
        print(t("participants"))
        for p in participants:
            print(f"  {p.info.emoji} {p.info.display_name}")
    print(t("start_conversation") if len(participants) == 1 else t("start_discussion"))
    print(t("commands_hint"))
    print("=" * 50 + "\n")

    # 如果是恢复的会话，显示历史对话记录
    if session.history:
        # 构建参与者 emoji 映射
        emoji_map = {p.info.display_name: p.info.emoji for p in participants}
        print(f"  ── 历史记录 ({len(session.history)} 条) ──\n")
        for msg in session.history:
            content = msg.content.strip()
            if not content:
                continue
            # 全部显示，不截断
            media_hint = ""
            if msg.media:
                names = ", ".join(m.filename for m in msg.media)
                media_hint = f" 📎{names}"
            if msg.role.value == "user":
                print(f"  👤 你: {content}{media_hint}")
            else:
                name = msg.name or "AI"
                emoji = emoji_map.get(name, "🤖")
                print(f"  {emoji} {name}: {content}")
            print()
        print(f"  ── 继续对话 ──\n")

    pending_suggestion = None  # 用于存储用户选择的建议
    session_title = ""  # 会话标题（只生成一次）

    while True:
        try:
            # 如果有待处理的建议选择，直接使用
            clipboard_media = []
            if pending_suggestion:
                user_input = pending_suggestion
                pending_suggestion = None
                if user_input == t("silence_prompt"):
                    print(t("silence_display"))
                else:
                    print(f"{t('input_prompt')}{user_input}")
            else:
                user_input, clipboard_media = input_with_clipboard(t("input_prompt"), participants=participants)

            if not user_input and not clipboard_media:
                continue

            # 处理命令
            if user_input.startswith("/"):
                cmd = user_input.lower()
                if cmd in ("/quit", "/exit"):
                    if session.history:
                        participant_names = [p.info.display_name for p in participants]
                        session_store.save(session, participant_names)
                        print(f"[{t('session_saved')}]")
                        print(f"[{t('profile_updating')}]", end="", flush=True)
                        updated = await user_memory.auto_extract(session.history, provider)
                        print(f"\r[{t('profile_updated') if updated else t('profile_unchanged')}]   ")
                    return ("quit", "")
                elif cmd == "/menu":
                    if session.history:
                        participant_names = [p.info.display_name for p in participants]
                        session_store.save(session, participant_names)
                        print(f"[{t('session_saved')}]")
                        print(f"[{t('profile_updating')}]", end="", flush=True)
                        updated = await user_memory.auto_extract(session.history, provider)
                        print(f"\r[{t('profile_updated') if updated else t('profile_unchanged')}]   ")
                    return ("menu", "")
                elif cmd == "/help":
                    print(t("help_title"))
                    print(t("help_help"))
                    print(t("help_history"))
                    print(t("help_clear"))
                    print(t("help_sessions"))
                    print(t("help_memory"))
                    print(t("help_config"))
                    print(t("help_model"))
                    print(t("help_menu"))
                    print(t("help_quit"))
                    print(t("help_image_title"))
                    print(t("help_image_ctrlv"))
                    print(t("help_image_atpath"))
                    print(t("help_image_drag"))
                    print(t("help_image_clipboard"))
                    print()
                elif cmd == "/clear":
                    session.clear_history()
                    session_store.clear()
                    print(f"\n[{t('history_cleared')}]\n")
                elif cmd == "/history":
                    if not session.history:
                        print(f"\n[{t('history_empty')}]\n")
                    else:
                        print(f"\n{t('history_title')}")
                        for msg in session.history:
                            if not msg.content.strip():
                                continue
                            if msg.role.value == "user":
                                print(f"\n[{t('you_label')}] {msg.content}")
                            else:
                                name = msg.name or "AI"
                                print(f"\n[{name}] {msg.content}")
                        print(f"\n{t('message_count').format(count=len(session.history))}\n")
                elif cmd == "/memory" or cmd.startswith("/memory "):
                    # 收集所有有知识库的参与者
                    km_participants = [p for p in participants if p.knowledge_manager]
                    if not km_participants:
                        print(f"\n{t('no_knowledge')}")
                        if len(participants) == 1:
                            print(f"{t('knowledge_create_hint')}\n")
                        else:
                            print()
                    elif cmd.startswith("/memory search "):
                        # 一次性搜索: /memory search <query>
                        query = user_input[15:].strip()
                        if query:
                            await _memory_search(km_participants, query)
                    else:
                        # /memory: 显示状态 + 进入交互搜索
                        for p in km_participants:
                            stats = p.knowledge_manager.get_stats()
                            print(f"\n{t('knowledge_label').format(emoji=p.info.emoji, name=p.info.display_name)}")
                            print(t("file_chunk_count").format(files=stats['file_count'], chunks=stats['chunk_count']))
                        print()
                        # 交互式搜索循环
                        while True:
                            try:
                                query = input(t("memory_search_prompt")).strip()
                            except (EOFError, KeyboardInterrupt):
                                break
                            if not query:
                                break
                            await _memory_search(km_participants, query)
                elif cmd == "/sessions":
                    history_sessions = session_store.list_history()
                    if not history_sessions:
                        print(f"\n[{t('no_sessions')}]\n")
                    else:
                        hist_labels = []
                        for s in history_sessions:
                            time_str = s["updated_at"][:16].replace("T", " ") if s["updated_at"] else t("unknown_time")
                            participants_str = ", ".join(s["participants"])
                            title = s.get("title", "")
                            label = f"{time_str} | {participants_str} | {t('messages_suffix').format(count=s['msg_count'])}"
                            if title:
                                label = f"{title} | {label}"
                            hist_labels.append(label)
                        hist_labels.append(t("back"))

                        hist_choice = select_menu_interactive(t("history"), hist_labels)
                        if hist_choice is not None and hist_choice < len(history_sessions):
                            selected = history_sessions[hist_choice]
                            history_data = session_store.load_history(selected["filename"])
                            if history_data:
                                session_store.archive()
                                session = session_store.restore_session(history_data)
                                old_participants = participants
                                participants = []
                                role_name_map = {}
                                for role_name in roles:
                                    info = role_manager.get_role_info(role_name)
                                    display = info.get("display_name", role_name)
                                    role_name_map[display] = role_name
                                for display_name in history_data.get("participants", []):
                                    rn = role_name_map.get(display_name)
                                    if rn:
                                        try:
                                            km = await role_manager.get_knowledge_manager(
                                                rn,
                                                google_api_key=settings.google_api_key,
                                            )
                                        except Exception:
                                            km = None
                                        p = Participant(
                                            role_name=rn,
                                            provider=provider,
                                            role_manager=role_manager,
                                            knowledge_manager=km,
                                        )
                                        participants.append(p)
                                for p in old_participants:
                                    if p.knowledge_manager:
                                        p.knowledge_manager.close()
                                memory_context = user_memory.get_context()
                                moderator = Moderator(participants, session, user_memory_context=memory_context)
                                print(f"\n[{t('session_restored').format(count=len(session.history))}]\n")
                            else:
                                print(f"\n[{t('session_load_failed')}]\n")
                elif cmd == "/me":
                    me_file = user_memory.user_file
                    if me_file.exists():
                        content = me_file.read_text(encoding="utf-8")
                        print(f"\n── USER.md ──\n{content}\n─────────────")
                    else:
                        print(f"\n[{me_file} 不存在，将创建]\n")
                    print("[在记事本中打开编辑，关闭后自动重载...]")
                    import subprocess
                    proc = subprocess.Popen(["notepad", str(me_file)])
                    proc.wait()
                    memory_context = user_memory.get_context()
                    moderator.user_memory_context = memory_context
                    print("[档案已重载]\n")
                elif cmd == "/roles":
                    role_manager = participants[0].role_manager
                    current_role_names = [p.role_name for p in participants]

                    # 子菜单
                    roles_opts = [
                        "修改角色（增删）" if settings.ui_lang == "zh" else "Edit roles (add/remove)",
                        "调整发言人数" if settings.ui_lang == "zh" else "Adjust speakers per round",
                        t("back"),
                    ]
                    roles_choice = select_menu_interactive(
                        "编辑角色" if settings.ui_lang == "zh" else "Edit roles",
                        roles_opts,
                    )

                    if roles_choice == 0:  # 修改角色
                        new_role_names = select_roles_interactive(role_manager, pre_selected=current_role_names)
                        if new_role_names:
                            # 关闭移除角色的知识库
                            new_set = set(new_role_names)
                            for p in participants:
                                if p.role_name not in new_set and p.knowledge_manager:
                                    p.knowledge_manager.close()

                            # 保留已有 participant，新增的重新创建
                            existing = {p.role_name: p for p in participants}
                            new_participants = []
                            for rn in new_role_names:
                                if rn in existing:
                                    new_participants.append(existing[rn])
                                else:
                                    print(f"[加载 {rn}...]", end="", flush=True)
                                    try:
                                        km = await role_manager.get_knowledge_manager(
                                            rn, google_api_key=settings.google_api_key
                                        )
                                    except Exception:
                                        km = None
                                    new_participants.append(Participant(
                                        role_name=rn,
                                        provider=provider,
                                        role_manager=role_manager,
                                        knowledge_manager=km,
                                    ))
                                    print(f"\r\033[K[{rn} 已加载]")

                            participants = new_participants
                            memory_context = user_memory.get_context()
                            moderator = Moderator(participants, session, user_memory_context=memory_context)
                            names = ", ".join(p.info.display_name for p in participants)
                            print(f"\n[当前角色: {names}]\n")

                    elif roles_choice == 1:  # 调整发言人数
                        n = len(participants)
                        if n <= 1:
                            print("\n[只有一个角色，无需调整]\n")
                        else:
                            spk_labels = [f"{i} {'人' if settings.ui_lang == 'zh' else 'speakers'}" for i in range(1, n)]
                            spk_labels.append(f"{n} {'人（全部）' if settings.ui_lang == 'zh' else 'speakers (all)'}")
                            spk_title = "每轮最多几人发言？" if settings.ui_lang == "zh" else "Speakers per round?"
                            cur_idx = (max_speakers_per_round - 1) if 0 < max_speakers_per_round <= n else n - 1
                            spk_choice = select_menu_interactive(spk_title, spk_labels, default_index=cur_idx)
                            if spk_choice is not None:
                                max_speakers_per_round = spk_choice + 1
                                print(f"\n[每轮发言人数: {max_speakers_per_round}]\n")

                elif cmd == "/config":
                    new_provider_id = select_provider_interactive(show_welcome=False)
                    if new_provider_id:
                        from .app import create_provider_with_fallback
                        try:
                            new_provider = create_provider_with_fallback(new_provider_id)
                            provider = new_provider
                            for p in participants:
                                p.provider = new_provider
                            suggestion_generator = SuggestionGenerator(new_provider)
                            print(f"\n[{t('switched_to').format(name=new_provider.name, model=new_provider.model)}]\n")
                        except Exception as e:
                            print(f"\n[{t('switch_failed').format(error=e)}]\n")
                elif cmd == "/model":
                    provider_id = settings.llm_provider.lower()
                    if provider_id == "qwen-portal":
                        print(f"\n{t('model_no_switch')}\n")
                    else:
                        new_model = select_model_for_provider(provider_id, provider.model)
                        if new_model:
                            from .app import create_provider_with_fallback
                            try:
                                new_provider = create_provider_with_fallback()
                                provider = new_provider
                                for p in participants:
                                    p.provider = new_provider
                                suggestion_generator = SuggestionGenerator(new_provider)
                                print(f"\n[{t('model_switched').format(model=new_provider.model)}]\n")
                            except Exception as e:
                                print(f"\n[{t('switch_failed').format(error=e)}]\n")
                else:
                    print(f"\n{t('unknown_command').format(cmd=cmd)}\n")
                continue

            # 解析 @mention（@角色名 只让指定角色回复）— 必须在图片解析之前
            mentioned_only = None
            if len(participants) > 1 and user_input.startswith("@"):
                mention_match = re.match(r"^@(\S+)\s*(.*)", user_input)
                if mention_match:
                    mention_name = mention_match.group(1)
                    for p in participants:
                        if (mention_name.lower() == p.role_name.lower()
                            or mention_name == p.info.display_name
                            or mention_name == p.info.emoji):
                            mentioned_only = p
                            user_input = mention_match.group(2) or user_input
                            break

            # 解析图片附件（@路径 + Alt+V 剪贴板）
            clean_input, path_media = parse_media_from_input(user_input)
            media = clipboard_media + path_media
            if media:
                path_names = [m.filename for m in path_media]
                if path_names:
                    print(f"  📎 {', '.join(path_names)}")
                if not clean_input:
                    clean_input = "请看这张图片"
                user_input = clean_input

            # 运行对话（统一的循环，包含所有角色的发言）
            current_participant = None
            skip_happened = False
            user_interjected = False
            all_participants_info = [p.info for p in participants]

            # 追踪当前角色输出的内容（用于 skip 时清除）
            current_output_lines = 0
            current_output_chars = 0

            _max_spk = max_speakers_per_round or settings.max_speakers_per_round
            _turns = min(_max_spk, len(participants)) if _max_spk > 0 else len(participants)
            if mentioned_only:
                _turns = 1  # @mention 时只让一个人说

            # 每轮刷新用户记忆（USER.md 可能已被自动提取更新）
            moderator.user_memory_context = user_memory.get_context()

            async for participant, chunk, is_skip in moderator.run(user_input, max_turns=_turns, media=media or None, mentioned_only=mentioned_only):
                if is_skip:
                    # 清除当前角色之前输出的内容
                    if current_output_chars > 0:
                        # 回到行首，向上移动到标题行，清除所有输出
                        sys.stdout.write(f"\r\033[{current_output_lines + 1}A\033[J")
                        sys.stdout.flush()
                    print(t("chose_silence").format(emoji=participant.info.emoji, name=participant.info.display_name))
                    skip_happened = True
                    break

                # 检测参与者切换
                if participant != current_participant:
                    # 检查前一个角色是否有输出
                    if current_participant is not None:
                        if current_output_chars == 0:
                            # 清除名字行，显示保持沉默
                            sys.stdout.write("\r\033[K")
                            print(f"{t('chose_silence').format(emoji=current_participant.info.emoji, name=current_participant.info.display_name)}\n")
                        else:
                            print("\n")
                    print(f"\n{participant.info.emoji} {participant.info.display_name}: ", end="", flush=True)
                    current_participant = participant
                    # 重置当前角色的输出追踪
                    current_output_lines = 0
                    current_output_chars = 0

                # 追踪输出的行数（用于 skip 时清除）
                if chunk:
                    current_output_chars += len(chunk)
                    current_output_lines += chunk.count('\n')
                print(chunk, end="", flush=True)

            # 如果当前角色没有输出任何内容，显示"保持沉默"（但如果已经因为 skip 打印过就跳过）
            if current_participant and current_output_chars == 0 and not skip_happened:
                sys.stdout.write("\r\033[K")
                print(t("chose_silence").format(emoji=current_participant.info.emoji, name=current_participant.info.display_name))
            elif not skip_happened:
                print()

            # 自动生成标题（只在第一轮、有用户消息时生成一次）
            if not session_title and session.history:
                first_user_msg = next(
                    (m.content for m in session.history if m.role == MessageRole.USER), ""
                )
                if first_user_msg:
                    try:
                        resp = await provider.chat(
                            messages=[Message(
                                role=MessageRole.USER,
                                content=f"为以下对话生成一个简短标题（10字以内，中文，不要引号）：\n{first_user_msg[:200]}",
                            )],
                            max_tokens=30,
                            temperature=0.3,
                        )
                        session_title = resp.content.strip().strip('"\'""')
                    except Exception:
                        session_title = first_user_msg[:20]

            # 自动保存会话
            participant_names = [p.info.display_name for p in participants]
            session_store.save(session, participant_names, title=session_title)

            # 一轮结束，显示建议菜单
            print()  # 回答与建议菜单之间的空行
            choice_text, is_silence = await show_suggestion_menu(
                suggestion_generator, session
            )

            if is_silence:
                pending_suggestion = t("silence_prompt")
            elif choice_text:
                # 用户选择了建议或输入了内容
                pending_suggestion = choice_text
            # 否则（ESC/自由输入但没输入）等待用户正常输入

        except KeyboardInterrupt:
            print(f"\n\n{t('interrupted')}")
            if session.history:
                participant_names = [p.info.display_name for p in participants]
                session_store.save(session, participant_names)
                print(f"[{t('session_saved')}]")
                print("[正在更新档案...]", end="", flush=True)
                updated = await user_memory.auto_extract(session.history, provider)
                print(f"\r[{'档案已更新' if updated else '档案无变化'}]   ")
            return ("quit", "")
        except Exception as e:
            print(f"\n{t('error_prefix').format(error=e)}\n")
            if settings.debug:
                import traceback
                traceback.print_exc()

    return ("quit", "")
