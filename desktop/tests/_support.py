"""测试公共设施：让 sidecar 包可导入，并把数据/状态目录指到临时目录。"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_here = Path(__file__).resolve().parent
_sidecar = _here.parent / "sidecar"
_repo_root = _here.parent.parent
for p in (str(_sidecar), str(_repo_root)):
    if p not in sys.path:
        sys.path.insert(0, p)


class TempDirsCase(unittest.IsolatedAsyncioTestCase):
    """每个用例独立的 data / state 目录。"""

    def setUp(self) -> None:
        # posix 上 /tmp 永远是可写根，测试目录得放在它之外，否则「工作区之外」的用例没有意义
        self.tmp = tempfile.mkdtemp(prefix="soulprout-desktop-test-", dir=str(Path.home()) if os.name == "posix" else None)
        self._saved = {k: os.environ.get(k) for k in ("SOULPROUT_DATA_DIR", "SOULPROUT_STATE_DIR")}
        os.environ["SOULPROUT_DATA_DIR"] = str(Path(self.tmp) / "data")
        os.environ["SOULPROUT_STATE_DIR"] = str(Path(self.tmp) / "state")
        (Path(self.tmp) / "state").mkdir(parents=True)
        # 把「系统临时目录」指到测试目录内的一个子目录：否则测试用的临时目录本身就落在可写根里，
        # 「工作区之外」的用例就测不出东西来。
        self._saved_tempdir = tempfile.tempdir
        systmp = Path(self.tmp) / "systmp"
        systmp.mkdir()
        tempfile.tempdir = str(systmp)
        super().setUp()

    def tearDown(self) -> None:
        tempfile.tempdir = self._saved_tempdir
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(self.tmp, ignore_errors=True)
        super().tearDown()
