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
    read_clawdbot_synthetic_credentials,
)
from lifee.sessions import SessionStore
from lifee.roles import RoleManager

from .setup import (
    save_api_key_to_env,
    get_ollama_models,
    select_ollama_model,
    prompt_for_api_key,
    select_provider_interactive,
)
from .chat import chat_loop
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
        current_settings = reload_settings()

        # 创建 Provider
        provider = create_provider()
        current_provider_id = current_settings.llm_provider.lower()

        # 如果有角色且有知识库，创建/更新知识库管理器
        if current_role:
            info = role_manager.get_role_info(current_role)
            if info.get("has_knowledge") and knowledge_manager is None:
                print(f"正在初始化角色知识库...")
                try:
                    knowledge_manager = await role_manager.get_knowledge_manager(
                        current_role,
                        google_api_key=current_settings.google_api_key,
                        openai_api_key=getattr(current_settings, 'openai_api_key', None),
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
