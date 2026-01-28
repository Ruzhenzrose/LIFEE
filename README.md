# LIFEE - 辩论式 AI 决策助手

Google Hackathon 2025 项目

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 选择 LLM Provider

支持多种 LLM 提供商，编辑 `.env` 文件选择：

| Provider | 免费额度 | 说明 |
|----------|---------|------|
| **Gemini** | 免费 | Google AI，推荐使用 |
| **Qwen** | 2000次/天 | 阿里通义千问 DashScope API |
| **Qwen Portal** | 2000次/天 | 通过 clawdbot OAuth 登录 |
| **Ollama** | 完全免费 | 本地运行，需安装 Ollama |
| **OpenCode** | $20 起 | 需绑定支付方式 |
| **Claude** | 需付费 | Anthropic Claude API |

### 3. 配置

复制配置文件：

```bash
cp .env.example .env
```

编辑 `.env`，设置 Provider 和对应的 API Key：

```bash
# 选择 Provider
LLM_PROVIDER=gemini

# Gemini (推荐)
GOOGLE_API_KEY=your-api-key

# 或者 Qwen
# LLM_PROVIDER=qwen
# QWEN_API_KEY=your-api-key

# 或者 Ollama (本地)
# LLM_PROVIDER=ollama
# ollama pull qwen2.5
```

### 4. 运行对话

```bash
python -m lifee.main
```

首次运行会让你选择具体模型。

### 5. 使用命令

```
/help    - 显示帮助
/history - 显示对话历史
/clear   - 清空对话历史
/role    - 切换角色
/model   - 切换模型
/memory  - 查看知识库状态
/quit    - 退出程序
```

## 角色系统

LIFEE 支持自定义 AI 角色，每个角色可以有独特的人格和专属知识库。

### 目录结构

```
lifee/roles/
└── <role_name>/
    ├── SOUL.md           # 核心人格（必需）
    ├── IDENTITY.md       # 身份信息（可选）
    └── knowledge/        # 专属知识库（可选）
        └── *.md
```

### 文件说明

| 文件 | 作用 |
|------|------|
| `SOUL.md` | 定义角色的核心人格、价值观、说话风格、行为边界 |
| `IDENTITY.md` | 名字、emoji 等元信息，用于显示 |
| `knowledge/` | Markdown 文件，会被自动索引，对话时通过语义搜索注入相关内容 |

### 知识库工作原理

知识库让 AI 能够基于角色专属的文档（书籍、文章等）回答问题，而不是泛泛而谈。

**工作流程：**

```
1. 索引阶段（首次运行）
   文档 → 分块（~400 token/块）→ 嵌入向量（Gemini API）→ 存入 knowledge.db

2. 对话阶段
   用户输入 → 生成查询向量 → 搜索最相似的分块 → 注入到 system prompt → AI 回答
```

**knowledge.db 结构（SQLite）：**

| 表 | 内容 |
|---|---|
| `files` | 已索引文件列表（路径、hash、修改时间） |
| `chunks` | 文本分块 + 嵌入向量（3072 维） |
| `chunks_fts` | 全文搜索索引（FTS5，用于关键词搜索） |

**搜索算法：** 混合搜索 = 70% 向量相似度 + 30% 关键词匹配

### 为你的角色构建知识库

**步骤 1：准备文档**

在角色目录下创建 `knowledge/` 文件夹，放入 `.md` 或 `.txt` 文件：

```
lifee/roles/your_role/
├── SOUL.md
├── IDENTITY.md
└── knowledge/
    ├── book1.txt      # 书籍文本
    ├── book2.txt
    └── notes.md       # 手写笔记
```

**步骤 2：运行程序**

```bash
python -m lifee.main
# 选择你的角色，会自动索引
# 显示进度: 索引知识库: 1/5 ... 5/5
```

首次索引需要调用 Gemini Embedding API，每个文件约 5-10 秒。

**步骤 3：测试搜索**

```
/memory            # 查看知识库状态
/memory search 关键词  # 测试搜索效果
```

### 知识库最佳实践

1. **文本格式**：纯文本最佳，PDF/EPUB 需先提取文本（见 `tools/extract_books.py`）
2. **分块大小**：默认 400 token，适合大多数场景
3. **文件命名**：使用有意义的文件名，搜索结果会显示来源
4. **预构建数据库**：仓库已包含预构建的 `knowledge.db`，队友克隆后可直接使用
5. **重建索引**：添加新文档后，删除 `knowledge.db`，重新运行程序即可

### 创建新角色

1. 在 `lifee/roles/` 下创建目录，如 `lifee/roles/stoic/`
2. 编写 `SOUL.md` 描述人格
3. （可选）添加 `IDENTITY.md`
4. （可选）在 `knowledge/` 下添加知识文档
5. 运行程序，用 `/role` 切换

## 支持的模型

### Gemini
- `gemini-3-flash-preview` - Gemini 3 快速
- `gemini-3-pro-preview` - Gemini 3 最强
- `gemini-2.5-pro` - 2.5 最强
- `gemini-2.5-flash` - 2.5 快速
- `gemini-2.0-flash` - 2.0 推荐

### Qwen
- `qwen-plus` - 通用增强
- `qwen-turbo` - 快速
- `qwen-max` - 最强

### Ollama
- `qwen2.5:latest` - 推荐
- `llama3.3:latest`
- `deepseek-r1:latest`

## 项目结构

```
lifee/
├── config/         # 配置管理
├── providers/      # LLM 提供商 (Claude, Gemini, Qwen, Ollama...)
├── sessions/       # 会话管理
├── roles/          # 角色系统
│   └── <role>/
│       ├── SOUL.md
│       ├── IDENTITY.md
│       └── knowledge/
├── memory/         # 知识库/RAG
│   ├── manager.py      # 索引管理
│   ├── embeddings.py   # 嵌入提供者 (Gemini/OpenAI)
│   ├── search.py       # 混合搜索 (向量+关键词)
│   └── chunker.py      # 文档分块
└── main.py         # CLI 入口
```

## 开发进度

- [x] Phase 1: 基础对话
- [x] 多 LLM Provider 支持
- [x] Phase 2: 角色系统
- [x] Phase 3: 知识库/RAG
- [ ] Phase 4: 多智能体辩论
