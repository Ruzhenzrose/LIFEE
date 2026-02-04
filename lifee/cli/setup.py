"""Provider/Model/Role 选择 UI"""
import sys
from pathlib import Path
from typing import Callable, Optional

import httpx


def prompt_for_choice(
    options: list,
    prompt_text: str = "请选择",
    allow_zero: bool = False,
    zero_label: str = "",
    allow_quit: bool = True,
    on_select: Optional[Callable[[int, any], any]] = None,
) -> tuple[int, any]:
    """
    通用选择交互 UI

    Args:
        options: 选项列表
        prompt_text: 提示文本
        allow_zero: 是否允许选择 0（特殊选项）
        zero_label: 0 选项的标签
        allow_quit: 是否允许 q 取消
        on_select: 选择后的回调函数 (idx, item) -> result

    Returns:
        (idx, item) 选中的索引和项目，取消返回 (-1, None)
    """
    min_idx = 0 if allow_zero else 1
    max_idx = len(options)
    range_text = f"{min_idx}-{max_idx}" if allow_zero else f"1-{len(options)}"
    quit_hint = "，或 q 取消" if allow_quit else ""

    while True:
        choice = input(f"{prompt_text} ({range_text}{quit_hint}): ").strip()

        if allow_quit and choice.lower() == 'q':
            print("已取消")
            return (-1, None)

        try:
            idx = int(choice)
            if allow_zero and idx == 0:
                return (0, None)
            if 1 <= idx <= len(options):
                item = options[idx - 1]
                if on_select:
                    return (idx, on_select(idx - 1, item))
                return (idx, item)
        except ValueError:
            pass

        print("无效选择，请重新输入")


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


def show_ollama_recommended_models():
    """显示 Ollama 推荐模型列表"""
    print("\n推荐模型:\n")
    for i, (name, size, desc) in enumerate(OLLAMA_RECOMMENDED_MODELS, 1):
        print(f"  {i}. {name}")
        print(f"     {size} | {desc}")
        print()
    print(f"  0. 手动输入模型名")
    print()


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

    idx, item = prompt_for_choice(models, "请选择模型")
    if idx == -1:
        return ""

    selected = item[0]
    save_api_key_to_env(env_key, selected)
    print(f"\n已选择: {selected}")
    return selected


def select_ollama_model() -> str:
    """交互式选择 Ollama 模型"""
    from lifee.config.settings import settings

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

    idx, item = prompt_for_choice(PROVIDER_OPTIONS, "请输入序号")
    if idx == -1:
        if show_welcome:
            sys.exit(0)
        return ""

    provider_id = item["id"]
    save_api_key_to_env("LLM_PROVIDER", provider_id)
    print(f"\n已选择: {item['name']}")
    return provider_id


def select_role_interactive(role_manager, current_role: str) -> str:
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

    idx, item = prompt_for_choice(roles, "请选择角色", allow_zero=True)
    if idx == -1:
        return current_role
    if idx == 0:
        print("\n已切换到: [无角色]")
        return ""

    print(f"\n已切换到: {item}")
    return item
