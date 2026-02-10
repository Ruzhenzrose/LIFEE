"""
技能加载器 - 三级技能系统

Tier 1 (Always-on): trigger: always 或无 trigger → 始终注入 system prompt
Tier 2 (Context-triggered): trigger: [关键词] → 用户输入命中时注入
Tier 3 (Query-based): 已有的 knowledge/ RAG 系统（不在此模块）

技能文件格式:
    ---
    trigger: [梦, 梦境, dream]
    description: 技能描述
    ---

    ## 技能正文内容
    ...

    无 frontmatter 或 trigger: always = Tier 1（核心技能）
    trigger: [关键词列表] = Tier 2（触发技能）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Skill:
    """单个技能"""

    name: str  # 文件名（无 .md）
    content: str  # 去掉 frontmatter 后的正文
    description: str = ""
    trigger: str | list[str] = "always"  # "always" 或关键词列表

    @property
    def is_core(self) -> bool:
        return self.trigger == "always"


@dataclass
class SkillSet:
    """角色的完整技能集"""

    core_skills: list[Skill] = field(default_factory=list)
    triggered_skills: list[Skill] = field(default_factory=list)

    @property
    def has_skills(self) -> bool:
        return bool(self.core_skills or self.triggered_skills)

    def get_core_prompt(self) -> str:
        """拼接所有核心技能内容"""
        if not self.core_skills:
            return ""
        return "\n\n".join(s.content for s in self.core_skills)

    def match_by_input(self, user_input: str) -> list[Skill]:
        """
        基于用户输入匹配触发技能

        直接检查用户输入中是否包含触发关键词，
        避免 RAG 结果中的噪声导致误触发。
        """
        if not self.triggered_skills or not user_input:
            return []

        text = user_input.lower()

        matched = []
        for skill in self.triggered_skills:
            if isinstance(skill.trigger, list):
                for keyword in skill.trigger:
                    if keyword.lower() in text:
                        matched.append(skill)
                        break
        return matched


def _parse_frontmatter(text: str) -> tuple[str | list[str], str]:
    """
    简单解析 YAML frontmatter（不依赖 PyYAML）

    Returns:
        (trigger, description)
    """
    trigger: str | list[str] = "always"
    description = ""

    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if line.startswith("description:"):
            description = line[len("description:") :].strip().strip("\"'")

        elif line.startswith("trigger:"):
            value = line[len("trigger:") :].strip()
            if value == "always" or value == "":
                trigger = "always"
            elif value.startswith("["):
                # 行内列表: [keyword1, keyword2]
                items = value.strip("[]").split(",")
                trigger = [
                    item.strip().strip("\"'") for item in items if item.strip()
                ]
            else:
                # 可能是多行列表，看下一行是否以 - 开头
                trigger_list = []
                j = i + 1
                while j < len(lines) and lines[j].strip().startswith("- "):
                    item = lines[j].strip()[2:].strip().strip("\"'")
                    if item:
                        trigger_list.append(item)
                    j += 1
                if trigger_list:
                    trigger = trigger_list
                    i = j - 1  # 跳过已处理的行

        i += 1

    return trigger, description


def parse_skill_file(path: Path) -> Optional[Skill]:
    """解析单个技能文件"""
    try:
        content = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None

    if not content:
        return None

    name = path.stem
    description = ""
    trigger: str | list[str] = "always"
    body = content

    # 解析 YAML frontmatter
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            frontmatter = content[3:end].strip()
            body = content[end + 3 :].strip()
            trigger, description = _parse_frontmatter(frontmatter)

    if not body:
        return None

    return Skill(
        name=name,
        content=body,
        description=description,
        trigger=trigger,
    )


def load_skill_set(role_dir: Path) -> SkillSet:
    """加载角色目录下的所有技能"""
    skills_dir = role_dir / "skills"
    skill_set = SkillSet()

    if not skills_dir.is_dir():
        return skill_set

    for path in sorted(skills_dir.glob("*.md")):
        if not path.is_file():
            continue
        skill = parse_skill_file(path)
        if skill is None:
            continue
        if skill.is_core:
            skill_set.core_skills.append(skill)
        else:
            skill_set.triggered_skills.append(skill)

    return skill_set
