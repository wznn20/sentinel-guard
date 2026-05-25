from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Skill:
    name: str
    trigger_terms: list[str]
    description: str
    instructions: str
    path: str = ""
    source: str = "builtin"
    tags: list[str] = field(default_factory=list)


BUILTIN_SKILLS = [
    Skill(
        name="gateway",
        trigger_terms=["route", "gateway", "channel", "dispatch", "message", "webhook"],
        description="route multi-channel requests and keep session isolation",
        instructions=(
            "You route inputs by channel, preserve session boundaries, and prefer explicit handoffs. "
            "When a message is ambiguous, ask one clarifying question."
        ),
        tags=["openclaw", "routing"],
    ),
    Skill(
        name="memory",
        trigger_terms=["remember", "history", "summary", "memory", "recall", "session"],
        description="persist, compress, and recall session memory",
        instructions=(
            "You maintain a compact memory tree: facts, preferences, decisions, open tasks, and summaries. "
            "Prefer short summaries over raw transcripts when context grows."
        ),
        tags=["hermes", "compression"],
    ),
    Skill(
        name="human",
        trigger_terms=["approve", "permission", "confirm", "human", "ask", "review"],
        description="human-in-the-loop approvals and user-friendly interaction",
        instructions=(
            "You keep the interface human-friendly: explain action consequences before asking for approval, "
            "and keep responses short, direct, and friendly."
        ),
        tags=["openhuman", "approval"],
    ),
    Skill(
        name="builder",
        trigger_terms=["code", "implement", "refactor", "fix", "patch", "test", "bug"],
        description="help plan and implement software changes",
        instructions=(
            "You act like a senior engineer: identify blockers, make minimal safe changes, and verify results."
        ),
        tags=["coding"],
    ),
]


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    text = text.lstrip()
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    import yaml

    front = yaml.safe_load(parts[1]) or {}
    body = parts[2].strip()
    return front, body


class SkillRegistry:
    def __init__(self, bundled_dir: Path | None = None, extra_dirs: list[Path] | None = None):
        repo_root = Path(__file__).resolve().parent.parent
        self.bundled_dir = bundled_dir or repo_root / "skills"
        self.extra_dirs = extra_dirs or []
        self.skills: list[Skill] = []
        self.load_builtin()
        self.load_directory(self.bundled_dir, source="bundled")
        for extra_dir in self.extra_dirs:
            self.load_directory(extra_dir, source="local")

    def load_builtin(self) -> None:
        self.skills.extend(BUILTIN_SKILLS)

    def load_directory(self, directory: Path, source: str = "local") -> None:
        if not directory.exists():
            return
        for path in sorted(directory.glob("*.md")):
            text = path.read_text(encoding="utf-8", errors="ignore")
            meta, body = _parse_frontmatter(text)
            name = str(meta.get("name") or path.stem)
            trigger_terms = list(meta.get("trigger_terms") or meta.get("triggers") or [name])
            first_line = body.splitlines()[0] if body.splitlines() else name
            description = str(meta.get("description") or first_line)
            tags = list(meta.get("tags") or [])
            self.skills.append(
                Skill(
                    name=name,
                    trigger_terms=[str(t).lower() for t in trigger_terms],
                    description=description,
                    instructions=body,
                    path=str(path),
                    source=source,
                    tags=tags,
                )
            )

    def register_skill(self, skill: Skill) -> None:
        self.skills.append(skill)

    def list(self) -> list[dict]:
        return [
            {
                "name": skill.name,
                "trigger_terms": skill.trigger_terms,
                "description": skill.description,
                "path": skill.path,
                "source": skill.source,
                "tags": skill.tags,
            }
            for skill in self.skills
        ]

    def match(self, message: str, context: str = "") -> Skill:
        text = f"{message}\n{context}".lower()
        best = self.skills[0]
        best_score = -1
        for skill in self.skills:
            score = sum(2 for term in skill.trigger_terms if term and term in text)
            score += sum(1 for tag in skill.tags if tag in text)
            if skill.name.lower() in text:
                score += 2
            if score > best_score:
                best = skill
                best_score = score
        return best

    def render_hub(self) -> str:
        lines = ["KX Skill Hub:"]
        for skill in self.skills:
            lines.append(f"- {skill.name}: {skill.description}")
        return "\n".join(lines)
