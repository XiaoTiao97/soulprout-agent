"""在用户电脑上执行云端 Agent 下发的本地工具：read / write / edit / read_picture / bash。

行为和云端 ``agent/tool/tools.py`` 里同名工具保持一致（参数、返回文案、``write`` 为追加写等），
区别只在两点：

1. 执行位置是用户自己的电脑，工作区是 ``<data_root>/workspaces/<conversation_id>``；
2. 每次调用都先过 ``policy`` 的权限判定与审批（设计参考 deepseek-harness，见 desktop/NOTICE.md）。

权限与审批流程：
- 调用带 ``sandbox_permissions`` + ``justification`` 时，先严格检查「是否比当前模式更宽」，再请用户批准，
  批准后只对这一次调用生效；
- 不带升级参数时，按常驻模式判定；被拒时返回 ``[sandbox: file access denied under <mode> mode]``
  标记和升级提示，由 Agent 决定是否带升级参数重试；
- ``bash`` 在受限模式下**没有内核级隔离**（v1），所以每条命令都要用户批准；审批策略是 ``never`` 而模式又受限时，
  fail closed，直接拒绝（和 harness「没有沙盒后端就拒绝无约束运行」同一原则）。
"""

from __future__ import annotations

import asyncio
import base64
import locale
import logging
import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from . import approvals, file_parse, paths, policy

logger = logging.getLogger(__name__)

VIEW_DEFAULT_LIMIT = 500
VIEW_MAX_LIMIT = 2000
BASH_TIMEOUT_S = 3600
MAX_OUTPUT_CHARS = 120_000

# bash 子进程里要抹掉的环境变量：桌面端自己的凭证/配置，以及 PyInstaller 注入的库路径。
_SCRUB_PREFIXES = ("SOULPROUT_", "GATEWAY_", "_PYI", "_MEIPASS")
_SCRUB_NAMES = {"AGENT_TOKEN", "AGENT_URL", "AUTH_URL", "PYTHONHOME", "PYTHONPATH", "LD_LIBRARY_PATH_ORIG"}


@dataclass
class CallContext:
    conversation_id: str
    kind: str  # "soulprout" | "task"
    standing: policy.Standing
    workspace: str
    call_id: Optional[str] = None


def scrubbed_env(workspace: str) -> Dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.upper().startswith(_SCRUB_PREFIXES) and k.upper() not in _SCRUB_NAMES
    }
    original = os.environ.get("LD_LIBRARY_PATH_ORIG")
    if getattr(sys, "frozen", False) and original is not None:
        env["LD_LIBRARY_PATH"] = original
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env["SOULPROUT_SHELL"] = "1"
    env["SOULPROUT_WORKSPACE"] = workspace
    return env


def decode_output(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    fallback = "mbcs" if sys.platform == "win32" else locale.getpreferredencoding(False)
    try:
        return data.decode(fallback, errors="replace")
    except LookupError:
        return data.decode("utf-8", errors="replace")


def tail_truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return f"...[输出过长，已截断，仅保留最后 {limit} 个字符]\n" + text[-limit:]


def _image_media_type(data: bytes) -> Optional[str]:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _kill_process_tree(pid: int) -> None:
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                creationflags=0x08000000,  # CREATE_NO_WINDOW
            )
        else:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
    except Exception:
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass


def _resolve(workspace: str, file_path: str) -> str:
    """和云端 ``os.path.join(workspace, file_path)`` 同一语义：相对路径落在工作区，绝对路径原样使用；额外支持 ``~``。"""
    return os.path.join(workspace, os.path.expanduser(str(file_path)))


def _clip(text: str, limit: int = 200) -> str:
    text = text.replace("\r", "")
    return text if len(text) <= limit else text[:limit] + "…"


class LocalToolRunner:
    def __init__(self, standing_provider: Callable[[], policy.Standing], broker: approvals.ApprovalBroker):
        self._standing = standing_provider
        self._broker = broker

    # ------------------------------------------------------------------ 入口

    async def execute(
        self,
        tool: str,
        arguments: Dict[str, Any],
        *,
        conversation_id: str = "",
        context: Optional[Dict[str, Any]] = None,
        call_id: Optional[str] = None,
    ) -> Any:
        args = dict(arguments or {})
        cid = str(args.pop("conversation_id", None) or conversation_id or "")
        try:
            workspace = str(paths.workspace_dir(cid))
        except ValueError:
            return "错误：无效的会话 ID，无法确定本地工作区。"
        kind = "soulprout" if (context or {}).get("kind") == "soulprout" else "task"
        ctx = CallContext(cid, kind, self._standing(), workspace, call_id)

        handlers = {
            "read": self._read,
            "write": self._write,
            "edit": self._edit,
            "read_picture": self._read_picture,
            "bash": self._bash,
            "sync_manifest": self._sync_manifest,
            "sync_put": self._sync_put,
        }
        handler = handlers.get(tool)
        if handler is None:
            return f"错误：本地不支持的工具：{tool}"
        return await handler(args, ctx)

    # ------------------------------------------------------------------ 权限

    def _pop_escalation(self, args: Dict[str, Any]) -> tuple:
        sandbox_permissions = args.pop("sandbox_permissions", None)
        justification = args.pop("justification", None)
        policy.validate_escalation_args(sandbox_permissions, justification)
        return sandbox_permissions, justification

    async def _ask(self, ctx: CallContext, *, tool: str, title: str, detail: str, reason: str, target_mode: str) -> str:
        return await self._broker.request(
            tool=tool,
            title=title,
            detail=detail,
            reason=reason,
            mode=ctx.standing.mode,
            target_mode=target_mode,
            conversation_id=ctx.conversation_id,
            call_id=ctx.call_id,
        )

    async def _effective_mode(
        self, ctx: CallContext, tool: str, sandbox_permissions: Optional[str], justification: Optional[str],
        *, subject: str, title: str, detail: str,
    ) -> str:
        """本次调用的有效模式：默认是常驻模式；带升级参数时先批准，只对这一次生效。"""
        mode = ctx.standing.mode
        if sandbox_permissions is None:
            return mode
        policy.check_strictly_wider(mode, sandbox_permissions)  # 非放宽请求不会打扰用户
        outcome = await self._ask(
            ctx, tool=tool, title=title, detail=detail,
            reason=f"escalate sandbox to {sandbox_permissions}: {justification}",
            target_mode=sandbox_permissions,
        )
        if outcome != approvals.ALLOWED_ONCE:
            raise policy.escalation_outcome_error(outcome, sandbox_permissions, subject)
        return sandbox_permissions

    # ------------------------------------------------------------------ read

    async def _read(self, args: Dict[str, Any], ctx: CallContext) -> str:
        file_path = str(args.get("file_path") or "")
        try:
            sp, just = self._pop_escalation(args)
            target = _resolve(ctx.workspace, file_path)
            mode = await self._effective_mode(
                ctx, "read", sp, just, subject="operation", title="读取文件", detail=policy.canonical_path(target)
            )
            decision = policy.check_read(target, mode=mode, kind=ctx.kind, workspace=ctx.workspace)
            if not decision.allowed:
                return policy.denial_text(decision, mode=mode, subject="operation")

            offset = self._int(args.get("offset"), 1)
            limit = self._int(args.get("limit"), VIEW_DEFAULT_LIMIT)
            offset = max(1, offset)
            limit = max(1, min(limit, VIEW_MAX_LIMIT))

            if file_path.lower().endswith(file_parse.PARSEABLE_SUFFIXES):
                return str(await file_parse.parse_document(target, file_path))
            return await asyncio.to_thread(self._read_text, target, file_path, offset, limit)
        except policy.EscalationError as exc:
            return f"错误：{exc}"
        except Exception as exc:
            return f"错误：阅读{file_path}失败，失败原因：{exc}"

    @staticmethod
    def _int(value: Any, default: int) -> int:
        try:
            return int(value) if value is not None else default
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _read_text(target: str, file_path: str, offset: int, limit: int) -> str:
        with open(target, "rb") as fh:
            raw = fh.read()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode(locale.getpreferredencoding(False), errors="strict")
        lines = text.splitlines(keepends=True)
        total = len(lines)
        if offset > total:
            return f"<file is empty or offset({offset}) > total lines({total})>"
        start = offset - 1
        end = min(start + limit, total)
        numbered = [f"{start + idx + 1:6}\u2502{line.rstrip(chr(10)).rstrip(chr(13))}" for idx, line in enumerate(lines[start:end])]
        header = f"# {file_path} (lines {start + 1}-{end} of {total})\n"
        footer = "" if end >= total else f"\n<... {total - end} more lines, call read again with offset={end + 1} to continue ...>"
        return header + "\n".join(numbered) + footer

    # ------------------------------------------------------------------ write / edit

    async def _write(self, args: Dict[str, Any], ctx: CallContext) -> str:
        file_path = str(args.get("file_path") or "")
        content = args.get("content")
        content = "" if content is None else str(content)
        try:
            sp, just = self._pop_escalation(args)
            target = _resolve(ctx.workspace, file_path)
            mode = await self._effective_mode(
                ctx, "write", sp, just, subject="operation", title="写入文件",
                detail=f"{policy.canonical_path(target)}\n\n{_clip(content)}",
            )
            decision = policy.check_write(target, mode=mode, workspace=ctx.workspace)
            if not decision.allowed:
                return policy.denial_text(decision, mode=mode, subject="operation")
            await asyncio.to_thread(self._append_text, target, content)
            return f"成功写入{file_path}"
        except policy.EscalationError as exc:
            return f"错误：{exc}"
        except Exception as exc:
            return f"错误：写入{file_path}失败，失败原因：{exc}"

    @staticmethod
    def _append_text(target: str, content: str) -> None:
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        with open(target, "a", encoding="utf-8", newline="") as fh:
            fh.write(content)

    async def _edit(self, args: Dict[str, Any], ctx: CallContext) -> str:
        file_path = str(args.get("file_path") or "")
        past_text = str(args.get("past_text") or "")
        replace_text = str(args.get("replace_text") or "")
        try:
            sp, just = self._pop_escalation(args)
            target = _resolve(ctx.workspace, file_path)
            mode = await self._effective_mode(
                ctx, "edit", sp, just, subject="operation", title="修改文件",
                detail=f"{policy.canonical_path(target)}\n\n- {_clip(past_text, 100)}\n+ {_clip(replace_text, 100)}",
            )
            read_decision = policy.check_read(target, mode=mode, kind=ctx.kind, workspace=ctx.workspace)
            if not read_decision.allowed:
                return policy.denial_text(read_decision, mode=mode, subject="operation")
            write_decision = policy.check_write(target, mode=mode, workspace=ctx.workspace)
            if not write_decision.allowed:
                return policy.denial_text(write_decision, mode=mode, subject="operation")
            changed = await asyncio.to_thread(self._replace_text, target, past_text, replace_text)
            if not changed:
                return "文本替换失败，请检查past_text是否对应原文内容"
            return f"成功修改{file_path}"
        except policy.EscalationError as exc:
            return f"错误：{exc}"
        except Exception as exc:
            return f"错误：修改{file_path}失败，失败原因：{exc}"

    @staticmethod
    def _replace_text(target: str, past_text: str, replace_text: str) -> bool:
        with open(target, "r", encoding="utf-8", newline="") as fh:
            src = fh.read()
        dst = src.replace(past_text, replace_text)
        if dst == src:
            return False
        with open(target, "w", encoding="utf-8", newline="") as fh:
            fh.write(dst)
        return True

    # ------------------------------------------------------------------ read_picture

    async def _read_picture(self, args: Dict[str, Any], ctx: CallContext) -> Dict[str, Any]:
        file_name = str(args.get("file_name") or "")

        def fail(message: str) -> Dict[str, Any]:
            return {"ok": False, "message": message, "base64": None, "media_type": None}

        try:
            sp, just = self._pop_escalation(args)
            target = _resolve(ctx.workspace, file_name)
            mode = await self._effective_mode(
                ctx, "read_picture", sp, just, subject="operation", title="读取图片", detail=policy.canonical_path(target)
            )
            decision = policy.check_read(target, mode=mode, kind=ctx.kind, workspace=ctx.workspace)
            if not decision.allowed:
                return fail(policy.denial_text(decision, mode=mode, subject="operation"))
            if not os.path.exists(target):
                return fail("路径不存在")
            raw = await asyncio.to_thread(self._read_bytes, target)
            media_type = _image_media_type(raw)
            if not media_type:
                return fail(f"图片格式不支持（仅支持 png、jpeg、gif、webp），未送入模型：{file_name}")
            return {
                "ok": True,
                "message": "成功读取图片",
                "base64": base64.b64encode(raw).decode("utf-8"),
                "media_type": media_type,
            }
        except policy.EscalationError as exc:
            return fail(f"错误：{exc}")
        except Exception as exc:
            return fail(f"读取图片失败: {exc}")

    @staticmethod
    def _read_bytes(target: str) -> bytes:
        with open(target, "rb") as fh:
            return fh.read()

    # ------------------------------------------------------------------ bash

    async def _bash(self, args: Dict[str, Any], ctx: CallContext) -> str:
        command = str(args.get("command") or "")
        try:
            sp, just = self._pop_escalation(args)
            standing = ctx.standing
            detail = f"工作目录：{ctx.workspace}\n\n{_clip(command, 600)}"
            if sp is not None:
                await self._effective_mode(
                    ctx, "bash", sp, just, subject="command", title="以更高权限执行命令", detail=detail
                )
            elif standing.mode != policy.DANGER_FULL_ACCESS:
                # v1 没有内核级隔离：受限模式下每条命令都必须由用户批准；不能问用户时 fail closed。
                if standing.approval != policy.APPROVAL_ASK:
                    return policy.sandbox_denial_marker(standing.mode) + "\n[sandbox: no confining backend is available; refusing to run unconfined]"
                outcome = await self._ask(
                    ctx, tool="bash", title="执行命令", detail=detail,
                    reason="run a command on this computer (no OS-level confinement available)",
                    target_mode=policy.DANGER_FULL_ACCESS,
                )
                if outcome != approvals.ALLOWED_ONCE:
                    raise policy.escalation_outcome_error(outcome, policy.DANGER_FULL_ACCESS, "command")
            return await self._run_command(command, ctx)
        except policy.EscalationError as exc:
            return f"错误：{exc}"
        except Exception as exc:
            return f"错误: bash 执行失败，原因：{exc}"

    async def _run_command(self, command: str, ctx: CallContext) -> str:
        os.makedirs(ctx.workspace, exist_ok=True)
        kwargs: Dict[str, Any] = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW：不闪黑窗
        else:
            kwargs["start_new_session"] = True  # 独立进程组，取消/超时时整组杀掉
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=ctx.workspace,
            env=scrubbed_env(ctx.workspace),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **kwargs,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), BASH_TIMEOUT_S)
        except asyncio.TimeoutError:
            await asyncio.to_thread(_kill_process_tree, proc.pid)
            return "错误: 命令执行超时"
        except asyncio.CancelledError:
            await asyncio.to_thread(_kill_process_tree, proc.pid)
            raise
        text = f"Command executed with return code: {proc.returncode}\n\n"
        if stdout:
            text += f"Standard Output:\n{decode_output(stdout)}"
        if stderr:
            text += f"Standard Error:\n{decode_output(stderr)}"
        return tail_truncate(text)

    # ------------------------------------------------------------------ 云端文件同步（智能体文件 / 技能）
    #
    # 这是云端准备工作区时的系统动作，不是模型发起的调用，所以不走审批；但严格限定在该会话工作区内。

    @staticmethod
    def _safe_target(workspace: str, rel: str) -> str:
        if not rel or os.path.isabs(rel) or rel.startswith(("/", "\\")):
            raise ValueError(f"unsafe path: {rel!r}")
        target = os.path.join(workspace, rel)
        if not policy.is_path_under(policy.canonical_path(target), policy.canonical_path(workspace)):
            raise ValueError(f"path escapes workspace: {rel!r}")
        return target

    async def _sync_manifest(self, args: Dict[str, Any], ctx: CallContext) -> List[str]:
        needed: List[str] = []
        for item in args.get("files") or []:
            rel = str((item or {}).get("path") or "")
            try:
                target = self._safe_target(ctx.workspace, rel)
            except ValueError:
                continue
            if not os.path.exists(target):  # 只补缺失的文件，不覆盖用户/Agent 在本地改过的
                needed.append(rel)
        return needed

    async def _sync_put(self, args: Dict[str, Any], ctx: CallContext) -> str:
        count = 0
        for item in args.get("files") or []:
            item = item or {}
            target = self._safe_target(ctx.workspace, str(item.get("path") or ""))
            data = base64.b64decode(item.get("b64") or "")
            await asyncio.to_thread(self._write_bytes, target, data, bool(item.get("append")))
            count += 1
        return f"ok:{count}"

    @staticmethod
    def _write_bytes(target: str, data: bytes, append: bool) -> None:
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        with open(target, "ab" if append else "wb") as fh:
            fh.write(data)
