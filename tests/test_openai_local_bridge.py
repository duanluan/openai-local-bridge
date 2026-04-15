import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "openai_local_bridge.py"


def load_module(language: str = "en"):
    env = {
        "OLB_UPSTREAM_BASE": "https://example.com/v1",
        "OLB_UPSTREAM_KEY": "test-key",
        "OLB_LISTEN_HOST": "127.0.0.1",
        "OLB_LISTEN_PORT": "443",
        "OLB_LANG": language,
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

        args = module.parse_args(["--cert", "cert.pem", "--key", "key.pem", "--pid-file", "/tmp/bridge.pid"])

        self.assertEqual(args.pid_file, "/tmp/bridge.pid")

    def test_main_accepts_explicit_argv(self):
        module = load_module()
        server = mock.Mock()
        server.socket = mock.Mock()

        with (
            mock.patch.object(module, "create_server", return_value=server),
            mock.patch.object(module.ssl, "SSLContext") as ssl_context,
            mock.patch.object(module, "pid_file_guard"),
            mock.patch.object(module, "install_signal_handlers", return_value={}),
            mock.patch.object(module, "restore_signal_handlers"),
        ):
            ssl_context.return_value.wrap_socket.return_value = server.socket
            exit_code = module.main(["--cert", "cert.pem", "--key", "key.pem"])

        self.assertEqual(exit_code, 0)
        server.serve_forever.assert_called_once()
        server.server_close.assert_called_once()

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

    def test_create_server_permission_error_uses_chinese_when_requested(self):
        module = load_module("zh")

        with mock.patch.dict(os.environ, {"OLB_LANG": "zh"}, clear=False):
            with mock.patch.object(
                module,
                "ThreadingHTTPServer",
                side_effect=PermissionError(13, "Permission denied"),
            ):
                with self.assertRaises(module.StartupError) as ctx:
                    module.create_server()

        self.assertEqual(
            str(ctx.exception),
            "无法绑定 127.0.0.1:443 的 HTTPS 监听；请把 OLB_LISTEN_PORT 设为 >=1024，或使用提权方式运行",
        )


if __name__ == "__main__":
    unittest.main()
