import os
import sys
import unittest
from pathlib import Path

from desktop.tests import _support
from soulprout_desktop import paths, policy


class EscalationVocabularyTests(unittest.TestCase):
    def test_pairing_is_required(self):
        with self.assertRaises(policy.EscalationError):
            policy.validate_escalation_args("danger-full-access", None)
        with self.assertRaises(policy.EscalationError):
            policy.validate_escalation_args(None, "because")
        with self.assertRaises(policy.EscalationError):
            policy.validate_escalation_args("danger-full-access", "   ")
        with self.assertRaises(policy.EscalationError):
            policy.validate_escalation_args("read-only", "nope")  # read-only 是地板，不是升级目标
        policy.validate_escalation_args(None, None)
        policy.validate_escalation_args("danger-full-access", "need to read ~/notes")

    def test_only_strictly_wider_modes(self):
        policy.check_strictly_wider("workspace-write", "danger-full-access")
        policy.check_strictly_wider("read-only", "workspace-write")
        with self.assertRaises(policy.EscalationError):
            policy.check_strictly_wider("workspace-write", "workspace-write")
        with self.assertRaises(policy.EscalationError):
            policy.check_strictly_wider("danger-full-access", "danger-full-access")
        with self.assertRaises(policy.EscalationError):
            policy.check_strictly_wider("workspace-write", "read-only")

    def test_markers_match_harness_wording(self):
        self.assertEqual(
            policy.sandbox_denial_marker("workspace-write"),
            "[sandbox: file access denied under workspace-write mode]",
        )
        self.assertIn("retry this exact operation once", policy.escalation_hint_marker("operation"))

    def test_presets(self):
        ww = policy.standing_for("workspace-write")
        self.assertEqual((ww.mode, ww.approval), ("workspace-write", "ask"))
        full = policy.standing_for("danger-full-access")
        self.assertEqual((full.mode, full.approval), ("danger-full-access", "never"))
        self.assertEqual(policy.standing_for("garbage").preset, policy.DEFAULT_PRESET)


class PathPolicyTests(_support.TempDirsCase):
    def setUp(self):
        super().setUp()
        self.workspace = str(paths.workspace_dir("conv-1"))
        os.makedirs(self.workspace, exist_ok=True)
        self.outside = str(Path(self.tmp) / "outside" / "a.txt")
        os.makedirs(os.path.dirname(self.outside), exist_ok=True)

    def test_workspace_write_allows_workspace_only(self):
        inside = os.path.join(self.workspace, "sub", "a.txt")
        self.assertTrue(policy.check_write(inside, mode="workspace-write", workspace=self.workspace).allowed)
        denied = policy.check_write(self.outside, mode="workspace-write", workspace=self.workspace)
        self.assertFalse(denied.allowed)
        self.assertFalse(denied.hard)

    def test_read_only_allows_no_writes(self):
        inside = os.path.join(self.workspace, "a.txt")
        self.assertFalse(policy.check_write(inside, mode="read-only", workspace=self.workspace).allowed)

    def test_full_access_allows_everything_but_protected(self):
        self.assertTrue(policy.check_write(self.outside, mode="danger-full-access", workspace=self.workspace).allowed)
        secret = str(paths.state_dir() / "gateway" / "settings.json")
        for mode in policy.SANDBOX_MODES:
            self.assertTrue(policy.check_write(secret, mode=mode, workspace=self.workspace).hard)
            self.assertTrue(policy.check_read(secret, mode=mode, kind="soulprout", workspace=self.workspace).hard)

    def test_dotdot_cannot_escape(self):
        sneaky = os.path.join(self.workspace, "..", "..", "outside", "a.txt")
        self.assertFalse(policy.check_write(sneaky, mode="workspace-write", workspace=self.workspace).allowed)

    @unittest.skipIf(sys.platform == "win32", "symlink creation needs privileges on Windows")
    def test_symlink_escape_is_resolved(self):
        link = os.path.join(self.workspace, "link")
        os.symlink(os.path.dirname(self.outside), link)
        target = os.path.join(link, "a.txt")
        self.assertFalse(policy.check_write(target, mode="workspace-write", workspace=self.workspace).allowed)

    def test_task_reads_are_limited_to_workspace_soulprout_reads_are_not(self):
        self.assertFalse(policy.check_read(self.outside, mode="workspace-write", kind="task", workspace=self.workspace).allowed)
        self.assertTrue(policy.check_read(self.outside, mode="workspace-write", kind="soulprout", workspace=self.workspace).allowed)
        inside = os.path.join(self.workspace, "a.txt")
        self.assertTrue(policy.check_read(inside, mode="read-only", kind="task", workspace=self.workspace).allowed)

    def test_credential_dirs_need_full_access(self):
        ssh_key = str(Path.home() / ".ssh" / "id_rsa")
        self.assertFalse(policy.check_read(ssh_key, mode="workspace-write", kind="soulprout", workspace=self.workspace).allowed)
        self.assertTrue(policy.check_read(ssh_key, mode="danger-full-access", kind="soulprout", workspace=self.workspace).allowed)

    @unittest.skipUnless(sys.platform == "win32", "case aliasing is a Windows/macOS filesystem property")
    def test_case_alias_still_counts_as_inside(self):
        inside = os.path.join(self.workspace.upper(), "a.txt")
        self.assertTrue(policy.check_write(inside, mode="workspace-write", workspace=self.workspace).allowed)

    def test_denial_text(self):
        d = policy.check_write(self.outside, mode="workspace-write", workspace=self.workspace)
        text = policy.denial_text(d, mode="workspace-write", subject="operation")
        self.assertIn("[sandbox: file access denied under workspace-write mode]", text)
        self.assertIn("escalation available", text)
        full = policy.denial_text(
            policy.Decision(False, reason="x"), mode="danger-full-access", subject="operation"
        )
        self.assertNotIn("escalation available", full)  # 已经是最宽模式，没有可升级的方向


if __name__ == "__main__":
    unittest.main()
