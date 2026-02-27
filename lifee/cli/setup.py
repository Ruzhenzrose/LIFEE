"""Provider/Model/Role 选择 UI"""
import ctypes
import msvcrt
import sys
from pathlib import Path

import httpx

from .i18n import t


def select_menu_interactive(
    title: str,
    options: list[str],
    subtitle: str = "",
) -> int | None:
    """通用方向键单选菜单

    Args:
        title: 菜单标题
        options: 选项文本列表
        subtitle: 标题下的副标题（如 Provider 信息）

    Returns:
        选中项的索引（0-based），ESC/q 取消返回 None
    """
    # 启用 Windows Virtual Terminal Processing
    kernel32 = ctypes.windll.kernel32
    stdout_handle = kernel32.GetStdHandle(-11)
    mode = ctypes.c_ulong()
    kernel32.GetConsoleMode(stdout_handle, ctypes.byref(mode))
    kernel32.SetConsoleMode(stdout_handle, mode.value | 0x0004)

    cursor = 0
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


OLLAMA_RECOMMENDED_MODELS = [
    ("qwen2.5", "7B, 4.4GB", "通用对话，中英文"),
    ("llama3.3", "70B, 43GB", "强大，需大显存"),
    ("deepseek-r1", "7B, 4.7GB", "推理能力强"),
    ("gemma2", "9B, 5.4GB", "Google 开源"),
    ("phi3", "3.8B, 2.3GB", "微软，轻量快速"),
    ("mistral", "7B, 4.1GB", "欧洲开源"),
]


def select_model_for_provider(provider_id: str, current_model: str) -> str:
    """交互式选择供应商模型"""
    if provider_id == "ollama":
        return select_ollama_model()

    if provider_id not in PROVIDER_MODELS:
        print(f"\n{t('no_model_switch').format(provider=provider_id)}")
        return ""

    config = PROVIDER_MODELS[provider_id]
    models = config["models"]
    env_key = config["env_key"]

    labels = []
    for model_id, desc in models:
        current = f" ({t('current_suffix')})" if model_id == current_model else ""
        labels.append(f"{model_id}{current} - {desc}")

    choice = select_menu_interactive(t("select_model"), labels)
    if choice is None:
        return ""

    selected = models[choice][0]
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
    return provider_id


def select_roles_interactive(role_manager) -> list[str] | None:
    """交互式多角色选择（checkbox + 方向键）

    Args:
        role_manager: RoleManager 实例

    Returns:
        选中的角色名列表，取消返回 None
    """
    roles = role_manager.list_roles()

    if not roles:
        print(f"\n{t('no_roles')}")
        print(t("create_role_hint"))
        return None

    # 获取角色信息
    role_choices = []  # [(role_name, display_name, emoji, selected), ...]
    for role_name in roles:
        info = role_manager.get_role_info(role_name)
        display_name = info.get("display_name", role_name)
        emoji = role_manager.get_role_emoji(role_name)
        role_choices.append([role_name, display_name, emoji, False])

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
