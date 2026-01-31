"""辩论模式"""
import sys
import ctypes
import msvcrt

from lifee.config.settings import settings
from lifee.providers import LLMProvider
from lifee.sessions import Session
from lifee.roles import RoleManager
from lifee.debate import Moderator, Participant, DebateContext, clean_response


def collect_user_input_nonblocking() -> str:
    """非阻塞收集用户输入（直到按回车）

    在 ping-pong 模式中，当检测到用户按键时调用此函数。
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

    # 创建主持者
    moderator = Moderator(participants, session)

    # 显示欢迎信息
    print("\n" + "=" * 50)
    print("LIFEE 多角度讨论模式")
    print("=" * 50)
    print("参与者:")
    for p in participants:
        print(f"  {p.info.emoji} {p.info.display_name}")
    print("\n输入问题开始讨论")
    print("命令: /quit 退出 | /clear 清空 | /history 历史")
    print("=" * 50 + "\n")

    while True:
        try:
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
                        if msg.role.value == "user":
                            print(f"[你] {msg.content[:80]}...")
                        else:
                            name = msg.name or "AI"
                            print(f"[{name}] {msg.content[:80]}...")
                    print(f"--- 共 {len(session.history)} 条消息 ---\n")
                continue

            # 运行一轮辩论（每个角色回应用户）
            current_participant = None
            async for participant, chunk in moderator.run_round(user_input):
                if participant != current_participant:
                    if current_participant is not None:
                        print("\n")
                    print(f"\n{participant.info.emoji} {participant.info.display_name}: ", end="", flush=True)
                    current_participant = participant
                print(chunk, end="", flush=True)

            print("\n")

            # Ping-pong 模式：角色之间自动继续对话
            if len(participants) >= 2:
                current_participant = None
                skip_happened = False
                user_interjected = False  # 用户是否插话
                last_participant = None  # 记录上一个完成发言的参与者
                pending_user_input = ""  # 待处理的用户输入
                all_participants_info = [p.info for p in participants]

                async for participant, chunk, is_skip in moderator.run_pingpong(max_turns=5):
                    if is_skip:
                        print(f"\n{participant.info.emoji} {participant.info.display_name} 选择保持沉默")
                        skip_happened = True
                        break

                    # 检测参与者切换（上一个角色说完了）
                    if participant != current_participant:
                        # 如果有待处理的用户输入，让刚完成的角色（current_participant）回应
                        if pending_user_input and current_participant is not None:
                            # 添加用户消息到会话
                            session.add_user_message(pending_user_input)

                            # 构建上下文让同一角色回应用户
                            interjection_context = DebateContext(
                                current_participant=current_participant.info,
                                all_participants=all_participants_info,
                                round_number=moderator.round_number,
                                speaking_order=1,
                                total_speakers=len(participants),
                                is_pingpong=False,  # 这是回应用户，不是 ping-pong
                            )

                            print(f"\n\n{current_participant.info.emoji} {current_participant.info.display_name}: ", end="", flush=True)

                            response = ""
                            async for resp_chunk in current_participant.respond(
                                messages=session.get_messages(),
                                user_query=pending_user_input,
                                debate_context=interjection_context,
                            ):
                                print(resp_chunk, end="", flush=True)
                                response += resp_chunk

                            session.add_assistant_message(clean_response(response), name=current_participant.info.display_name)
                            print("\n")
                            pending_user_input = ""
                            user_interjected = True
                            break  # 停止 ping-pong，让用户继续主导

                        # 检查是否有用户按键（开始收集输入）
                        if current_participant is not None and msvcrt.kbhit():
                            # 收集用户输入（会阻塞直到用户按回车）
                            pending_user_input = collect_user_input_nonblocking()
                            if pending_user_input:
                                # 立即让刚完成发言的角色（current_participant）回应
                                session.add_user_message(pending_user_input)

                                interjection_context = DebateContext(
                                    current_participant=current_participant.info,
                                    all_participants=all_participants_info,
                                    round_number=moderator.round_number,
                                    speaking_order=1,
                                    total_speakers=len(participants),
                                    is_pingpong=False,
                                )

                                print(f"\n{current_participant.info.emoji} {current_participant.info.display_name}: ", end="", flush=True)

                                response = ""
                                async for resp_chunk in current_participant.respond(
                                    messages=session.get_messages(),
                                    user_query=pending_user_input,
                                    debate_context=interjection_context,
                                ):
                                    print(resp_chunk, end="", flush=True)
                                    response += resp_chunk

                                session.add_assistant_message(clean_response(response), name=current_participant.info.display_name)
                                print("\n")
                                user_interjected = True
                                break  # 停止 ping-pong，让用户继续主导

                        if current_participant is not None:
                            print("\n")
                        print(f"\n{participant.info.emoji} {participant.info.display_name}: ", end="", flush=True)
                        last_participant = current_participant
                        current_participant = participant

                    print(chunk, end="", flush=True)

                if not user_interjected and not skip_happened:
                    print("\n\n--- 达到对话轮次上限 ---")
                print()

        except KeyboardInterrupt:
            print("\n\n[中断] 退出讨论模式")
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
