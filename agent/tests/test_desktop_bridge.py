"""桌面端接入层单测（不连数据库、不连网络）。

运行：python -m unittest agent.tests.test_desktop_bridge

覆盖：工具定义改写、本地/云端路由、离线报错、系统提示词里的设备状态、来源行、
请求校验、智能体文件同步，以及连接表（顶替、过期连接的下线不覆盖新连接）。
"""

import asyncio
import base64
import copy
import os
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest import mock

from agent.services import desktop_bridge as bridge
from agent.services.desktop_hub import DesktopConn, DesktopHub, DeviceOffline


class MemoryStore:
    """内存版设备表，接口与 MongoDeviceStore 一致。"""

    def __init__(self):
        self.rows = {}

    async def upsert(self, user_id, device_id, fields):
        row = self.rows.setdefault((user_id, device_id), {"user_id": user_id, "device_id": device_id})
        row.update(fields)

    async def get(self, user_id, device_id):
        return self.rows.get((user_id, device_id))

    async def latest(self, user_id):
        rows = [r for (u, _), r in self.rows.items() if u == user_id]
        return max(rows, key=lambda r: r.get("last_seen") or 0) if rows else None

    async def list(self, user_id):
        return [r for (u, _), r in self.rows.items() if u == user_id]


class FakeWS:
    """假的 WebSocket：记录发出的帧；可挂一个自动应答函数模拟桌面端。"""

    def __init__(self):
        self.sent = []
        self.closed = None
        self.responder = None

    async def send_json(self, data):
        self.sent.append(data)
        if self.responder is not None:
            self.responder(data)

    async def close(self, code=1000):
        self.closed = code


class FakeCollection:
    def __init__(self, docs):
        self.docs = docs

    async def find_one(self, query, projection=None):
        return self.docs.get(query["conversation_id"])


def make_config(docs, root):
    return SimpleNamespace(db_conversation=FakeCollection(docs), local_file_path=root)


TOOLS = [
    {"type": "function", "function": {"name": "read", "description": "read a file", "parameters": {"type": "object", "properties": {"file_path": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "bash", "description": "run a command", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "list_info", "description": "list stuff", "parameters": {"type": "object", "properties": {"category": {"type": "string", "enum": ["skill", "tool"]}}}}},
    {"type": "function", "function": {"name": "web_search", "description": "search", "parameters": {"type": "object", "properties": {}}}},
]


class BridgeTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.hub = DesktopHub(self.store)
        patcher = mock.patch.object(bridge, "hub", self.hub)
        patcher.start()
        self.addCleanup(patcher.stop)
        bridge.clear_conversation_cache()
        bridge._pending_sync.clear()
        self.addCleanup(bridge.clear_conversation_cache)
        self._saved_flag = os.environ.pop("DESKTOP_BRIDGE_ENABLED", None)
        self.addCleanup(self._restore_flag)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _restore_flag(self):
        if self._saved_flag is None:
            os.environ.pop("DESKTOP_BRIDGE_ENABLED", None)
        else:
            os.environ["DESKTOP_BRIDGE_ENABLED"] = self._saved_flag

    async def connect(self, user_id="u1", device_id="dk-1", name="My PC", channels=None, info=None):
        ws = FakeWS()
        conn = DesktopConn(ws=ws, user_id=user_id, device_id=device_id, device_name=name,
                           info=info or {"os": "Windows 11", "shell": "PowerShell"}, channels=channels or {})
        await self.hub.register(conn)
        return conn, ws

    @staticmethod
    def answer(hub, conn, result="done", ok=True):
        """让假桌面端对每个 tool_call 立刻回一个结果。"""
        def respond(frame):
            if frame.get("type") == "tool_call":
                hub.handle_result(conn, {"call_id": frame["call_id"], "ok": ok, "result": result, "error": result})
        conn.ws.responder = respond


class AdaptToolsTests(BridgeTestCase):
    async def test_cloud_conversations_get_the_original_list_object(self):
        config = make_config({"c1": {"user_id": "u1", "workspace": "cloud", "agent_use": "select-agent"}}, self.tmp.name)
        chat = SimpleNamespace(config=config, conversation_id="c1", user_id="u1", agent_use="select-agent")
        out = await bridge.adapt_tools(chat, TOOLS)
        self.assertIs(out, TOOLS)

    async def test_local_task_gets_escalation_params_but_no_target(self):
        await self.connect()
        before = copy.deepcopy(TOOLS)
        config = make_config({"c1": {"user_id": "u1", "workspace": "local", "device_id": "dk-1", "agent_use": "select-agent"}}, self.tmp.name)
        chat = SimpleNamespace(config=config, conversation_id="c1", user_id="u1", agent_use="select-agent")
        out = await bridge.adapt_tools(chat, TOOLS)
        by_name = {t["function"]["name"]: t["function"] for t in out}
        self.assertNotIn("target", by_name["read"]["parameters"]["properties"])
        self.assertIn("sandbox_permissions", by_name["bash"]["parameters"]["properties"])
        self.assertIn("Windows 11", by_name["bash"]["description"])
        self.assertNotIn("device", by_name["list_info"]["parameters"]["properties"]["category"]["enum"])
        self.assertEqual(TOOLS, before, "原工具定义不能被改动")

    async def test_soulprout_gets_target_and_device_category(self):
        await self.connect()
        config = make_config({"u1": {"user_id": "u1", "workspace": "cloud", "agent_use": "soulprout"}}, self.tmp.name)
        chat = SimpleNamespace(config=config, conversation_id="u1", user_id="u1", agent_use="soulprout")
        out = await bridge.adapt_tools(chat, TOOLS)
        by_name = {t["function"]["name"]: t["function"] for t in out}
        self.assertIn("target", by_name["read"]["parameters"]["properties"])
        self.assertIn("device", by_name["list_info"]["parameters"]["properties"]["category"]["enum"])
        self.assertEqual(by_name["web_search"], TOOLS[3]["function"])

    async def test_tool_definitions_do_not_depend_on_online_state(self):
        config = make_config({"u1": {"user_id": "u1", "workspace": "cloud", "agent_use": "soulprout"}}, self.tmp.name)
        chat = SimpleNamespace(config=config, conversation_id="u1", user_id="u1", agent_use="soulprout")
        conn, _ = await self.connect()
        online = await bridge.adapt_tools(chat, TOOLS)
        await self.hub.unregister(conn)
        offline = await bridge.adapt_tools(chat, TOOLS)
        self.assertEqual(online, offline, "上下线不能改变工具前缀，否则缓存会失效")

    async def test_kill_switch_returns_original(self):
        os.environ["DESKTOP_BRIDGE_ENABLED"] = "0"
        config = make_config({"u1": {"user_id": "u1", "workspace": "local", "agent_use": "soulprout"}}, self.tmp.name)
        chat = SimpleNamespace(config=config, conversation_id="u1", user_id="u1", agent_use="soulprout")
        self.assertIs(await bridge.adapt_tools(chat, TOOLS), TOOLS)


class RoutingTests(BridgeTestCase):
    async def test_cloud_conversation_is_not_routed_and_extra_args_are_dropped(self):
        config = make_config({"c1": {"user_id": "u1", "workspace": "cloud", "agent_use": "select-agent"}}, self.tmp.name)
        args = {"conversation_id": "c1", "file_path": "a.txt", "target": "local", "sandbox_permissions": "danger-full-access", "justification": "x"}
        self.assertIs(await bridge.route_local_tool(config, "read", args), bridge.NOT_ROUTED)
        self.assertEqual(args, {"conversation_id": "c1", "file_path": "a.txt"})

    async def test_local_task_goes_to_the_device(self):
        conn, ws = await self.connect()
        self.answer(self.hub, conn, "hello from pc")
        config = make_config({"c1": {"user_id": "u1", "workspace": "local", "device_id": "dk-1", "agent_use": "select-agent"}}, self.tmp.name)
        out = await bridge.route_local_tool(config, "read", {"conversation_id": "c1", "file_path": "a.txt"})
        self.assertEqual(out, "hello from pc")
        frame = ws.sent[0]
        self.assertEqual((frame["type"], frame["tool"], frame["conversation_id"]), ("tool_call", "read", "c1"))
        self.assertEqual(frame["context"], {"kind": "task"})

    async def test_soulprout_target_local_vs_cloud(self):
        conn, ws = await self.connect()
        self.answer(self.hub, conn, "local result")
        config = make_config({"u1": {"user_id": "u1", "workspace": "cloud", "agent_use": "soulprout"}}, self.tmp.name)
        out = await bridge.route_local_tool(config, "bash", {"conversation_id": "u1", "command": "dir", "target": "local"})
        self.assertEqual(out, "local result")
        self.assertEqual(ws.sent[0]["context"], {"kind": "soulprout"})
        ws.sent.clear()
        self.assertIs(await bridge.route_local_tool(config, "bash", {"conversation_id": "u1", "command": "ls", "target": "cloud"}), bridge.NOT_ROUTED)
        self.assertIs(await bridge.route_local_tool(config, "bash", {"conversation_id": "u1", "command": "ls"}), bridge.NOT_ROUTED)
        self.assertEqual(ws.sent, [])

    async def test_target_local_is_ignored_for_task_conversations_that_are_cloud(self):
        await self.connect()
        config = make_config({"c1": {"user_id": "u1", "workspace": "cloud", "agent_use": "select-agent"}}, self.tmp.name)
        self.assertIs(await bridge.route_local_tool(config, "read", {"conversation_id": "c1", "target": "local"}), bridge.NOT_ROUTED)

    async def test_offline_device_returns_an_explanatory_error(self):
        conn, _ = await self.connect(name="Office PC")
        await self.hub.unregister(conn)
        config = make_config({"c1": {"user_id": "u1", "workspace": "local", "device_id": "dk-1", "agent_use": "select-agent"}}, self.tmp.name)
        out = await bridge.route_local_tool(config, "bash", {"conversation_id": "c1", "command": "dir"})
        self.assertIsInstance(out, str)
        self.assertIn("未连接", out)
        self.assertIn("Office PC", out)

    async def test_offline_read_picture_keeps_its_dict_shape(self):
        conn, _ = await self.connect()
        await self.hub.unregister(conn)
        config = make_config({"c1": {"user_id": "u1", "workspace": "local", "device_id": "dk-1", "agent_use": "select-agent"}}, self.tmp.name)
        out = await bridge.route_local_tool(config, "read_picture", {"conversation_id": "c1", "file_path": "a.png"})
        self.assertEqual(out["ok"], False)
        self.assertIsNone(out["base64"])

    async def test_device_error_text_is_passed_through(self):
        conn, _ = await self.connect()
        self.answer(self.hub, conn, "错误：被权限设置拒绝", ok=False)
        config = make_config({"c1": {"user_id": "u1", "workspace": "local", "device_id": "dk-1", "agent_use": "select-agent"}}, self.tmp.name)
        out = await bridge.route_local_tool(config, "write", {"conversation_id": "c1", "file_path": "a", "content": "x"})
        self.assertEqual(out, "错误：被权限设置拒绝")

    async def test_kill_switch_disables_routing(self):
        os.environ["DESKTOP_BRIDGE_ENABLED"] = "0"
        config = make_config({"c1": {"user_id": "u1", "workspace": "local", "device_id": "dk-1"}}, self.tmp.name)
        args = {"conversation_id": "c1", "target": "local"}
        self.assertIs(await bridge.route_local_tool(config, "read", args), bridge.NOT_ROUTED)
        self.assertNotIn("target", args)


class PromptAndHeaderTests(BridgeTestCase):
    async def test_never_connected(self):
        text = await bridge.device_prompt_section("nobody")
        self.assertIn("never connected", text)

    async def test_online_lists_only_connected_channels(self):
        await self.connect(channels={"weixin": True, "feishu": False})
        text = await bridge.device_prompt_section("u1")
        self.assertIn("Desktop: online", text)
        self.assertIn("Connected channels: Wechat", text)
        self.assertNotIn("Feishu", text)

    async def test_offline_always_shown_without_channels(self):
        conn, _ = await self.connect(channels={"weixin": True})
        await self.hub.unregister(conn)
        text = await bridge.device_prompt_section("u1")
        self.assertIn("Desktop: offline", text)
        self.assertNotIn("Connected channels", text)

    async def test_source_header_only_in_soulprout_mode(self):
        soul = SimpleNamespace(agent_use="soulprout", client="desktop", source_channel=None, runtime_mode="main")
        task = SimpleNamespace(agent_use="select-agent", client="desktop", source_channel=None, runtime_mode="main")
        header = bridge.source_header(soul)
        self.assertRegex(header, r"^Source: Desktop \d{4}-\d{2}-\d{2} \d{2}:\d{2} (Mon|Tue|Wed|Thu|Fri|Sat|Sun)$")
        self.assertIsNone(bridge.source_header(task))
        wechat = SimpleNamespace(agent_use="soulprout", client=None, source_channel="weixin", runtime_mode="main")
        self.assertTrue(bridge.source_header(wechat).startswith("Source: Wechat "))
        mobile = SimpleNamespace(agent_use="soulprout", client="mobile", source_channel=None, runtime_mode="main")
        self.assertTrue(bridge.source_header(mobile).startswith("Source: Mobile "))
        sched = SimpleNamespace(agent_use="soulprout", client=None, source_channel=None, runtime_mode="scheduled")
        self.assertTrue(bridge.source_header(sched).startswith("Source: Scheduled "))

    def test_apply_source_header(self):
        self.assertEqual(bridge.apply_source_header("hi", "Source: Web x"), "Source: Web x\nhi")
        self.assertEqual(bridge.apply_source_header("hi", None), "hi")
        parts = [{"type": "image_url"}]
        self.assertIs(bridge.apply_source_header(parts, "Source: Web x"), parts)

    async def test_describe_devices(self):
        await self.connect(channels={"weixin": True})
        text = await bridge.describe_devices("u1")
        self.assertIn('"status": "online"', text)
        self.assertIn("Wechat", text)


class PrepareRequestTests(BridgeTestCase):
    async def test_web_requests_pass_through(self):
        req = SimpleNamespace(workspace=None, device_id=None, device_name=None, agent_use="select-agent")
        await bridge.prepare_request(req, "u1")
        self.assertIsNone(req.workspace)

    async def test_soulprout_never_local(self):
        await self.connect()
        req = SimpleNamespace(workspace="local", device_id="dk-1", device_name=None, agent_use="soulprout")
        await bridge.prepare_request(req, "u1")
        self.assertIsNone(req.workspace)
        self.assertIsNone(req.device_id)

    async def test_unknown_device_is_rejected(self):
        req = SimpleNamespace(workspace="local", device_id="dk-x", device_name=None, agent_use="select-agent")
        with self.assertRaises(bridge.LocalWorkspaceError):
            await bridge.prepare_request(req, "u1")

    async def test_known_device_fills_name(self):
        await self.connect(name="My PC")
        req = SimpleNamespace(workspace="local", device_id="dk-1", device_name=None, agent_use="select-agent")
        await bridge.prepare_request(req, "u1")
        self.assertEqual((req.workspace, req.device_id, req.device_name), ("local", "dk-1", "My PC"))

    async def test_other_users_device_is_rejected(self):
        await self.connect(user_id="u2", device_id="dk-1")
        req = SimpleNamespace(workspace="local", device_id="dk-1", device_name=None, agent_use="select-agent")
        with self.assertRaises(bridge.LocalWorkspaceError):
            await bridge.prepare_request(req, "u1")


class SyncTests(BridgeTestCase):
    def _make_workspace(self, cid, files):
        for rel, data in files.items():
            full = os.path.join(self.tmp.name, cid, *rel.split("/"))
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "wb") as fh:
                fh.write(data)

    def _desktop(self, conn, needed):
        calls = []

        def respond(frame):
            if frame.get("type") != "tool_call":
                return
            calls.append(frame)
            result = needed if frame["tool"] == "sync_manifest" else "ok"
            self.hub.handle_result(conn, {"call_id": frame["call_id"], "ok": True, "result": result})

        conn.ws.responder = respond
        return calls

    async def test_non_local_conversation_is_a_noop(self):
        config = make_config({"c1": {"user_id": "u1", "workspace": "cloud"}}, self.tmp.name)
        self.assertTrue(await bridge.sync_to_device(config, "c1"))

    async def test_only_needed_files_are_pushed_and_large_files_are_chunked(self):
        conn, _ = await self.connect()
        self._make_workspace("c1", {"card/a.txt": b"hello", "skills/s.md": b"skill"})
        calls = self._desktop(conn, ["card/a.txt"])
        config = make_config({"c1": {"user_id": "u1", "workspace": "local", "device_id": "dk-1"}}, self.tmp.name)
        with mock.patch.object(bridge, "SYNC_CHUNK_BYTES", 4):
            self.assertTrue(await bridge.sync_to_device(config, "c1"))
        manifest = [c for c in calls if c["tool"] == "sync_manifest"][0]
        self.assertEqual(sorted(f["path"] for f in manifest["arguments"]["files"]), ["card/a.txt", "skills/s.md"])
        pushed = [f for c in calls if c["tool"] == "sync_put" for f in c["arguments"]["files"]]
        self.assertEqual({f["path"] for f in pushed}, {"card/a.txt"})
        data = b"".join(base64.b64decode(f["b64"]) for f in pushed)
        self.assertEqual(data, b"hello")
        self.assertEqual([f["append"] for f in pushed], [False, True])  # 5 字节、块 4 字节 → 两段
        self.assertNotIn("c1", bridge._pending_sync)

    async def test_offline_device_is_remembered_and_retried_before_next_local_call(self):
        self._make_workspace("c1", {"a.txt": b"x"})
        config = make_config({"c1": {"user_id": "u1", "workspace": "local", "device_id": "dk-1"}}, self.tmp.name)
        self.assertFalse(await bridge.sync_to_device(config, "c1"))
        self.assertIn("c1", bridge._pending_sync)

        conn, _ = await self.connect()
        calls = self._desktop(conn, ["a.txt"])
        out = await bridge.route_local_tool(config, "read", {"conversation_id": "c1", "file_path": "a.txt"})
        self.assertEqual(out, "ok")
        tools = [c["tool"] for c in calls]
        self.assertEqual(tools[:2], ["sync_manifest", "sync_put"])
        self.assertEqual(tools[-1], "read")
        self.assertNotIn("c1", bridge._pending_sync)

    async def test_too_many_files_is_reported_not_raised(self):
        conn, _ = await self.connect()
        self._make_workspace("c1", {"a.txt": b"x", "b.txt": b"y"})
        self._desktop(conn, [])
        config = make_config({"c1": {"user_id": "u1", "workspace": "local", "device_id": "dk-1"}}, self.tmp.name)
        with mock.patch.object(bridge, "SYNC_MAX_FILES", 1):
            self.assertFalse(await bridge.sync_to_device(config, "c1"))


class HubTests(BridgeTestCase):
    async def test_reconnect_replaces_old_connection_and_fails_its_pending_calls(self):
        old, old_ws = await self.connect()
        fut = asyncio.get_running_loop().create_future()
        old.pending["x"] = fut
        new, _ = await self.connect()
        self.assertIs(self.hub.get_conn("u1", "dk-1"), new)
        self.assertEqual(old_ws.closed, 1012)
        with self.assertRaises(DeviceOffline):
            fut.result()

    async def test_stale_unregister_does_not_mark_the_new_connection_offline(self):
        old, _ = await self.connect(channels={"weixin": True})
        new, _ = await self.connect(channels={"weixin": True})
        await self.hub.unregister(old)
        self.assertIs(self.hub.get_conn("u1", "dk-1"), new)
        self.assertEqual(self.store.rows[("u1", "dk-1")]["channels"], {"weixin": True})

    async def test_unregister_marks_offline_and_snapshot_reports_it(self):
        conn, _ = await self.connect(channels={"weixin": True})
        await self.hub.unregister(conn)
        snap = await self.hub.snapshot("u1")
        self.assertEqual((snap["known"], snap["online"], snap["channels"]), (True, False, {}))

    async def test_results_for_unknown_call_ids_are_ignored(self):
        conn, _ = await self.connect()
        self.hub.handle_result(conn, {"call_id": "nope", "ok": True, "result": "x"})  # 不抛异常即可

    async def test_result_cannot_be_delivered_through_another_connection(self):
        a, a_ws = await self.connect(device_id="dk-a")
        b, _ = await self.connect(device_id="dk-b")
        task = asyncio.create_task(self.hub.call("u1", "read", {}, device_id="dk-a", timeout=0.3))
        await asyncio.sleep(0.05)
        call_id = a_ws.sent[0]["call_id"]
        self.hub.handle_result(b, {"call_id": call_id, "ok": True, "result": "spoofed"})
        with self.assertRaises(Exception):
            await task
        self.assertEqual(a_ws.sent[-1]["type"], "cancel")

    async def test_touch_updates_channels_and_last_seen(self):
        conn, _ = await self.connect()
        before = conn.last_seen
        await asyncio.sleep(0.01)
        await self.hub.touch(conn, {"weixin": True})
        self.assertGreater(conn.last_seen, before)
        self.assertEqual(self.store.rows[("u1", "dk-1")]["channels"], {"weixin": True})


if __name__ == "__main__":
    unittest.main()
