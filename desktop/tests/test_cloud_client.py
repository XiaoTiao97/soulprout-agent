"""桌面端 <-> 云端 ``/desktop/ws`` 协议的端到端测试：用一个假云端实现协议，真实的 CloudClient 与 LocalToolRunner 在另一头跑。"""

import asyncio
import json
import sys
import unittest

import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestServer

from desktop.tests import _support
from soulprout_desktop import approvals, cloud_client, local_tools, paths, policy, settings


class FakeCloud:
    def __init__(self, close_1008: bool = False):
        self.close_1008 = close_1008
        self.hello = None
        self.frames = []
        self.ws = None
        self.results = {}
        self.connected = asyncio.Event()
        self.tokens = []

    async def handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.tokens.append(request.query.get("token"))
        if self.close_1008:
            await ws.close(code=1008)
            return ws
        self.ws = ws
        first = await ws.receive_json()
        self.hello = first
        await ws.send_json({"type": "ready", "heartbeat_timeout": 75})
        self.connected.set()
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                self.frames.append(data)
                if data.get("type") == "tool_result":
                    self.results[data["call_id"]] = data
        return ws

    async def call(self, tool, arguments, call_id, conversation_id="conv-1", context=None):
        await self.ws.send_json({
            "type": "tool_call", "call_id": call_id, "tool": tool, "arguments": arguments,
            "conversation_id": conversation_id, "context": context or {"kind": "task"},
        })

    async def wait_result(self, call_id, timeout=10):
        deadline = asyncio.get_running_loop().time() + timeout
        while call_id not in self.results:
            if asyncio.get_running_loop().time() > deadline:
                raise AssertionError(f"no result for {call_id}")
            await asyncio.sleep(0.05)
        return self.results[call_id]


class CloudClientTests(_support.TempDirsCase):
    async def start(self, cloud: FakeCloud, preset="danger-full-access", token="tok"):
        app = web.Application()
        app.router.add_get("/desktop/ws", cloud.handler)
        server = TestServer(app)
        await server.start_server()
        self.addAsyncCleanup(server.close)

        broker = approvals.ApprovalBroker(timeout=5, subscriber_grace=0.1)
        runner = local_tools.LocalToolRunner(lambda: policy.standing_for(preset), broker)
        client = cloud_client.CloudClient(
            executor=runner.execute,
            get_token=lambda: token,
            get_agent_url=lambda: f"http://127.0.0.1:{server.port}",
            get_channels=lambda: {"weixin": True, "feishu": False},
            on_cancel=broker.cancel_call,
            ws_url_builder=lambda base: [f"ws://127.0.0.1:{server.port}/desktop/ws"],
        )
        stop = asyncio.Event()
        task = asyncio.create_task(client.run(stop))

        async def shutdown():
            stop.set()
            client.poke()
            await client.disconnect()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        self.addAsyncCleanup(shutdown)
        return client, broker

    async def test_hello_ready_and_tool_roundtrip(self):
        cloud = FakeCloud()
        client, _ = await self.start(cloud)
        await asyncio.wait_for(cloud.connected.wait(), 10)
        hello = cloud.hello
        self.assertEqual(hello["type"], "hello")
        self.assertEqual(hello["device_id"], settings.device_id())
        self.assertEqual(hello["channels"], {"weixin": True, "feishu": False})
        self.assertIn(hello["info"]["os_family"], ("windows", "darwin", "linux"))
        self.assertEqual(cloud.tokens, ["tok"])
        for _ in range(50):
            if client.state == "online":
                break
            await asyncio.sleep(0.05)
        self.assertEqual(client.state, "online")

        await cloud.call("write", {"file_path": "a.txt", "content": "hello", "conversation_id": "conv-1"}, "c1")
        result = await cloud.wait_result("c1")
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"], "成功写入a.txt")
        self.assertEqual((paths.workspace_dir("conv-1") / "a.txt").read_text(encoding="utf-8"), "hello")

        await cloud.call("read", {"file_path": "a.txt", "conversation_id": "conv-1"}, "c2")
        self.assertIn("hello", (await cloud.wait_result("c2"))["result"])

    async def test_parallel_calls_are_correlated_by_call_id(self):
        cloud = FakeCloud()
        await self.start(cloud)
        await asyncio.wait_for(cloud.connected.wait(), 10)
        for i in range(5):
            await cloud.call("write", {"file_path": f"f{i}.txt", "content": str(i)}, f"p{i}")
        for i in range(5):
            self.assertEqual((await cloud.wait_result(f"p{i}"))["result"], f"成功写入f{i}.txt")

    async def test_cancel_stops_a_running_bash(self):
        cloud = FakeCloud()
        await self.start(cloud)
        await asyncio.wait_for(cloud.connected.wait(), 10)
        marker = paths.workspace_dir("conv-1") / "late.txt"
        sleeper = "ping -n 4 127.0.0.1 >nul" if sys.platform == "win32" else "sleep 3"
        await cloud.call("bash", {"command": f'{sleeper} && echo done> "{marker}"'}, "b1")
        await asyncio.sleep(0.8)
        await cloud.ws.send_json({"type": "cancel", "call_id": "b1"})
        await asyncio.sleep(4.5)
        self.assertFalse(marker.exists())
        self.assertNotIn("b1", cloud.results)  # 云端已不再等，桌面端不回帧

    async def test_confined_bash_waits_for_user_approval_over_the_wire(self):
        cloud = FakeCloud()
        _client, broker = await self.start(cloud, preset="workspace-write")
        await asyncio.wait_for(cloud.connected.wait(), 10)
        queue = broker.subscribe()
        await cloud.call("bash", {"command": "echo approved-run"}, "b2")
        event = await asyncio.wait_for(queue.get(), 5)
        self.assertEqual(event["request"]["tool"], "bash")
        self.assertNotIn("b2", cloud.results)  # 用户还没点头，命令没有跑
        self.assertTrue(broker.decide(event["request"]["id"], "allow"))
        result = await cloud.wait_result("b2")
        self.assertIn("approved-run", result["result"])

    async def test_stop_on_cloud_side_cancels_the_pending_approval(self):
        cloud = FakeCloud()
        _client, broker = await self.start(cloud, preset="workspace-write")
        await asyncio.wait_for(cloud.connected.wait(), 10)
        queue = broker.subscribe()
        await cloud.call("bash", {"command": "echo never"}, "b3")
        await asyncio.wait_for(queue.get(), 5)
        await cloud.ws.send_json({"type": "cancel", "call_id": "b3"})
        resolved = await asyncio.wait_for(queue.get(), 5)
        self.assertEqual(resolved["type"], "resolved")
        self.assertEqual(broker.pending(), [])

    async def test_auth_failure_is_reported_and_not_hammered(self):
        cloud = FakeCloud(close_1008=True)
        client, _ = await self.start(cloud)
        for _ in range(60):
            if client.state == "auth_failed":
                break
            await asyncio.sleep(0.05)
        self.assertEqual(client.state, "auth_failed")
        await asyncio.sleep(0.5)
        self.assertEqual(len(cloud.tokens), 1)

    async def test_no_token_stays_idle_until_poked(self):
        cloud = FakeCloud()
        holder = {"token": ""}
        app = web.Application()
        app.router.add_get("/desktop/ws", cloud.handler)
        server = TestServer(app)
        await server.start_server()
        self.addAsyncCleanup(server.close)
        broker = approvals.ApprovalBroker()
        runner = local_tools.LocalToolRunner(lambda: policy.standing_for("workspace-write"), broker)
        client = cloud_client.CloudClient(
            executor=runner.execute,
            get_token=lambda: holder["token"],
            get_agent_url=lambda: "",
            get_channels=lambda: {},
            ws_url_builder=lambda base: [f"ws://127.0.0.1:{server.port}/desktop/ws"],
        )
        stop = asyncio.Event()
        task = asyncio.create_task(client.run(stop))

        async def shutdown():
            stop.set()
            client.poke()
            await client.disconnect()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        self.addAsyncCleanup(shutdown)
        await asyncio.sleep(0.3)
        self.assertEqual(client.state, "no_login")
        self.assertIsNone(cloud.hello)
        holder["token"] = "new-token"
        client.poke()
        await asyncio.wait_for(cloud.connected.wait(), 10)
        self.assertEqual(cloud.tokens, ["new-token"])


if __name__ == "__main__":
    unittest.main()
