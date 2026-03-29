## Life Lab 项目总览（超简明版）

> 一句话总结：这是一个「人生实验室」，前端是一个多功能网页，后端是一个会调用大模型的大脑，两边通过一条 `/api` 管道不停对话。

---

## 1. 项目结构一眼看懂

- `backend/`：FastAPI 后端
  - 负责：对接大模型（Gemini）、定义业务流程、生成 PDF 报告。
  - 核心文件：
    - `main.py`：所有 HTTP 接口（人生模拟 / 塔罗 / 决策）。
    - `services/ai_service.py`：封装调用大模型的逻辑。
    - `services/pdf_service.py`：生成人生模拟的 PDF 报告。
    - 以及一堆 `*_models.py`、`*_prompts.py`：数据结构和 Prompt 模板。

- `frontend/`：纯 HTML/CSS/JS 前端
  - 负责：页面 UI、用户交互、把用户输入打包成请求发给后端，再把结果漂亮地展示出来。
  - 核心文件：
    - `index.html`：唯一页面，内置 3 个小应用容器。
    - `style.css`：统一暗色主题 + 动效。
    - `script.js`：人生模拟器前端逻辑。
    - `tarot.js`：AI 塔罗前端逻辑。
    - `decision.js`：决策实验室前端逻辑。

你可以把它想成：**前端是「游戏界面」+「控制器」，后端是「世界规则」+「AI 剧本写手」。**

---

## 2. 前后端是怎么「聊天」的？

### 2.1 一条简单的「管道」：`/api`

- 前端所有请求，都走同一条前缀：`/api/...`
  - 人生模拟：`/api/init`、`/api/simulation`、`/api/epiphany`
  - 塔罗：`/api/tarot/reading`
  - 决策：`/api/decision/analyze`
- 请求方式：
  - **统一用 `fetch` 发送 `POST` 请求 + JSON**（查询类少量 `GET`）。
  - 头部固定：`Content-Type: application/json`。
- 返回结果：
  - 后端用 Pydantic 定义好结构，前端直接当 JS 对象使用（属性名和后端字段完全一致）。

可以形象地理解为：

> 前端每点一次按钮，就把「一条 JSON 小纸条」丢进 `/api` 管道，  
> 后端接到纸条，去问大模型，算清楚结果，再把「另一张 JSON 小纸条」塞回来。

### 2.2 典型交互 1：人生模拟器

#### 步骤 1：初始化人物设定

1. 用户在网页上输入一段自我描述（如「27 岁程序员，想转行做独立游戏」）。
2. `script.js` 调用：

```js
POST /api/init
{
  "user_input": "用户的自我描述..."
}
```

3. 后端：
   - 用 Prompt 引导大模型：帮我设计这个人的「人生角色卡」（年龄、目标、属性、胜负条件等）。
   - 返回一个结构化 JSON，比如：

```json
{
  "age": 27.0,
  "attributes": { "health": 70, "wealth": 30, "happiness": 60, "capability": 75 },
  "current_dilemma": "白天上班，下班做游戏，时间不够用",
  "target_goal": "在三年内做出一款盈利的独立游戏",
  "win_condition": "...",
  "loss_condition": "...",
  "narrative_start": "你今年 27 岁..."
}
```

4. 前端：
   - 把这个 JSON 存到 `currentState`。
   - 侧边栏显示年龄和四个属性进度条。
   - 聊天区显示 `narrative_start` 作为故事开篇。

> 这一步可以理解成：**玩家给出背景，后端 + 大模型帮你生成游戏的「存档 0 号」。**

#### 步骤 2：每一次选择 -> 一次 `/api/simulation`

1. 用户做出选择（例如「立刻辞职全职做游戏」），前端调用：

```js
POST /api/simulation
{
  "current_state": { ...整份当前人生状态... },
  "user_choice": "立刻辞职全职做游戏",
  "history": [ "【初始状态】...", "【半年后】..." ]
}
```

2. 后端：
   - 把当前目标 / 胜负条件 / 选择，结合 `current_state` 一起交给大模型。
   - 大模型返回这一回合的：
     - 剧情文本（`narrative`）
     - 过了多久（`time_passed`，比如「半年」）
     - 属性变化（`state_changes`，如财富 -10、能力 +5）
     - 是否结束、结局是「胜利」还是「失败」
     - 下一步建议选项列表。
   - 后端再做一件事：**给属性加减后做「0~100 之间的钳制」**，防止属性爆表。
3. 前端：
   - 更新本地 `currentState`（年龄+0.5、属性+变化）。
   - 把这一条时间线文字加入 `history`。
   - 在聊天区显示新剧情 + 旁边出现可点击选项 chips。

如此往复，形成一条**「状态 JSON ↔ 故事 JSON」**的回合制循环。

#### 步骤 3：剧终 -> `/api/epiphany` + PDF 报告

1. 某次模拟后，大模型判断满足胜利/失败条件，后端回应 `is_concluded = true`。
2. 前端不再展示下一步选项，而是调用：

```js
POST /api/epiphany
{
  "history": [ ...完整时间线文字... ],
  "dilemma": currentState.current_dilemma,
  "final_state": currentState,
  "conclusion": "win" | "loss"
}
```

3. 后端：
   - 用 Prompt 让大模型写一段「人生复盘」长文（成败关键、如果重来、最后寄语）。
   - 用 `reportlab` 把：
     - 初始设定
     - 每一步历史
     - 最终属性
     - Epiphany 长文  
     一起排成一份 PDF 报告存在 `reports/`。
   - 返回：

```json
{
  "epiphany": "长文本...",
  "report_url": "/api/report/report_xxx.pdf"
}
```

4. 前端：
   - 把 `epiphany` 渲染在页面下方。
   - 把 `report_url` 绑到一个「Download PDF」按钮上。

> 至此，一个完整的「平行人生实验」从前端交互，到后端推演，到 PDF 报告，闭环完成。

### 2.3 AI Tarot & Decision Lab（模式一样，只是问题不同）

**AI Tarot**：

- 前端：
  - 用户选择牌阵 + 输入问题。
  - 调用 `POST /api/tarot/reading`。
- 后端：
  - 先在本地代码中**随机抽牌**（大阿卡纳/小阿卡纳、正逆位、位置）。
  - 再把「问题 + 抽到的牌」发给大模型，让它写一段「带剧情感的塔罗解读」。
  - 返回：结构化的牌阵数组 + 解读文本。
- 前端：
  - 用 CSS + JS 把每张牌做出「翻牌」动画。
  - 把解读文本渲染成排版良好的中文段落。

**Decision Lab**：

- 前端：
  - 用户输入一个困境（如「辞职创业还是留在大厂？」）。
  - 调用 `POST /api/decision/analyze`。
- 后端：
  - 让大模型：
    - 先列出 2–4 个可行方案。
    - 再对每个方案，在 6 个维度上打分（财务 / 风险 / 成长 / 时间成本 / 幸福感 / 可行性）。
    - 给出三种情景（最佳/最差/最可能）和综合建议。
  - 返回一个非常结构化的 JSON。
- 前端：
  - 用 Canvas 画雷达图，用表格对比各维度得分，用卡片展示三种情景，用富文本展示建议。

> 可以看到：**三个实验的前端交互形式不同，但本质都是：  
> 用户输入 → `/api/...` → 模型算完返回结构化 JSON → 前端负责「讲得好看」。**

---

## 3. 如何本地跑起来？

### 3.1 启动后端（FastAPI）

```bash
cd backend
pip install -r requirements.txt

# 配置 .env，至少要有：
# GEMINI_API_KEY=你的密钥

uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

后端此时会监听 `http://localhost:8000`，对外暴露 `/api/...` 接口。

### 3.2 启动前端（Vite）

```bash
cd frontend
npm install
npm run dev
```

默认打开 `http://localhost:5173`，即可看到 Life Lab 首页。

> 建议在 Vite 配置中加一个 `/api` 代理，把前端的 `/api` 请求转到 `http://localhost:8000`，  
> 这样开发时就不用改任何前端代码。

---

## 4. 如果你想快速理解这项目，可以这样看

1. **先打开网页玩一圈**：体验一次人生模拟 + 塔罗 + 决策，感受「玩法」。
2. **再看前端代码**：
   - 看 `script.js`，理解每个按钮会发什么样的 JSON 到后端。
   - 看 `tarot.js` 和 `decision.js`，体会「同一条 `/api` 管道，不同玩法」的模式。
3. **最后看后端**：
   - 看 `main.py` 的路由定义，对照请求体 / 响应体。
   - 看 `*_prompts.py`，理解每个实验是如何把「用户输入 + 当前状态」翻译成对大模型的指令。

理解之后，你可以很容易：

- 加一个新的「实验模块」（比如「职业规划 Lab」），只要：
  - 后端增加一条新的 `/api/...` 接口 + Prompt + 模型结构。
  - 前端增加一个卡片 + 一个 JS 文件，照抄现有交互模式即可。

这就是 Life Lab 的 **核心设计思想**：  
**前端只负责「界面和体验」；后端负责「规则和故事」；  
前后端之间只传来传去结构化的 JSON。**

