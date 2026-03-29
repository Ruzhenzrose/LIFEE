## Life Lab 后端说明文档（Backend）

本目录是 **Life Lab / AI Sandbox** 的后端代码，实现了三个主要能力：

- **人生模拟器（Life Simulator）**
- **AI 塔罗占卜（AI Tarot）**
- **量化决策实验室（Decision Lab）**

后端基于 **FastAPI**，通过 OpenAI 兼容协议连接 **Gemini 模型**，并对外暴露一组 REST API，前端通过 `fetch("/api/...")` 与之交互。

---

## 一、整体架构设计

### 1. 技术栈

- **语言与框架**
  - **Python 3 + FastAPI**：提供异步 Web API。
  - **Pydantic v2**：定义请求 / 响应的数据模型，做校验与文档。
  - **Uvicorn**：作为 ASGI 服务器运行 FastAPI。
- **大模型调用**
  - **openai.AsyncOpenAI**：使用 OpenAI SDK，但 `base_url` 指向 Gemini 的 OpenAI 兼容端点。
  - 使用 `tenacity` 做自动重试，统一 JSON 解析与错误处理。
- **文档与报告**
  - **ReportLab**：生成多页 PDF 报告，支持中文（自动加载 CJK 字体）。
- **配置与环境**
  - **python-dotenv**：从 `.env` 文件读取 `GEMINI_API_KEY` 等环境变量。

依赖见 `requirements.txt`。

### 2. 目录结构与职责

- `main.py`
  - FastAPI 应用入口：定义所有 HTTP 接口、挂载中间件、组织核心业务流程。
- `config.py`
  - 集中配置：读取 API Key、模型名、CORS 允许来源、报告输出目录等。
- `models.py`
  - 人生模拟器（Life Simulator）的 Pydantic 数据模型：初始状态 / 模拟请求 / 顿悟请求等。
- `prompts.py`
  - 人生模拟器相关的大模型 Prompt 模板：构造初始画像、模拟步骤、人生复盘。
- `tarot_models.py`
  - 塔罗占卜（AI Tarot）的请求 / 响应结构。
- `tarot_prompts.py`
  - 塔罗牌 78 张牌完整数据、牌阵定义、抽牌逻辑以及塔罗解读 Prompt。
- `decision_models.py`
  - 量化决策（Decision Lab）的请求 / 响应数据结构。
- `decision_prompts.py`
  - 决策分析的维度定义（DIMENSIONS）和用于让大模型输出结构化 JSON 的 Prompt。
- `services/ai_service.py`
  - 统一的大模型调用封装：异步、自动重试、可选 JSON 模式的解析。
- `services/pdf_service.py`
  - 使用 ReportLab 生成「人生模拟报告」PDF，包含：概况、时间线、最终属性与 Epiphany。

整体上，**业务路由不直接依赖第三方 SDK**，而是通过 `services` 抽象调用，确保：

- 上层只需要关心「我要问模型什么」以及「模型返回什么结构」；
- 下层负责「如何调用模型 + 错误重试 + JSON 清洗与解析」。

---

## 二、配置与运行方式

### 1. 环境变量配置（`config.py`）

`config.py` 中通过 `dotenv` 读取 `.env`，关键变量：

- **GEMINI_API_KEY**：必需，不配置会在 import 时直接抛出 `RuntimeError` 阻止服务启动。
- **GEMINI_BASE_URL**：默认值
  - `https://generativelanguage.googleapis.com/v1beta/openai/`
  - 即 Gemini 提供的 OpenAI 协议兼容 HTTP 端点。
- **GEMINI_MODEL_NAME**：默认 `gemini-3-pro-preview`，可按需替换为其它模型。
- **CORS_ORIGINS**
  - 例如：`http://localhost:5173,http://127.0.0.1:5173`
  - 在 `main.py` 中配置给 `CORSMiddleware`，允许前端页面跨域访问。
- **REPORT_DIR**
  - PDF 报告输出目录，默认 `reports`，在 import 时自动 `os.makedirs`。

### 2. 大模型客户端（`services/ai_service.py`）

- 使用 `AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL)` 创建客户端。
- 封装函数：

```python
async def call_ai(
    system_prompt: str,
    user_prompt: str,
    json_mode: bool = True,
) -> Optional[Any]:
    ...
```

设计要点：

- **统一系统提示 + 用户提示**：
  - `system` 角色：传入 `system_prompt`，定义 AI 的角色与任务。
  - `user` 角色：传入 `user_prompt`，包含具体问题与上下文数据。
- **JSON 模式与容错**：
  - 若 `json_mode=True`：
    - `response_format={"type": "json_object"}`，强制模型输出 JSON 对象。
    - 对返回内容调用 `_clean_json_content()` 去除 ```json 或 ``` 包裹，再 `json.loads`。
    - 若解析失败，记录日志并抛出 `ValueError`。
  - 若 `json_mode=False`：直接返回字符串内容，适用于塔罗解读、文本 epiphany 等。
- **自动重试**：
  - 使用 `tenacity.retry`，遇到 `RateLimitError` 时指数退避重试，最多 3 次。

因此，在上层业务路由中，**只需要关心 Prompt 的内容和预期返回结构**。

### 3. 启动方式

开发环境下可直接运行：

```bash
cd backend
pip install -r requirements.txt

uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

或执行：

```bash
python main.py
```

`main.py` 最底部有：

```python
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

---

## 三、API 设计与前后端交互

前端统一以 `API_BASE = "/api"` 调用后端，所有接口都在 `main.py` 中定义。

### 1. 健康检查

- **方法**：`GET /`
- **作用**：返回 `{ "message": "Life Simulator API is running" }`，用于前端或部署环境做健康检查。

---

### 2. 人生模拟器（Life Simulator）

#### 2.1 初始化用户画像：`POST /api/init`

- **请求模型**：`InitRequest`

```json
{
  "user_input": "字符串，自然语言描述：现在的状态、想做的事、困惑等"
}
```

- **处理逻辑（真实设计）**：
  1. 使用 `PROFILE_BUILDER_PROMPT` 作为 system prompt。
  2. 将 `user_input` 直接作为 user prompt。
  3. 调用 `call_ai(..., json_mode=True)`，期望模型返回严格的 JSON，字段包括：
     - `age`: 初始年龄（float / int）
     - `attributes`: 各种属性，如健康 / 财富 / 快乐 / 能力
     - `inventory`: 初始资产 / 标签列表
     - `current_dilemma`: 当前核心困境
     - `target_goal`: 整个模拟的人生目标
     - `win_condition` / `loss_condition`: 胜负条件说明
     - `narrative_start`: 初始叙事文案，用于前端展示。
  4. 若调用失败或返回为空，抛出 500 错误。

- **响应结构**：实际上就是 `SimulationState`：

```json
{
  "age": 25.0,
  "attributes": {
    "health": 80,
    "wealth": 30,
    "happiness": 50,
    "capability": 60
  },
  "inventory": ["编程技能"],
  "current_dilemma": "启动资金不足，且家人反对",
  "target_goal": "在30岁前通过独立开发实现财务自由",
  "win_condition": "财富达到80 或 开发出爆款应用",
  "loss_condition": "财富降至0 或 快乐降至10",
  "narrative_start": "..."
}
```

- **前端交互**：
  - `frontend/script.js` 在首次用户输入后请求 `/api/init`。
  - 将响应对象存入 `currentState` 与 `history`，并在侧边栏渲染数值属性，在对话区显示 `narrative_start`。

#### 2.2 模拟步骤：`POST /api/simulation`

- **请求模型**：`SimulationRequest`

```json
{
  "current_state": { ... SimulationState ... },
  "user_choice": "本轮用户做出的选择文本",
  "history": [
    "【初始状态】......",
    "【半年后】......"
  ]
}
```

- **真实设计逻辑**：

1. 根据当前状态构造 system prompt `SIMULATION_PROMPT`：
   - 使用 `target_goal`、`win_condition`、`loss_condition` 填入模板。
   - 把本轮 `user_choice` 嵌入提示，作为「用户选择」信息。
2. 将 `current_state` 整体序列化为 JSON 字符串（`json.dumps(request.current_state.model_dump(), ensure_ascii=False)`）作为 user prompt。
3. 调 `call_ai(prompt, user_state_json, json_mode=True)`，期望返回结构：

```json
{
  "narrative": "剧情描述...",
  "time_passed": "半年",
  "state_changes": {"wealth": -5, "capability": 2},
  "new_inventory_events": [],
  "is_concluded": false,
  "conclusion": null,
  "next_options": ["选项A", "选项B", "选项C"]
}
```

4. 服务端对属性更新做后处理：
   - 把 `state_changes` 作用到 `current_state.attributes` 上：
     - 使用 `clamp(value, 0, 100)`，约束在 0~100 区间。
5. 最终返回给前端的结构为：

```json
{
  "narrative": "本轮故事文本",
  "time_passed": "半年",
  "new_attributes": { "health": 80, "wealth": 25, ... },
  "new_age": 25.5,
  "is_concluded": false,
  "conclusion": null,
  "next_options": ["选项A", "选项B", "选项C"],
  "history_entry": "【半年后】......叙事拼接文本"
}
```

- **前端交互**：
  - 前端将返回的 `new_attributes` 合并进 `currentState`，更新 `age`。
  - 将 `history_entry` 加入本地 `history` 列表。
  - 在聊天区域追加 `narrative` 文本，并用 `next_options` 渲染可点击 chips。
  - 若 `is_concluded == true`，则不再显示 chips，而是调用 `/api/epiphany`。

#### 2.3 顿悟与报告：`POST /api/epiphany`

- **请求模型**：`EpiphanyRequest`

```json
{
  "history": [
    "【初始状态】......",
    "【半年后】......",
    "【一年后】......"
  ],
  "dilemma": "currentState.current_dilemma 的内容",
  "final_state": { ... SimulationState ... },
  "conclusion": "win" | "loss" | null
}
```

- **真实设计逻辑**：

1. 把 `history` 拼接成多行字符串 `history_text`。
2. 将内部结局标签 `"win"` / `"loss"` 翻译为中文：
   - `"win" -> "胜利"`，`"loss" -> "失败"`，其他 -> `"模拟结束"`。
3. 使用 `EPIPHANY_PROMPT` 模板填入：
   - `target_goal`
   - 中文化后的 `conclusion_label`
   - `history_text`
4. 调用 `call_ai("你是一个智慧的人生导师。", prompt_filled, json_mode=False)`：
   - 这里不要求结构化 JSON，只需要一段自然语言复盘文本。
5. 生成 PDF 报告：
   - 构造路径：`REPORT_DIR/report_<uuid>.pdf`。
   - 调 `create_pdf_report(path, history, epiphany, final_state, conclusion_label)`。
   - 若成功，返回 `report_url = "/api/report/<filename>"`；若生成失败，仅在日志记录错误，不影响 epiphany 文本返回。

- **响应结构**：

```json
{
  "epiphany": "长文本，人生复盘、关键转折与建议",
  "report_url": "/api/report/report_xxx.pdf"   // 可能为 null
}
```

- **前端交互**：
  - 在聊天区下方显示整个 epiphany 文本（换行转 `<br>` 渲染）。
  - 若 `report_url` 非空，则展示「Download Report (PDF)」按钮，跳转到该 URL。

#### 2.4 报告下载：`GET /api/report/{filename}`

- **请求示例**：`GET /api/report/report_d8a0c5ca-... .pdf`
- **逻辑**：
  - 拼接真实文件路径：`os.path.join(REPORT_DIR, filename)`。
  - 若存在：`FileResponse(..., media_type="application/pdf")`。
  - 若不存在：`HTTPException(404, "Report not found")`。
- **前端交互**：
  - 前端 `<a href="/api/report/xxx.pdf" target="_blank">`，由浏览器处理下载或预览。

---

### 3. AI 塔罗占卜（AI Tarot）

#### 3.1 获取可用牌阵：`GET /api/tarot/spreads`

- **响应示例**（映射自 `tarot_prompts.SPREADS`）：

```json
{
  "single": {
    "name": "单牌占卜",
    "name_en": "Single Card",
    "description": "抽取一张牌，快速获得对当前问题的指引。",
    "count": 1
  },
  "three_card": {
    "name": "三牌阵",
    "name_en": "Past · Present · Future",
    "description": "三张牌分别代表过去、现在和未来的启示。",
    "count": 3
  },
  "celtic_cross": {
    "name": "凯尔特十字",
    "name_en": "Celtic Cross",
    "description": "经典十牌阵，深入剖析你的处境与命运走向。",
    "count": 10
  }
}
```

- **用途**：
  - 前端在牌阵选择界面展示可用选项和描述，避免硬编码。

#### 3.2 塔罗解读：`POST /api/tarot/reading`

- **请求模型**：`TarotReadingRequest`

```json
{
  "question": "在未来一年，我的感情运势如何？",
  "spread_type": "three_card"
}
```

- **真实设计逻辑**：

1. 校验 `spread_type` 是否在 `SPREADS` 中，不存在则 `400` + 错误信息（包含可用类型列表）。
2. 根据牌阵信息 `spread_info = SPREADS[spread_type]` 获取张数与各位置说明。
3. 调用 `draw_cards(spread_type)`：
   - 从 78 张大阿卡纳 + 小阿卡纳中随机抽取对应张数。
   - 对每张牌随机决定正位 / 逆位。
   - 拼出字段：
     - `name` / `name_cn`
     - `orientation` / `orientation_cn`
     - `keywords`（根据 upright / reversed 选取）、
     - `position`（e.g. "过去" / "现在" / "未来" 等）。
4. 构造用户 prompt：

```text
用户的问题：{question}

牌阵：{spread_info['name']}（{spread_info['name_en']}）

抽到的牌：
位置【过去】: 愚者（The Fool）— 正位
  关键词: 新开始、冒险、纯真、自由
...
```

5. 使用 `TAROT_READING_PROMPT` 作为 system prompt，`json_mode=False` 调用大模型，得到中文长文本解读。
6. 将 `draw_cards` 原始列表映射为 `TarotCard` 对象，并打包成 `TarotReadingResponse`：

```json
{
  "cards": [
    {
      "name": "The Fool",
      "name_cn": "愚者",
      "orientation": "upright",
      "orientation_cn": "正位",
      "keywords": "新开始、冒险、纯真、自由",
      "position": "过去"
    },
    ...
  ],
  "reading": "长文本解读...",
  "spread_name": "Past · Present · Future",
  "spread_name_cn": "三牌阵"
}
```

- **前后端分工**：
  - **后端**：
    - 严格控制抽牌的随机逻辑和牌阵结构。
    - 将所有结构化信息发送给 AI，只让 AI 负责「语言解读」。
  - **前端**：
    - 使用 `cards` 列表渲染 UI：牌面、位置、正逆位、关键词等。
    - 使用 `reading` 文本展示详细占卜结果。

---

### 4. 量化决策实验室（Decision Lab）

#### 4.1 获取分析维度：`GET /api/decision/dimensions`

- **响应内容**：来自 `DECISION_PROMPTS.DIMENSIONS`：

```json
[
  { "key": "financial",   "label": "💰 财务影响",   "label_en": "Financial Impact" },
  { "key": "risk",        "label": "⚠️ 风险水平",   "label_en": "Risk Level" },
  { "key": "growth",      "label": "📈 成长潜力",   "label_en": "Growth Potential" },
  { "key": "time_cost",   "label": "⏰ 时间成本",   "label_en": "Time Cost" },
  { "key": "wellbeing",   "label": "😊 幸福感",     "label_en": "Wellbeing" },
  { "key": "feasibility", "label": "✅ 可行性",     "label_en": "Feasibility" }
]
```

- **用途**：
  - 前端绘制雷达图和评分表时使用统一的 key / label 映射，避免硬编码字符串。

#### 4.2 决策分析：`POST /api/decision/analyze`

- **请求模型**：`DecisionRequest`

```json
{
  "dilemma": "我应该辞职去创业，还是继续在大厂发展？"
}
```

- **真实设计逻辑**：

1. 使用 `DECISION_ANALYSIS_PROMPT` 作为 system prompt，传入内容类似：

```text
用户的决策困境：我应该辞职去创业，还是继续在大厂发展？
```

2. 设置 `json_mode=True`，强制要求 AI 返回结构化 JSON。
3. AI 必须生成形如：

```json
{
  "options": [
    {
      "name": "留在大厂",
      "description": "继续在当前公司工作，获得稳定收入与晋升机会。",
      "scores": {
        "financial": 80,
        "risk": 30,
        "growth": 70,
        "time_cost": 60,
        "wellbeing": 65,
        "feasibility": 90
      },
      "expected_value": 76,
      "scenarios": {
        "best_case": "...",
        "worst_case": "...",
        "most_likely": "..."
      }
    },
    {
      "name": "辞职创业",
      "description": "辞去目前工作，投入全职创业。",
      "scores": { ... },
      "expected_value": 82,
      "scenarios": { ... }
    }
  ],
  "recommendation": "详细分析与建议..."
}
```

4. 服务端对结果进行基本空值检查：
   - 若 `analysis` 为空，则返回 500。
   - 不对具体分值做额外处理，直接透传给前端。

- **前端交互**：
  - 使用 `options[*].scores` 渲染雷达图和对比表格。
  - 使用 `options[*].scenarios` 展示三种场景的文本说明。
  - 使用 `recommendation` 展示长文建议。

---

## 四、数据模型设计（Pydantic）

### 1. 人生模拟相关（`models.py`）

- `UserAttributes`
  - 仅提供一个默认结构（health/wealth/happiness/capability），实际接口多用通用 `Dict[str, float]` 存储属性。
- `SimulationState`
  - 将整个「人生状态」建模为单个对象，方便序列化给 AI 和前端：
    - `age: float`
    - `attributes: Dict[str, float>`
    - `inventory: List[str]`
    - `current_dilemma: str`
    - `target_goal: str`
    - `win_condition: str`
    - `loss_condition: str`
    - `narrative_start: Optional[str]`
- `InitRequest` / `SimulationRequest` / `EpiphanyRequest`
  - 明确各阶段 API 的入参结构，便于 FastAPI 自动生成文档与 swagger。

### 2. 塔罗相关（`tarot_models.py`）

- `TarotCard`
  - 放大而结构化地描述每张牌的信息：
    - 中英文名、正逆位标志与中文文案、关键词、在牌阵中的位置。
- `TarotReadingRequest`
  - `question` + `spread_type`，默认 `three_card`。
- `TarotReadingResponse`
  - 让前端同时拿到「结构化的牌阵信息」与「AI 文本解读」。

### 3. 决策相关（`decision_models.py`）

- `DecisionRequest`
  - 仅包含 `dilemma` 一项，保持接口简单。
- `Scenarios`
  - 描述「最佳 / 最差 / 最可能」三个情景。
- `DecisionOption`
  - 对每个方案的完整结构定义（含多维打分与期望值）。
- `DecisionResponse`
  - 包含所有方案与整体 `recommendation`。

---

## 五、PDF 报告生成设计（`services/pdf_service.py`）

### 1. 字体与样式

- 启动时尝试在多路径中寻找 CJK 字体（如 `simhei.ttf`、`msyh.ttc` 等），如果找到则注册为 `"CJKFont"`，否则回退到 `"Helvetica"` 并在日志提示可能无法正常显示中文。
- `_build_styles()` 定义了一整套样式：
  - 标题、副标题、章节标题、时间线条目、统计标签和值、胜利 / 失败结局样式、Epiphany 正文、页脚说明等。

### 2. 报告布局

`create_pdf_report(filepath, history, epiphany, state, conclusion)` 的整体结构：

1. **封面与概览**
   - 标题「🧬 人生模拟报告」与副标题。
   - 若有结局（如「胜利」「失败」等），在封面处以不同颜色强调。
2. **模拟概况**
   - 使用两列表格展示：
     - 目标
     - 胜利条件 / 失败条件
     - 核心困境
     - 最终年龄
     - 最终属性（健康 / 财富 / 快乐 / 能力）。
   - 如有 `narrative_start`，作为「初始叙事」展示。
3. **时间线**
   - 遍历 `history`，逐条以编号和统一样式展示，类似 Event Log。
4. **人生总结与启示（新页面）**
   - 在新的一页展示 `epiphany` 文本。
   - 对 `epiphany` 做简单 Markdown 兼容：
     - `##` / `#` 当作小标题。
     - `**text**` 当作加粗。
   - 所有文本在放入 Paragraph 前进行 XML 字符转义，避免破坏 ReportLab 内部标记。
5. **页脚**
   - 添加一段说明：报告仅供娱乐与参考。

通过 Platypus（`SimpleDocTemplate + Paragraph + Spacer + Table + PageBreak`）架构，**长文本会自动分页**，不会出现截断。

---

## 六、前后端交互一览（时序概念）

### 场景 1：人生模拟器

1. 用户在前端输入自我描述，点击发送。
2. 前端 `POST /api/init`，得到初始状态与开场叙事。
3. 用户每做一次选择：
   - 前端 `POST /api/simulation`（携带当前状态和历史）；
   - 后端调用 AI 生成新剧情和属性变化；
   - 前端更新数值条与对话框，并提供下一步可选项 chips。
4. 某一回合 AI 判断满足胜利 / 失败条件：
   - `is_concluded = true`，`conclusion = "win" / "loss"`。
   - 前端调用 `POST /api/epiphany` 请求人生复盘。
5. 后端生成 epiphany 文本和 PDF，返回给前端；前端渲染文本与下载按钮。

### 场景 2：AI 塔罗

1. 前端在「选择牌阵」页面请求 `GET /api/tarot/spreads`，展示可选牌阵。
2. 用户输入问题与牌阵类型，点击开始。
3. 前端 `POST /api/tarot/reading`。
4. 后端抽牌 + 调用 AI 生成解读，返回结构化牌阵 + 文本。
5. 前端渲染牌阵动画和解读内容。

### 场景 3：量化决策实验室

1. 前端页面加载时，调用 `GET /api/decision/dimensions` 获取维度元信息。
2. 用户输入决策困境，点击分析。
3. 前端 `POST /api/decision/analyze`。
4. 后端调用 AI 返回多方案、多维打分及建议。
5. 前端用雷达图、表格与文本解释展示结果。

---

## 七、扩展与二次开发建议

- **更换大模型 / 服务商**
  - 一般只需修改 `config.py` 中的 `BASE_URL`、`MODEL_NAME`，以及 `.env` 中对应的 API Key。
  - 若新模型不支持 `response_format={"type": "json_object"}`，可在 `ai_service.py` 中调整调用参数。
- **新增实验模块**
  - 可以参考 Decision Lab 的结构：
    - 新建 `xxx_models.py`、`xxx_prompts.py`。
    - 在 `main.py` 中增加对应的路由。
    - 在前端增加新容器与脚本，沿用现有布局与交互模式。
- **安全与配额控制**
  - 目前示例代码主要关注 Demo 体验：
    - 未做用户鉴权。
    - 未做调用频率限制 / 配额控制。
  - 在生产环境中可在 `main.py` 外层加上反向代理与网关，集中处理这些横切关注点。

本 README 旨在帮助你快速理解整个后端系统的设计思路与接口细节，以便调试、扩展或重构。若你希望针对某个模块（如 Prompt 设计或决策打分逻辑）做更深入的优化，可以在对应文件中迭代，并保持与本 README 中描述的数据契约一致。

