"""Provider/Model/Role 选择 UI"""
import ctypes
import json
import msvcrt
import sys
import time
from pathlib import Path

import httpx

from .i18n import t

# 模型缓存文件路径和刷新间隔
_MODELS_CACHE_PATH = Path.home() / ".lifee" / "models_cache.json"
_CACHE_REFRESH_INTERVAL = 86400  # 24 小时


def select_menu_interactive(
    title: str,
    options: list[str],
    subtitle: str = "",
    default_index: int = 0,
) -> int | None:
    """通用方向键单选菜单

    Args:
        title: 菜单标题
        options: 选项文本列表
        subtitle: 标题下的副标题（如 Provider 信息）
        default_index: 默认选中项索引

    Returns:
        选中项的索引（0-based），ESC/q 取消返回 None
    """
    # 启用 Windows Virtual Terminal Processing
    kernel32 = ctypes.windll.kernel32
    stdout_handle = kernel32.GetStdHandle(-11)
    mode = ctypes.c_ulong()
    kernel32.GetConsoleMode(stdout_handle, ctypes.byref(mode))
    kernel32.SetConsoleMode(stdout_handle, mode.value | 0x0004)

    cursor = max(0, min(default_index, len(options) - 1))
    # 标题行 + 副标题行（如果有）+ 空行 + 选项行
    header_lines = 3  # "===", title, "==="
    if subtitle:
        header_lines += 1
    header_lines += 1  # 空行
    total_lines = header_lines + len(options)

    def render(first_time=False):
        if not first_time:
            sys.stdout.write(f"\033[{total_lines}A")

        sys.stdout.write(f"\033[2K{'=' * 50}\n")
        sys.stdout.write(f"\033[2K{title}\n")
        sys.stdout.write(f"\033[2K{'=' * 50}\n")
        if subtitle:
            sys.stdout.write(f"\033[2K{subtitle}\n")
        sys.stdout.write("\033[2K\n")
        for i, opt in enumerate(options):
            pointer = ">" if i == cursor else " "
            sys.stdout.write(f"\033[2K  {pointer} {opt}\n")
        sys.stdout.flush()

    sys.stdout.write("\033[?25l")  # 隐藏光标
    sys.stdout.flush()
    render(first_time=True)

    try:
        while True:
            key = msvcrt.getch()

            if key == b'\r':  # 回车
                break
            elif key == b'\x1b' or key == b'q':  # ESC 或 q
                sys.stdout.write("\033[?25h\n")
                sys.stdout.flush()
                return None
            elif key == b'\xe0':  # 方向键前缀
                arrow = msvcrt.getch()
                if arrow == b'H':  # 上
                    cursor = (cursor - 1) % len(options)
                    render()
                elif arrow == b'P':  # 下
                    cursor = (cursor + 1) % len(options)
                    render()
            elif key in [b'1', b'2', b'3', b'4', b'5', b'6', b'7', b'8', b'9']:
                idx = int(key.decode()) - 1
                if 0 <= idx < len(options):
                    cursor = idx
                    render()
    finally:
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()

    return cursor


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


# 动态获取模型列表的 Provider 配置：provider_id → (base_url, key_env_var)
_DYNAMIC_MODEL_PROVIDERS = {
    "deepseek": ("https://api.deepseek.com/v1", "DEEPSEEK_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "qwen": ("https://dashscope.aliyuncs.com/compatible-mode/v1", "QWEN_API_KEY"),
    "opencode": ("https://opencode.ai/zen/v1", "OPENCODE_API_KEY"),
}


def _load_models_cache() -> dict:
    """读取本地模型缓存"""
    try:
        if _MODELS_CACHE_PATH.exists():
            return json.loads(_MODELS_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_models_cache(cache: dict) -> None:
    """保存模型缓存到本地"""
    try:
        _MODELS_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _MODELS_CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _fetch_models_from_api(provider_id: str) -> list[str] | None:
    """从 Provider API 获取模型列表，失败返回 None"""
    if provider_id not in _DYNAMIC_MODEL_PROVIDERS:
        return None

    base_url, key_env_var = _DYNAMIC_MODEL_PROVIDERS[provider_id]

    # 从 .env 读取 API Key
    env_path = Path(".env")
    api_key = ""
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").split("\n"):
            if line.startswith(f"{key_env_var}="):
                api_key = line.split("=", 1)[1].strip()
                break
    if not api_key:
        return None

    try:
        response = httpx.get(
            f"{base_url}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=8,
        )
        if response.status_code != 200:
            return None

        data = response.json()
        models = data.get("data", [])
        return [m["id"] for m in models if m.get("id")]
    except Exception:
        return None


def fetch_provider_models(provider_id: str) -> list[str]:
    """获取 Provider 可用模型列表

    策略：联网获取 → 更新本地缓存 → 离线时用缓存 → 都没有返回空列表
    每 24 小时自动刷新一次。
    """
    cache = _load_models_cache()
    entry = cache.get(provider_id, {})
    cached_models = entry.get("models", [])
    last_update = entry.get("updated_at", 0)

    # 缓存未过期，直接返回
    if cached_models and (time.time() - last_update) < _CACHE_REFRESH_INTERVAL:
        return cached_models

    # 尝试联网刷新
    fresh = _fetch_models_from_api(provider_id)
    if fresh:
        cache[provider_id] = {"models": fresh, "updated_at": time.time()}
        _save_models_cache(cache)
        return fresh

    # 联网失败，返回旧缓存（即使过期也比没有好）
    return cached_models


# 各供应商的模型列表
PROVIDER_MODELS = {
    "gemini": {
        "env_key": "GEMINI_MODEL",
        "models": [
            ("gemini-2.5-flash", "2.5 快速（推荐）"),
            ("gemini-2.5-pro", "2.5 最强"),
            ("gemini-2.0-flash", "2.0 快速"),
        ],
    },
    "deepseek": {
        "env_key": "DEEPSEEK_MODEL",
        "models": [
            ("deepseek-chat", "V3.2 通用对话（推荐）"),
            ("deepseek-reasoner", "V3.2 深度推理"),
        ],
    },
    "claude": {
        "env_key": "CLAUDE_MODEL",
        "models": [
            ("claude-sonnet-4-6", "Sonnet 4.6（推荐）"),
            ("claude-opus-4-6", "Opus 4.6 最强"),
            ("claude-haiku-4-5", "Haiku 4.5 快速"),
        ],
    },
    "qwen": {
        "env_key": "QWEN_MODEL",
        "models": [
            ("qwen3-max", "Qwen3 旗舰"),
            ("qwen3.5-flash", "Qwen3.5 快速（便宜）"),
            ("qwen3.6-plus", "Qwen3.6 均衡"),
            ("qwen-plus", "Qwen Plus 通用"),
            ("qwen-max", "Qwen Max 旧旗舰"),
        ],
    },
    "openrouter": {
        "env_key": "OPENROUTER_MODEL",
        "models": [
            ("deepseek/deepseek-v3.2", "DeepSeek V3.2"),
            ("google/gemini-2.5-flash", "Gemini 2.5 Flash"),
            ("google/gemini-2.5-pro", "Gemini 2.5 Pro"),
            ("anthropic/claude-sonnet-4-6", "Claude Sonnet 4.6"),
            ("meta-llama/llama-4-maverick", "Llama 4 Maverick"),
        ],
    },
    "groq": {
        "env_key": "GROQ_MODEL",
        "models": [
            ("llama-3.3-70b-versatile", "Llama 3.3 70B"),
            ("deepseek-r1-distill-llama-70b", "DeepSeek R1 蒸馏"),
            ("llama-3.1-8b-instant", "Llama 3.1 8B 快速"),
            ("gemma2-9b-it", "Gemma 2 9B"),
        ],
    },
    "opencode": {
        "env_key": "OPENCODE_MODEL",
        "models": [
            ("big-pickle", "OpenCode 免费"),
        ],
    },
}


OLLAMA_RECOMMENDED_MODELS = [
    ("qwen2.5", "7B, 4.4GB", "通用对话，中英文"),
    ("llama3.3", "70B, 43GB", "强大，需大显存"),
    ("deepseek-r1", "7B, 4.7GB", "推理能力强"),
    ("gemma2", "9B, 5.4GB", "Google 开源"),
    ("phi3", "3.8B, 2.3GB", "微软，轻量快速"),
    ("mistral", "7B, 4.1GB", "欧洲开源"),
]


def select_model_for_provider(provider_id: str, current_model: str) -> str:
    """交互式选择供应商模型

    优先从 API 动态获取模型列表，失败则用静态列表兜底。
    """
    if provider_id == "ollama":
        return select_ollama_model()

    if provider_id not in PROVIDER_MODELS:
        print(f"\n{t('no_model_switch').format(provider=provider_id)}")
        return ""

    config = PROVIDER_MODELS[provider_id]
    static_models = config["models"]  # [(id, desc), ...]
    env_key = config["env_key"]

    # 尝试动态获取模型列表
    dynamic_ids = fetch_provider_models(provider_id)

    if dynamic_ids:
        # 用静态描述为动态模型添加注释
        desc_map = {m[0]: m[1] for m in static_models}
        # 静态推荐的排前面，其余按 API 返回顺序
        static_ids = [m[0] for m in static_models]
        recommended = [mid for mid in static_ids if mid in dynamic_ids]
        others = [mid for mid in dynamic_ids if mid not in set(static_ids)]
        ordered = recommended + others

        labels = []
        for model_id in ordered:
            current = f" ({t('current_suffix')})" if model_id == current_model else ""
            desc = desc_map.get(model_id, "")
            suffix = f" - {desc}" if desc else ""
            labels.append(f"{model_id}{current}{suffix}")

        choice = select_menu_interactive(t("select_model"), labels)
        if choice is None:
            return ""

        selected = ordered[choice]
    else:
        # 静态兜底
        labels = []
        for model_id, desc in static_models:
            current = f" ({t('current_suffix')})" if model_id == current_model else ""
            labels.append(f"{model_id}{current} - {desc}")

        choice = select_menu_interactive(t("select_model"), labels)
        if choice is None:
            return ""

        selected = static_models[choice][0]

    save_api_key_to_env(env_key, selected)
    print(f"\n{t('selected').format(name=selected)}")
    return selected


def select_ollama_model() -> str:
    """交互式选择 Ollama 模型"""
    from lifee.config.settings import settings

    print(f"\n{t('checking_ollama')}")

    models = get_ollama_models()

    if not models:
        labels = [f"{name} - {size} | {desc}" for name, size, desc in OLLAMA_RECOMMENDED_MODELS]
        labels.append(t("manual_input"))

        choice = select_menu_interactive(t("select_ollama"), labels)
        if choice is None:
            return ""

        if choice < len(OLLAMA_RECOMMENDED_MODELS):
            model = OLLAMA_RECOMMENDED_MODELS[choice][0]
        else:
            model = input(f"\n{t('enter_model_name')}").strip()
            if not model:
                return ""

        save_api_key_to_env("OLLAMA_MODEL", model)
        print(f"\n{t('ollama_selected_download').format(model=model)}")
        return model

    labels = []
    for model in models:
        current = f" ({t('current_suffix')})" if model == settings.ollama_model else ""
        labels.append(f"{model}{current}")
    labels.append(t("download_new_model"))

    choice = select_menu_interactive(t("select_ollama_model"), labels)
    if choice is None:
        return ""

    if choice < len(models):
        selected = models[choice]
        save_api_key_to_env("OLLAMA_MODEL", selected)
        print(f"\n{t('selected').format(name=selected)}")
        return selected

    rec_labels = [f"{name} - {size} | {desc}" for name, size, desc in OLLAMA_RECOMMENDED_MODELS]
    rec_labels.append(t("manual_input"))

    rec_choice = select_menu_interactive(t("select_download_model"), rec_labels)
    if rec_choice is None:
        return ""

    if rec_choice < len(OLLAMA_RECOMMENDED_MODELS):
        model = OLLAMA_RECOMMENDED_MODELS[rec_choice][0]
    else:
        model = input(f"\n{t('enter_model_name')}").strip()
        if not model:
            return ""

    save_api_key_to_env("OLLAMA_MODEL", model)
    print(f"\n{t('ollama_selected_download').format(model=model)}")
    return model


def prompt_for_api_key(provider_name: str, key_name: str, get_url: str) -> str:
    """提示用户输入 API Key"""
    print(f"\n{'='*50}")
    print(t("api_key_setup_title").format(provider=provider_name))
    print(f"{'='*50}")
    print(t("api_key_get_url").format(url=get_url))
    print()

    while True:
        api_key = input(t("api_key_prompt")).strip()

        if api_key.lower() == 'q':
            print(t("api_key_cancelled"))
            sys.exit(0)

        if not api_key:
            print(t("api_key_empty"))
            continue

        if save_api_key_to_env(key_name, api_key):
            print(f"\n{t('api_key_saved')}")
            return api_key
        else:
            print(t("api_key_save_failed"))
            sys.exit(1)


# Provider 选项配置
PROVIDER_OPTIONS = [
    {
        "id": "gemini",
        "name": "Google Gemini",
        "desc": "免费 | gemini-2.5-flash/pro",
        "needs_key": True,
    },
    {
        "id": "deepseek",
        "name": "DeepSeek",
        "desc": "超便宜 | deepseek-chat, deepseek-reasoner",
        "needs_key": True,
    },
    {
        "id": "claude",
        "name": "Claude",
        "desc": "需 API Key | claude-sonnet-4-6, claude-opus-4-6",
        "needs_key": True,
    },
    {
        "id": "qwen",
        "name": "Qwen (通义千问)",
        "desc": "免费 2000 请求/天 | qwen-plus, qwen-max",
        "needs_key": True,
    },
    {
        "id": "openrouter",
        "name": "OpenRouter",
        "desc": "一个 key 多模型 | Gemini, Claude, Llama 等",
        "needs_key": True,
    },
    {
        "id": "groq",
        "name": "Groq",
        "desc": "超快推理 | 免费额度 | Llama, Gemma, Mixtral",
        "needs_key": True,
    },
    {
        "id": "ollama",
        "name": "Ollama (本地)",
        "desc": "完全免费 | qwen2.5, llama3.3, deepseek-r1",
        "needs_key": False,
    },
    {
        "id": "opencode",
        "name": "OpenCode Zen",
        "desc": "Big Pickle 免费",
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
        "gemini": "GOOGLE_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "claude": "ANTHROPIC_API_KEY",
        "qwen": "QWEN_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "groq": "GROQ_API_KEY",
        "opencode": "OPENCODE_API_KEY",
        "synthetic": "SYNTHETIC_API_KEY",
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
    title = t("welcome_title") if show_welcome else t("switch_provider")

    labels = []
    for opt in PROVIDER_OPTIONS:
        status = get_provider_key_status(opt["id"])
        labels.append(f"{opt['name']}{status} - {opt['desc']}")

    choice = select_menu_interactive(title, labels, subtitle=t("configured_hint"))
    if choice is None:
        if show_welcome:
            sys.exit(0)
        return ""

    item = PROVIDER_OPTIONS[choice]
    provider_id = item["id"]
    save_api_key_to_env("LLM_PROVIDER", provider_id)
    print(f"\n{t('selected').format(name=item['name'])}")

    # 立即弹出模型选择（如果该服务商有多个模型）
    if provider_id in PROVIDER_MODELS:
        models = PROVIDER_MODELS[provider_id]["models"]
        if len(models) > 1:
            select_model_for_provider(provider_id, "")

    return provider_id


def select_roles_interactive(role_manager, pre_selected: list[str] | None = None) -> list[str] | None:
    """交互式多角色选择（checkbox + 方向键）

    Args:
        role_manager: RoleManager 实例
        pre_selected: 预选中的角色名列表

    Returns:
        选中的角色名列表，取消返回 None
    """
    roles = role_manager.list_roles()

    if not roles:
        print(f"\n{t('no_roles')}")
        print(t("create_role_hint"))
        return None

    pre_selected_set = set(pre_selected or [])

    # 获取角色信息
    role_choices = []  # [(role_name, display_name, emoji, selected), ...]
    for role_name in roles:
        info = role_manager.get_role_info(role_name)
        display_name = info.get("display_name", role_name)
        emoji = role_manager.get_role_emoji(role_name)
        selected = role_name in pre_selected_set
        role_choices.append([role_name, display_name, emoji, selected])

    # 启用 Windows Virtual Terminal Processing（ANSI 转义序列）
    kernel32 = ctypes.windll.kernel32
    stdout_handle = kernel32.GetStdHandle(-11)
    mode = ctypes.c_ulong()
    kernel32.GetConsoleMode(stdout_handle, ctypes.byref(mode))
    kernel32.SetConsoleMode(stdout_handle, mode.value | 0x0004)

    cursor = 0
    total_lines = 1 + len(role_choices)

    def render_lines():
        lines = [t("select_participants")]
        for i, (_, display_name, emoji, selected) in enumerate(role_choices):
            checkbox = "☑" if selected else "☐"
            pointer = ">" if i == cursor else " "
            lines.append(f"  {pointer} {i+1}. {checkbox} {emoji} {display_name}")
        return lines

    def render(first_time=False):
        if not first_time:
            sys.stdout.write(f"\033[{total_lines}A")
        lines = render_lines()
        for line in lines:
            sys.stdout.write(f"\033[2K{line}\n")
        sys.stdout.flush()

    sys.stdout.write("\033[?25l")  # 隐藏光标
    sys.stdout.flush()
    render(first_time=True)

    try:
        while True:
            key = msvcrt.getch()

            if key == b'\r':  # 回车
                break
            elif key == b'\x1b' or key == b'q':  # ESC 或 q
                sys.stdout.write("\033[?25h\n")
                sys.stdout.flush()
                return None
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
                idx = int(key.decode()) - 1
                if 0 <= idx < len(role_choices):
                    role_choices[idx][3] = not role_choices[idx][3]
                    cursor = idx
                    render()
    finally:
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()

    selected = [rc[0] for rc in role_choices if rc[3]]

    if not selected:
        sys.stdout.write(f"\n{t('no_selection')}\n")
        sys.stdout.flush()
        return None

    return selected


def select_language_interactive() -> str:
    """交互式选择系统语言"""
    from .i18n import set_lang

    options = ["中文 (Chinese)", "English"]
    choice = select_menu_interactive(t("language_title"), options)
    if choice is None:
        return ""

    lang = "zh" if choice == 0 else "en"
    save_api_key_to_env("UI_LANG", lang)
    set_lang(lang)
    return lang
