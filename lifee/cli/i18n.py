"""国际化 (i18n) 模块 - 系统语言支持"""

_current_lang = "zh"

STRINGS = {
    # === 主菜单 ===
    "main_title": {"zh": "LIFEE - AI 决策助手", "en": "LIFEE - AI Decision Assistant"},
    "continue_session": {
        "zh": "继续上次对话（{time}）| {participants} | {count}条消息",
        "en": "Continue last chat ({time}) | {participants} | {count} messages",
    },
    "new_chat": {"zh": "新对话", "en": "New Chat"},
    "history": {"zh": "历史会话", "en": "History"},
    "settings": {"zh": "设置（Provider/Model/Language）", "en": "Settings (Provider/Model/Language)"},
    "quit": {"zh": "退出", "en": "Quit"},
    "goodbye": {"zh": "再见！", "en": "Goodbye!"},

    # === 设置菜单 ===
    "settings_title": {"zh": "设置", "en": "Settings"},
    "settings_provider": {"zh": "Provider / Model", "en": "Provider / Model"},
    "settings_language": {"zh": "语言 / Language", "en": "Language"},
    "settings_back": {"zh": "返回", "en": "Back"},
    "language_title": {"zh": "选择语言", "en": "Select Language"},

    # === 欢迎 / 对话头 ===
    "conversation_mode": {
        "zh": "LIFEE 对话模式 - {emoji} {name}",
        "en": "LIFEE Chat - {emoji} {name}",
    },
    "discussion_mode": {"zh": "LIFEE 多角度讨论模式", "en": "LIFEE Multi-Perspective Discussion"},
    "participants": {"zh": "参与者:", "en": "Participants:"},
    "start_conversation": {"zh": "\n输入问题开始对话", "en": "\nType a question to start"},
    "start_discussion": {"zh": "\n输入问题开始讨论", "en": "\nType a question to start the discussion"},
    "commands_hint": {
        "zh": "命令: /help 帮助 | /menu 主菜单 | /quit 退出 | Ctrl+V 粘贴图片",
        "en": "Commands: /help | /menu | /quit | Ctrl+V paste image",
    },

    # === 用户输入 ===
    "input_prompt": {"zh": "你: ", "en": "You: "},
    "silence_display": {"zh": "你: （保持沉默）", "en": "You: (silence)"},
    "interject_prompt": {"zh": "\n\n[插话] 你: ", "en": "\n\n[Interject] You: "},
    "cancel": {"zh": "[取消]", "en": "[Cancel]"},

    # === 建议菜单 ===
    "thinking_suggestions": {"zh": "正在思考建议回复...", "en": "Thinking of suggestions..."},
    "silence_option": {
        "zh": "[保持沉默，让对话继续]",
        "en": "[Stay silent, let the conversation continue]",
    },
    "free_input_option": {"zh": "[自由输入]", "en": "[Free input]"},
    "suggestion_prompt": {
        "zh": "你想说什么？ (↑↓选择 | 回车确认 | 直接打字输入)",
        "en": "Your reply? (↑↓ select | Enter confirm | type to input)",
    },

    # === /help 命令 ===
    "help_title": {"zh": "\n命令列表:", "en": "\nCommands:"},
    "help_help": {"zh": "  /help     - 显示帮助", "en": "  /help     - Show help"},
    "help_history": {"zh": "  /history  - 显示对话历史", "en": "  /history  - Show chat history"},
    "help_clear": {"zh": "  /clear    - 清空对话历史", "en": "  /clear    - Clear chat history"},
    "help_sessions": {"zh": "  /sessions - 历史会话", "en": "  /sessions - Session history"},
    "help_memory": {"zh": "  /memory   - 知识库状态", "en": "  /memory   - Knowledge base status"},
    "help_config": {"zh": "  /config   - 切换 LLM Provider", "en": "  /config   - Switch LLM Provider"},
    "help_model": {"zh": "  /model    - 切换当前 Provider 的模型", "en": "  /model    - Switch model"},
    "help_menu": {"zh": "  /menu     - 返回主菜单", "en": "  /menu     - Back to main menu"},
    "help_quit": {"zh": "  /quit     - 退出", "en": "  /quit     - Quit"},
    "help_image_title": {"zh": "\n发送图片:", "en": "\nSend images:"},
    "help_image_ctrlv": {
        "zh": "  Ctrl+V    - 粘贴剪贴板图片",
        "en": "  Ctrl+V    - Paste clipboard image",
    },
    "help_image_atpath": {
        "zh": "  @文件路径  - 附加图片（如 @photo.jpg @\"C:/有空格/img.png\"）",
        "en": "  @filepath  - Attach image (e.g. @photo.jpg @\"path with spaces/img.png\")",
    },
    "help_image_drag": {
        "zh": "  拖入文件   - 直接拖图片到终端，自动识别",
        "en": "  Drag file  - Drag image into terminal, auto-detected",
    },
    "help_image_clipboard": {
        "zh": "  @clipboard - 从剪贴板读取图片（同 Ctrl+V）",
        "en": "  @clipboard - Read image from clipboard (same as Ctrl+V)",
    },

    # === 会话状态 ===
    "session_saved": {"zh": "会话已自动保存", "en": "Session saved"},
    "profile_updating": {"zh": "正在更新档案...", "en": "Updating profile..."},
    "profile_updated": {"zh": "档案已更新", "en": "Profile updated"},
    "profile_unchanged": {"zh": "档案无变化", "en": "Profile unchanged"},
    "history_cleared": {"zh": "对话历史已清空", "en": "Chat history cleared"},
    "history_empty": {"zh": "对话历史为空", "en": "Chat history is empty"},
    "history_title": {"zh": "--- 对话历史 ---", "en": "--- Chat History ---"},
    "you_label": {"zh": "你", "en": "You"},
    "message_count": {
        "zh": "--- 共 {count} 条消息 ---",
        "en": "--- {count} messages total ---",
    },

    # === 知识库 ===
    "no_knowledge": {"zh": "当前角色没有知识库", "en": "This role has no knowledge base"},
    "knowledge_create_hint": {
        "zh": "创建方法: 在角色目录下创建 knowledge/ 目录，添加 .md 文件",
        "en": "To create one: add a knowledge/ directory with .md files under the role directory",
    },
    "knowledge_status": {"zh": "知识库状态:", "en": "Knowledge base status:"},
    "file_count": {"zh": "  文件数: {count}", "en": "  Files: {count}"},
    "chunk_count": {"zh": "  分块数: {count}", "en": "  Chunks: {count}"},
    "embedding_model": {"zh": "  嵌入模型: {model}", "en": "  Embedding: {model}"},
    "memory_search_usage": {
        "zh": "用法: /memory search <查询内容>",
        "en": "Usage: /memory search <query>",
    },
    "searching": {"zh": "搜索: {query}", "en": "Search: {query}"},
    "no_results": {"zh": "没有找到相关内容", "en": "No results found"},
    "result_count": {
        "zh": "找到 {count} 条结果:",
        "en": "Found {count} results:",
    },
    "memory_usage": {"zh": "\n用法:", "en": "\nUsage:"},
    "memory_usage_status": {
        "zh": "  /memory         - 显示知识库状态",
        "en": "  /memory         - Show knowledge base status",
    },
    "memory_usage_search": {
        "zh": "  /memory search <query> - 搜索知识库",
        "en": "  /memory search <query> - Search knowledge base",
    },
    "no_knowledge_all": {"zh": "当前参与者均没有知识库", "en": "No participants have a knowledge base"},
    "knowledge_label": {
        "zh": "{emoji} {name} 知识库:",
        "en": "{emoji} {name} Knowledge:",
    },
    "file_chunk_count": {
        "zh": "  文件数: {files}, 分块数: {chunks}",
        "en": "  Files: {files}, Chunks: {chunks}",
    },

    # === 历史会话 ===
    "no_sessions": {"zh": "没有历史会话", "en": "No session history"},
    "unknown_time": {"zh": "未知", "en": "Unknown"},
    "messages_suffix": {"zh": "{count}条消息", "en": "{count} messages"},
    "back": {"zh": "返回", "en": "Back"},
    "session_restored": {
        "zh": "已恢复会话，共 {count} 条消息",
        "en": "Session restored, {count} messages",
    },
    "session_load_failed": {"zh": "无法加载该会话", "en": "Failed to load session"},

    # === Provider/Model 切换 ===
    "switched_to": {
        "zh": "已切换到 {name} ({model})",
        "en": "Switched to {name} ({model})",
    },
    "switch_failed": {"zh": "切换失败: {error}", "en": "Switch failed: {error}"},
    "model_no_switch": {
        "zh": "Qwen Portal 不支持模型切换",
        "en": "Qwen Portal does not support model switching",
    },
    "model_switched": {
        "zh": "已切换模型: {model}",
        "en": "Model switched: {model}",
    },
    "unknown_command": {
        "zh": "未知命令: {cmd}，输入 /help 查看帮助",
        "en": "Unknown command: {cmd}, type /help for help",
    },

    # === 角色行为 ===
    "chose_silence": {
        "zh": "{emoji} {name} 选择保持沉默",
        "en": "{emoji} {name} chose to stay silent",
    },
    "silence_prompt": {
        "zh": "[用户选择保持沉默，请继续你的思考或追问]",
        "en": "[The user chose to stay silent. Please continue your thoughts or ask a follow-up question.]",
    },

    # === 错误 / 中断 ===
    "interrupted": {"zh": "[中断]", "en": "[Interrupted]"},
    "error_prefix": {"zh": "[错误] {error}", "en": "[Error] {error}"},

    # === app.py 专用 ===
    "loading_participants": {"zh": "正在加载参与者...", "en": "Loading participants..."},
    "session_restored_count": {
        "zh": "已恢复会话，共 {count} 条消息",
        "en": "Session restored, {count} messages",
    },
    "history_restored_count": {
        "zh": "已恢复历史会话，共 {count} 条消息",
        "en": "History session restored, {count} messages",
    },
    "session_load_failed_bracket": {"zh": "[无法加载该会话]", "en": "[Failed to load session]"},
    "error_no_claude": {
        "zh": "\n错误: 未找到 Claude 认证凭据",
        "en": "\nError: No Claude credentials found",
    },
    "error_unknown_provider": {
        "zh": "\n错误: 未知的 Provider: {name}",
        "en": "\nError: Unknown provider: {name}",
    },
    "fallback_warning": {
        "zh": "[警告] 无法创建 fallback provider '{name}': {error}",
        "en": "[Warning] Failed to create fallback provider '{name}': {error}",
    },

    # === setup.py 专用 ===
    "welcome_title": {"zh": "欢迎使用 LIFEE - AI 决策助手", "en": "Welcome to LIFEE - AI Decision Assistant"},
    "switch_provider": {"zh": "切换 LLM Provider", "en": "Switch LLM Provider"},
    "configured_hint": {"zh": "✓ 表示已配置", "en": "✓ = configured"},
    "selected": {"zh": "已选择: {name}", "en": "Selected: {name}"},
    "select_model": {"zh": "选择模型", "en": "Select Model"},
    "current_suffix": {"zh": "(当前)", "en": "(current)"},
    "no_model_switch": {
        "zh": "{provider} 不支持模型切换",
        "en": "{provider} does not support model switching",
    },
    "checking_ollama": {"zh": "正在检查 Ollama 模型...", "en": "Checking Ollama models..."},
    "manual_input": {"zh": "手动输入模型名", "en": "Enter model name manually"},
    "select_ollama": {
        "zh": "选择 Ollama 模型（未安装会自动下载）",
        "en": "Select Ollama model (will auto-download if not installed)",
    },
    "enter_model_name": {"zh": "输入模型名: ", "en": "Enter model name: "},
    "ollama_selected_download": {
        "zh": "已选择 {model}，首次使用会自动下载",
        "en": "Selected {model}, will auto-download on first use",
    },
    "download_new_model": {"zh": "下载新模型...", "en": "Download new model..."},
    "select_ollama_model": {"zh": "选择 Ollama 模型", "en": "Select Ollama model"},
    "select_download_model": {"zh": "选择要下载的模型", "en": "Select model to download"},
    "api_key_setup_title": {
        "zh": "首次使用 {provider}，需要配置 API Key",
        "en": "First time using {provider}, API Key required",
    },
    "api_key_get_url": {"zh": "获取地址: {url}", "en": "Get it here: {url}"},
    "api_key_prompt": {
        "zh": "请粘贴你的 API Key (输入 q 退出): ",
        "en": "Paste your API Key (q to quit): ",
    },
    "api_key_cancelled": {"zh": "已取消", "en": "Cancelled"},
    "api_key_empty": {"zh": "API Key 不能为空，请重新输入", "en": "API Key cannot be empty, please try again"},
    "api_key_saved": {"zh": "已保存到 .env 文件", "en": "Saved to .env file"},
    "api_key_save_failed": {"zh": "保存失败，请手动编辑 .env 文件", "en": "Save failed, please edit .env manually"},
    "no_roles": {"zh": "没有可用的角色", "en": "No roles available"},
    "create_role_hint": {
        "zh": "请先创建角色: lifee/roles/<name>/SOUL.md",
        "en": "Create a role first: lifee/roles/<name>/SOUL.md",
    },
    "select_participants": {
        "zh": "选择参与者 (↑↓移动 | 空格/数字切换 | 回车确认):",
        "en": "Select participants (↑↓ move | Space/Number toggle | Enter confirm):",
    },
    "no_selection": {"zh": "[取消] 未选择任何角色", "en": "[Cancel] No roles selected"},

    # === 角色显示名 ===
    "role_krishnamurti": {"zh": "克里希那穆提", "en": "Krishnamurti"},
    "role_buffett": {"zh": "沃伦·巴菲特", "en": "Warren Buffett"},
    "role_munger": {"zh": "查理·芒格", "en": "Charlie Munger"},
    "role_lacan": {"zh": "拉康", "en": "Lacan"},
    "role_enterprise": {"zh": "企业家", "en": "Entrepreneur"},
    "role_positive_psychologist": {"zh": "积极心理学家", "en": "Positive Psychologist"},
    "role_Simone de Beauvoir": {"zh": "西蒙娜·德·波伏娃", "en": "Simone de Beauvoir"},
}


def get_lang() -> str:
    return _current_lang


def set_lang(lang: str):
    global _current_lang
    if lang in ("zh", "en"):
        _current_lang = lang


def t(key: str) -> str:
    """翻译函数：根据当前语言返回对应文本"""
    entry = STRINGS.get(key)
    if entry is None:
        return key
    return entry.get(_current_lang, entry.get("zh", key))
