"""辩论模式"""
import asyncio
import sys
import ctypes
import msvcrt

from lifee.config.settings import settings
from lifee.providers import LLMProvider
from lifee.sessions import Session, DebateSessionStore
from lifee.roles import RoleManager
from lifee.debate import Moderator, Participant, DebateContext, clean_response
from lifee.debate.suggestions import SuggestionGenerator
from lifee.memory import UserMemory


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
    print("正在思考建议回复...", end="", flush=True)
    suggestions = await suggestion_generator.generate(session.get_messages())
    sys.stdout.write("\r\033[K")
    sys.stdout.flush()

    # 即使建议生成失败，也显示菜单（只有保持沉默和自由输入）
    if not suggestions:
        suggestions = []

    # 构建选项列表（建议 + 保持沉默 + 自由输入）
    options = suggestions + ["[保持沉默，让对话继续]", "[自由输入]"]
    silence_idx = len(suggestions)  # 保持沉默的索引
    free_input_idx = len(suggestions) + 1  # 自由输入的索引
    cursor = 0
    total_lines = 1 + len(options)

    def render_menu(first_time=False):
        if not first_time:
            sys.stdout.write(f"\033[{total_lines}A")
        sys.stdout.write("\033[2K你想说什么？ (↑↓选择 | 回车确认 | 直接打字输入)\n")
        for i, opt in enumerate(options):
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
                        sys.stdout.write(f"你: {first_char}")
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
    sys.stdout.write("\n\n[插话] 你: ")
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
                sys.stdout.write("\n[取消]\n")
                sys.stdout.flush()
                return ""
            elif ord(char) >= 32:  # 可打印字符
                chars.append(char)
                sys.stdout.write(char)
                sys.stdout.flush()

    return ''.join(chars)


async def debate_loop(
    provider: LLMProvider,
    session: Session,
) -> tuple[str, str]:
    """辩论模式主循环"""
    role_manager = RoleManager()
    roles = role_manager.list_roles()

    if not roles:
        print("\n没有可用的角色，无法启动辩论模式")
        print("请先创建角色: lifee/roles/<name>/SOUL.md")
        return ("continue", "")

    if len(roles) < 2:
        print(f"\n只有 {len(roles)} 个角色，辩论需要至少 2 个角色")
        return ("continue", "")

    # 初始化会话存储和用户记忆
    session_store = DebateSessionStore()
    user_memory = UserMemory()
    selected_roles = None  # 用于存储恢复的角色列表

    # 检查是否有保存的会话
    saved_data = session_store.load()
    history_sessions = session_store.list_history()

    if saved_data or history_sessions:
        print("\n" + "=" * 40)
        print("会话选择")
        print("=" * 40)

        options = []
        if saved_data:
            time_ago = session_store.get_time_ago(saved_data)
            participants_str = "、".join(saved_data.get("participants", []))
            msg_count = len(saved_data.get("history", []))
            print(f"\n[1] 继续上次讨论（{time_ago}）")
            print(f"    参与者：{participants_str} | {msg_count}条消息")
            options.append("current")

        print(f"\n[{len(options) + 1}] 新讨论")
        options.append("new")

        if history_sessions:
            print(f"\n[{len(options) + 1}] 历史会话...")
            options.append("history")

        choice = ""
        valid_choices = [str(i + 1) for i in range(len(options))]
        while choice not in valid_choices:
            choice = input("\n选择: ").strip()

        selected_option = options[int(choice) - 1]

        if selected_option == "current":
            # 恢复当前会话
            session = session_store.restore_session(saved_data)
            selected_roles = saved_data.get("participants", [])
            role_name_map = {}
            for role_name in roles:
                info = role_manager.get_role_info(role_name)
                display = info.get("display_name", role_name)
                role_name_map[display] = role_name
            selected_roles = [role_name_map.get(n, n) for n in selected_roles]
            print(f"\n已恢复会话，共 {len(saved_data.get('history', []))} 条消息")

        elif selected_option == "new":
            # 归档旧会话，开始新讨论
            if saved_data:
                session_store.archive()
                print("\n旧会话已归档")

        elif selected_option == "history":
            # 显示历史会话列表
            print("\n--- 历史会话 ---")
            for i, s in enumerate(history_sessions):
                time_str = s["updated_at"][:16].replace("T", " ") if s["updated_at"] else "未知"
                participants_str = "、".join(s["participants"])
                print(f"  [{i+1}] {time_str} | {participants_str} | {s['msg_count']}条消息")
            print(f"\n  [0] 返回")

            hist_choice = input("\n选择: ").strip()
            if hist_choice.isdigit() and 1 <= int(hist_choice) <= len(history_sessions):
                selected_hist = history_sessions[int(hist_choice) - 1]
                history_data = session_store.load_history(selected_hist["filename"])
                if history_data:
                    # 归档当前会话，恢复历史会话
                    if saved_data:
                        session_store.archive()
                    session = session_store.restore_session(history_data)
                    selected_roles = history_data.get("participants", [])
                    role_name_map = {}
                    for role_name in roles:
                        info = role_manager.get_role_info(role_name)
                        display = info.get("display_name", role_name)
                        role_name_map[display] = role_name
                    selected_roles = [role_name_map.get(n, n) for n in selected_roles]
                    print(f"\n已恢复历史会话，共 {len(history_data.get('history', []))} 条消息")
                else:
                    print("\n[无法加载该会话，开始新讨论]")
            else:
                # 返回或无效输入，开始新讨论
                if saved_data:
                    session_store.archive()
                print("\n开始新讨论")

    # 如果没有从保存的会话恢复角色，显示选择界面
    if selected_roles is None:
        # 获取角色信息，构建选项列表
        role_choices = []  # [(role_name, display_name, emoji, selected), ...]
        for role_name in roles:
            info = role_manager.get_role_info(role_name)
            display_name = info.get("display_name", role_name)
            emoji = role_manager.get_role_emoji(role_name)
            role_choices.append([role_name, display_name, emoji, False])  # 默认不选

        # 交互式选择界面（支持方向键、空格、数字）
        # 启用 Windows Virtual Terminal Processing（支持 ANSI 转义序列）
        kernel32 = ctypes.windll.kernel32
        stdout_handle = kernel32.GetStdHandle(-11)
        # 获取当前模式
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(stdout_handle, ctypes.byref(mode))
        # 启用 ENABLE_VIRTUAL_TERMINAL_PROCESSING (0x0004)
        kernel32.SetConsoleMode(stdout_handle, mode.value | 0x0004)

        cursor = 0  # 当前光标位置
        total_lines = 1 + len(role_choices)  # 1 行标题 + N 行角色

        def render_lines():
            """生成所有行"""
            lines = ["选择辩论参与者 (↑↓移动 | 空格/数字切换 | 回车确认):"]
            for i, (_, display_name, emoji, selected) in enumerate(role_choices):
                checkbox = "☑" if selected else "☐"
                pointer = ">" if i == cursor else " "
                lines.append(f"  {pointer} {i+1}. {checkbox} {emoji} {display_name}")
            return lines

        def render(first_time=False):
            if not first_time:
                # 光标上移 total_lines 行
                sys.stdout.write(f"\033[{total_lines}A")

            lines = render_lines()
            for line in lines:
                # 清除当前行并写入内容
                sys.stdout.write(f"\033[2K{line}\n")
            sys.stdout.flush()

        # 隐藏光标
        sys.stdout.write("\033[?25l")
        sys.stdout.flush()
        # 首次渲染
        render(first_time=True)

        try:
            while True:
                # 读取按键
                key = msvcrt.getch()

                if key == b'\r':  # 回车
                    break
                elif key == b'\x1b' or key == b'q':  # ESC 或 q
                    sys.stdout.write("\033[?25h\n")  # 显示光标
                    sys.stdout.flush()
                    return ("continue", "")
                elif key == b' ':  # 空格
                    role_choices[cursor][3] = not role_choices[cursor][3]
                    render()
                elif key == b'\xe0':  # 方向键前缀
                    arrow = msvcrt.getch()
                    if arrow == b'H':  # 上
                        cursor = (cursor - 1) % len(role_choices)
                        render()
                    elif arrow == b'P':  # 下
                        cursor = (cursor + 1) % len(role_choices)
                        render()
                elif key in [b'1', b'2', b'3', b'4', b'5', b'6', b'7', b'8', b'9']:
                    # 数字键直接切换
                    idx = int(key.decode()) - 1
                    if 0 <= idx < len(role_choices):
                        role_choices[idx][3] = not role_choices[idx][3]
                        cursor = idx
                        render()
        finally:
            # 确保光标恢复显示
            sys.stdout.write("\033[?25h")
            sys.stdout.flush()

        # 获取选中的角色
        selected_roles = [rc[0] for rc in role_choices if rc[3]]

        if len(selected_roles) == 0:
            sys.stdout.write("\n[取消] 未选择任何角色\n")
            sys.stdout.flush()
            return ("continue", "")

        if len(selected_roles) == 1:
            # 选 1 个角色 = 切换到该角色的对话模式
            sys.stdout.write(f"\n已选择 1 个角色，切换到对话模式\n")
            sys.stdout.flush()
            return ("switch_role", selected_roles[0])

    # 创建选中的参与者
    print("\n正在加载参与者...")
    participants = []
    for role_name in selected_roles:
        # 获取知识库管理器
        try:
            km = await role_manager.get_knowledge_manager(
                role_name,
                google_api_key=settings.google_api_key,
            )
        except Exception:
            km = None

        p = Participant(
            role_name=role_name,
            provider=provider,
            role_manager=role_manager,
            knowledge_manager=km,
        )
        participants.append(p)

    # 创建主持者（注入用户记忆上下文）
    memory_context = user_memory.get_context()
    moderator = Moderator(participants, session, user_memory_context=memory_context)

    # 创建建议生成器
    suggestion_generator = SuggestionGenerator(provider)

    # 显示欢迎信息
    print("\n" + "=" * 50)
    print("LIFEE 多角度讨论模式")
    print("=" * 50)
    print("参与者:")
    for p in participants:
        print(f"  {p.info.emoji} {p.info.display_name}")
    print("\n输入问题开始讨论")
    print("命令: /quit 退出 | /clear 清空 | /history 历史 | /sessions 历史会话")
    print("=" * 50 + "\n")

    pending_suggestion = None  # 用于存储用户选择的建议

    while True:
        try:
            # 如果有待处理的建议选择，直接使用
            if pending_suggestion:
                user_input = pending_suggestion
                pending_suggestion = None
                print(f"你: {user_input}")
            else:
                user_input = input("你: ").strip()

            if not user_input:
                continue

            # 处理命令
            if user_input.lower() in ["/quit", "/exit"]:
                # 关闭知识库管理器
                for p in participants:
                    if p.knowledge_manager:
                        p.knowledge_manager.close()
                return ("quit", "")

            if user_input.lower() == "/clear":
                session.clear_history()
                print("\n[讨论历史已清空]\n")
                continue

            if user_input.lower() == "/history":
                if not session.history:
                    print("\n[讨论历史为空]\n")
                else:
                    print("\n--- 讨论历史 ---")
                    for msg in session.history:
                        # 跳过空消息
                        if not msg.content.strip():
                            continue
                        if msg.role.value == "user":
                            print(f"\n[你] {msg.content}")
                        else:
                            name = msg.name or "AI"
                            print(f"\n[{name}] {msg.content}")
                    print(f"\n--- 共 {len(session.history)} 条消息 ---\n")
                continue

            if user_input.lower() == "/sessions":
                history_sessions = session_store.list_history()
                if not history_sessions:
                    print("\n[没有历史会话]\n")
                else:
                    print("\n--- 历史会话 ---")
                    for i, s in enumerate(history_sessions):
                        time_str = s["updated_at"][:16].replace("T", " ") if s["updated_at"] else "未知"
                        participants_str = "、".join(s["participants"])
                        print(f"  [{i+1}] {time_str} | {participants_str} | {s['msg_count']}条消息")
                    print("\n输入序号恢复，或按回车取消")
                    choice = input("选择: ").strip()
                    if choice.isdigit() and 1 <= int(choice) <= len(history_sessions):
                        selected = history_sessions[int(choice) - 1]
                        history_data = session_store.load_history(selected["filename"])
                        if history_data:
                            # 归档当前会话，恢复历史会话
                            session_store.archive()
                            session = session_store.restore_session(history_data)
                            # 重新创建参与者（使用历史会话的角色）
                            old_participants = participants
                            participants = []
                            role_name_map = {}
                            for role_name in roles:
                                info = role_manager.get_role_info(role_name)
                                display = info.get("display_name", role_name)
                                role_name_map[display] = role_name
                            for display_name in history_data.get("participants", []):
                                role_name = role_name_map.get(display_name)
                                if role_name:
                                    try:
                                        km = await role_manager.get_knowledge_manager(
                                            role_name,
                                            google_api_key=settings.google_api_key,
                                        )
                                    except Exception:
                                        km = None
                                    p = Participant(
                                        role_name=role_name,
                                        provider=provider,
                                        role_manager=role_manager,
                                        knowledge_manager=km,
                                    )
                                    participants.append(p)
                            # 关闭旧的知识库管理器
                            for p in old_participants:
                                if p.knowledge_manager:
                                    p.knowledge_manager.close()
                            # 重新创建 moderator
                            memory_context = user_memory.get_context()
                            moderator = Moderator(participants, session, user_memory_context=memory_context)
                            print(f"\n[已恢复会话，共 {len(session.history)} 条消息]\n")
                        else:
                            print("\n[无法加载该会话]\n")
                continue

            # 运行对话（统一的循环，包含所有角色的发言）
            current_participant = None
            skip_happened = False
            user_interjected = False
            all_participants_info = [p.info for p in participants]

            # 追踪当前角色输出的内容（用于 skip 时清除）
            current_output_lines = 0
            current_output_chars = 0

            async for participant, chunk, is_skip in moderator.run(user_input, max_turns=len(participants)):
                if is_skip:
                    # 清除当前角色之前输出的内容
                    if current_output_chars > 0:
                        # 回到行首，向上移动到标题行，清除所有输出
                        sys.stdout.write(f"\r\033[{current_output_lines + 1}A\033[J")
                        sys.stdout.flush()
                    print(f"{participant.info.emoji} {participant.info.display_name} 选择保持沉默")
                    skip_happened = True
                    break

                # 检测参与者切换
                if participant != current_participant:
                    # 检查前一个角色是否有输出
                    if current_participant is not None:
                        if current_output_chars == 0:
                            # 清除名字行，显示保持沉默
                            sys.stdout.write("\r\033[K")
                            print(f"{current_participant.info.emoji} {current_participant.info.display_name} 选择保持沉默\n")
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
                print(f"{current_participant.info.emoji} {current_participant.info.display_name} 选择保持沉默")
            elif not skip_happened:
                print()

            # 自动保存会话
            participant_names = [p.info.display_name for p in participants]
            session_store.save(session, participant_names)

            # 后台提取用户记忆（不阻塞主流程）
            asyncio.create_task(user_memory.auto_extract(session.history, provider))

            # 一轮结束，显示建议菜单
            choice_text, is_silence = await show_suggestion_menu(
                suggestion_generator, session
            )

            if is_silence:
                # 用户选择保持沉默，让角色继续讨论
                pending_suggestion = "[继续]"
            elif choice_text:
                # 用户选择了建议或输入了内容
                pending_suggestion = choice_text
            # 否则（ESC/自由输入但没输入）等待用户正常输入

        except KeyboardInterrupt:
            print("\n\n[中断] 退出讨论模式")
            # 保存会话
            participant_names = [p.info.display_name for p in participants]
            session_store.save(session, participant_names)
            print("[会话已自动保存]")
            for p in participants:
                if p.knowledge_manager:
                    p.knowledge_manager.close()
            return ("quit", "")
        except Exception as e:
            print(f"\n[错误] {e}\n")
            if settings.debug:
                import traceback
                traceback.print_exc()

    return ("quit", "")
