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
from lifee.providers.base import MediaItem
from lifee.sessions import Session, DebateSessionStore
from lifee.roles import RoleManager
from lifee.debate import Moderator, Participant, DebateContext, clean_response
from lifee.debate.suggestions import SuggestionGenerator
from lifee.memory import UserMemory
from .i18n import t
from .setup import select_provider_interactive, select_model_for_provider, select_menu_interactive


_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}

SLASH_COMMANDS = [
    ("/help",     "显示帮助"),
    ("/history",  "查看对话历史"),
    ("/clear",    "清除对话历史"),
    ("/sessions", "查看历史会话"),
    ("/memory",   "知识库状态"),
    ("/me",       "查看/编辑我的档案"),
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


def input_with_clipboard(prompt: str) -> Tuple[str, List[MediaItem]]:
    """带剪贴板粘贴 + slash 命令菜单的自定义输入函数

    功能:
        - Ctrl+V / Alt+V: 粘贴剪贴板图片
        - Backspace: 文本为空时删除最后一张图片
        - /: 触发 slash 命令菜单（方向键导航，继续输入过滤）
        - ESC: 关闭 slash 菜单

    Returns:
        (输入文本, 剪贴板媒体列表)
    """
    sys.stdout.write(prompt)
    sys.stdout.flush()

    chars = []
    media = []
    has_attachment_line = False

    # slash 菜单状态
    in_slash_mode = False
    slash_cursor = 0
    slash_prev_count = 0  # 上次绘制的菜单行数

    def _redraw():
        """重绘附件行 + 输入行"""
        nonlocal has_attachment_line
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
            else:
                sys.stdout.write("\n")
                sys.stdout.flush()
                break

        elif char == "\x1b":  # ESC — 关闭 slash 菜单
            if in_slash_mode:
                _clear_slash_menu()
                in_slash_mode = False
                slash_cursor = 0

        elif char == "\x08":  # Backspace
            if in_slash_mode:
                if chars:
                    removed = chars.pop()
                    w = _char_width(removed)
                    sys.stdout.write("\b" * w + " " * w + "\b" * w)
                    sys.stdout.flush()
                    if not chars:
                        _clear_slash_menu()
                        in_slash_mode = False
                    else:
                        slash_cursor = 0
                        _draw_slash_menu()
                else:
                    _clear_slash_menu()
                    in_slash_mode = False
            else:
                if chars:
                    removed = chars.pop()
                    w = _char_width(removed)
                    sys.stdout.write("\b" * w + " " * w + "\b" * w)
                    sys.stdout.flush()
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
            # 非 slash 模式下忽略方向键（保持原行为）

        elif ord(char) >= 32:  # 可打印字符
            chars.append(char)
            sys.stdout.write(char)
            sys.stdout.flush()

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

    return "".join(chars).strip(), media


async def show_suggestion_menu(
    suggestion_generator,
    session,
) -> tuple[str, bool]:
    """
    显示建议回复菜单

    Returns:
        (选择的文本, 是否保持沉默)
        - 选择建议: ("建议文本", False)
        - 自由输入: ("输入文本", False)
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
    max_opt_len = term_width - 8  # "  > N. " 前缀占 ~7 字符
    display_options = []
    for s in suggestions:
        if len(s) > max_opt_len:
            display_options.append(s[:max_opt_len - 3] + "...")
        else:
            display_options.append(s)
    display_options += [t("silence_option"), t("free_input_option")]

    options = suggestions + [t("silence_option"), t("free_input_option")]
    silence_idx = len(suggestions)
    free_input_idx = len(suggestions) + 1
    cursor = 0
    total_lines = 1 + len(options)

    def render_menu(first_time=False):
        if not first_time:
            sys.stdout.write(f"\033[{total_lines}A")
        prompt = t("suggestion_prompt")
        sys.stdout.write(f"\033[2K{prompt}\n")
        for i, opt in enumerate(display_options):
            pointer = ">" if i == cursor else " "
            sys.stdout.write(f"\033[2K  {pointer} {i+1}. {opt}\n")
        sys.stdout.flush()

    sys.stdout.write("\033[?25l")  # 隐藏光标
    render_menu(first_time=True)

    result = ("", False)
    try:
        while True:
            key = msvcrt.getch()

            if key == b'\r':  # 回车
                if cursor < len(suggestions):
                    result = (suggestions[cursor], False)
                elif cursor == silence_idx:
                    result = ("", True)  # 保持沉默
                # 自由输入则返回空字符串
                break

            elif key == b'\x1b':  # ESC
                break

            elif key == b'\xe0':  # 方向键
                arrow = msvcrt.getch()
                if arrow == b'H':  # 上
                    cursor = (cursor - 1) % len(options)
                    render_menu()
                elif arrow == b'P':  # 下
                    cursor = (cursor + 1) % len(options)
                    render_menu()

            elif key in [b'1', b'2', b'3', b'4', b'5']:
                idx = int(key.decode()) - 1
                if idx < len(suggestions):
                    result = (suggestions[idx], False)
                    break
                elif idx == silence_idx:
                    result = ("", True)
                    break
                elif idx == free_input_idx:
                    break

            elif key not in [b'\x00', b'\xe0']:
                # 其他字符 - 自由输入
                try:
                    first_char = key.decode('utf-8')
                    if ord(first_char) >= 32:
                        sys.stdout.write("\033[?25h")
                        sys.stdout.write(f"\033[{total_lines}A\033[J")
                        sys.stdout.write(f"{t('input_prompt')}{first_char}")
                        sys.stdout.flush()
                        rest = input()
                        result = (first_char + rest, False)
                        return result
                except:
                    pass
    finally:
        sys.stdout.write("\033[?25h")
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


async def debate_loop(
    participants: list[Participant],
    session: Session,
    provider: LLMProvider,
    session_store: DebateSessionStore,
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
                user_input, clipboard_media = input_with_clipboard(t("input_prompt"))

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
                    if len(participants) == 1:
                        km = participants[0].knowledge_manager
                        if not km:
                            print(f"\n{t('no_knowledge')}")
                            print(f"{t('knowledge_create_hint')}\n")
                        elif cmd == "/memory":
                            stats = km.get_stats()
                            print(f"\n{t('knowledge_status')}")
                            print(t("file_count").format(count=stats['file_count']))
                            print(t("chunk_count").format(count=stats['chunk_count']))
                            print(t("embedding_model").format(model=f"{stats['embedding_provider']}/{stats['embedding_model']}"))
                            print()
                        elif cmd.startswith("/memory search "):
                            query = user_input[15:].strip()
                            if not query:
                                print(f"\n{t('memory_search_usage')}\n")
                            else:
                                print(f"\n{t('searching').format(query=query)}")
                                results = await km.search(query, max_results=5)
                                if not results:
                                    print(f"{t('no_results')}\n")
                                else:
                                    print(f"{t('result_count').format(count=len(results))}\n")
                                    for i, r in enumerate(results, 1):
                                        print(f"[{i}] {Path(r.path).name}:{r.start_line}-{r.end_line} (score: {r.score:.2f})")
                                        preview = r.text[:100].replace("\n", " ")
                                        print(f"    {preview}...")
                                        print()
                        else:
                            print(t("memory_usage"))
                            print(t("memory_usage_status"))
                            print(f"{t('memory_usage_search')}\n")
                    else:
                        has_any = False
                        for p in participants:
                            if p.knowledge_manager:
                                has_any = True
                                stats = p.knowledge_manager.get_stats()
                                print(f"\n{t('knowledge_label').format(emoji=p.info.emoji, name=p.info.display_name)}")
                                print(t("file_chunk_count").format(files=stats['file_count'], chunks=stats['chunk_count']))
                        if not has_any:
                            print(f"\n{t('no_knowledge_all')}\n")
                        else:
                            print()
                elif cmd == "/sessions":
                    history_sessions = session_store.list_history()
                    if not history_sessions:
                        print(f"\n[{t('no_sessions')}]\n")
                    else:
                        hist_labels = []
                        for s in history_sessions:
                            time_str = s["updated_at"][:16].replace("T", " ") if s["updated_at"] else t("unknown_time")
                            participants_str = ", ".join(s["participants"])
                            hist_labels.append(f"{time_str} | {participants_str} | {t('messages_suffix').format(count=s['msg_count'])}")
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

            async for participant, chunk, is_skip in moderator.run(user_input, max_turns=len(participants), media=media or None):
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

            # 自动保存会话
            participant_names = [p.info.display_name for p in participants]
            session_store.save(session, participant_names)

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
