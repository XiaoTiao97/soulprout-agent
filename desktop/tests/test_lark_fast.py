"""飞书 SDK 快速入口（gateway/platforms/_lark_fast.py）的回归测试。

在子进程里跑：入口会改写 ``sys.modules``，不能污染其它测试。
"""

import importlib.util
import json
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _run(code: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=180,
    )


@unittest.skipIf(importlib.util.find_spec("lark_oapi") is None, "lark-oapi 未安装")
class LarkFastTests(unittest.TestCase):
    def test_does_not_import_every_business_domain(self):
        r = _run(
            """
            import sys
            from gateway.platforms._lark_fast import load_lark
            lark = load_lark()
            from lark_oapi.api.im.v1 import CreateMessageRequest
            from lark_oapi.ws import Client
            n = len([m for m in sys.modules if m.startswith("lark_oapi")])
            heavy = [m for m in sys.modules if m.startswith(("lark_oapi.api.corehr", "lark_oapi.api.hire"))]
            print(n, len(heavy), getattr(lark, "__lark_light__", False))
            """
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        n, heavy, light = r.stdout.split()
        self.assertEqual(light, "True")
        self.assertEqual(heavy, "0")
        self.assertLess(int(n), 1500)  # 完整 SDK 约 9000

    def test_client_and_event_dispatch_behave_like_the_sdk(self):
        r = _run(
            """
            import json
            from gateway.platforms._lark_fast import load_lark
            lark = load_lark()
            from lark_oapi.event.dispatcher_handler import EventDispatcherHandler

            c = lark.Client.builder().app_id("a").app_secret("s").log_level(lark.LogLevel.WARNING).build()
            assert hasattr(c.im.v1.message, "create")

            got = []
            h = EventDispatcherHandler.builder("", "").register_p2_im_message_receive_v1(got.append).build()
            evt = {"schema": "2.0",
                   "header": {"event_id": "e", "event_type": "im.message.receive_v1", "token": "",
                              "app_id": "a", "tenant_key": "t", "create_time": "1"},
                   "event": {"sender": {"sender_id": {"open_id": "ou_x"}, "sender_type": "user"},
                             "message": {"message_id": "om_1", "chat_id": "oc_1", "chat_type": "p2p",
                                         "message_type": "text", "content": json.dumps({"text": "hi"})}}}
            h._do_without_validation(json.dumps(evt).encode())
            m = got[0].event.message
            print(got[0].event.sender.sender_id.open_id, m.message_id, json.loads(m.content)["text"])

            evt["header"]["event_type"] = "foo.bar_v1"
            try:
                h._do_without_validation(json.dumps(evt).encode())
            except Exception as e:
                print(type(e).__name__)
            """
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = r.stdout.strip().splitlines()
        self.assertEqual(lines[-2], "ou_x om_1 hi")
        self.assertEqual(lines[-1], "EventException")

    def test_domain_must_be_https(self):
        r = _run(
            """
            from gateway.platforms._lark_fast import load_lark
            lark = load_lark()
            for bad in ("http://evil.example.com", "https://a.com/path", "https://u@a.com"):
                try:
                    lark.Client.builder().domain(bad)
                    print("accepted", bad)
                except ValueError:
                    pass
            lark.Client.builder().domain("https://open.feishu.cn")
            print("ok")
            """
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip().splitlines()[-1], "ok", r.stdout)

    def test_falls_back_to_full_sdk_when_fast_path_breaks(self):
        r = _run(
            """
            import sys
            from gateway.platforms import _lark_fast
            # 导入 gateway.platforms 时飞书适配器已经走过一次快速入口，这里重置后模拟 SDK 内部结构变化
            _lark_fast._light = None
            _lark_fast._purge()
            def boom(): raise RuntimeError("sdk layout changed")
            _lark_fast._install_light_dispatcher = boom
            lark = _lark_fast.load_lark()
            # 退回完整导入：拿到真正的包（不是空壳/轻量对象），业务域模块也确实被加载了
            print(getattr(lark, "__lark_fast_stub__", False), getattr(lark, "__lark_light__", False),
                  hasattr(lark, "Client"), "lark_oapi.api.corehr" in sys.modules)
            """
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip().splitlines()[-1], "False False True True")


if __name__ == "__main__":
    unittest.main()
