"""
角色系统 - 基于 Markdown 文件定义角色

目录结构:
    roles/
    ├── __init__.py      # 角色加载器
    ├── default/         # 默认角色（可选）
    │   └── SOUL.md
    └── <role_name>/     # 自定义角色
        ├── SOUL.md      # 核心人格、价值观、行为边界
        ├── IDENTITY.md  # 名字、风格、emoji（可选）
        ├── skills/      # 角色专属技能（可选）
        │   └── *.md     # trigger: always = 核心技能, trigger: [关键词] = 触发技能
        ├── knowledge/   # 角色专属知识库（可选）
        │   └── *.md
        └── knowledge.db # 知识库索引（自动生成）

使用方式:
    from lifee.roles import RoleManager

    rm = RoleManager()
    roles = rm.list_roles()           # 列出所有角色
    prompt = rm.load_role("critic")   # 加载角色的 system prompt（含核心技能）

    # 技能支持
    skill_set = rm.load_skills("critic")  # 加载技能集（用于触发技能匹配）

    # 知识库支持
    manager = await rm.get_knowledge_manager("critic", google_api_key="...")
    results = await manager.search("查询")
"""

import os
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from .skills import SkillSet, load_skill_set

if TYPE_CHECKING:
    from lifee.memory import MemoryManager


class RoleManager:
    """角色管理器"""

    def __init__(self, roles_dir: Optional[Path] = None):
        if roles_dir is None:
            roles_dir = Path(__file__).parent
        self.roles_dir = Path(roles_dir)

    def list_roles(self) -> list[str]:
        """列出所有可用角色"""
        roles = []
        for item in self.roles_dir.iterdir():
            if item.is_dir() and not item.name.startswith("_"):
                soul_file = item / "SOUL.md"
                if soul_file.exists():
                    roles.append(item.name)
        return sorted(roles)

    def load_role(self, role_name: str) -> Optional[str]:
        """
        加载角色配置，返回组合后的 system prompt

        加载顺序:
        1. SOUL.md (必须) - 核心人格
        2. IDENTITY.md (可选) - 身份信息
        3. core skills (可选) - 始终生效的核心技能 (Tier 1)
        """
        role_dir = self.roles_dir / role_name

        if not role_dir.exists():
            return None

        soul_file = role_dir / "SOUL.md"
        if not soul_file.exists():
            return None

        parts = []

        # 加载 SOUL.md
        soul_content = soul_file.read_text(encoding="utf-8").strip()
        if soul_content:
            parts.append(soul_content)

        # 加载 IDENTITY.md (可选)
        identity_file = role_dir / "IDENTITY.md"
        if identity_file.exists():
            identity_content = identity_file.read_text(encoding="utf-8").strip()
            if identity_content:
                parts.append(identity_content)

        if not parts:
            return None

        # 加载核心技能 (Tier 1: always-on)
        skill_set = load_skill_set(role_dir)
        core_prompt = skill_set.get_core_prompt()
        if core_prompt:
            parts.append(core_prompt)

        # 不用 --- 分隔符，避免 LLM 模仿输出
        return "\n\n".join(parts)

    def load_skills(self, role_name: str) -> SkillSet:
        """加载角色的技能集（用于 Tier 2 触发技能匹配）"""
        role_dir = self.roles_dir / role_name
        return load_skill_set(role_dir)

    def get_role_info(self, role_name: str) -> dict:
        """获取角色的基本信息"""
        role_dir = self.roles_dir / role_name

        info = {
            "name": role_name,
            "exists": role_dir.exists(),
            "has_soul": (role_dir / "SOUL.md").exists() if role_dir.exists() else False,
            "has_identity": (role_dir / "IDENTITY.md").exists() if role_dir.exists() else False,
            "has_skills": (role_dir / "skills").is_dir() if role_dir.exists() else False,
            "has_knowledge": (role_dir / "knowledge").is_dir() if role_dir.exists() else False,
        }

        # 尝试从 IDENTITY.md 提取显示名称和 emoji
        if info["has_identity"]:
            identity_file = role_dir / "IDENTITY.md"
            content = identity_file.read_text(encoding="utf-8")
            for line in content.split("\n"):
                if line.startswith("- **Name:**") or line.startswith("- **名字:**"):
                    info["display_name"] = line.split(":**")[1].strip()
                elif "**Emoji:**" in line:
                    info["emoji"] = line.split(":**")[1].strip()

        return info

    def get_role_emoji(self, role_name: str) -> str:
        """获取角色的 emoji 标识"""
        info = self.get_role_info(role_name)
        return info.get("emoji", "🤖")

    def get_knowledge_dir(self, role_name: str) -> Optional[Path]:
        """获取角色的知识库目录"""
        role_dir = self.roles_dir / role_name
        knowledge_dir = role_dir / "knowledge"
        if knowledge_dir.is_dir():
            return knowledge_dir
        return None

    def get_knowledge_db_path(self, role_name: str) -> Path:
        """获取角色的知识库数据库路径"""
        role_dir = self.roles_dir / role_name
        return role_dir / "knowledge.db"

    async def get_knowledge_manager(
        self,
        role_name: str,
        google_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        auto_index: bool = True,
    ) -> Optional["MemoryManager"]:
        """
        获取角色的知识库管理器

        Args:
            role_name: 角色名称
            google_api_key: Google API Key（用于 Gemini 嵌入）
            openai_api_key: OpenAI API Key
            auto_index: 是否自动索引知识库目录

        Returns:
            MemoryManager 实例，如果角色没有知识库则返回 None
        """
        knowledge_dir = self.get_knowledge_dir(role_name)
        if knowledge_dir is None:
            return None

        # 延迟导入避免循环依赖
        from lifee.memory import MemoryManager, create_embedding_provider

        # 创建嵌入提供者
        try:
            embedding = create_embedding_provider(
                google_api_key=google_api_key,
                openai_api_key=openai_api_key,
            )
        except ValueError:
            # 没有可用的 API Key
            return None

        # 创建管理器
        db_path = self.get_knowledge_db_path(role_name)
        manager = MemoryManager(db_path, embedding)

        # 自动索引（支持 .md 和 .txt 文件）
        if auto_index:
            # 收集所有待索引文件
            files = list(knowledge_dir.rglob("*.md")) + list(knowledge_dir.rglob("*.txt"))
            files = [f for f in files if f.is_file()]

            if files:
                # 检查是否需要索引（对比数据库中已有的文件数）
                stats = manager.get_stats()
                if stats["file_count"] < len(files):
                    total = len(files)
                    print(f"  索引知识库: 0/{total}", end="", flush=True)
                    indexed = 0
                    for f in files:
                        await manager.index_file(f)
                        indexed += 1
                        print(f"\r  索引知识库: {indexed}/{total}", end="", flush=True)
                    print()  # 换行

        return manager


# 便捷函数
_manager: Optional[RoleManager] = None


def get_manager() -> RoleManager:
    """获取全局角色管理器"""
    global _manager
    if _manager is None:
        _manager = RoleManager()
    return _manager


def list_roles() -> list[str]:
    """列出所有可用角色"""
    return get_manager().list_roles()


def load_role(role_name: str) -> Optional[str]:
    """加载角色的 system prompt"""
    return get_manager().load_role(role_name)
