import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "openai_local_bridge.py"


def load_module():
    env = {
        "OLB_UPSTREAM_BASE": "https://example.com/v1",
        "OLB_UPSTREAM_KEY": "test-key",
        "OLB_LISTEN_HOST": "127.0.0.1",
        "OLB_LISTEN_PORT": "443",
    }
    spec = importlib.util.spec_from_file_location("openai_local_bridge_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)

    with mock.patch.dict(os.environ, env, clear=False):
        assert spec.loader is not None
        spec.loader.exec_module(module)

    return module


class StartupTests(unittest.TestCase):
    def test_create_server_permission_error_has_actionable_message(self):
        module = load_module()

        with mock.patch.object(
            module,
            "ThreadingHTTPServer",
            side_effect=PermissionError(13, "Permission denied"),
        ):
            with self.assertRaises(module.StartupError) as ctx:
                module.create_server()

        self.assertEqual(
            str(ctx.exception),
            "cannot bind https listener on 127.0.0.1:443; "
            "choose OLB_LISTEN_PORT>=1024 or run with elevated privileges",
        )

    def test_parse_args_accepts_pid_file(self):
        module = load_module()

        with mock.patch.object(module.sys, "argv", ["openai_local_bridge", "--cert", "cert.pem", "--key", "key.pem", "--pid-file", "/tmp/bridge.pid"]):
            args = module.parse_args()

        self.assertEqual(args.pid_file, "/tmp/bridge.pid")

    def test_pid_file_guard_writes_and_removes_pid_file(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as tmp:
            pid_file = Path(tmp) / "bridge.pid"

            with module.pid_file_guard(str(pid_file)):
                self.assertEqual(pid_file.read_text(encoding="utf-8").strip(), str(os.getpid()))

            self.assertFalse(pid_file.exists())

    def test_pid_file_guard_rejects_running_instance(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as tmp:
            pid_file = Path(tmp) / "bridge.pid"
            pid_file.write_text("789\n", encoding="utf-8")

            with mock.patch.object(module, "process_exists", return_value=True):
                with self.assertRaises(module.StartupError) as ctx:
                    with module.pid_file_guard(str(pid_file)):
                        pass

        self.assertEqual(str(ctx.exception), "bridge already running (pid 789)")


if __name__ == "__main__":
    unittest.main()
