## Life Lab 前端说明文档（Frontend）

本目录是 **Life Lab / AI Sandbox** 的前端部分，为整个应用提供单页多应用的交互界面：

- **Life Simulator 人生模拟器**
- **AI Tarot 塔罗占卜**
- **Decision Lab 决策实验室**

前端使用 **原生 HTML/CSS/JS + Vite**，不依赖复杂框架（虽然 `package.json` 中安装了 `vue`，当前实现并未使用 Vue 组件体系）。三大功能共用一套 Dark 风格 UI，在同一页面内切换不同「应用容器」。

---

## 一、整体结构与文件说明

### 1. 顶层文件

- `index.html`
  - 整个前端唯一的 HTML 页面。
  - 包含：
    - **Home 视图**：功能选择页（Life Simulator / AI Tarot / Decision Lab 卡片）。
    - **人生模拟器容器**：`#app-container`，含侧边栏 + 聊天主视图。
    - **塔罗容器**：`#tarot-container`，含塔罗专用侧边栏 + 主视图。
    - **决策实验室容器**：`#decision-container`，含决策专用侧边栏 + 主视图。
  - 通过 `<script type="module" src="script.js">`、`tarot.js`、`decision.js` 引入三块逻辑。

- `style.css`
  - 全站样式与布局定义：
    - Dark 主题变量（颜色、字体等）。
    - 通用布局：侧边栏、主内容区、聊天消息、输入框、chips、加载状态等。
    - Home 视图：Logo、大标题、副标题、功能卡片、动画。
    - AI Tarot 专用样式：牌阵选择布局、卡牌翻转动画、结果面板等。
    - Decision Lab 专用样式：输入页、结果页、雷达图容器、对比表格、情景卡片、推荐卡片等。

- `script.js`
  - 人生模拟器前端逻辑。
  - 管理用户输入、状态机（currentState/history）、与后端 `/api` 的交互。
  - 实现 Home <-> Life Simulator 之间的导航与侧边栏折叠逻辑。

- `tarot.js`
  - AI Tarot 前端逻辑。
  - 管理牌阵选择、问题输入、与后端 `/api/tarot/reading` 的交互。
  - 渲染带有翻牌动画的塔罗牌 UI 与解读文本。

- `decision.js`
  - Decision Lab 前端逻辑。
  - 管理决策困境输入、与 `/api/decision/analyze` 的交互。
  - 实现纯 Canvas 的雷达图绘制、对比表格、情景卡片以及推荐文本渲染。

- `package.json`
  - Vite 工程配置与依赖说明：
    - `scripts`：
      - `dev`: 启动开发服务器（默认 http://localhost:5173）。
      - `build`: 打包静态文件到 `dist/`。
      - `preview`: 预览构建结果。
    - `dependencies`：当前只声明了 `vue`，但在实际代码中未使用。
    - `devDependencies`：`vite` + `@vitejs/plugin-vue`（未在 `vite.config.js` 中启用插件）。

- `vite.config.js`
  - 极简 Vite 配置：
    - `base: './'`：以相对路径加载静态资源，方便部署到子目录或静态托管平台。

- `dist/`
  - 由 `npm run build` 生成的静态构建产物（HTML + JS + CSS）。

---

## 二、前后端交互总览

前端通过 `fetch` 与后端 `/api` 接口通信，所有模块遵循统一模式：

- 使用固定 `API_BASE = "/api"` 或 `TAROT_API = "/api"` / `DECISION_API = "/api"`。
- 以 `Content-Type: application/json` 发送 `POST` 请求。
- 对 `response.ok` 做基础检查，失败时在控制台输出错误并在 UI 中提示用户检查后端。

对应后端接口（见 `backend/README.md`）：

- Life Simulator
  - `POST /api/init`
  - `POST /api/simulation`
  - `POST /api/epiphany`
  - `GET /api/report/{filename}`
- AI Tarot
  - `GET /api/tarot/spreads`（前端当前代码未使用，可拓展为动态渲染牌阵列表）
  - `POST /api/tarot/reading`
- Decision Lab
  - `GET /api/decision/dimensions`（当前由前端写死 `DIMENSION_META`，可未来改为动态拉取）
  - `POST /api/decision/analyze`

下文按模块详细说明「前端真实运行逻辑」与「如何与后端交互」。

---

## 三、Life Simulator 前端逻辑（`script.js`）

### 1. 状态与 DOM 映射

- 全局状态：
  - `const API_BASE = "/api";`
  - `let currentState = null;`：当前模拟的人生状态（后端返回的 `SimulationState`）。
  - `let history = [];`：每一步叙事记录，用于传给 `/api/epiphany` 以及在前端展示。
  - `let isSimulating = false;`：防止用户在模型还未返回时重复点击发送。

- `els` 对象缓存所有需要频繁操作的 DOM 元素：
  - `viewInit` / `viewSim`：初始化视图与正式模拟视图。
  - `narrativeBox`：展示对话 / 叙事的容器。
  - `inputBox` / `sendBtn` / `chipsContainer`：输入区域组件。
  - `loadingSim` / `loadingInit`：两个不同阶段的 loading 状态。
  - `statusBar` + `stats.*` + `bars.*`：侧边栏中的年龄、各项属性数值与进度条。
  - `epiphanyView` / `epiphanyText`：显示人生顿悟文本和报告下载链接的区域。

### 2. 通用网络请求封装

```js
async function postData(endpoint, data) {
    const response = await fetch(`${API_BASE}${endpoint}`, { ... });
    if (!response.ok) throw new Error(...);
    return await response.json();
}
```

- 统一为 `POST` 请求，发送 JSON。
- 出错时：
  - `console.error` 打印错误。
  - 调用 `appendMessage('system', "⚠️ Connection to Parallel Universe interrupted...")` 在对话中提示用户后端连接异常。

### 3. 消息与 UI 辅助函数

- `appendMessage(sender, text)`
  - 在聊天窗口追加一条消息：
    - `sender` ∈ `"user" | "ai" | "system"`。
    - 自动按 sender 设置 avatar 样式（比如 AI 为彩色小图标）。
    - 处理换行：将 `\n` 转为 `<br>`。
    - 自动滚动到底。
  - 首次用户消息与 AI 回复组合后，会隐藏初始化视图、显示模拟视图。

- `updateStats(attrs, age)`
  - 打开状态栏（使其 `display: flex`）。
  - 设置：
    - 文本：`stat-age` 显示一位小数的年龄。
    - 进度条：各属性根据数值（0~100）设置 `width: X%`。

- `renderChips(options)`
  - 渲染模型给出的下一步选项列表，每个选项为一个按钮 chip。
  - 点击 chip 即调用 `handleInput(opt)`，并自动滚动聊天到底部。

### 4. 核心函数：`handleInput(text = null)`

该函数贯穿两个阶段：**初始化** 和 **循环模拟**。

#### 阶段 1：初始化（调用 `/api/init`）

触发条件：

- 首次用户在输入框输入一段描述并发送。

流程：

1. 若 `isSimulating` 为 `true`，直接 return（避免重入）。
2. 获取用户输入文本 `input`，清空输入框与 chips。
3. 将输入追加到对话区 `appendMessage('user', input)`。
4. 判断 `currentState` 是否为 `null`：
   - 为 `null` 说明尚未初始化：
     - 显示 `loadingInit`。
     - 调用 `postData('/init', { user_input: input })`。
     - 隐藏 `loadingInit`。
5. 若返回了有效 `profile`：
   - 将后端的 `SimulationState` 保存为 `currentState`。
   - 将 `【初始状态】narrative_start` 推入 `history`，作为时间线第一条。
   - 切换视图：
     - 隐藏初始化欢迎页（`viewInit`）。
     - 显示聊天视图（`viewSim`）。
   - 调用 `updateStats(profile.attributes, profile.age)` 更新属性面板。
   - 在对话区显示开场叙事，并附加提示：
     - 「模拟开始。如果你在现实中做出了第一个选择，会是什么？」。

#### 阶段 2：循环模拟（调用 `/api/simulation`）

触发条件：

- `currentState` 不为 null，用户再次输入选择文本（或点击某个 chip）。

流程：

1. 设置 `isSimulating = true`，显示 `loadingSim`。
2. 构造请求 payload：

```js
const payload = {
  current_state: currentState,
  user_choice: input,
  history: history,
};
```

3. 调用 `postData('/simulation', payload)`。
4. 完成后隐藏 `loadingSim`，重置 `isSimulating = false`。
5. 若 `result` 存在：
   - **状态更新**：
     - 将 `result.new_attributes` 合并到 `currentState.attributes`。
     - 更新 `currentState.age = result.new_age`。
     - 将 `result.history_entry` 推入 `history`。
   - **UI 更新**：
     - 调用 `updateStats(...)` 刷新侧边栏属性。
     - 将新的叙事以 `📅 time_passed + narrative` 格式追加到对话区。
   - **分支逻辑**：
     - 若 `result.is_concluded === true`：
       - 调用 `generateEpiphany(result.conclusion)` 请求人生总结。
     - 否则：
       - 调用 `renderChips(result.next_options)` 渲染下一轮可选项。

### 5. 结束阶段：`generateEpiphany(conclusion)`

对应后端 `/api/epiphany`。

- 构造 payload：

```js
const payload = {
  history,
  dilemma: currentState.current_dilemma,
  final_state: currentState,
  conclusion,
};
```

- 调用 `postData('/epiphany', payload)`。
- 将返回的 `epiphany`：
  - 放入 `els.epiphanyText`，用 `<br>` 渲染换行。
  - 显示 `#view-epiphany` 区块。
- 若有 `result.report_url`：
  - 更新 `#btn-download-report` 的 `href`。
  - 显示 `#report-container` 下载按钮区域。

### 6. 导航与重置逻辑

- `window.openApp(appName)`
  - `simulator`：
    - 隐藏 `view-home` / `tarot-container` / `decision-container`。
    - 显示 `app-container`。
    - 若尚未初始化（`currentState == null`），则激活 `viewInit`。
  - `tarot` / `decision`：
    - 同理切换不同容器。

- `window.goHome()`
  - 显示 `view-home`（Home 页），隐藏所有子应用容器。

- `window.resetSimulator()`
  - 弹窗确认后：
    - 清空 `currentState`、`history`、`narrativeBox` 内容。
    - 隐藏 epiphany 区域与报告链接。
    - 重置所有属性显示为 `--`，进度条为 0。
    - 切回初始化视图，隐藏属性栏。

- 侧边栏折叠与响应式：
  - 针对 `.menu-btn`，在桌面端操作 `.sidebar.collapsed`，在移动端操作 `.sidebar.open`。
  - 添加全局 `click` 监听，在移动端点击侧边栏以外区域自动关闭侧边栏。

---

## 四、AI Tarot 前端逻辑（`tarot.js`）

### 1. 状态及入口

- 常量：
  - `const TAROT_API = "/api";`
  - `let selectedSpread = "three_card";`：默认三牌阵。

- 入口函数：
  - `window.selectSpread(type)`：切换牌阵：
    - 更新 `selectedSpread`。
    - 为对应 `.spread-option` 添加 `selected` 类，用 CSS 高亮。

### 2. 启动占卜：`startTarotReading()`

触发方式：

- 点击「开始占卜」按钮。
- 在 `#tarot-question` 中按 Enter（非 Shift+Enter）。

逻辑：

1. 读取问题文本并 `trim()`。
2. 若为空：
   - 更新 placeholder 为「✨ 请先输入你的问题…」并聚焦输入框。
   - 直接 return。
3. 切换界面：
   - 隐藏 `#tarot-setup` 与 `#tarot-result`。
   - 显示 `#tarot-loading`，展示水晶球动画与提示语。
4. 使用 `fetch` 调用后端：

```js
const response = await fetch(`${TAROT_API}/tarot/reading`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ question, spread_type: selectedSpread }),
});
```

5. 若返回成功：
   - 隐藏 loading，显示 `#tarot-result`。
   - 调用 `renderTarotCards(data.cards)` 渲染卡牌。
   - 调用 `renderReading(data.reading)` 渲染文本解读。
6. 若出错：
   - 打印错误日志。
   - 隐藏 loading，恢复到 `#tarot-setup` 。
   - 用 `alert('⚠️ 塔罗解读失败，请检查后端是否运行。')` 提示用户。

### 3. 卡牌渲染与翻转动画

核心函数：`renderTarotCards(cards)`。

- 会根据 `cards.length` 设置不同布局 class（`single-layout` / `three-layout` / `cross-layout`），配合 CSS 调整排布。
- 对每张牌：
  - 创建 `.tarot-card-wrapper`，设置逐张延迟的 `animationDelay` 形成入场动画。
  - 创建 `.tarot-card`，并为其 onclick 绑定 `flipCard(cardEl)`。
  - 背面 `.tarot-card-back`：
    - 随机从 `CARD_BACK_SYMBOLS` 中选取一个符号作为图案。
  - 正面 `.tarot-card-front`：
    - 显示牌位标签（`card.position`）。
    - 中英文牌名（`name_cn` / `name`）。
    - 正逆位标签（`orientation_cn`，并根据正逆设置不同颜色 class）。
    - 关键字 `card.keywords`。
    - 若为逆位，则整体内容容器 `.card-name-area` 添加 `reversed-card` 类，通过 CSS `transform: rotate(180deg)` 做视觉反转。
  - 自动翻牌：
    - 使用 `setTimeout(() => flipCard(cardEl), 800 + index * 500);` 在 0.8 秒后开始，逐张延迟翻转。

`flipCard(cardEl)` 只在尚未翻转时为其添加 `.flipped` 类，CSS 控制 3D 旋转。

### 4. 解读文本渲染：`renderReading(text)`

- 将 AI 返回的 Markdown 风格文案转换为 HTML：
  - `**bold**` -> `<strong>bold</strong>`
  - `*italic*` -> `<em>italic</em>`
  - `# heading` / `## subheading` -> `<h2>` / `<h3>`
  - 换行 `\n` -> `<br>`
- 放入 `#tarot-reading-text` 容器中，并在样式中定义排版与颜色。

### 5. 重置逻辑：`resetTarot()`

- 清空：
  - 用户问题输入框。
  - 卡牌区域与解读区域内容。
- 切换视图回「牌阵选择 + 问题输入」页面：
  - 显示 `#tarot-setup`。
  - 隐藏 `#tarot-result` 和 `#tarot-loading`。

---

## 五、Decision Lab 前端逻辑（`decision.js`）

### 1. 元数据与配色

- `DECISION_API = "/api";`
- `DIMENSION_META`：
  - 为六个维度定义 label、emoji 和颜色，以及 `invert` 标志（表示分数高是否代表更好）：
    - `financial`: 财务影响，分数高更好。
    - `risk`: 风险水平，高分 = 高风险，`invert: true`（后续计算最佳值时会取最小值）。
    - `time_cost`: 时间成本，同样 `invert: true`（越低越好）。
    - `growth` / `wellbeing` / `feasibility`: 分数越高越好。
- `OPTION_COLORS` / `OPTION_FILLS`：
  - 各方案在雷达图中对应的线条与填充颜色。

### 2. 启动分析：`startDecisionAnalysis()`

触发方式：

- 点击「分析」按钮。
- 在 `#decision-input` 中按 Enter（非 Shift+Enter）。

逻辑：

1. 获取 `dilemma` 文本并 `trim()`。
2. 若为空：
   - 修改 placeholder 为「✨ 请先描述你的决策困境…」并聚焦输入框后直接 return。
3. 切换 UI：
   - 隐藏 `#decision-setup`、`#decision-result`。
   - 显示 `#decision-loading`，展示加载动画与提示话。
4. 发送请求：

```js
const response = await fetch(`${DECISION_API}/decision/analyze`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ dilemma }),
});
```

5. 若响应成功：
   - 隐藏 loading，显示 `#decision-result`。
   - 调 `renderDecisionResult(data)` 填充详细结果。
6. 若出错：
   - 日志输出错误。
   - 隐藏 loading，回到 `#decision-setup`。
   - 弹窗提示用户检查后端。

### 3. 渲染总入口：`renderDecisionResult(data)`

- 从 `data.options` 中提取所有方案（数组）。
- 调用：
  - `drawRadarChart(options)`：绘制多方案雷达图。
  - `renderComparisonTable(options)`：维度对比表。
  - `renderScenarios(options)`：每个方案的三种情景描述卡片。
  - `renderRecommendation(data.recommendation)`：长文综合建议。

### 4. 雷达图绘制（Canvas 纯实现）

`drawRadarChart(options)`：

- 动态创建 `<canvas>`，大小为 `min(containerWidth, 420)`。
- 使用原生 Canvas API：
  - 绘制 5 层同心多边形网格（代表 20/40/60/80/100 分）。
  - 绘制从中心到各维度的射线，并在末尾绘制维度标签（含 emoji）。
  - 对每个方案：
    - 按维度顺序连接评分点形成多边形：
      - 半径 = `radius * (score / 100)`。
      - 外圈使用 `OPTION_COLORS`，内部半透明填充使用 `OPTION_FILLS`。
    - 在每个顶点处画小圆点，以增强可读性。
- 绘制图例：
  - 在图下方添加 `radar-legend`，每条包含一个彩色圆点和方案名称/期望值：

```text
● 留在大厂 (EV: 76)
● 辞职创业 (EV: 82)
...
```

### 5. 维度对比表：`renderComparisonTable(options)`

- 通过字符串拼接生成 `<table class="decision-table">`：
  - 表头：维度 / 各方案名称（带颜色）。
  - 每一行代表一个维度：
    - 第一列显示 emoji + label。
    - 之后每列是该方案在该维度的得分。
    - 根据 `DIMENSION_META[dim].invert` 与分数数组，选出「最佳值」，为其加上 `best-score` class，用 CSS 高亮。
  - 最后一行为期望值行（`ev-row`），用横线区隔并高亮期望值最高的方案。

### 6. 情景卡片：`renderScenarios(options)`

- 生成 `scenario-grid`：
  - 对每个方案创建 `.scenario-card`：
    - 顶部显示方案名及简短描述。
    - 下面三行：
      - 🌟 最佳 情景
      - 📋 最可能 情景
      - ⚡ 最差 情景
    - 使用不同颜色强调不同类型情景的标签。

### 7. 综合建议：`renderRecommendation(text)`

- 将 AI 返回的 Markdown 风格文本转为 HTML：
  - 同样支持 `**加粗**` / `*斜体*` / `# 标题` / `## 子标题` / 换行。
- 包装为：

```html
<h3>🤖 AI 综合建议</h3>
<div class="rec-text">...</div>
```

- 放入 `#decision-recommendation` 中展示。

### 8. 重置逻辑：`resetDecision()`

- 清空输入框与所有结果区域 DOM 内容。
- 隐藏结果与 loading，显示输入页 `#decision-setup`。

---

## 六、样式与响应式设计（`style.css`）

### 1. 主题与基础布局

- 使用 CSS 变量统一管理颜色、字号、间距等。
- 整体采用 Flex 布局：
  - `body` 是一个水平方向的 Flex 容器。
  - 侧边栏固定宽度，主内容区自适应。

### 2. Home 视图

- `home-container`：
  - 垂直居中，背景为径向渐变。
- `feature-card`：
  - 卡片式布局，每个功能一个独立卡片，带 hover 动效和阴影。
  - 通过额外的 icon class（如 `.tarot-icon`, `.decision-icon`）呈现不同配色。

### 3. 通用聊天界面

- `.message-row` + `.avatar` + `.message-content`：
  - 用户消息右对齐，AI 消息左对齐。
  - 输入框使用类似 Gemini/ChatGPT 风格的圆角输入盒。
- `.suggestion-chips`：
  - AI 提供的下一步选项以 chips 形式展示，便于点击。

### 4. AI Tarot & Decision Lab 专用样式

- AI Tarot：
  - 牌阵选择区：`spread-grid` + `.spread-option` 带选中态。
  - 牌面：`.tarot-card` + `.tarot-card-front/back` + 动画。
  - 解读面板：`.tarot-reading-panel`，支持 Markdown 转 HTML 后的排版。

- Decision Lab：
  - 结果页总体由 `decision-result-scroll` 控制滚动和居中。
  - 雷达图容器配合 Canvas 自动自适应宽度。
  - 对比表、情景卡片、建议卡片各自封装成块状视觉组件。

---

## 七、开发与运行方式

### 1. 开发环境

在前端目录执行：

```bash
cd frontend
npm install
npm run dev
```

- 默认 Vite 开发服务器运行在 `http://localhost:5173`。
- 需要保证后端（FastAPI）已运行并监听 `http://localhost:8000`（或你配置的地址），同时根据部署方案做好 API 代理或反向代理：
  - 常见做法是在 Vite 中配置 `server.proxy` 将 `/api` 代理到后端（当前 `vite.config.js` 未配置，可视需要添加）。
  - 也可以用 Nginx / Caddy 等在部署层处理 `/api` 的转发。

### 2. 构建与预览

```bash
npm run build   # 构建到 dist/
npm run preview # 本地预览构建结果
```

- 构建结果默认使用相对路径（`base: './'`），可直接丢到任意静态服务器（如 Nginx、静态托管平台等）。

### 3. 部署建议

**静态文件部署 + API 反向代理**（推荐）：

1. 后端单独运行在某个域名/路径，如 `https://api.example.com`。
2. 前端构建后，将 `dist/` 部署到 `https://lab.example.com`：
   - 在前端中将 `API_BASE` / `TAROT_API` / `DECISION_API` 改为完整 URL（或在运行时注入）。
3. 或者：
   - 在同一个域名下提供前端静态文件和后端 API，通过 Nginx 区分路径：
     - `/` -> 前端 `dist/index.html`。
     - `/assets/...` -> 前端静态资源。
     - `/api/...` -> 反向代理到 FastAPI 服务。

**Vite 开发时的 API 代理（可选）**：

- 可以在 `vite.config.js` 中补全：

```js
export default defineConfig({
  base: './',
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
```

这样前端开发环境下 `fetch('/api/...')` 会自动代理到后端。

---

## 八、扩展与二次开发建议

- **引入 Vue 组件化**
  - 目前前端虽然安装了 Vue 依赖，但仍采用原生 DOM 操作。
  - 若想改造成 Vue 单页应用：
    - 建议新建 `main.ts` / `App.vue`，将 Life Simulator / Tarot / Decision 分别封装为组件。
    - 使用路由或简单的状态切换替代当前的 `openApp()` / `goHome()`。

- **动态牌阵与维度配置**
  - 目前 Tarot 与 Decision 的一些元数据在前端写死。
  - 可扩展为：
    - 页面加载时调用 `GET /api/tarot/spreads`、`GET /api/decision/dimensions`。
    - 用返回的数据动态构建 feature/维度 UI，减少前后端配置重复。

- **错误处理与状态提示**
  - 当前错误处理逻辑简单：
    - 控制台输出 + `alert(...)` 或在对话中插入一条系统消息。
  - 生产环境中可加入：
    - 全局 Toast / Notification 系统。
    - 针对网络错误 / 超时时间的专门提示。

- **样式 / 国际化**
  - 所有文案目前为中英文混合，可进一步提取为文案配置文件，支持多语言切换。

本 README 旨在帮助你快速理解前端实现的真实逻辑与与后端的交互方式，方便你继续开发新功能、重构为框架化前端、或进行生产级部署优化。若你希望针对某一模块继续做更深入的设计说明（如 Canvas 雷达图的算法或动画系统），可以在对应文件基础上再拆分出更细的文档。 

# Vue 3 + Vite

This template should help get you started developing with Vue 3 in Vite. The template uses Vue 3 `<script setup>` SFCs, check out the [script setup docs](https://v3.vuejs.org/api/sfc-script-setup.html#sfc-script-setup) to learn more.

Learn more about IDE Support for Vue in the [Vue Docs Scaling up Guide](https://vuejs.org/guide/scaling-up/tooling.html#ide-support).
