"""本地工具的权限策略。

**设计参考 deepseek-harness**（https://github.com/deepseek-ai/deepseek-harness ，MIT License，Copyright (c) 2026 DeepSeek），
具体对应关系见 ``desktop/NOTICE.md``。这里不是它的代码移植，而是按它的模型用 Python 重新实现：

- 三种沙盒模式 ``read-only`` / ``workspace-write`` / ``danger-full-access``，默认最严的 ``read-only`` 思路
  （本项目的默认预设是 ``workspace-write``，与 harness 的默认预设一致）；
- 审批策略 ``ask`` / ``never``，预设把两者捆在一起：
  ``workspace-write`` + ask、``danger-full-access`` + never；
- 严格放宽表 ``WIDER_MODES``：升级只能到「严格更宽」的模式，在执行时检查而不是写进 schema；
- ``sandbox_permissions`` 与 ``justification`` 必须成对出现，且理由不能为空；
- 拒绝时给模型的标记 ``[sandbox: file access denied under <mode> mode]`` 与升级提示，
  以及「先检查是否更宽 → 再检查有无审批通道 → 再映射审批结果」的 fail-closed 顺序；
- 可写根 = 工作区 + 系统临时目录；路径包含判断先走规范化后的字面比较，
  不一致时回退到文件系统身份（dev/inode）比较，覆盖 Windows 8.3 短名与大小写别名。

和 harness 的差异（诚实记录）：Windows 上 v1 没有内核级的进程隔离，所以 bash 在受限模式下
不是「在沙盒里跑、被拒再升级」，而是**每条命令都需要用户批准**（见 ``local_tools``）。
"""

from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import paths

# ---------------------------------------------------------------------------
# 模式、预设与升级词汇
# ---------------------------------------------------------------------------

READ_ONLY = "read-only"
WORKSPACE_WRITE = "workspace-write"
DANGER_FULL_ACCESS = "danger-full-access"
SANDBOX_MODES = (READ_ONLY, WORKSPACE_WRITE, DANGER_FULL_ACCESS)

APPROVAL_ASK = "ask"
APPROVAL_NEVER = "never"

# 调用的有效模式可以升级到哪些「严格更宽」的模式（在执行时检查）。
WIDER_MODES: Dict[str, Tuple[str, ...]] = {
    READ_ONLY: (WORKSPACE_WRITE, DANGER_FULL_ACCESS),
    WORKSPACE_WRITE: (DANGER_FULL_ACCESS,),
}

# 工具 schema 里公布的升级目标（封闭词表；read-only 是地板，没有谁升级到它）。
ESCALATION_TARGETS = (WORKSPACE_WRITE, DANGER_FULL_ACCESS)


@dataclass(frozen=True)
class Preset:
    name: str
    sandbox: str
    approval: str
    label: str
    description: str


PRESETS: Dict[str, Preset] = {
    READ_ONLY: Preset(
        READ_ONLY, READ_ONLY, APPROVAL_ASK,
        "只读",
        "只能读取文件；任何写入或命令都需要你逐次批准。",
    ),
    WORKSPACE_WRITE: Preset(
        WORKSPACE_WRITE, WORKSPACE_WRITE, APPROVAL_ASK,
        "工作区读写（推荐）",
        "可在会话工作区和系统临时目录内读写；超出范围的操作和每条命令都需要你批准。",
    ),
    DANGER_FULL_ACCESS: Preset(
        DANGER_FULL_ACCESS, DANGER_FULL_ACCESS, APPROVAL_NEVER,
        "完全访问",
        "不再弹出批准：Agent 可读写整台电脑并直接执行命令。仅在你完全信任时使用。",
    ),
}

DEFAULT_PRESET = WORKSPACE_WRITE


@dataclass(frozen=True)
class Standing:
    """用户当前设置的常驻策略。"""

    preset: str
    mode: str
    approval: str


def standing_for(preset_name: Optional[str]) -> Standing:
    preset = PRESETS.get(preset_name or "") or PRESETS[DEFAULT_PRESET]
    return Standing(preset.name, preset.sandbox, preset.approval)


# ---------------------------------------------------------------------------
# 升级参数校验与模型可见的文案（与 harness 的词汇保持一致）
# ---------------------------------------------------------------------------

class EscalationError(Exception):
    """升级请求不成立或被拒；``str(exc)`` 就是给 Agent 看的原因。"""


def validate_escalation_args(sandbox_permissions: Optional[str], justification: Optional[str]) -> None:
    if sandbox_permissions is not None and justification is None:
        raise EscalationError("invalid escalation: sandbox_permissions requires a justification")
    if justification is not None and sandbox_permissions is None:
        raise EscalationError("invalid escalation: justification is only valid together with sandbox_permissions")
    if justification is not None and not str(justification).strip():
        raise EscalationError("invalid justification: expected a non-empty sentence")
    if sandbox_permissions is not None and sandbox_permissions not in ESCALATION_TARGETS:
        raise EscalationError(
            f'invalid escalation: sandbox_permissions must be one of {", ".join(ESCALATION_TARGETS)}'
        )


def sandbox_denial_marker(mode: str) -> str:
    return f"[sandbox: file access denied under {mode} mode]"


def escalation_hint_marker(subject: str) -> str:
    return (
        f"[sandbox: escalation available — retry this exact {subject} once with sandbox_permissions "
        "(the narrowest wider mode that suffices) + justification; the approval prompt asks the user]"
    )


def can_escalate(mode: str) -> bool:
    return bool(WIDER_MODES.get(mode))


def check_strictly_wider(effective_mode: str, requested_mode: str) -> None:
    if requested_mode not in WIDER_MODES.get(effective_mode, ()):
        raise EscalationError(
            f'sandbox escalation to "{requested_mode}" is not strictly wider than this call\'s current '
            f'"{effective_mode}" mode'
        )


def escalation_outcome_error(outcome: str, mode: str, subject: str) -> EscalationError:
    if outcome == "rejected":
        return EscalationError(f'the user rejected escalating this {subject} to "{mode}"')
    if outcome == "cancelled":
        return EscalationError(f'approval for escalating to "{mode}" was cancelled')
    return EscalationError(f'sandbox escalation to "{mode}" requires approval, but no approval channel is available')


# ---------------------------------------------------------------------------
# 路径：规范化、包含判断、受保护路径
# ---------------------------------------------------------------------------

_CASE_INSENSITIVE_FS = sys.platform in ("win32", "darwin")


def canonical_path(path: os.PathLike | str) -> str:
    """规范化：解析符号链接；路径（或其前缀）不存在时保留原拼写（保守：不会因此多授权）。"""
    try:
        return os.path.realpath(os.fspath(path))
    except OSError:
        return os.path.abspath(os.fspath(path))


def _comparable(path: str, case_sensitive: bool) -> str:
    return path if case_sensitive else path.lower()


def _lexically_under(path: str, root: str, case_sensitive: bool) -> bool:
    target, base = _comparable(path, case_sensitive), _comparable(root, case_sensitive)
    if target == base:
        return True
    prefix = base if base.endswith(os.sep) else base + os.sep
    return target.startswith(prefix)


def _stat_identity(path: str) -> Optional[Tuple[int, int]]:
    try:
        st = os.stat(path)
    except (FileNotFoundError, NotADirectoryError):
        return None
    except OSError:
        return None
    if not st.st_ino:
        return None  # 拿不到可靠的文件系统身份时，宁可判定「不在内」
    return (st.st_dev, st.st_ino)


def is_path_under(path: str, root: str, case_sensitive: Optional[bool] = None) -> bool:
    """``path`` 是 ``root`` 本身或其后代。

    字面比较走快路径；拼写不同时沿着 ``path`` 现存的祖先逐级比较文件系统身份，
    识别 Windows 长短名/大小写别名，同时不把包含判断放宽成文本近似。
    """
    if case_sensitive is None:
        case_sensitive = not _CASE_INSENSITIVE_FS
    if _lexically_under(path, root, case_sensitive):
        return True
    root_id = _stat_identity(root)
    if root_id is None:
        return False
    ancestor = path
    while True:
        if _stat_identity(ancestor) == root_id:
            return True
        parent = os.path.dirname(ancestor)
        if parent == ancestor:
            return False
        ancestor = parent


def temp_roots() -> List[str]:
    roots = {canonical_path(tempfile.gettempdir())}
    if os.name == "posix":
        roots.add(canonical_path("/tmp"))
    return sorted(roots)


def writable_roots(workspace: str, mode: str) -> List[str]:
    """workspace-write 的含义：工作区根 + 系统临时目录；read-only 什么都不许写。"""
    if mode != WORKSPACE_WRITE:
        return []
    return sorted({canonical_path(workspace), *temp_roots()})


def protected_roots() -> List[str]:
    """桌面端自己的状态目录（登录凭证等）：任何模式下 Agent 的文件工具都不得读写。"""
    return [canonical_path(paths.state_dir())]


def sensitive_roots() -> List[str]:
    """常见的凭证目录：受限模式下默认不可读，需要升级到完全访问并经用户批准。"""
    home = Path.home()
    candidates = [
        home / ".ssh",
        home / ".aws",
        home / ".gnupg",
        home / ".kube",
        home / ".azure",
        home / ".config" / "gcloud",
        home / ".docker",
        home / ".npmrc",
        home / ".pypirc",
        home / ".git-credentials",
        home / ".netrc",
    ]
    if sys.platform == "win32":
        local = Path(os.getenv("LOCALAPPDATA") or home / "AppData" / "Local")
        roaming = Path(os.getenv("APPDATA") or home / "AppData" / "Roaming")
        candidates += [
            local / "Google" / "Chrome" / "User Data",
            local / "Microsoft" / "Edge" / "User Data",
            roaming / "Mozilla" / "Firefox" / "Profiles",
        ]
    elif sys.platform == "darwin":
        candidates += [
            home / "Library" / "Keychains",
            home / "Library" / "Application Support" / "Google" / "Chrome",
        ]
    else:
        candidates += [home / ".config" / "google-chrome", home / ".mozilla"]
    return [canonical_path(c) for c in candidates]


# ---------------------------------------------------------------------------
# 判定
# ---------------------------------------------------------------------------

HARD_DENIAL = "[sandbox: access to Soulprout's own data directory is never allowed]"


@dataclass(frozen=True)
class Decision:
    allowed: bool
    # hard=True：任何模式、任何审批都不可能放行，不要给升级提示。
    hard: bool = False
    reason: str = ""

    @staticmethod
    def allow() -> "Decision":
        return Decision(True)


def _under_any(path: str, roots: List[str]) -> bool:
    return any(is_path_under(path, root) for root in roots)


def check_read(path: str, *, mode: str, kind: str, workspace: str) -> Decision:
    """读判定。``kind`` 为 ``soulprout``（整台电脑范围）或 ``task``（只限工作区 + 临时目录）。"""
    target = canonical_path(path)
    if _under_any(target, protected_roots()):
        return Decision(False, hard=True, reason=HARD_DENIAL)
    if mode == DANGER_FULL_ACCESS:
        return Decision.allow()
    if _under_any(target, sensitive_roots()):
        return Decision(False, reason="credential directory")
    if kind == "soulprout":
        return Decision.allow()
    roots = {canonical_path(workspace), *temp_roots()}
    if _under_any(target, sorted(roots)):
        return Decision.allow()
    return Decision(False, reason="outside the workspace")


def check_write(path: str, *, mode: str, workspace: str) -> Decision:
    target = canonical_path(path)
    if _under_any(target, protected_roots()):
        return Decision(False, hard=True, reason=HARD_DENIAL)
    if mode == DANGER_FULL_ACCESS:
        return Decision.allow()
    if _under_any(target, writable_roots(workspace, mode)):
        return Decision.allow()
    return Decision(False, reason="outside the writable roots")


def denial_text(decision: Decision, *, mode: str, subject: str) -> str:
    """给 Agent 的拒绝文案：标记 +（可升级时）升级提示。"""
    if decision.hard:
        return f"错误：{decision.reason}"
    text = sandbox_denial_marker(mode)
    if can_escalate(mode):
        text += "\n" + escalation_hint_marker(subject)
    return text
