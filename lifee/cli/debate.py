"""统一对话循环"""
import asyncio
import sys
import msvcrt
from pathlib import Path

from lifee.config.settings import settings
from lifee.providers import LLMProvider
from lifee.sessions import Session, DebateSessionStore
from lifee.roles import RoleManager
from lifee.debate import Moderator, Participant, DebateContext, clean_response
from lifee.debate.suggestions import SuggestionGenerator
from lifee.memory import UserMemory
from .setup import select_provider_interactive, select_model_for_provider, select_menu_interactive


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
        print(f"LIFEE 对话模式 - {participants[0].info.emoji} {participants[0].info.display_name}")
    else:
        print("LIFEE 多角度讨论模式")
    print("=" * 50)
    if len(participants) > 1:
        print("参与者:")
        for p in participants:
            print(f"  {p.info.emoji} {p.info.display_name}")
    print("\n输入问题开始对话" if len(participants) == 1 else "\n输入问题开始讨论")
    print("命令: /help 帮助 | /quit 退出 | /menu 主菜单")
    print("=" * 50 + "\n")

    pending_suggestion = None  # 用于存储用户选择的建议

    while True:
        try:
            # 如果有待处理的建议选择，直接使用
            if pending_suggestion:
                user_input = pending_suggestion
                pending_suggestion = None
                if user_input.startswith("[用户选择保持沉默"):
                    print("你: （保持沉默）")
                else:
                    print(f"你: {user_input}")
            else:
                user_input = input("你: ").strip()

            if not user_input:
                continue

            # 处理命令
            if user_input.startswith("/"):
                cmd = user_input.lower()
                if cmd in ("/quit", "/exit"):
                    # 保存会话后退出
                    if session.history:
                        participant_names = [p.info.display_name for p in participants]
                        session_store.save(session, participant_names)
                        print("[会话已自动保存]")
                    return ("quit", "")
                elif cmd == "/menu":
                    # 保存会话后返回主菜单
                    if session.history:
                        participant_names = [p.info.display_name for p in participants]
                        session_store.save(session, participant_names)
                        print("[会话已自动保存]")
                    return ("menu", "")
                elif cmd == "/help":
                    print("\n命令列表:")
                    print("  /help     - 显示帮助")
                    print("  /history  - 显示对话历史")
                    print("  /clear    - 清空对话历史")
                    print("  /sessions - 历史会话")
                    print("  /memory   - 知识库状态")
                    print("  /config   - 切换 LLM Provider")
                    print("  /model    - 切换当前 Provider 的模型")
                    print("  /menu     - 返回主菜单")
                    print("  /quit     - 退出")
                    print()
                elif cmd == "/clear":
                    session.clear_history()
                    session_store.clear()
                    print("\n[对话历史已清空]\n")
                elif cmd == "/history":
                    if not session.history:
                        print("\n[对话历史为空]\n")
                    else:
                        print("\n--- 对话历史 ---")
                        for msg in session.history:
                            if not msg.content.strip():
                                continue
                            if msg.role.value == "user":
                                print(f"\n[你] {msg.content}")
                            else:
                                name = msg.name or "AI"
                                print(f"\n[{name}] {msg.content}")
                        print(f"\n--- 共 {len(session.history)} 条消息 ---\n")
                elif cmd == "/memory" or cmd.startswith("/memory "):
                    # 知识库管理
                    if len(participants) == 1:
                        km = participants[0].knowledge_manager
                        if not km:
                            print("\n当前角色没有知识库")
                            print("创建方法: 在角色目录下创建 knowledge/ 目录，添加 .md 文件\n")
                        elif cmd == "/memory":
                            stats = km.get_stats()
                            print("\n知识库状态:")
                            print(f"  文件数: {stats['file_count']}")
                            print(f"  分块数: {stats['chunk_count']}")
                            print(f"  嵌入模型: {stats['embedding_provider']}/{stats['embedding_model']}")
                            print()
                        elif cmd.startswith("/memory search "):
                            query = user_input[15:].strip()
                            if not query:
                                print("\n用法: /memory search <查询内容>\n")
                            else:
                                print(f"\n搜索: {query}")
                                results = await km.search(query, max_results=5)
                                if not results:
                                    print("没有找到相关内容\n")
                                else:
                                    print(f"找到 {len(results)} 条结果:\n")
                                    for i, r in enumerate(results, 1):
                                        print(f"[{i}] {Path(r.path).name}:{r.start_line}-{r.end_line} (分数: {r.score:.2f})")
                                        preview = r.text[:100].replace("\n", " ")
                                        print(f"    {preview}...")
                                        print()
                        else:
                            print("\n用法:")
                            print("  /memory         - 显示知识库状态")
                            print("  /memory search <query> - 搜索知识库\n")
                    else:
                        # 多参与者：显示各角色知识库状态
                        has_any = False
                        for p in participants:
                            if p.knowledge_manager:
                                has_any = True
                                stats = p.knowledge_manager.get_stats()
                                print(f"\n{p.info.emoji} {p.info.display_name} 知识库:")
                                print(f"  文件数: {stats['file_count']}, 分块数: {stats['chunk_count']}")
                        if not has_any:
                            print("\n当前参与者均没有知识库\n")
                        else:
                            print()
                elif cmd == "/sessions":
                    history_sessions = session_store.list_history()
                    if not history_sessions:
                        print("\n[没有历史会话]\n")
                    else:
                        hist_labels = []
                        for s in history_sessions:
                            time_str = s["updated_at"][:16].replace("T", " ") if s["updated_at"] else "未知"
                            participants_str = "、".join(s["participants"])
                            hist_labels.append(f"{time_str} | {participants_str} | {s['msg_count']}条消息")
                        hist_labels.append("返回")

                        hist_choice = select_menu_interactive("历史会话", hist_labels)
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
                                print(f"\n[已恢复会话，共 {len(session.history)} 条消息]\n")
                            else:
                                print("\n[无法加载该会话]\n")
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
                            print(f"\n[已切换到 {new_provider.name} ({new_provider.model})]\n")
                        except Exception as e:
                            print(f"\n[切换失败: {e}]\n")
                elif cmd == "/model":
                    provider_id = settings.llm_provider.lower()
                    if provider_id == "qwen-portal":
                        print("\nQwen Portal 不支持模型切换\n")
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
                                print(f"\n[已切换模型: {new_provider.model}]\n")
                            except Exception as e:
                                print(f"\n[切换失败: {e}]\n")
                else:
                    print(f"\n未知命令: {cmd}，输入 /help 查看帮助\n")
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
                pending_suggestion = "[用户选择保持沉默，请继续你的思考或追问]"
            elif choice_text:
                # 用户选择了建议或输入了内容
                pending_suggestion = choice_text
            # 否则（ESC/自由输入但没输入）等待用户正常输入

        except KeyboardInterrupt:
            print("\n\n[中断]")
            # 保存会话
            if session.history:
                participant_names = [p.info.display_name for p in participants]
                session_store.save(session, participant_names)
                print("[会话已自动保存]")
            return ("quit", "")
        except Exception as e:
            print(f"\n[错误] {e}\n")
            if settings.debug:
                import traceback
                traceback.print_exc()

    return ("quit", "")
