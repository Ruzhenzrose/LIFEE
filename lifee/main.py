"""LIFEE CLI 入口"""
import asyncio
import sys
from pathlib import Path

# Windows 控制台 UTF-8 编码支持
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")

from lifee.config.settings import settings


def save_api_key_to_env(key_name: str, key_value: str) -> bool:
    """保存 API Key 到 .env 文件"""
    env_path = Path(".env")

    # 如果 .env 不存在，从 .env.example 复制
    if not env_path.exists():
        example_path = Path(".env.example")
        if example_path.exists():
            env_path.write_text(example_path.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            # 创建基础 .env
            env_path.write_text(f"LLM_PROVIDER=qwen\n{key_name}={key_value}\n", encoding="utf-8")
            return True

    # 读取现有内容
    content = env_path.read_text(encoding="utf-8")
    lines = content.split("\n")

    # 查找并更新 key
    found = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key_name}="):
            lines[i] = f"{key_name}={key_value}"
            found = True
            break

    if not found:
        # 添加新的 key
        lines.append(f"{key_name}={key_value}")

    # 写回文件
    env_path.write_text("\n".join(lines), encoding="utf-8")
    return True


import httpx


def get_ollama_models() -> list:
    """获取 Ollama 已安装的模型列表"""
    try:
        response = httpx.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            data = response.json()
            models = data.get("models", [])
            return [m["name"] for m in models]
    except Exception:
        pass
    return []


# 各供应商的模型列表
PROVIDER_MODELS = {
    "qwen": {
        "env_key": "QWEN_MODEL",
        "models": [
            ("qwen-plus", "通用对话，性价比高"),
            ("qwen-max", "最强模型，复杂任务"),
            ("qwen-turbo", "快速响应，简单任务"),
            ("qwen-long", "超长上下文"),
        ],
    },
    "gemini": {
        "env_key": "GEMINI_MODEL",
        "models": [
            ("gemini-3-flash-preview", "Gemini 3 快速"),
            ("gemini-3-pro-preview", "Gemini 3 最强"),
            ("gemini-2.5-pro", "2.5 最强"),
            ("gemini-2.5-flash", "2.5 快速"),
            ("gemini-2.5-flash-lite", "2.5 轻量"),
            ("gemini-2.0-flash", "2.0 推荐"),
            ("gemini-2.0-flash-lite", "2.0 轻量"),
        ],
    },
    "opencode": {
        "env_key": "OPENCODE_MODEL",
        "models": [
            ("big-pickle", "OpenCode 免费"),
        ],
    },
    "claude": {
        "env_key": "CLAUDE_MODEL",
        "models": [
            ("claude-opus-4-5", "最强模型"),
            ("claude-sonnet-4", "平衡能力和速度"),
            ("claude-3-5-haiku", "快速响应"),
        ],
    },
}


def select_model_for_provider(provider_id: str, current_model: str) -> str:
    """交互式选择供应商模型"""
    if provider_id == "ollama":
        return select_ollama_model()

    if provider_id not in PROVIDER_MODELS:
        print(f"\n{provider_id} 不支持模型切换")
        return ""

    config = PROVIDER_MODELS[provider_id]
    models = config["models"]
    env_key = config["env_key"]

    print(f"\n可用模型:\n")
    for i, (model_id, desc) in enumerate(models, 1):
        current = " (当前)" if model_id == current_model else ""
        print(f"  {i}. {model_id}{current}")
        print(f"     {desc}")
        print()

    while True:
        choice = input(f"请选择模型 (1-{len(models)}，或 q 取消): ").strip()

        if choice.lower() == 'q':
            print("已取消")
            return ""

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(models):
                selected = models[idx][0]
                save_api_key_to_env(env_key, selected)
                print(f"\n已选择: {selected}")
                return selected
        except ValueError:
            pass

        print("无效选择，请重新输入")


OLLAMA_RECOMMENDED_MODELS = [
    ("qwen2.5", "7B, 4.4GB", "通用对话，中英文"),
    ("llama3.3", "70B, 43GB", "强大，需大显存"),
    ("deepseek-r1", "7B, 4.7GB", "推理能力强"),
    ("gemma2", "9B, 5.4GB", "Google 开源"),
    ("phi3", "3.8B, 2.3GB", "微软，轻量快速"),
    ("mistral", "7B, 4.1GB", "欧洲开源"),
]


def show_ollama_recommended_models():
    """显示 Ollama 推荐模型列表"""
    print("\n推荐模型:\n")
    for i, (name, size, desc) in enumerate(OLLAMA_RECOMMENDED_MODELS, 1):
        print(f"  {i}. {name}")
        print(f"     {size} | {desc}")
        print()
    print(f"  0. 手动输入模型名")
    print()


def select_ollama_model() -> str:
    """交互式选择 Ollama 模型"""
    print("\n正在检查 Ollama 模型...")

    models = get_ollama_models()

    if not models:
        print("\n未找到已安装的 Ollama 模型")
        show_ollama_recommended_models()

        while True:
            choice = input(f"请选择模型 (1-{len(OLLAMA_RECOMMENDED_MODELS)}，或 0 手动输入): ").strip()

            if choice == "0":
                model = input("输入模型名: ").strip()
                if model:
                    break
                continue

            try:
                idx = int(choice) - 1
                if 0 <= idx < len(OLLAMA_RECOMMENDED_MODELS):
                    model = OLLAMA_RECOMMENDED_MODELS[idx][0]
                    break
            except ValueError:
                pass
            print("无效选择，请重新输入")

        print(f"\n已选择 {model}，首次使用会自动下载")
        save_api_key_to_env("OLLAMA_MODEL", model)
        return model

    print(f"\n已安装的 Ollama 模型:\n")
    for i, model in enumerate(models, 1):
        # 标记当前使用的模型
        current = " (当前)" if model == settings.ollama_model else ""
        print(f"  {i}. {model}{current}")

    print()
    print("  0. 下载新模型")
    print()

    while True:
        choice = input(f"请选择模型 (1-{len(models)}，或 0 下载新模型): ").strip()

        if choice == "0":
            # 显示推荐模型列表
            show_ollama_recommended_models()

            while True:
                sub_choice = input(f"请选择模型 (1-{len(OLLAMA_RECOMMENDED_MODELS)}，或 0 手动输入): ").strip()

                if sub_choice == "0":
                    model = input("输入模型名: ").strip()
                    if model:
                        save_api_key_to_env("OLLAMA_MODEL", model)
                        print(f"\n已选择 {model}，首次使用会自动下载")
                        return model
                    continue

                try:
                    idx = int(sub_choice) - 1
                    if 0 <= idx < len(OLLAMA_RECOMMENDED_MODELS):
                        model = OLLAMA_RECOMMENDED_MODELS[idx][0]
                        save_api_key_to_env("OLLAMA_MODEL", model)
                        print(f"\n已选择 {model}，首次使用会自动下载")
                        return model
                except ValueError:
                    pass
                print("无效选择，请重新输入")

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(models):
                selected = models[idx]
                save_api_key_to_env("OLLAMA_MODEL", selected)
                print(f"\n已选择: {selected}")
                return selected
        except ValueError:
            pass

        print("无效选择，请重新输入")


def prompt_for_api_key(provider_name: str, key_name: str, get_url: str) -> str:
    """提示用户输入 API Key"""
    print(f"\n{'='*50}")
    print(f"首次使用 {provider_name}，需要配置 API Key")
    print(f"{'='*50}")
    print(f"获取地址: {get_url}")
    print()

    while True:
        api_key = input("请粘贴你的 API Key (输入 q 退出): ").strip()

        if api_key.lower() == 'q':
            print("已取消")
            sys.exit(0)

        if not api_key:
            print("API Key 不能为空，请重新输入")
            continue

        # 保存到 .env
        if save_api_key_to_env(key_name, api_key):
            print(f"\n已保存到 .env 文件")
            return api_key
        else:
            print("保存失败，请手动编辑 .env 文件")
            sys.exit(1)


# Provider 选项配置
PROVIDER_OPTIONS = [
    {
        "id": "qwen",
        "name": "Qwen (通义千问)",
        "desc": "免费 2000 请求/天 | 模型: qwen-plus, qwen-max, qwen-turbo",
        "needs_key": True,
    },
    {
        "id": "gemini",
        "name": "Google Gemini",
        "desc": "免费 | 模型: gemini-3-flash, gemini-2.5-pro, gemini-2.0-flash",
        "needs_key": True,
    },
    {
        "id": "ollama",
        "name": "Ollama (本地)",
        "desc": "完全免费 | 推荐: qwen2.5, llama3.3, deepseek-r1",
        "needs_key": False,
    },
    {
        "id": "opencode",
        "name": "OpenCode Zen",
        "desc": "Big Pickle 免费 | 其他模型需订阅",
        "needs_key": True,
    },
    {
        "id": "claude",
        "name": "Claude",
        "desc": "需要会员 | 模型: claude-opus-4-5, claude-sonnet-4",
        "needs_key": True,
    },
]


def get_provider_key_status(provider_id: str) -> str:
    """检查 Provider 是否已配置 API Key，返回状态标记"""
    env_path = Path(".env")
    if not env_path.exists():
        return ""

    content = env_path.read_text(encoding="utf-8")

    # 各 Provider 对应的 KEY 名称
    key_mapping = {
        "qwen": "QWEN_API_KEY",
        "gemini": "GOOGLE_API_KEY",
        "opencode": "OPENCODE_API_KEY",
        "synthetic": "SYNTHETIC_API_KEY",
        "claude": "ANTHROPIC_API_KEY",
    }

    # 不需要 Key 的 Provider
    if provider_id == "ollama":
        return " ✓"

    key_name = key_mapping.get(provider_id)
    if not key_name:
        return ""

    for line in content.split("\n"):
        if line.startswith(f"{key_name}="):
            value = line.split("=", 1)[1].strip()
            if value:
                return " ✓"
    return ""


def select_provider_interactive(show_welcome: bool = True) -> str:
    """交互式选择 LLM Provider"""
    if show_welcome:
        print("\n" + "=" * 50)
        print("欢迎使用 LIFEE - 辩论式 AI 决策助手")
        print("=" * 50)
    else:
        print("\n" + "=" * 50)
        print("切换 LLM Provider")
        print("=" * 50)

    print("\n请选择 LLM Provider (✓ 表示已配置):\n")

    for i, opt in enumerate(PROVIDER_OPTIONS, 1):
        status = get_provider_key_status(opt["id"])
        print(f"  {i}. {opt['name']}{status}")
        print(f"     {opt['desc']}")
        print()

    while True:
        choice = input("请输入序号 (1-7，或 q 取消): ").strip()

        if choice.lower() == 'q':
            if show_welcome:
                print("已取消")
                sys.exit(0)
            else:
                print("已取消切换")
                return ""

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(PROVIDER_OPTIONS):
                selected = PROVIDER_OPTIONS[idx]
                provider_id = selected["id"]

                # 保存选择到 .env
                save_api_key_to_env("LLM_PROVIDER", provider_id)
                print(f"\n已选择: {selected['name']}")

                return provider_id
            else:
                print("无效的序号，请重新输入")
        except ValueError:
            print("请输入有效的数字")


from lifee.providers import (
    LLMProvider,
    Message,
    MessageRole,
    ClaudeProvider,
    SyntheticProvider,
    QwenPortalProvider,
    QwenProvider,
    OllamaProvider,
    OpenCodeZenProvider,
    GeminiProvider,
    read_clawdbot_qwen_credentials,
    read_clawdbot_synthetic_credentials,
)
from lifee.sessions import Session, SessionStore
from lifee.roles import RoleManager
from lifee.memory import MemoryManager, format_search_results
from lifee.debate import Moderator, Participant, DebateContext


def collect_user_input_nonblocking() -> str:
    """非阻塞收集用户输入（直到按回车）

    在 ping-pong 模式中，当检测到用户按键时调用此函数。
    用户输入会实时回显到屏幕上。
    """
    import msvcrt

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


def reload_settings():
    """重新加载配置"""
    from importlib import reload
    import sys
    # 获取实际的模块对象
    settings_module = sys.modules.get('lifee.config.settings')
    if settings_module is not None:
        reload(settings_module)
    # 更新全局 settings 引用
    global settings
    from lifee.config.settings import settings as new_settings
    settings = new_settings
    return new_settings


def create_provider(provider_name: str = None) -> LLMProvider:
    """根据配置创建 LLM Provider

    Args:
        provider_name: 指定的 Provider 名称，如果为 None 则从配置读取
    """
    if provider_name is None:
        provider_name = settings.llm_provider.lower()
    else:
        provider_name = provider_name.lower()

    if provider_name == "claude":
        api_key = settings.get_anthropic_api_key()
        if not api_key:
            print("\n错误: 未找到 Claude 认证凭据")
            print("解决方法:")
            print("  1. 运行 'claude login' 登录 Claude Code")
            print("  2. 或设置环境变量 ANTHROPIC_API_KEY")
            sys.exit(1)
        return ClaudeProvider(api_key=api_key, model=settings.claude_model)

    elif provider_name == "synthetic":
        # 尝试从环境变量或 clawdbot 获取 API Key
        api_key = settings.synthetic_api_key
        if not api_key:
            # 尝试从 clawdbot 获取
            api_key = read_clawdbot_synthetic_credentials()
        if not api_key:
            api_key = prompt_for_api_key(
                "Synthetic (免费大模型代理)",
                "SYNTHETIC_API_KEY",
                "https://synthetic.new/"
            )
        return SyntheticProvider(
            api_key=api_key,
            model=settings.synthetic_model,
        )

    elif provider_name == "qwen":
        api_key = settings.qwen_api_key
        if not api_key:
            api_key = prompt_for_api_key(
                "Qwen (通义千问)",
                "QWEN_API_KEY",
                "https://dashscope.console.aliyun.com/"
            )
        return QwenProvider(api_key=api_key, model=settings.qwen_model)

    elif provider_name == "gemini":
        api_key = settings.google_api_key
        if not api_key:
            api_key = prompt_for_api_key(
                "Google Gemini",
                "GOOGLE_API_KEY",
                "https://aistudio.google.com/apikey"
            )
        return GeminiProvider(api_key=api_key, model=settings.gemini_model)

    elif provider_name == "ollama":
        # 检查是否需要选择模型（首次使用或模型未设置）
        model = settings.ollama_model
        if not model or model == "qwen2.5":
            # 检查是否有已安装的模型
            installed_models = get_ollama_models()
            if installed_models and model not in installed_models:
                # 当前配置的模型未安装，让用户选择
                model = select_ollama_model()
                reload_settings()
                model = settings.ollama_model

        return OllamaProvider(
            model=model,
            base_url=settings.ollama_base_url,
        )

    elif provider_name == "opencode":
        api_key = settings.opencode_api_key
        if not api_key:
            api_key = prompt_for_api_key(
                "OpenCode Zen (GLM-4.7 免费)",
                "OPENCODE_API_KEY",
                "https://opencode.ai/"
            )
        return OpenCodeZenProvider(
            api_key=api_key,
            model=settings.opencode_model,
        )

    else:
        print(f"\n错误: 未知的 Provider: {provider_name}")
        print("支持的 Provider: claude, synthetic, qwen, gemini, ollama, opencode")
        sys.exit(1)


def select_role_interactive(role_manager: RoleManager, current_role: str) -> str:
    """交互式选择角色"""
    roles = role_manager.list_roles()

    if not roles:
        print("\n没有可用的角色")
        print("创建角色: 在 lifee/roles/ 下创建目录，添加 SOUL.md 文件")
        print("参考模板: lifee/roles/_template/")
        return current_role

    print("\n可用角色:\n")
    print(f"  0. [无角色] (默认对话模式)")
    for i, role in enumerate(roles, 1):
        info = role_manager.get_role_info(role)
        display_name = info.get("display_name", role)
        current = " (当前)" if role == current_role else ""
        print(f"  {i}. {role}{current}")
        if display_name != role:
            print(f"     名字: {display_name}")

    print()

    while True:
        choice = input(f"请选择角色 (0-{len(roles)}，或 q 取消): ").strip()

        if choice.lower() == 'q':
            print("已取消")
            return current_role

        try:
            idx = int(choice)
            if idx == 0:
                print("\n已切换到: [无角色]")
                return ""
            if 1 <= idx <= len(roles):
                selected = roles[idx - 1]
                print(f"\n已切换到: {selected}")
                return selected
        except ValueError:
            pass

        print("无效选择，请重新输入")


async def chat_loop(
    provider: LLMProvider,
    session: Session,
    current_role: str = "",
    knowledge_manager: MemoryManager = None,
) -> tuple[str, str]:
    """主对话循环

    Args:
        provider: LLM Provider
        session: 会话对象
        current_role: 当前角色名称
        knowledge_manager: 角色知识库管理器

    Returns:
        (action, value):
        - ("quit", "") - 正常退出
        - ("switch_provider", provider_id) - 切换 Provider
        - ("switch_role", role_name) - 切换角色
    """
    role_manager = RoleManager()

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
                    print("\n再见！")
                    return ("quit", "")
                elif cmd == "/help":
                    print("\n命令列表:")
                    print("  /help    - 显示帮助")
                    print("  /history - 显示对话历史")
                    print("  /clear   - 清空对话历史")
                    print("  /role    - 切换角色")
                    print("  /debate  - 进入多角度讨论模式")
                    print("  /config  - 切换 LLM Provider")
                    print("  /model   - 切换当前 Provider 的模型")
                    print("  /memory  - 显示知识库状态")
                    print("  /quit    - 退出程序")
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
                    return ("start_debate", "")
                elif cmd == "/role":
                    new_role = select_role_interactive(role_manager, current_role)
                    if new_role != current_role:
                        return ("switch_role", new_role)
                    continue
                elif cmd == "/config":
                    new_provider_id = select_provider_interactive(show_welcome=False)
                    if new_provider_id:
                        return ("switch_provider", new_provider_id)
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
                        return ("switch_provider", provider_id)
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
                    print("\n[对话历史已清空]\n")
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

            # 如果有知识库，搜索相关内容并注入
            if knowledge_manager:
                try:
                    search_results = await knowledge_manager.search(
                        user_input,
                        max_results=3,
                        min_score=0.35,
                    )
                    if search_results:
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

        except KeyboardInterrupt:
            print("\n\n[中断] 再见！")
            return ("quit", "")
        except Exception as e:
            print(f"\n[错误] {e}\n")
            if settings.debug:
                import traceback
                traceback.print_exc()

    return ("quit", "")


def check_first_run() -> bool:
    """检查是否是首次运行（没有配置 .env）"""
    env_path = Path(".env")
    if not env_path.exists():
        return True

    # 检查 LLM_PROVIDER 是否有值
    content = env_path.read_text(encoding="utf-8")
    for line in content.split("\n"):
        if line.startswith("LLM_PROVIDER="):
            value = line.split("=", 1)[1].strip()
            # 如果是默认值 claude 且没有 API key，也算首次
            if value and value != "claude":
                return False
            # claude 需要检查是否有认证
            if value == "claude":
                from lifee.config.settings import settings
                if settings.get_anthropic_api_key():
                    return False
    return True


async def main():
    """主函数"""
    # 检查是否首次运行，显示交互式选择
    if check_first_run():
        select_provider_interactive()
        reload_settings()

    # 初始化会话存储（Phase 1 使用内存存储）
    store = SessionStore(storage_dir=None)

    # 创建新会话
    session = store.create()

    # 当前状态
    current_provider_id = None
    current_role = ""  # 当前角色
    knowledge_manager = None  # 角色知识库管理器
    role_manager = RoleManager()

    # 主循环：支持热切换 Provider 和角色
    while True:
        # 重新加载配置以获取最新的 Provider 设置
        reload_settings()

        # 创建 Provider
        provider = create_provider()
        current_provider_id = settings.llm_provider.lower()

        # 如果有角色且有知识库，创建/更新知识库管理器
        if current_role:
            info = role_manager.get_role_info(current_role)
            if info.get("has_knowledge") and knowledge_manager is None:
                print(f"正在初始化角色知识库...")
                try:
                    knowledge_manager = await role_manager.get_knowledge_manager(
                        current_role,
                        google_api_key=settings.google_api_key,
                        openai_api_key=getattr(settings, 'openai_api_key', None),
                    )
                    if knowledge_manager:
                        stats = knowledge_manager.get_stats()
                        print(f"知识库已加载: {stats['file_count']} 个文件, {stats['chunk_count']} 个分块")
                except Exception as e:
                    print(f"知识库初始化失败: {e}")
                    knowledge_manager = None

        # 启动对话循环
        action, value = await chat_loop(provider, session, current_role, knowledge_manager)

        if action == "quit":
            # 关闭知识库管理器
            if knowledge_manager:
                knowledge_manager.close()
            break
        elif action == "switch_provider":
            print(f"\n正在切换到 {value}...")
            continue
        elif action == "switch_role":
            # 关闭旧的知识库管理器
            if knowledge_manager:
                knowledge_manager.close()
                knowledge_manager = None
            current_role = value
            continue
        elif action == "start_debate":
            # 进入辩论模式
            action, value = await debate_loop(provider, session)
            if action == "quit":
                if knowledge_manager:
                    knowledge_manager.close()
                break
            continue


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
        # 获取 emoji
        role_dir = role_manager.roles_dir / role_name
        emoji = "🤖"
        identity_file = role_dir / "IDENTITY.md"
        if identity_file.exists():
            content = identity_file.read_text(encoding="utf-8")
            for line in content.split("\n"):
                if "**Emoji:**" in line:
                    emoji = line.split(":**")[1].strip()
                    break
        role_choices.append([role_name, display_name, emoji, False])  # 默认不选

    # 交互式选择界面（支持方向键、空格、数字）
    import msvcrt
    import ctypes

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
                print("--- 角色对话 (按任意键插话) ---")
                current_participant = None
                skip_happened = False
                user_interjected = False  # 用户是否插话
                last_participant = None  # 记录上一个完成发言的参与者
                pending_user_input = ""  # 待处理的用户输入
                all_participants_info = [p.info for p in participants]

                async for participant, chunk, is_skip in moderator.run_pingpong(max_turns=5):
                    if is_skip:
                        print(f"\n{participant.info.emoji} {participant.info.display_name} 选择不再继续对话")
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

                            session.add_assistant_message(response, name=current_participant.info.display_name)
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

                                session.add_assistant_message(response, name=current_participant.info.display_name)
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


if __name__ == "__main__":
    asyncio.run(main())
