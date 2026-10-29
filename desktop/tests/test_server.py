import asyncio
import json
import os
import unittest
from urllib.parse import quote

import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestServer

from desktop.tests import _support
from soulprout_desktop import approvals, auth_store, paths, settings
from soulprout_desktop.cloud_client import CloudClient
from soulprout_desktop.gateway_host import find_free_port
from soulprout_desktop.server import COOKIE_NAME, AppContext, DesktopServer

SECRET = "test-secret-123"


class FakeUpstream:
    """假的云端 HTTP 服务：记录收到的请求，按需返回内容。"""

    def __init__(self):
        self.conversations = []
        self.chats = []
        self.cloud_files = ["agent-card.md"]
        self.deleted = []
        self.logout_called = False
        self.seen_auth = []

    def app(self) -> web.Application:
        app = web.Application()
        r = app.router
        r.add_get("/conversations", self.list_conversations)
        r.add_post("/message/chat", self.chat)
        r.add_get("/files", self.files)
        r.add_get("/user/me", self.me)
        r.add_post("/user/email/login", self.login)
        r.add_post("/user/logout", self.logout)
        r.add_delete("/conversations/{cid}", self.delete)
        r.add_get("/boom", self.boom)
        return app

    async def list_conversations(self, request):
        self.seen_auth.append(request.headers.get("Authorization"))
        return web.json_response(self.conversations)

    async def chat(self, request):
        reader = await request.multipart()
        payload, files = {}, []
        async for part in reader:
            if part.name == "chat_request":
                payload = json.loads((await part.read()).decode())
            elif part.name == "files":
                files.append((part.filename, bytes(await part.read())))
        self.chats.append({"payload": payload, "files": files, "auth": request.headers.get("Authorization"), "cookie": request.headers.get("Cookie")})
        resp = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        await resp.prepare(request)
        await resp.write(b'data: {"type":"user_message","content":"hi"}\n\n')
        await asyncio.sleep(0.05)
        await resp.write(b'data: {"type":"end"}\n\n')
        return resp

    async def files(self, request):
        return web.json_response({"files": self.cloud_files, "conversation_id": request.query.get("conversation_id")})

    async def me(self, request):
        auth = request.headers.get("Authorization")
        return web.json_response({"success": bool(auth), "auth": auth})

    async def login(self, request):
        body = await request.json()
        resp = web.json_response({"success": True, "user_id": "u1", "email": body["email"], "token": "jwt-abc"})
        resp.set_cookie("token", "jwt-abc", httponly=True)
        return resp

    async def logout(self, request):
        self.logout_called = True
        return web.json_response({"message": "logged out"})

    async def delete(self, request):
        self.deleted.append(request.match_info["cid"])
        return web.json_response({"success": True})

    async def boom(self, request):
        return web.json_response({"detail": "nope"}, status=418)


class ServerCase(_support.TempDirsCase):
    async def asyncSetUp(self):
        self.upstream = FakeUpstream()
        self.upstream_server = TestServer(self.upstream.app())
        await self.upstream_server.start_server()
        self._saved_url = os.environ.get("AGENT_URL")
        os.environ["AGENT_URL"] = f"http://127.0.0.1:{self.upstream_server.port}"
        auth_store.redirect_gateway_storage()
        auth_store.save_login(token="tok-1", user_id="u1", email="a@b.c")

        self.broker = approvals.ApprovalBroker(timeout=5, subscriber_grace=0.1)
        self.cloud = CloudClient(
            executor=None, get_token=lambda: "", get_agent_url=lambda: "", get_channels=lambda: {},
        )
        port = find_free_port()
        self.ctx = AppContext(
            secret=SECRET, port=port, broker=self.broker, cloud=self.cloud,
            gateway_info=lambda: {"enabled": False, "url": None, "channels": {"weixin": True}, "error": ""},
            ui_dir=paths.data_root() / "ui",
        )
        (paths.data_root() / "ui" / "assets").mkdir(parents=True)
        (paths.data_root() / "ui" / "index.html").write_text("<html>desktop-ui</html>", encoding="utf-8")
        (paths.data_root() / "ui" / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
        self.desktop = DesktopServer(self.ctx)
        self.server = TestServer(self.desktop.build_app(), port=port)
        await self.server.start_server()
        self.base = f"http://127.0.0.1:{port}"
        jar = aiohttp.CookieJar(unsafe=True)
        self.client = aiohttp.ClientSession(cookie_jar=jar)
        async with self.client.get(f"{self.base}/__boot?s={SECRET}", allow_redirects=False) as resp:
            assert resp.status == 302, resp.status

    async def asyncTearDown(self):
        await self.client.close()
        await self.server.close()
        await self.upstream_server.close()
        if self._saved_url is None:
            os.environ.pop("AGENT_URL", None)
        else:
            os.environ["AGENT_URL"] = self._saved_url

    def chat_form(self, payload, files=()):
        # 网页端始终发 multipart（即使没有附件），这里保持一致
        form = aiohttp.FormData(default_to_multipart=True)
        form.add_field("chat_request", json.dumps(payload))
        for name, data in files:
            form.add_field("files", data, filename=name, content_type="text/plain")
        return form


class SecurityTests(ServerCase):
    async def test_requests_without_the_boot_cookie_are_rejected(self):
        async with aiohttp.ClientSession() as bare:
            async with bare.get(f"{self.base}/api/user/me") as resp:
                self.assertEqual(resp.status, 401)
            async with bare.post(f"{self.base}/__desktop/policy", json={"preset": "danger-full-access"}) as resp:
                self.assertEqual(resp.status, 401)
        self.assertEqual(settings.preset(), "workspace-write")

    async def test_wrong_boot_secret(self):
        async with aiohttp.ClientSession() as bare:
            async with bare.get(f"{self.base}/__boot?s=wrong", allow_redirects=False) as resp:
                self.assertEqual(resp.status, 401)

    async def test_foreign_host_and_origin_are_rejected(self):
        async with self.client.get(f"{self.base}/__desktop/state", headers={"Host": "evil.example.com"}) as resp:
            self.assertEqual(resp.status, 403)
        async with self.client.get(f"{self.base}/__desktop/state", headers={"Origin": "https://evil.example.com"}) as resp:
            self.assertEqual(resp.status, 403)
        async with self.client.get(f"{self.base}/__desktop/state", headers={"Origin": self.base}) as resp:
            self.assertEqual(resp.status, 200)

    async def test_boot_cookie_flags(self):
        async with aiohttp.ClientSession() as bare:
            async with bare.get(f"{self.base}/__boot?s={SECRET}", allow_redirects=False) as resp:
                cookie = resp.headers["Set-Cookie"]
        self.assertIn(COOKIE_NAME, cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)


class StaticAndStateTests(ServerCase):
    async def test_static_and_spa_fallback(self):
        async with self.client.get(f"{self.base}/") as resp:
            self.assertIn("desktop-ui", await resp.text())
        async with self.client.get(f"{self.base}/assets/app.js") as resp:
            self.assertIn("javascript", resp.headers["Content-Type"])
        async with self.client.get(f"{self.base}/chat") as resp:  # 前端路由 → 回退到 index.html
            self.assertIn("desktop-ui", await resp.text())
        async with self.client.get(f"{self.base}/..%2f..%2fsettings.json") as resp:
            self.assertIn("desktop-ui", await resp.text())

    async def test_state_and_policy(self):
        async with self.client.get(f"{self.base}/__desktop/state") as resp:
            state = await resp.json()
        self.assertEqual(state["policy"]["preset"], "workspace-write")
        self.assertEqual(state["device"]["id"], settings.device_id())
        self.assertTrue(state["cloud"]["logged_in"])
        self.assertEqual(state["gateway"]["channels"], {"weixin": True})
        self.assertEqual({p["name"] for p in state["policy"]["presets"]}, {"read-only", "workspace-write", "danger-full-access"})
        async with self.client.post(f"{self.base}/__desktop/policy", json={"preset": "danger-full-access"}) as resp:
            self.assertTrue((await resp.json())["success"])
        self.assertEqual(settings.preset(), "danger-full-access")
        async with self.client.post(f"{self.base}/__desktop/policy", json={"preset": "bogus"}) as resp:
            self.assertEqual(resp.status, 400)

    async def test_approval_stream_and_decision(self):
        async with self.client.get(f"{self.base}/__desktop/approvals/stream") as resp:
            await asyncio.wait_for(resp.content.readline(), 5)  # ": ok"
            waiter = asyncio.create_task(self.broker.request(
                tool="bash", title="执行命令", detail="echo hi", reason="r", mode="workspace-write",
                target_mode="danger-full-access", conversation_id="c1",
            ))
            line = b""
            while not line.startswith(b"data:"):
                line = await asyncio.wait_for(resp.content.readline(), 5)
            event = json.loads(line[5:].decode())
            self.assertEqual(event["request"]["detail"], "echo hi")
            async with self.client.post(f"{self.base}/__desktop/approvals/{event['request']['id']}", json={"decision": "allow"}) as dec:
                self.assertTrue((await dec.json())["success"])
            self.assertEqual(await asyncio.wait_for(waiter, 5), approvals.ALLOWED_ONCE)


class ProxyTests(ServerCase):
    async def test_generic_proxy_injects_credentials_and_passes_status(self):
        async with self.client.get(f"{self.base}/api/user/me") as resp:
            body = await resp.json()
        self.assertEqual(body["auth"], "Bearer tok-1")
        async with self.client.get(f"{self.base}/api/boom") as resp:
            self.assertEqual(resp.status, 418)

    async def test_client_supplied_credentials_are_replaced(self):
        async with self.client.get(f"{self.base}/api/user/me", headers={"Authorization": "Bearer attacker"}) as resp:
            self.assertEqual((await resp.json())["auth"], "Bearer tok-1")

    async def test_login_stores_token_and_hides_it_from_the_ui(self):
        auth_store.clear_login()
        async with self.client.post(f"{self.base}/api/user/email/login", json={"email": "x@y.z", "code": "123456"}) as resp:
            body = await resp.json()
            self.assertNotIn("Set-Cookie", resp.headers)
        self.assertTrue(body["success"])
        self.assertNotIn("token", body)
        self.assertEqual(auth_store.get_token(), "jwt-abc")
        self.assertEqual(auth_store.get_user_id(), "u1")

    async def test_logout_clears_local_credentials(self):
        async with self.client.post(f"{self.base}/api/user/logout") as resp:
            self.assertEqual(resp.status, 200)
        self.assertTrue(self.upstream.logout_called)
        self.assertEqual(auth_store.get_token(), "")


class ChatTests(ServerCase):
    async def test_new_task_conversation_becomes_local_and_files_stay_on_this_computer(self):
        payload = {"message": "hello", "conversation_id": "task-1", "agent_use": "select-agent"}
        async with self.client.post(f"{self.base}/api/message/chat", data=self.chat_form(payload, [("note.txt", b"local bytes")])) as resp:
            text = await resp.text()
        self.assertIn("user_message", text)
        self.assertIn('"end"', text)
        sent = self.upstream.chats[0]
        self.assertEqual(sent["payload"]["workspace"], "local")
        self.assertEqual(sent["payload"]["device_id"], settings.device_id())
        self.assertEqual(sent["payload"]["client"], "desktop")
        self.assertEqual(sent["payload"]["file_name_list"], ["note.txt"])
        self.assertEqual(sent["files"], [])  # 附件没有上传云端
        self.assertEqual(sent["auth"], "Bearer tok-1")
        self.assertEqual((paths.workspace_dir("task-1") / "note.txt").read_bytes(), b"local bytes")
        self.assertIn("task-1", settings.local_conversations())

    async def test_missing_conversation_id_gets_one_assigned(self):
        async with self.client.post(f"{self.base}/api/message/chat", data=self.chat_form({"message": "hi", "conversation_id": ""})) as resp:
            await resp.read()
        sent = self.upstream.chats[0]["payload"]
        self.assertTrue(sent["conversation_id"])
        self.assertEqual(sent["workspace"], "local")

    async def test_existing_cloud_conversation_is_left_alone(self):
        self.upstream.conversations = [{"conversation_id": "web-1", "workspace": "cloud"}]
        payload = {"message": "hello", "conversation_id": "web-1", "agent_use": "select-agent"}
        async with self.client.post(f"{self.base}/api/message/chat", data=self.chat_form(payload, [("a.txt", b"cloud bytes")])) as resp:
            await resp.read()
        sent = self.upstream.chats[0]
        self.assertNotIn("workspace", sent["payload"])
        self.assertEqual(sent["files"], [("a.txt", b"cloud bytes")])  # 云端会话的附件照旧上传
        self.assertFalse((paths.workspaces_root() / "web-1").exists())

    async def test_existing_local_conversation_stays_local(self):
        self.upstream.conversations = [{"conversation_id": "t-9", "workspace": "local"}]
        payload = {"message": "again", "conversation_id": "t-9", "agent_use": "select-agent"}
        async with self.client.post(f"{self.base}/api/message/chat", data=self.chat_form(payload)) as resp:
            await resp.read()
        self.assertEqual(self.upstream.chats[0]["payload"]["workspace"], "local")

    async def test_soulprout_mode_is_never_tagged_local_and_keeps_uploads_in_cloud(self):
        payload = {"message": "hi", "conversation_id": "u1", "agent_use": "soulprout"}
        async with self.client.post(f"{self.base}/api/message/chat", data=self.chat_form(payload, [("s.txt", b"x")])) as resp:
            await resp.read()
        sent = self.upstream.chats[0]
        self.assertNotIn("workspace", sent["payload"])
        self.assertEqual(sent["payload"]["client"], "desktop")
        self.assertEqual(sent["files"], [("s.txt", b"x")])

    async def test_upload_names_cannot_escape_the_workspace(self):
        payload = {"message": "hello", "conversation_id": "task-2", "agent_use": "select-agent"}
        # aiohttp 客户端会把文件名里的 \ / 做百分号编码；浏览器是原样发送，所以这里手工拼 multipart 原始报文
        boundary = "XBOUNDARYX"
        body = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="chat_request"\r\n\r\n{json.dumps(payload)}\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="../../evil.txt"\r\n'
            f'Content-Type: text/plain\r\n\r\nx\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="../ok.txt"\r\n'
            f'Content-Type: text/plain\r\n\r\ny\r\n--{boundary}--\r\n'
        ).encode()
        async with self.client.post(
            f"{self.base}/api/message/chat", data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        ) as resp:
            await resp.read()
        self.assertEqual(self.upstream.chats[0]["payload"]["file_name_list"], ["evil.txt", "ok.txt"])
        self.assertFalse((paths.workspaces_root() / "evil.txt").exists())
        self.assertTrue((paths.workspace_dir("task-2") / "evil.txt").exists())

    async def test_invalid_conversation_id_is_never_treated_as_local(self):
        payload = {"message": "hello", "conversation_id": "../escape", "agent_use": "select-agent"}
        async with self.client.post(f"{self.base}/api/message/chat", data=self.chat_form(payload, [("a.txt", b"x")])) as resp:
            await resp.read()
        sent = self.upstream.chats[0]
        self.assertNotIn("workspace", sent["payload"])
        self.assertFalse((paths.workspaces_root().parent / "escape").exists())

    async def test_chinese_upload_filename_is_not_percent_encoded_to_cloud(self):
        # 灵芽模式附件走云端；中文文件名不能变成 %E4%B8%B4....txt
        payload = {"message": "hi", "conversation_id": "u1", "agent_use": "soulprout"}
        async with self.client.post(
            f"{self.base}/api/message/chat",
            data=self.chat_form(payload, [("临时笔记.txt", "中文内容".encode("utf-8"))]),
        ) as resp:
            await resp.read()
        sent = self.upstream.chats[0]
        self.assertEqual(sent["files"][0][0], "临时笔记.txt")
        self.assertNotIn("%", sent["files"][0][0])
        self.assertEqual(sent["files"][0][1], "中文内容".encode("utf-8"))


class LocalFileEndpointTests(ServerCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.upstream.conversations = [{"conversation_id": "loc-1", "workspace": "local"}, {"conversation_id": "web-1", "workspace": "cloud"}]
        workspace = paths.workspace_dir("loc-1")
        (workspace / "sub").mkdir(parents=True)
        (workspace / "sub" / "a.md").write_text("# hello", encoding="utf-8")
        (workspace / "b.html").write_text("<p>x</p>", encoding="utf-8")
        (workspace / "中文.txt").write_text("你好世界", encoding="utf-8")

    async def test_list_download_preview_for_local_conversation(self):
        async with self.client.get(f"{self.base}/api/files", params={"conversation_id": "loc-1"}) as resp:
            self.assertEqual((await resp.json())["files"], ["b.html", "sub/a.md", "中文.txt"])
        async with self.client.get(f"{self.base}/api/download/sub/a.md", params={"conversation_id": "loc-1"}) as resp:
            self.assertEqual(await resp.text(), "# hello")
            self.assertIn("attachment", resp.headers["Content-Disposition"])
        async with self.client.get(f"{self.base}/api/file_content/b.html", params={"conversation_id": "loc-1"}) as resp:
            self.assertIn("text/html", resp.headers["Content-Type"])
            self.assertEqual(await resp.text(), "<p>x</p>")

    async def test_chinese_text_preview_is_utf8(self):
        async with self.client.get(
            f"{self.base}/api/file_content/{quote('中文.txt')}",
            params={"conversation_id": "loc-1"},
        ) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("charset=utf-8", resp.headers["Content-Type"])
            self.assertEqual(await resp.text(), "你好世界")

    async def test_cloud_conversation_files_still_come_from_the_cloud(self):
        async with self.client.get(f"{self.base}/api/files", params={"conversation_id": "web-1"}) as resp:
            body = await resp.json()
        self.assertEqual(body["files"], ["agent-card.md"])

    async def test_path_traversal_is_refused(self):
        async with self.client.get(f"{self.base}/api/file_content/..%2f..%2fstate%2fsettings.json", params={"conversation_id": "loc-1"}) as resp:
            self.assertIn(resp.status, (400, 404))
        secret = paths.state_dir() / "settings.json"
        secret.write_text("{}", encoding="utf-8")
        async with self.client.get(f"{self.base}/api/download/..%2f..%2f..%2fstate%2fsettings.json", params={"conversation_id": "loc-1"}) as resp:
            self.assertEqual(resp.status, 404)

    async def test_save_and_export(self):
        form = aiohttp.FormData()
        form.add_field("file_content", "# edited")
        form.add_field("conversation_id", "loc-1")
        async with self.client.post(f"{self.base}/api/save_file/sub/a.md", data=form) as resp:
            self.assertTrue((await resp.json())["message"])
        self.assertEqual((paths.workspace_dir("loc-1") / "sub" / "a.md").read_text(encoding="utf-8"), "# edited")
        async with self.client.get(f"{self.base}/api/export/b.html", params={"conversation_id": "loc-1", "format": "pdf"}) as resp:
            self.assertEqual(resp.status, 501)

    async def test_deleting_a_local_conversation_removes_its_workspace(self):
        async with self.client.delete(f"{self.base}/api/conversations/loc-1") as resp:
            self.assertEqual(resp.status, 200)
        self.assertEqual(self.upstream.deleted, ["loc-1"])
        self.assertFalse(paths.workspace_dir("loc-1").exists())

    async def test_deleting_a_cloud_conversation_touches_nothing_local(self):
        keep = paths.workspace_dir("web-1")
        keep.mkdir(parents=True)
        async with self.client.delete(f"{self.base}/api/conversations/web-1") as resp:
            self.assertEqual(resp.status, 200)
        self.assertTrue(keep.exists())


if __name__ == "__main__":
    unittest.main()
