# LIFEE 角色咨询

咨询 LIFEE 的 AI/CS 先驱角色（Turing、Shannon、Von Neumann、Lacan 等）。
角色带有完整人格和知识库，基于他们的实际著作。会继承 LIFEE 当前对话的上下文。

## 使用方式

用户输入 `/lifee` 后面跟角色名和问题。

| 用户输入 | 执行命令 |
|---------|---------|
| `/lifee turing 什么是图灵机？` | `python -m lifee.cli.ask turing "什么是图灵机？"` |
| `/lifee shannon 信息论的核心是什么？` | `python -m lifee.cli.ask shannon "信息论的核心是什么？"` |
| `/lifee turing,shannon 信息和计算的关系？` | `python -m lifee.cli.ask --consult turing,shannon "信息和计算的关系？"` |
| `/lifee turing,shannon,vonneumann,lacan 讨论一下意识` | `python -m lifee.cli.ask --consult turing,shannon,vonneumann,lacan "讨论一下意识"` |

## 规则

- 单个角色名 → 用 `python -m lifee.cli.ask <角色> "<问题>"`
- 多个角色名（逗号分隔）→ 用 `python -m lifee.cli.ask --consult <角色1,角色2,...> "<问题>"`
- 问题用双引号包裹
- 工作目录必须是 LIFEE 项目根目录
- 每个角色大约需要 10-15 秒回答

## 可用角色

- `turing` — 🧮 图灵，计算机科学之父
- `shannon` — 📡 香农，信息论之父
- `vonneumann` — ⚛️ 冯·诺依曼，数学与计算通才
- `lacan` — 拉康，精神分析学家
- 其他角色可通过 `python -m lifee.cli.ask --help` 查看

## 参数说明

`$ARGUMENTS` 格式为 `<角色> <问题>` 或 `<角色1,角色2> <问题>`。

解析 `$ARGUMENTS`：
1. 第一个空格前的部分是角色名（可能包含逗号表示多角色）
2. 第一个空格后的所有内容是问题
