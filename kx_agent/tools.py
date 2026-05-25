from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from fnmatch import fnmatch
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import SandboxConfig, ShellConfig


@dataclass
class ToolSpec:
    name: str
    description: str
    requires_approval: bool
    permission: str
    input_schema: dict[str, Any]


@dataclass
class ToolResult:
    tool_name: str
    status: str
    output: str
    metadata: dict[str, Any]


class ToolRegistry:
    def __init__(
        self,
        workspace_root: Path,
        allow_roots: list[Path] | None = None,
        shell_config: ShellConfig | None = None,
        sandbox_config: SandboxConfig | None = None,
    ):
        self.workspace_root = workspace_root.resolve()
        self.allow_roots = [path.resolve() for path in (allow_roots or [self.workspace_root])]
        self.shell_config = shell_config or ShellConfig()
        self.sandbox_config = sandbox_config or SandboxConfig()
        self.read_roots = [self._abs_path(path) for path in self.sandbox_config.read_roots]
        self.write_roots = [self._abs_path(path) for path in self.sandbox_config.write_roots]
        self.specs = {
            "read_file": ToolSpec(
                name="read_file",
                description="read a local text file",
                requires_approval=False,
                permission="read",
                input_schema={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            ),
            "search_code": ToolSpec(
                name="search_code",
                description="search text in the workspace",
                requires_approval=False,
                permission="read",
                input_schema={
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string"},
                        "path": {"type": "string"},
                    },
                    "required": ["pattern"],
                },
            ),
            "list_dir": ToolSpec(
                name="list_dir",
                description="list files in a directory",
                requires_approval=False,
                permission="read",
                input_schema={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            ),
            "read_many": ToolSpec(
                name="read_many",
                description="read multiple files matching a glob pattern",
                requires_approval=False,
                permission="read",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "pattern": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                    "required": ["path", "pattern"],
                },
            ),
            "write_file": ToolSpec(
                name="write_file",
                description="write content to a file",
                requires_approval=True,
                permission="write",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
            ),
            "make_dir": ToolSpec(
                name="make_dir",
                description="create a directory",
                requires_approval=True,
                permission="write",
                input_schema={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            ),
            "delete_file": ToolSpec(
                name="delete_file",
                description="delete a file",
                requires_approval=True,
                permission="dangerous",
                input_schema={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            ),
            "run_shell": ToolSpec(
                name="run_shell",
                description="run a shell command",
                requires_approval=True,
                permission="execute",
                input_schema={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                        "cwd": {"type": "string"},
                        "timeout_seconds": {"type": "integer"},
                    },
                    "required": ["command"],
                },
            ),
        }

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": spec.name,
                "description": spec.description,
                "requires_approval": spec.requires_approval,
                "permission": spec.permission,
                "input_schema": spec.input_schema,
            }
            for spec in self.specs.values()
        ]

    def spec(self, name: str) -> ToolSpec:
        return self.specs[name]

    def execute(self, name: str, arguments: dict[str, Any], sandbox_profile: str = "default") -> ToolResult:
        profile = self._profile(sandbox_profile)
        if name in {"write_file", "make_dir"} and not profile.get("allow_write", True):
            return ToolResult(name, "error", "write denied by sandbox profile", {"profile": sandbox_profile})
        if name == "delete_file" and not profile.get("allow_dangerous", False):
            return ToolResult(name, "error", "dangerous action denied by sandbox profile", {"profile": sandbox_profile})
        if name == "run_shell" and not profile.get("allow_shell", True):
            return ToolResult(name, "error", "shell denied by sandbox profile", {"profile": sandbox_profile})
        if name == "read_file":
            return self._read_file(arguments)
        if name == "search_code":
            return self._search_code(arguments)
        if name == "list_dir":
            return self._list_dir(arguments)
        if name == "read_many":
            return self._read_many(arguments)
        if name == "write_file":
            return self._write_file(arguments)
        if name == "make_dir":
            return self._make_dir(arguments)
        if name == "delete_file":
            return self._delete_file(arguments)
        if name == "run_shell":
            return self._run_shell(arguments)
        raise KeyError(f"unknown tool: {name}")

    def _profile(self, name: str) -> dict[str, Any]:
        return dict(self.sandbox_config.profiles.get(name, self.sandbox_config.profiles.get("default", {})))

    def _resolve(self, raw_path: str) -> Path:
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = self.workspace_root / path
        resolved = path.resolve()
        if not self._is_allowed(resolved, self.read_roots + self.write_roots):
            raise PermissionError(f"path outside allowed roots: {resolved}")
        return resolved

    def _abs_path(self, raw_path: str) -> Path:
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = self.workspace_root / path
        return path.resolve()

    def _is_allowed(self, path: Path, roots: list[Path]) -> bool:
        for root in roots:
            try:
                path.relative_to(root)
                return True
            except ValueError:
                continue
        return False

    def _resolve_read(self, raw_path: str) -> Path:
        path = self._resolve(raw_path)
        if not self._is_allowed(path, self.read_roots):
            raise PermissionError(f"read path outside sandbox read roots: {path}")
        return path

    def _resolve_write(self, raw_path: str) -> Path:
        path = self._resolve(raw_path)
        if not self._is_allowed(path, self.write_roots):
            raise PermissionError(f"write path outside sandbox write roots: {path}")
        return path

    def _read_file(self, arguments: dict[str, Any]) -> ToolResult:
        path = self._resolve_read(arguments["path"])
        output = path.read_text(encoding="utf-8", errors="ignore")
        return ToolResult(
            "read_file",
            "ok",
            output[: self.sandbox_config.max_output_bytes],
            {"path": str(path), "bytes": len(output)},
        )

    def _search_code(self, arguments: dict[str, Any]) -> ToolResult:
        root = self._resolve_read(arguments.get("path", str(self.workspace_root)))
        pattern = str(arguments["pattern"])
        rg_path = shutil.which("rg")
        if rg_path:
            cmd = [rg_path, "-n", pattern, str(root)]
        else:
            if os.name == "nt":
                cmd = ["findstr", "/S", "/N", "/P", pattern, str(root / "*")]
            else:
                cmd = ["grep", "-R", "-n", pattern, str(root)]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        output = proc.stdout or proc.stderr
        status = "ok" if proc.returncode in (0, 1) else "error"
        return ToolResult(
            "search_code",
            status,
            output[: self.sandbox_config.max_output_bytes],
            {"path": str(root), "pattern": pattern, "code": proc.returncode},
        )

    def _list_dir(self, arguments: dict[str, Any]) -> ToolResult:
        path = self._resolve_read(arguments["path"])
        entries = []
        for child in sorted(path.iterdir()):
            entries.append(
                {
                    "name": child.name,
                    "type": "dir" if child.is_dir() else "file",
                }
            )
        return ToolResult(
            "list_dir",
            "ok",
            json.dumps(entries, ensure_ascii=False, indent=2),
            {"path": str(path), "count": len(entries)},
        )

    def _read_many(self, arguments: dict[str, Any]) -> ToolResult:
        root = self._resolve_read(arguments["path"])
        pattern = str(arguments["pattern"])
        limit = int(arguments.get("limit", 20))
        files: list[dict[str, Any]] = []
        for child in sorted(root.rglob("*")):
            if not child.is_file():
                continue
            rel = child.relative_to(root).as_posix()
            if fnmatch(rel, pattern) or fnmatch(child.name, pattern):
                files.append(
                    {
                        "path": str(child),
                        "content": child.read_text(encoding="utf-8", errors="ignore")[: self.sandbox_config.max_output_bytes],
                    }
                )
            if len(files) >= limit:
                break
        return ToolResult(
            "read_many",
            "ok",
            json.dumps(files, ensure_ascii=False, indent=2),
            {"path": str(root), "pattern": pattern, "count": len(files), "limit": limit},
        )

    def _write_file(self, arguments: dict[str, Any]) -> ToolResult:
        path = self._resolve_write(arguments["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        content = str(arguments["content"])
        path.write_text(content, encoding="utf-8")
        return ToolResult(
            "write_file",
            "ok",
            f"wrote {path}",
            {"path": str(path), "bytes": len(content)},
        )

    def _make_dir(self, arguments: dict[str, Any]) -> ToolResult:
        path = self._resolve_write(arguments["path"])
        path.mkdir(parents=True, exist_ok=True)
        return ToolResult(
            "make_dir",
            "ok",
            f"created {path}",
            {"path": str(path)},
        )

    def _delete_file(self, arguments: dict[str, Any]) -> ToolResult:
        path = self._resolve_write(arguments["path"])
        if not path.exists():
            return ToolResult("delete_file", "error", f"missing {path}", {"path": str(path)})
        if path.is_dir():
            raise IsADirectoryError(f"delete_file only supports files: {path}")
        path.unlink()
        return ToolResult(
            "delete_file",
            "ok",
            f"deleted {path}",
            {"path": str(path)},
        )

    def _run_shell(self, arguments: dict[str, Any]) -> ToolResult:
        cwd = self._resolve_read(arguments.get("cwd", str(self.workspace_root)))
        command = str(arguments["command"])
        timeout_seconds = int(
            min(
                int(arguments.get("timeout_seconds", self.shell_config.timeout_seconds)),
                self.sandbox_config.max_shell_seconds,
            )
        )

        if not self.sandbox_config.shell_enabled:
            return ToolResult("run_shell", "error", "shell disabled by sandbox policy", {"cwd": str(cwd)})

        lowered = command.lower().strip()
        if any(pattern in lowered for pattern in [p.lower() for p in self.sandbox_config.denied_shell_patterns]):
            return ToolResult("run_shell", "error", "command denied by sandbox policy", {"cwd": str(cwd)})

        prefixes = [prefix.lower().strip() for prefix in self.sandbox_config.allowed_shell_prefixes]
        if prefixes and not any(lowered.startswith(prefix) for prefix in prefixes):
            return ToolResult("run_shell", "error", "command not allowlisted by sandbox policy", {"cwd": str(cwd)})

        if os.name == "nt":
            if "powershell" in self.shell_config.executable.lower():
                cmd = [self.shell_config.executable, "-NoLogo", "-NoProfile", "-Command", command]
            else:
                cmd = [self.shell_config.executable, "/c", command]
        else:
            shell = self.shell_config.executable or "/bin/bash"
            cmd = [shell, "-lc", command]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                cwd=str(cwd),
                timeout=timeout_seconds,
            )
            output = proc.stdout or proc.stderr
            status = "ok" if proc.returncode == 0 else "error"
            code = proc.returncode
        except subprocess.TimeoutExpired as exc:
            output = (exc.stdout or "") + (exc.stderr or "")
            status = "error"
            code = -1

        return ToolResult(
            "run_shell",
            status,
            output[: self.sandbox_config.max_output_bytes],
            {
                "cwd": str(cwd),
                "code": code,
                "os": platform.system(),
                "shell": self.shell_config.executable,
                "timeout_seconds": timeout_seconds,
            },
        )
