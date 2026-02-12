"""对话循环"""
import asyncio
from pathlib import Path

from lifee.config.settings import settings
from lifee.providers import LLMProvider, MessageRole
from lifee.sessions import Session, ChatSessionStore
from lifee.roles import RoleManager
from lifee.roles.skills import SkillSet, load_skill_set
from lifee.memory import MemoryManager, format_search_results, UserMemory
from .setup import select_role_interactive, select_provider_interactive, select_model_for_provider


async def chat_loop(
    provider: LLMProvider,
    session: Session,
    current_role: str = "",
    knowledge_manager: MemoryManager = None,
) -> tuple[str, str, Session]:
    """主对话循环

    Args:
        provider: LLM Provider
        session: 会话对象
        current_role: 当前角色名称
        knowledge_manager: 角色知识库管理器

    Returns:
        (action, value, session):
        - ("quit", "", session) - 正常退出
        - ("switch_provider", provider_id, session) - 切换 Provider
        - ("switch_role", role_name, session) - 切换角色
        - ("start_debate", "", session) - 进入辩论模式
    """
    role_manager = RoleManager()

    # 初始化会话存储和用户记忆
    session_store = ChatSessionStore()
    user_memory = UserMemory()

    # 检查是否有保存的会话
    saved_data = session_store.load()
    if saved_data:
        time_ago = session_store.get_time_ago(saved_data)
        saved_role = saved_data.get("participants", [""])[0]
        msg_count = len(saved_data.get("history", []))
        print(f"\n发现上次对话（{time_ago}）| 角色: {saved_role or '无'} | {msg_count}条消息")
        print("[1] 继续上次对话")
        print("[2] 新对话")
        choice = input("\n选择: ").strip()
        if choice != "2":
            session = session_store.restore_session(saved_data)
            print(f"已恢复会话，共 {msg_count} 条消息")
        else:
            session_store.archive()

    # 显示欢迎信息
    print("\n" + "=" * 50)
    print("LIFEE - 辩论式 AI 决策助手")
    print("=" * 50)
    print(f"Provider: {provider.name} ({provider.model})")
    if current_role:
        info = role_manager.get_role_info(current_role)
        display_name = info.get("display_name", current_role)
        print(f"角色: {display_name}")
        if info.get("has_knowledge"):
            print(f"知识库: 已启用")
    print("输入 /help 查看帮助，/quit 退出")
    print("=" * 50 + "\n")

    while True:
        try:
            # 获取用户输入
            user_input = input("你: ").strip()

            if not user_input:
                continue

            # 处理命令
            if user_input.startswith("/"):
                cmd = user_input.lower()
                if cmd == "/quit" or cmd == "/exit":
                    # 保存会话后退出
                    if session.history:
                        session_store.save(session, [current_role or "default"])
                        print("[会话已自动保存]")
                    print("\n再见！")
                    return ("quit", "", session)
                elif cmd == "/help":
                    print("\n命令列表:")
                    print("  /help     - 显示帮助")
                    print("  /history  - 显示对话历史")
                    print("  /clear    - 清空对话历史")
                    print("  /sessions - 历史会话")
                    print("  /role     - 切换角色")
                    print("  /debate   - 进入多角度讨论模式")
                    print("  /config   - 切换 LLM Provider")
                    print("  /model    - 切换当前 Provider 的模型")
                    print("  /memory   - 显示知识库状态")
                    print("  /quit     - 退出程序")
                    print()
                    continue
                elif cmd == "/memory" or cmd.startswith("/memory "):
                    if not knowledge_manager:
                        print("\n当前角色没有知识库")
                        print("创建方法: 在角色目录下创建 knowledge/ 目录，添加 .md 文件\n")
                        continue
                    # /memory status
                    if cmd == "/memory":
                        stats = knowledge_manager.get_stats()
                        print("\n知识库状态:")
                        print(f"  文件数: {stats['file_count']}")
                        print(f"  分块数: {stats['chunk_count']}")
                        print(f"  嵌入模型: {stats['embedding_provider']}/{stats['embedding_model']}")
                        print()
                        continue
                    # /memory search <query>
                    if cmd.startswith("/memory search "):
                        query = user_input[15:].strip()
                        if not query:
                            print("\n用法: /memory search <查询内容>\n")
                            continue
                        print(f"\n搜索: {query}")
                        results = await knowledge_manager.search(query, max_results=5)
                        if not results:
                            print("没有找到相关内容\n")
                        else:
                            print(f"找到 {len(results)} 条结果:\n")
                            for i, r in enumerate(results, 1):
                                print(f"[{i}] {Path(r.path).name}:{r.start_line}-{r.end_line} (分数: {r.score:.2f})")
                                # 显示前 100 字符
                                preview = r.text[:100].replace("\n", " ")
                                print(f"    {preview}...")
                                print()
                        continue
                    print("\n未知的 /memory 子命令")
                    print("用法:")
                    print("  /memory         - 显示知识库状态")
                    print("  /memory search <query> - 搜索知识库\n")
                    continue
                elif cmd == "/debate":
                    # 保存当前会话后进入辩论模式
                    if session.history:
                        session_store.save(session, [current_role or "default"])
                    return ("start_debate", "", session)
                elif cmd == "/role":
                    new_role = select_role_interactive(role_manager, current_role)
                    if new_role != current_role:
                        # 切换角色时归档当前会话
                        if session.history:
                            session_store.save(session, [current_role or "default"])
                            session_store.archive()
                        return ("switch_role", new_role, session)
                    continue
                elif cmd == "/config":
                    new_provider_id = select_provider_interactive(show_welcome=False)
                    if new_provider_id:
                        return ("switch_provider", new_provider_id, session)
                    continue
                elif cmd == "/model":
                    # 获取当前 Provider ID
                    provider_id = settings.llm_provider.lower()
                    current_model = provider.model

                    # 检查是否支持模型切换
                    if provider_id == "qwen-portal":
                        print("\nQwen Portal 不支持模型切换")
                        print("可选模型固定为: coder-model, vision-model\n")
                        continue

                    new_model = select_model_for_provider(provider_id, current_model)
                    if new_model:
                        return ("switch_provider", provider_id, session)
                    continue
                elif cmd == "/history":
                    if not session.history:
                        print("\n[对话历史为空]\n")
                    else:
                        print("\n--- 对话历史 ---")
                        for i, msg in enumerate(session.history, 1):
                            role = "你" if msg.role == MessageRole.USER else "AI"
                            content = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
                            print(f"{i}. [{role}] {content}")
                        print("--- 共 {} 条消息 ---\n".format(len(session.history)))
                    continue
                elif cmd == "/clear":
                    session.clear_history()
                    session_store.clear()
                    print("\n[对话历史已清空]\n")
                    continue
                elif cmd == "/sessions":
                    history_sessions = session_store.list_history()
                    if not history_sessions:
                        print("\n[没有历史会话]\n")
                    else:
                        print("\n--- 历史会话 ---")
                        for i, s in enumerate(history_sessions):
                            time_str = s["updated_at"][:16].replace("T", " ") if s["updated_at"] else "未知"
                            role_str = s["participants"][0] if s["participants"] else "default"
                            print(f"  [{i+1}] {time_str} | {role_str} | {s['msg_count']}条消息")
                        print("\n输入序号恢复，或按回车取消")
                        choice = input("选择: ").strip()
                        if choice.isdigit() and 1 <= int(choice) <= len(history_sessions):
                            selected = history_sessions[int(choice) - 1]
                            history_data = session_store.load_history(selected["filename"])
                            if history_data:
                                session_store.archive()
                                session = session_store.restore_session(history_data)
                                print(f"\n[已恢复会话，共 {len(session.history)} 条消息]\n")
                            else:
                                print("\n[无法加载该会话]\n")
                    continue
                else:
                    print(f"\n未知命令: {cmd}，输入 /help 查看帮助\n")
                    continue

            # 添加用户消息到历史
            session.add_user_message(user_input)

            # 准备消息列表
            messages = session.get_messages()

            # 构建系统提示词
            base_prompt = """你是 LIFEE 的 AI 助手，一个辩论式决策助手。
你的职责是帮助用户思考人生决策问题，提供多角度的观点和建议。
保持友好、专业的态度，用中文回复。"""

            # 如果有角色，加载角色配置
            if current_role:
                role_prompt = role_manager.load_role(current_role)
                if role_prompt:
                    system_prompt = role_prompt + "\n\n---\n\n" + base_prompt
                else:
                    system_prompt = base_prompt
            else:
                system_prompt = base_prompt

            # 注入用户记忆上下文
            memory_context = user_memory.get_context()
            if memory_context:
                system_prompt += f"\n\n关于与你对话的用户：\n{memory_context}"

            # 如果有知识库，搜索相关内容并注入
            if knowledge_manager:
                try:
                    search_results = await knowledge_manager.search(
                        user_input,
                        max_results=3,
                        min_score=0.35,
                    )
                    if search_results:
                        # 基于用户输入匹配触发技能 (Tier 2)
                        if current_role:
                            skill_set = load_skill_set(role_manager.roles_dir / current_role)
                            if skill_set.triggered_skills:
                                matched = skill_set.match_by_input(user_input)
                                if matched:
                                    triggered_text = "\n\n".join(s.content for s in matched)
                                    system_prompt = system_prompt + "\n\n" + triggered_text

                        knowledge_context = format_search_results(search_results)
                        system_prompt = system_prompt + "\n\n---\n\n## 相关知识（供参考）\n\n" + knowledge_context
                except Exception as e:
                    # 搜索失败不影响对话
                    if settings.debug:
                        print(f"[知识库搜索失败: {e}]")

            # 流式输出
            print("\nAI: ", end="", flush=True)
            full_response = ""

            async for chunk in provider.stream(
                messages=messages,
                system=system_prompt,
                temperature=0.7,
            ):
                print(chunk, end="", flush=True)
                full_response += chunk

            print("\n")

            # 添加助手消息到历史
            session.add_assistant_message(full_response)

            # 自动保存会话
            session_store.save(session, [current_role or "default"])

            # 后台提取用户记忆（不阻塞主流程）
            asyncio.create_task(user_memory.auto_extract(session.history, provider))

        except KeyboardInterrupt:
            print("\n\n[中断] 再见！")
            if session.history:
                session_store.save(session, [current_role or "default"])
                print("[会话已自动保存]")
            return ("quit", "", session)
        except Exception as e:
            print(f"\n[错误] {e}\n")
            if settings.debug:
                import traceback
                traceback.print_exc()

    return ("quit", "", session)
