"""LIFEE 主应用"""
import sys
from pathlib import Path

# Windows 控制台 UTF-8 编码支持
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")

from lifee.config.settings import settings
from lifee.providers import (
    LLMProvider,
    ClaudeProvider,
    SyntheticProvider,
    QwenProvider,
    OllamaProvider,
    OpenCodeZenProvider,
    GeminiProvider,
    FallbackProvider,
    read_clawdbot_synthetic_credentials,
)
from lifee.sessions import Session, SessionStore, DebateSessionStore
from lifee.roles import RoleManager
from lifee.debate import Participant

from .setup import (
    save_api_key_to_env,
    get_ollama_models,
    select_ollama_model,
    prompt_for_api_key,
    select_provider_interactive,
    select_roles_interactive,
    select_menu_interactive,
)
from .debate import debate_loop


# Provider 配置表：简化 API Key 获取逻辑
PROVIDER_REGISTRY = {
    "qwen": {
        "class": QwenProvider,
        "key_attr": "qwen_api_key",
        "model_attr": "qwen_model",
        "prompt_name": "Qwen (通义千问)",
        "env_key": "QWEN_API_KEY",
        "get_url": "https://dashscope.console.aliyun.com/",
    },
    "gemini": {
        "class": GeminiProvider,
        "key_attr": "google_api_key",
        "model_attr": "gemini_model",
        "prompt_name": "Google Gemini",
        "env_key": "GOOGLE_API_KEY",
        "get_url": "https://aistudio.google.com/apikey",
    },
    "opencode": {
        "class": OpenCodeZenProvider,
        "key_attr": "opencode_api_key",
        "model_attr": "opencode_model",
        "prompt_name": "OpenCode Zen (GLM-4.7 免费)",
        "env_key": "OPENCODE_API_KEY",
        "get_url": "https://opencode.ai/",
    },
}


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
    return new_settings


def create_provider(provider_name: str = None) -> LLMProvider:
    """根据配置创建 LLM Provider

    Args:
        provider_name: 指定的 Provider 名称，如果为 None 则从配置读取
    """
    current_settings = reload_settings()

    if provider_name is None:
        provider_name = current_settings.llm_provider.lower()
    else:
        provider_name = provider_name.lower()

    if provider_name == "claude":
        api_key = current_settings.get_anthropic_api_key()
        if not api_key:
            print("\n错误: 未找到 Claude 认证凭据")
            print("解决方法:")
            print("  1. 运行 'claude login' 登录 Claude Code")
            print("  2. 或设置环境变量 ANTHROPIC_API_KEY")
            sys.exit(1)
        return ClaudeProvider(api_key=api_key, model=current_settings.claude_model)

    elif provider_name == "synthetic":
        # 尝试从环境变量或 clawdbot 获取 API Key
        api_key = current_settings.synthetic_api_key
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
            model=current_settings.synthetic_model,
        )

    # 使用配置表处理通用 Provider
    elif provider_name in PROVIDER_REGISTRY:
        config = PROVIDER_REGISTRY[provider_name]
        api_key = getattr(current_settings, config["key_attr"])
        if not api_key:
            api_key = prompt_for_api_key(
                config["prompt_name"],
                config["env_key"],
                config["get_url"],
            )
        model = getattr(current_settings, config["model_attr"])
        return config["class"](api_key=api_key, model=model)

    elif provider_name == "ollama":
        # 检查是否需要选择模型（首次使用或模型未设置）
        model = current_settings.ollama_model
        if not model or model == "qwen2.5":
            # 检查是否有已安装的模型
            installed_models = get_ollama_models()
            if installed_models and model not in installed_models:
                # 当前配置的模型未安装，让用户选择
                model = select_ollama_model()
                current_settings = reload_settings()
                model = current_settings.ollama_model

        return OllamaProvider(
            model=model,
            base_url=current_settings.ollama_base_url,
        )

    else:
        print(f"\n错误: 未知的 Provider: {provider_name}")
        print("支持的 Provider: claude, synthetic, qwen, gemini, ollama, opencode")
        sys.exit(1)


def get_available_providers() -> list[str]:
    """检测所有配置了 API Key 的 Provider

    Returns:
        可用 Provider 名称列表（按推荐优先级排序）
    """
    current_settings = reload_settings()
    available = []

    # 检查各 Provider 的 API Key（按优先级排序）
    checks = [
        ("claude", current_settings.get_anthropic_api_key()),
        ("gemini", current_settings.google_api_key),
        ("qwen", current_settings.qwen_api_key),
        ("opencode", current_settings.opencode_api_key),
        ("synthetic", current_settings.synthetic_api_key),
        # ollama 不需要 API Key，暂不自动加入
    ]

    for name, key in checks:
        if key:
            available.append(name)

    return available


def create_provider_with_fallback(provider_name: str = None) -> LLMProvider:
    """创建带 fallback 的 Provider

    如果配置了 LLM_FALLBACK，当主 Provider 不可用时会自动切换到备用 Provider。
    LLM_FALLBACK=auto 时，自动检测所有配置了 API Key 的 Provider。

    Args:
        provider_name: 指定的 Provider 名称，如果为 None 则从配置读取
    """
    current_settings = reload_settings()

    # 创建主 Provider
    primary = create_provider(provider_name)
    primary_name = (provider_name or current_settings.llm_provider).lower()

    # 检查是否有 fallback 配置
    fallback_str = current_settings.llm_fallback.strip().lower()
    if not fallback_str:
        return primary

    # 解析 fallback 列表
    if fallback_str == "auto":
        # 自动检测所有可用的 Provider
        fallback_names = get_available_providers()
    else:
        fallback_names = [s.strip() for s in fallback_str.split(",") if s.strip()]

    if not fallback_names:
        return primary

    # 创建所有 Provider
    providers = [primary]
    for name in fallback_names:
        try:
            # 跳过和主 Provider 相同的
            if name.lower() == primary_name:
                continue
            providers.append(create_provider(name))
        except Exception as e:
            # 无法创建的 fallback Provider 跳过，但打印警告
            print(f"[警告] 无法创建 fallback provider '{name}': {e}")

    if len(providers) == 1:
        return primary

    return FallbackProvider(providers)


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


async def create_participants(
    role_names: list[str],
    provider: LLMProvider,
    role_manager: RoleManager,
) -> list[Participant]:
    """创建参与者列表

    Args:
        role_names: 角色名称列表
        provider: LLM Provider
        role_manager: 角色管理器

    Returns:
        Participant 对象列表
    """
    print("\n正在加载参与者...")
    participants = []
    for role_name in role_names:
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
    return participants


def map_display_names_to_role_names(
    display_names: list[str],
    role_manager: RoleManager,
) -> list[str]:
    """将显示名称映射回角色目录名称

    Args:
        display_names: 显示名称列表（如 ["克里希那穆提", "拉康"]）
        role_manager: 角色管理器

    Returns:
        角色目录名称列表
    """
    roles = role_manager.list_roles()
    name_map = {}
    for role_name in roles:
        info = role_manager.get_role_info(role_name)
        display = info.get("display_name", role_name)
        name_map[display] = role_name
    return [name_map.get(n, n) for n in display_names]


async def main_menu(
    provider: LLMProvider,
    role_manager: RoleManager,
    session_store: DebateSessionStore,
) -> tuple[str, dict | None]:
    """主菜单

    Returns:
        ("start", {"participants": [...], "session": Session}) - 开始对话
        ("settings", None) - 进入设置
        ("quit", None) - 退出
    """
    saved_data = session_store.load()
    history_sessions = session_store.list_history()

    # 构建菜单选项
    option_labels = []
    option_keys = []

    if saved_data:
        time_ago = session_store.get_time_ago(saved_data)
        participants_str = "、".join(saved_data.get("participants", []))
        msg_count = len(saved_data.get("history", []))
        option_labels.append(f"继续上次对话（{time_ago}）| {participants_str} | {msg_count}条消息")
        option_keys.append("continue")

    option_labels.append("新对话")
    option_keys.append("new")

    if history_sessions:
        option_labels.append("历史会话")
        option_keys.append("history")

    option_labels.append("设置（Provider/Model）")
    option_keys.append("settings")

    option_labels.append("退出")
    option_keys.append("quit")

    # 方向键选择
    choice = select_menu_interactive(
        "LIFEE - AI 决策助手",
        option_labels,
        subtitle=f"Provider: {provider.name} ({provider.model})",
    )

    if choice is None:
        print("\n再见！")
        return ("quit", None)

    selected = option_keys[choice]

    if selected == "continue":
        session = session_store.restore_session(saved_data)
        role_names = map_display_names_to_role_names(
            saved_data.get("participants", []), role_manager
        )
        participants = await create_participants(role_names, provider, role_manager)
        print(f"已恢复会话，共 {len(saved_data.get('history', []))} 条消息")
        return ("start", {"participants": participants, "session": session})

    elif selected == "new":
        if saved_data:
            session_store.archive()

        selected_roles = select_roles_interactive(role_manager)
        if not selected_roles:
            return await main_menu(provider, role_manager, session_store)

        session = Session()
        participants = await create_participants(selected_roles, provider, role_manager)
        return ("start", {"participants": participants, "session": session})

    elif selected == "history":
        # 历史会话也用方向键选择
        hist_labels = []
        for s in history_sessions:
            time_str = s["updated_at"][:16].replace("T", " ") if s["updated_at"] else "未知"
            participants_str = "、".join(s["participants"])
            hist_labels.append(f"{time_str} | {participants_str} | {s['msg_count']}条消息")
        hist_labels.append("返回")

        hist_choice = select_menu_interactive("历史会话", hist_labels)

        if hist_choice is not None and hist_choice < len(history_sessions):
            selected_hist = history_sessions[hist_choice]
            history_data = session_store.load_history(selected_hist["filename"])
            if history_data:
                if saved_data:
                    session_store.archive()
                session = session_store.restore_session(history_data)
                role_names = map_display_names_to_role_names(
                    history_data.get("participants", []), role_manager
                )
                participants = await create_participants(role_names, provider, role_manager)
                print(f"已恢复历史会话，共 {len(history_data.get('history', []))} 条消息")
                return ("start", {"participants": participants, "session": session})
            else:
                print("\n[无法加载该会话]")

        return await main_menu(provider, role_manager, session_store)

    elif selected == "settings":
        select_provider_interactive(show_welcome=False)
        reload_settings()
        return ("settings", None)

    elif selected == "quit":
        print("\n再见！")
        return ("quit", None)

    return ("quit", None)


async def main():
    """主函数"""
    # 检查是否首次运行，显示交互式选择
    if check_first_run():
        select_provider_interactive()
        reload_settings()

    role_manager = RoleManager()
    session_store = DebateSessionStore()

    while True:
        # 重新加载配置以获取最新的 Provider 设置
        reload_settings()

        # 创建 Provider（带 fallback 支持）
        provider = create_provider_with_fallback()

        # 显示主菜单
        action, data = await main_menu(provider, role_manager, session_store)

        if action == "quit":
            break
        elif action == "settings":
            continue
        elif action == "start":
            participants = data["participants"]
            session = data["session"]

            # 进入统一对话循环
            result_action, _ = await debate_loop(
                participants, session, provider, session_store
            )

            # 清理知识库
            for p in participants:
                if p.knowledge_manager:
                    p.knowledge_manager.close()

            if result_action == "quit":
                break
            # "menu" → continue 回到主菜单
