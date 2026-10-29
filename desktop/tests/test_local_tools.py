import asyncio
import base64
import os
import sys
import unittest
from pathlib import Path

from desktop.tests import _support
from soulprout_desktop import approvals, local_tools, paths, policy

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


class Approver:
    """脚本化的审批：模拟界面侧订阅并自动给出决定。"""

    def __init__(self, broker: approvals.ApprovalBroker, decision: str = "allow"):
        self.broker = broker
        self.decision = decision
        self.requests = []
        self.queue = broker.subscribe()
        self.task = asyncio.create_task(self._loop())

    async def _loop(self):
        while True:
            event = await self.queue.get()
            if event["type"] == "request":
                self.requests.append(event["request"])
                self.broker.decide(event["request"]["id"], self.decision)

    def close(self):
        self.task.cancel()


class RunnerCase(_support.TempDirsCase):
    def make(self, preset="workspace-write", decision=None):
        self.broker = approvals.ApprovalBroker(timeout=5, subscriber_grace=0.2)
        self.preset = preset
        self.runner = local_tools.LocalToolRunner(lambda: policy.standing_for(self.preset), self.broker)
        self.approver = Approver(self.broker, decision) if decision else None
        self.addCleanup(lambda: self.approver and self.approver.close())

    async def call(self, tool, args, cid="conv-1", kind="task"):
        return await self.runner.execute(tool, args, conversation_id=cid, context={"kind": kind})

    def ws(self, cid="conv-1") -> Path:
        return paths.workspace_dir(cid)


class FileToolTests(RunnerCase):
    async def test_write_read_edit_roundtrip_matches_cloud_semantics(self):
        self.make()
        self.assertEqual(await self.call("write", {"file_path": "notes/a.txt", "content": "one\ntwo\n"}), "成功写入notes/a.txt")
        await self.call("write", {"file_path": "notes/a.txt", "content": "three\n"})  # write 是追加
        text = await self.call("read", {"file_path": "notes/a.txt"})
        self.assertIn("# notes/a.txt (lines 1-3 of 3)", text)
        self.assertIn("     1\u2502one", text)
        self.assertIn("     3\u2502three", text)
        self.assertEqual(await self.call("edit", {"file_path": "notes/a.txt", "past_text": "two", "replace_text": "2"}), "成功修改notes/a.txt")
        self.assertIn("2", (self.ws() / "notes" / "a.txt").read_text(encoding="utf-8"))
        self.assertIn("文本替换失败", await self.call("edit", {"file_path": "notes/a.txt", "past_text": "zzz", "replace_text": "y"}))

    async def test_read_paging(self):
        self.make()
        body = "".join(f"line{i}\n" for i in range(1, 11))
        await self.call("write", {"file_path": "p.txt", "content": body})
        text = await self.call("read", {"file_path": "p.txt", "offset": 3, "limit": 2})
        self.assertIn("(lines 3-4 of 10)", text)
        self.assertIn("call read again with offset=5", text)
        self.assertIn("offset(99) > total lines(10)", await self.call("read", {"file_path": "p.txt", "offset": 99}))

    async def test_read_missing_file_reports_error_like_cloud(self):
        self.make()
        self.assertIn("错误：阅读nope.txt失败", await self.call("read", {"file_path": "nope.txt"}))

    async def test_write_outside_workspace_is_denied_with_marker_and_hint(self):
        self.make()
        outside = str(Path(self.tmp) / "elsewhere.txt")
        result = await self.call("write", {"file_path": outside, "content": "x"})
        self.assertIn("[sandbox: file access denied under workspace-write mode]", result)
        self.assertIn("escalation available", result)
        self.assertFalse(os.path.exists(outside))

    async def test_escalation_approved_once_allows_that_call_only(self):
        self.make(decision="allow")
        outside = str(Path(self.tmp) / "elsewhere.txt")
        ok = await self.call("write", {
            "file_path": outside, "content": "hi", "sandbox_permissions": "danger-full-access", "justification": "user asked to save here",
        })
        self.assertEqual(ok, f"成功写入{outside}")
        self.assertEqual(Path(outside).read_text(encoding="utf-8"), "hi")
        self.assertEqual(self.approver.requests[0]["target_mode"], "danger-full-access")
        self.assertIn("user asked to save here", self.approver.requests[0]["reason"])
        # 下一次不带升级参数的同类调用仍然被拒：批准不会变成长期授权
        again = await self.call("write", {"file_path": outside + "2", "content": "x"})
        self.assertIn("[sandbox:", again)

    async def test_escalation_rejected_is_final(self):
        self.make(decision="reject")
        outside = str(Path(self.tmp) / "elsewhere.txt")
        result = await self.call("write", {
            "file_path": outside, "content": "hi", "sandbox_permissions": "danger-full-access", "justification": "because",
        })
        self.assertIn("the user rejected escalating this operation", result)
        self.assertFalse(os.path.exists(outside))

    async def test_escalation_without_any_ui_fails_closed(self):
        self.make()  # 没有任何审批界面订阅
        outside = str(Path(self.tmp) / "elsewhere.txt")
        result = await self.call("write", {
            "file_path": outside, "content": "hi", "sandbox_permissions": "danger-full-access", "justification": "because",
        })
        self.assertIn("no approval channel is available", result)
        self.assertFalse(os.path.exists(outside))

    async def test_non_widening_escalation_never_prompts(self):
        self.make(preset="danger-full-access", decision="allow")
        result = await self.call("write", {
            "file_path": "a.txt", "content": "x", "sandbox_permissions": "danger-full-access", "justification": "because",
        })
        self.assertIn("is not strictly wider", result)
        self.assertEqual(self.approver.requests, [])

    async def test_unpaired_escalation_args_are_rejected(self):
        self.make()
        result = await self.call("write", {"file_path": "a.txt", "content": "x", "sandbox_permissions": "danger-full-access"})
        self.assertIn("requires a justification", result)

    async def test_read_only_preset_blocks_writes_but_allows_reads(self):
        self.make(preset="read-only")
        (self.ws()).mkdir(parents=True)
        (self.ws() / "a.txt").write_text("hello", encoding="utf-8")
        self.assertIn("hello", await self.call("read", {"file_path": "a.txt"}))
        result = await self.call("write", {"file_path": "b.txt", "content": "x"})
        self.assertIn("[sandbox: file access denied under read-only mode]", result)

    async def test_task_read_outside_workspace_denied_but_soulprout_allowed(self):
        self.make()
        other = Path(self.tmp) / "docs" / "n.txt"
        other.parent.mkdir(parents=True)
        other.write_text("private note", encoding="utf-8")
        denied = await self.call("read", {"file_path": str(other)}, kind="task")
        self.assertIn("[sandbox:", denied)
        self.assertIn("private note", await self.call("read", {"file_path": str(other)}, kind="soulprout"))

    async def test_protected_state_dir_is_never_reachable(self):
        self.make(preset="danger-full-access")
        secret = paths.state_dir() / "gateway" / "settings.json"
        secret.parent.mkdir(parents=True)
        secret.write_text('{"agent_token":"SECRET"}', encoding="utf-8")
        result = await self.call("read", {"file_path": str(secret)}, kind="soulprout")
        self.assertNotIn("SECRET", result)
        self.assertIn("never allowed", result)
        wrote = await self.call("write", {"file_path": str(secret), "content": "x"}, kind="soulprout")
        self.assertIn("never allowed", wrote)

    async def test_invalid_conversation_id(self):
        self.make()
        self.assertIn("无效的会话 ID", await self.runner.execute("read", {"file_path": "a"}, conversation_id="../x"))

    async def test_read_picture(self):
        self.make()
        self.ws().mkdir(parents=True)
        (self.ws() / "p.png").write_bytes(PNG_1PX)
        (self.ws() / "t.png").write_text("not an image", encoding="utf-8")
        ok = await self.call("read_picture", {"file_name": "p.png"})
        self.assertTrue(ok["ok"])
        self.assertEqual(ok["media_type"], "image/png")
        self.assertEqual(base64.b64decode(ok["base64"]), PNG_1PX)
        bad = await self.call("read_picture", {"file_name": "t.png"})
        self.assertFalse(bad["ok"])
        missing = await self.call("read_picture", {"file_name": "zzz.png"})
        self.assertEqual(missing["message"], "路径不存在")

    async def test_unknown_tool(self):
        self.make()
        self.assertIn("不支持的工具", await self.call("rm_rf", {}))


class BashTests(RunnerCase):
    CMD = "echo hello-from-bash"

    async def test_confined_mode_needs_approval_for_every_command(self):
        self.make(decision="allow")
        result = await self.call("bash", {"command": self.CMD})
        self.assertIn("Command executed with return code: 0", result)
        self.assertIn("hello-from-bash", result)
        self.assertEqual(self.approver.requests[0]["tool"], "bash")
        self.assertIn(self.CMD, self.approver.requests[0]["detail"])

    async def test_rejected_command_does_not_run(self):
        self.make(decision="reject")
        marker = self.ws() / "ran.txt"
        cmd = f'echo x> "{marker}"'
        result = await self.call("bash", {"command": cmd})
        self.assertIn("the user rejected", result)
        self.assertFalse(marker.exists())

    async def test_no_ui_means_fail_closed(self):
        self.make()
        self.assertIn("no approval channel is available", await self.call("bash", {"command": self.CMD}))

    async def test_approval_never_with_confined_mode_refuses_unconfined_run(self):
        self.make()
        self.runner = local_tools.LocalToolRunner(lambda: policy.Standing("custom", "workspace-write", "never"), self.broker)
        result = await self.call("bash", {"command": self.CMD})
        self.assertIn("refusing to run unconfined", result)

    async def test_full_access_runs_without_prompt(self):
        self.make(preset="danger-full-access", decision="allow")
        result = await self.call("bash", {"command": self.CMD})
        self.assertIn("hello-from-bash", result)
        self.assertEqual(self.approver.requests, [])

    async def test_runs_in_workspace_and_reports_exit_code_and_stderr(self):
        self.make(preset="danger-full-access")
        cwd_cmd = "cd" if sys.platform == "win32" else "pwd"
        out = await self.call("bash", {"command": cwd_cmd})
        self.assertIn(str(self.ws()).lower(), out.lower().replace("\\\\", "\\"))
        failing = await self.call("bash", {"command": "exit 3"})
        self.assertIn("return code: 3", failing)

    async def test_environment_is_scrubbed(self):
        self.make(preset="danger-full-access")
        os.environ["SOULPROUT_DESKTOP_SECRET"] = "top-secret-value"
        os.environ["AGENT_TOKEN"] = "tok-123"
        self.addCleanup(lambda: [os.environ.pop(k, None) for k in ("SOULPROUT_DESKTOP_SECRET", "AGENT_TOKEN")])
        cmd = "set" if sys.platform == "win32" else "env"
        out = await self.call("bash", {"command": cmd})
        self.assertNotIn("top-secret-value", out)
        self.assertNotIn("tok-123", out)
        self.assertIn("SOULPROUT_SHELL=1", out)

    async def test_cancel_kills_the_process(self):
        self.make(preset="danger-full-access")
        marker = self.ws() / "late.txt"
        sleeper = "ping -n 4 127.0.0.1 >nul" if sys.platform == "win32" else "sleep 5"
        cmd = f'{sleeper} && echo done> "{marker}"'
        task = asyncio.create_task(self.call("bash", {"command": cmd}))
        await asyncio.sleep(0.8)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        await asyncio.sleep(4.5)
        self.assertFalse(marker.exists())

    async def test_bash_escalation_pairing_validated(self):
        self.make(decision="allow")
        result = await self.call("bash", {"command": self.CMD, "justification": "just because"})
        self.assertIn("only valid together with sandbox_permissions", result)

    async def test_tail_truncate(self):
        text = "a" * 10 + "b" * 10
        out = local_tools.tail_truncate(text, limit=10)
        self.assertTrue(out.endswith("b" * 10))
        self.assertIn("已截断", out)


class SyncTests(RunnerCase):
    async def test_manifest_and_put(self):
        self.make()
        files = [{"path": "skill/a.md", "size": 3}, {"path": "skill/b.md", "size": 3}]
        self.assertEqual(await self.call("sync_manifest", {"files": files}), ["skill/a.md", "skill/b.md"])
        put = await self.call("sync_put", {"files": [
            {"path": "skill/a.md", "b64": base64.b64encode(b"abc").decode(), "append": False},
            {"path": "skill/big.bin", "b64": base64.b64encode(b"12").decode(), "append": False},
            {"path": "skill/big.bin", "b64": base64.b64encode(b"34").decode(), "append": True},
        ]})
        self.assertEqual(put, "ok:3")
        self.assertEqual((self.ws() / "skill" / "big.bin").read_bytes(), b"1234")
        # 已存在的文件不再要求同步，也就不会覆盖本地改动
        (self.ws() / "skill" / "a.md").write_text("edited locally", encoding="utf-8")
        self.assertEqual(await self.call("sync_manifest", {"files": files}), ["skill/b.md"])

    async def test_paths_cannot_escape_workspace(self):
        self.make()
        with self.assertRaises(ValueError):
            await self.call("sync_put", {"files": [{"path": "../../evil.txt", "b64": "", "append": False}]})
        self.assertEqual(await self.call("sync_manifest", {"files": [{"path": "../x", "size": 1}, {"path": "/abs", "size": 1}]}), [])


if __name__ == "__main__":
    unittest.main()

