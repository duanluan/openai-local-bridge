import subprocess
import tempfile
from pathlib import Path
import unittest
from unittest import mock

import olb_cli


def make_paths(root: Path) -> olb_cli.AppPaths:
    cert_dir = root / "ca"
    return olb_cli.AppPaths(
        root=root,
        config_file=root / "config.json",
        cert_dir=cert_dir,
        root_ca_key=cert_dir / "openai-local-bridge-root-ca.key",
        root_ca_cert=cert_dir / "openai-local-bridge-root-ca.crt",
        root_ca_srl=cert_dir / "openai-local-bridge-root-ca.srl",
        nss_db_dir=root / "nssdb",
    )


class PromptForConfigTests(unittest.TestCase):
    def test_prompt_for_config_uses_fixed_reasoning_effort_choices(self):
        with (
            mock.patch.object(olb_cli.Prompt, "ask", side_effect=["https://example.com/v1", "test-key", "xhigh"]) as ask,
            mock.patch.object(olb_cli, "validate_upstream"),
        ):
            config = olb_cli.prompt_for_config({})

        self.assertEqual(config["reasoning_effort"], "xhigh")
        self.assertEqual(ask.call_args_list[0].args[0], "Base URL（默认示例值仅作格式参考）")
        self.assertEqual(
            ask.call_args_list[2].kwargs["choices"],
            ["minimal", "low", "medium", "high", "xhigh"],
        )
        self.assertEqual(ask.call_args_list[2].kwargs["default"], "medium")

    def test_prompt_for_config_marks_saved_values_clearly(self):
        existing = {
            "upstream_base": "https://saved.example/v1",
            "upstream_key": "secret-key",
            "reasoning_effort": "high",
        }

        with (
            mock.patch.object(olb_cli.Prompt, "ask", side_effect=["https://saved.example/v1", "", "high"]) as ask,
            mock.patch.object(olb_cli, "validate_upstream"),
        ):
            config = olb_cli.prompt_for_config(existing)

        self.assertEqual(config["upstream_key"], "secret-key")
        self.assertEqual(ask.call_args_list[0].args[0], "Base URL（回车保留当前已保存值）")
        self.assertIn("留空保留当前已保存值", ask.call_args_list[1].args[0])
        self.assertEqual(ask.call_args_list[2].args[0], "推理强度（回车保留当前已保存值）")
        self.assertEqual(ask.call_args_list[2].kwargs["default"], "high")

    def test_reasoning_effort_choices_preserve_existing_custom_value(self):
        self.assertEqual(
            olb_cli.reasoning_effort_choices("custom"),
            ["minimal", "low", "medium", "high", "xhigh", "custom"],
        )


class ValidateUpstreamTests(unittest.TestCase):
    def test_validate_upstream_accepts_normal_https_url(self):
        config = {
            "upstream_base": "https://example.com/v1",
            "upstream_model": "real-model",
            "model_map": {},
        }

        with mock.patch.object(olb_cli, "get_target_host", return_value="api.openai.com"):
            olb_cli.validate_upstream(config)


class VersionTests(unittest.TestCase):
    def test_app_version_reads_package_metadata(self):
        with mock.patch.object(olb_cli, "package_version", return_value="1.2.3"):
            self.assertEqual(olb_cli.app_version(), "1.2.3")

    def test_app_version_falls_back_when_metadata_missing(self):
        with mock.patch.object(olb_cli, "package_version", side_effect=olb_cli.PackageNotFoundError):
            self.assertEqual(olb_cli.app_version(), "0.1.0")

    def test_main_supports_version_subcommand(self):
        with (
            mock.patch.object(olb_cli, "get_paths", return_value=make_paths(Path("/tmp/olb-test"))),
            mock.patch.object(olb_cli, "app_version", return_value="1.2.3"),
            mock.patch.object(olb_cli.console, "print") as console_print,
            mock.patch.object(olb_cli.sys, "argv", ["olb", "version"]),
        ):
            exit_code = olb_cli.main()

        self.assertEqual(exit_code, 0)
        console_print.assert_called_once_with("1.2.3")

    def test_main_rejects_dash_dash_version(self):
        with (
            mock.patch.object(olb_cli, "get_paths", return_value=make_paths(Path("/tmp/olb-test"))),
            mock.patch.object(olb_cli.sys, "argv", ["olb", "--version"]),
            self.assertRaises(SystemExit) as exc,
        ):
            olb_cli.main()

        self.assertEqual(exc.exception.code, 2)

    def test_main_rejects_all_subcommand(self):
        with (
            mock.patch.object(olb_cli, "get_paths", return_value=make_paths(Path("/tmp/olb-test"))),
            mock.patch.object(olb_cli.sys, "argv", ["olb", "all"]),
            self.assertRaises(SystemExit) as exc,
        ):
            olb_cli.main()

        self.assertEqual(exc.exception.code, 2)


class DefaultCommandTests(unittest.TestCase):
    def test_default_command_uses_init_when_config_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(Path(tmp))
            self.assertEqual(olb_cli.default_command(paths), "init")

    def test_default_command_uses_status_when_config_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(Path(tmp))
            paths.root.mkdir(parents=True, exist_ok=True)
            paths.config_file.write_text("{}\n", encoding="utf-8")
            self.assertEqual(olb_cli.default_command(paths), "status")


class RunStartTests(unittest.TestCase):
    def test_run_start_prints_init_notice_when_config_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(Path(tmp))
            config = {"upstream_base": "https://example.com/v1", "upstream_key": "test-key", "reasoning_effort": "medium"}

            with (
                mock.patch.object(olb_cli.console, "print") as console_print,
                mock.patch.object(olb_cli, "ensure_config", return_value=config) as ensure_config,
                mock.patch.object(olb_cli, "run_enable") as run_enable,
                mock.patch.object(olb_cli, "start_proxy", return_value=0) as start_proxy,
            ):
                exit_code = olb_cli.run_start(paths)

        self.assertEqual(exit_code, 0)
        console_print.assert_called_once_with("未检测到配置，先进入初始化。初始化完成后会继续执行 enable 和 start。")
        ensure_config.assert_called_once_with(paths, interactive=True)
        run_enable.assert_called_once_with(paths)
        start_proxy.assert_called_once_with(paths, config, background=False)

    def test_run_start_skips_init_notice_when_config_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(Path(tmp))
            paths.root.mkdir(parents=True, exist_ok=True)
            paths.config_file.write_text("{}\n", encoding="utf-8")
            config = {"upstream_base": "https://example.com/v1", "upstream_key": "test-key", "reasoning_effort": "medium"}

            with (
                mock.patch.object(olb_cli.console, "print") as console_print,
                mock.patch.object(olb_cli, "ensure_config", return_value=config),
                mock.patch.object(olb_cli, "run_enable"),
                mock.patch.object(olb_cli, "start_proxy", return_value=0),
            ):
                exit_code = olb_cli.run_start(paths)

        self.assertEqual(exit_code, 0)
        console_print.assert_not_called()

    def test_main_start_runs_init_enable_and_proxy_flow(self):
        paths = make_paths(Path("/tmp/olb-test"))
        with (
            mock.patch.object(olb_cli, "get_paths", return_value=paths),
            mock.patch.object(olb_cli, "run_start", return_value=0) as run_start,
            mock.patch.object(olb_cli.sys, "argv", ["olb", "start"]),
        ):
            exit_code = olb_cli.main()

        self.assertEqual(exit_code, 0)
        run_start.assert_called_once_with(paths, background=False)

    def test_run_start_supports_background_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(Path(tmp))
            config = {"upstream_base": "https://example.com/v1", "upstream_key": "test-key", "reasoning_effort": "medium"}

            with (
                mock.patch.object(olb_cli, "ensure_config", return_value=config),
                mock.patch.object(olb_cli, "run_enable"),
                mock.patch.object(olb_cli, "start_proxy", return_value=0) as start_proxy,
            ):
                exit_code = olb_cli.run_start(paths, background=True)

        self.assertEqual(exit_code, 0)
        start_proxy.assert_called_once_with(paths, config, background=True)

    def test_main_start_background_passes_flag(self):
        paths = make_paths(Path("/tmp/olb-test"))
        with (
            mock.patch.object(olb_cli, "get_paths", return_value=paths),
            mock.patch.object(olb_cli, "run_start", return_value=0) as run_start,
            mock.patch.object(olb_cli.sys, "argv", ["olb", "start", "--background"]),
        ):
            exit_code = olb_cli.main()

        self.assertEqual(exit_code, 0)
        run_start.assert_called_once_with(paths, background=True)


class StartProxyTests(unittest.TestCase):
    def test_build_proxy_command_uses_sudo_for_privileged_port(self):
        env = {
            "OLB_LISTEN_PORT": "443",
            "OLB_LISTEN_HOST": "127.0.0.1",
            "OLB_TARGET_HOST": "api.openai.com",
            "OLB_UPSTREAM_BASE": "https://example.com/v1",
            "OLB_UPSTREAM_KEY": "test-key",
            "OLB_REASONING_EFFORT": "medium",
        }

        with (
            mock.patch.object(olb_cli, "detect_os", return_value="linux"),
            mock.patch.object(olb_cli.os, "geteuid", return_value=1000, create=True),
            mock.patch.object(olb_cli, "require_command", return_value="/usr/bin/sudo"),
        ):
            command = olb_cli.build_proxy_command(Path("/tmp/test.crt"), Path("/tmp/test.key"), env)

        self.assertEqual(command[0], "sudo")
        self.assertTrue(command[1].startswith("--preserve-env="))
        preserved = set(command[1].split("=", 1)[1].split(","))
        self.assertEqual(
            preserved,
            {
                "OLB_LISTEN_HOST",
                "OLB_LISTEN_PORT",
                "OLB_REASONING_EFFORT",
                "OLB_TARGET_HOST",
                "OLB_UPSTREAM_BASE",
                "OLB_UPSTREAM_KEY",
            },
        )

    def test_build_proxy_command_skips_sudo_for_unprivileged_port(self):
        env = {
            "OLB_LISTEN_PORT": "8443",
            "OLB_UPSTREAM_BASE": "https://example.com/v1",
            "OLB_UPSTREAM_KEY": "test-key",
        }

        with (
            mock.patch.object(olb_cli, "detect_os", return_value="linux"),
            mock.patch.object(olb_cli.os, "geteuid", return_value=1000, create=True),
        ):
            command = olb_cli.build_proxy_command(Path("/tmp/test.crt"), Path("/tmp/test.key"), env)

        self.assertEqual(command[:3], [olb_cli.sys.executable, "-m", "openai_local_bridge"])

    def test_build_proxy_command_appends_pid_file(self):
        env = {
            "OLB_LISTEN_PORT": "8443",
            "OLB_UPSTREAM_BASE": "https://example.com/v1",
            "OLB_UPSTREAM_KEY": "test-key",
        }

        with (
            mock.patch.object(olb_cli, "detect_os", return_value="linux"),
            mock.patch.object(olb_cli.os, "geteuid", return_value=1000, create=True),
        ):
            command = olb_cli.build_proxy_command(
                Path("/tmp/test.crt"),
                Path("/tmp/test.key"),
                env,
                pid_file=Path("/tmp/bridge.pid"),
            )

        self.assertEqual(command[-2:], ["--pid-file", "/tmp/bridge.pid"])

    def test_start_proxy_rejects_second_running_instance(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(Path(tmp))
            config = {"upstream_base": "https://example.com/v1", "upstream_key": "test-key", "reasoning_effort": "medium"}

            with mock.patch.object(olb_cli, "running_bridge_pid", return_value=321):
                with self.assertRaises(olb_cli.CliError) as exc:
                    olb_cli.start_proxy(paths, config)

        self.assertEqual(str(exc.exception), "bridge already running (pid 321)")

    def test_start_proxy_background_uses_popen(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(Path(tmp))
            config = {"upstream_base": "https://example.com/v1", "upstream_key": "test-key", "reasoning_effort": "medium"}
            process = mock.Mock(spec=subprocess.Popen)
            process.poll.return_value = None

            with (
                mock.patch.object(olb_cli, "running_bridge_pid", return_value=None),
                mock.patch.object(olb_cli, "validate_upstream"),
                mock.patch.object(olb_cli, "ensure_domain_cert", return_value=(Path("/tmp/test.crt"), Path("/tmp/test.key"))),
                mock.patch.object(olb_cli, "env_from_config", return_value={"OLB_LISTEN_HOST": "127.0.0.1", "OLB_LISTEN_PORT": "8443"}),
                mock.patch.object(olb_cli, "build_proxy_command", return_value=["python", "-m", "openai_local_bridge"]) as build_proxy_command,
                mock.patch.object(olb_cli, "prepare_background_launch"),
                mock.patch.object(olb_cli.subprocess, "Popen", return_value=process) as popen,
                mock.patch.object(olb_cli, "wait_for_background_start", return_value=0) as wait_for_background_start,
            ):
                exit_code = olb_cli.start_proxy(paths, config, background=True)

        self.assertEqual(exit_code, 0)
        build_proxy_command.assert_called_once_with(
            Path("/tmp/test.crt"),
            Path("/tmp/test.key"),
            {"OLB_LISTEN_HOST": "127.0.0.1", "OLB_LISTEN_PORT": "8443"},
            pid_file=paths.root / "bridge.pid",
        )
        popen.assert_called_once()
        wait_for_background_start.assert_called_once_with(paths, process, paths.root / "bridge.log")


class NssTests(unittest.TestCase):
    def test_install_nss_suppresses_expected_delete_error_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(Path(tmp))
            paths.nss_db_dir.mkdir(parents=True)
            (paths.nss_db_dir / "cert9.db").write_text("", encoding="utf-8")

            with (
                mock.patch.object(olb_cli, "detect_os", return_value="linux"),
                mock.patch.object(olb_cli, "require_command"),
                mock.patch.object(olb_cli, "ensure_root_ca"),
                mock.patch.object(olb_cli.console, "print"),
                mock.patch.object(olb_cli, "run_command") as run_command,
            ):
                run_command.side_effect = [
                    subprocess.CompletedProcess(["certutil"], 255, "", "missing"),
                    subprocess.CompletedProcess(["certutil"], 0, "", ""),
                ]
                olb_cli.install_nss(paths)

        self.assertEqual(run_command.call_args_list[0].kwargs["check"], False)
        self.assertTrue(run_command.call_args_list[0].kwargs["capture_output"])

    def test_status_data_checks_nss_silently(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(Path(tmp))
            paths.nss_db_dir.mkdir(parents=True)
            paths.cert_dir.mkdir(parents=True)
            paths.root_ca_cert.write_text("dummy", encoding="utf-8")
            (paths.nss_db_dir / "cert9.db").write_text("", encoding="utf-8")

            with (
                mock.patch.object(olb_cli, "detect_os", return_value="linux"),
                mock.patch.object(olb_cli, "detect_ca_strategy", return_value="trust"),
                mock.patch.object(olb_cli, "listener_state", return_value="stopped"),
                mock.patch.object(olb_cli.shutil, "which", side_effect=lambda name: "/usr/bin/certutil" if name == "certutil" else None),
                mock.patch.object(olb_cli, "run_command", return_value=subprocess.CompletedProcess(["certutil"], 255, "", "missing")) as run_command,
            ):
                data = olb_cli.status_data(paths)

        self.assertEqual(data["nss"], "missing")
        self.assertTrue(run_command.call_args.kwargs["capture_output"])


class RequireCommandTests(unittest.TestCase):
    def test_require_command_shows_windows_openssl_hint(self):
        with (
            mock.patch.object(olb_cli.shutil, "which", return_value=None),
            mock.patch.object(olb_cli, "detect_os", return_value="windows"),
        ):
            with self.assertRaises(olb_cli.CliError) as exc:
                olb_cli.require_command("openssl")

        self.assertIn("Windows 请先安装 OpenSSL", str(exc.exception))


class StopProxyTests(unittest.TestCase):
    def test_running_bridge_pid_removes_stale_pid_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(Path(tmp))
            paths.root.mkdir(parents=True, exist_ok=True)
            pid_file = paths.root / "bridge.pid"
            pid_file.write_text("123\n", encoding="utf-8")

            with mock.patch.object(olb_cli, "process_exists", return_value=False):
                pid = olb_cli.running_bridge_pid(paths)

            stale_removed = not pid_file.exists()

        self.assertIsNone(pid)
        self.assertTrue(stale_removed)

    def test_stop_proxy_returns_zero_when_not_running(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(Path(tmp))

            with mock.patch.object(olb_cli.console, "print") as console_print:
                exit_code = olb_cli.stop_proxy(paths)

        self.assertEqual(exit_code, 0)
        console_print.assert_called_once_with("bridge 未运行")

    def test_stop_proxy_terminates_running_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(Path(tmp))
            paths.root.mkdir(parents=True, exist_ok=True)
            (paths.root / "bridge.pid").write_text("456\n", encoding="utf-8")

            with (
                mock.patch.object(olb_cli, "running_bridge_pid", return_value=456),
                mock.patch.object(olb_cli, "stop_signal") as stop_signal,
                mock.patch.object(olb_cli, "wait_for_process_exit", side_effect=[True]) as wait_for_process_exit,
                mock.patch.object(olb_cli.console, "print") as console_print,
            ):
                exit_code = olb_cli.stop_proxy(paths)

        self.assertEqual(exit_code, 0)
        stop_signal.assert_called_once_with(456)
        wait_for_process_exit.assert_called_once_with(456, 5)
        console_print.assert_called_once_with("bridge 已停止（PID 456）")

    def test_main_stop_runs_stop_flow(self):
        paths = make_paths(Path("/tmp/olb-test"))
        with (
            mock.patch.object(olb_cli, "get_paths", return_value=paths),
            mock.patch.object(olb_cli, "run_stop", return_value=0) as run_stop,
            mock.patch.object(olb_cli.sys, "argv", ["olb", "stop"]),
        ):
            exit_code = olb_cli.main()

        self.assertEqual(exit_code, 0)
        run_stop.assert_called_once_with(paths)

    def test_run_command_shows_windows_openssl_hint_on_file_not_found(self):
        with (
            mock.patch.object(olb_cli.subprocess, "run", side_effect=FileNotFoundError),
            mock.patch.object(olb_cli.shutil, "which", return_value=None),
            mock.patch.object(olb_cli, "detect_os", return_value="windows"),
        ):
            with self.assertRaises(olb_cli.CliError) as exc:
                olb_cli.run_command(["openssl", "version"])

        self.assertIn("Windows 请先安装 OpenSSL", str(exc.exception))


if __name__ == "__main__":
    unittest.main()
