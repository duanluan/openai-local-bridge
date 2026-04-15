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


def lang_env(language: str):
    return mock.patch.dict(olb_cli.os.environ, {"OLB_LANG": language}, clear=False)


class PromptForConfigTests(unittest.TestCase):
    def test_prompt_for_config_uses_fixed_reasoning_effort_choices(self):
        with (
            lang_env("zh"),
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
            lang_env("zh"),
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

    def test_prompt_for_config_supports_custom_intro(self):
        with (
            lang_env("zh"),
            mock.patch.object(olb_cli.Prompt, "ask", side_effect=["https://example.com/v1", "test-key", "xhigh"]),
            mock.patch.object(olb_cli, "validate_upstream"),
            mock.patch.object(olb_cli.Panel, "fit", return_value="panel") as panel_fit,
            mock.patch.object(olb_cli.console, "print"),
        ):
            olb_cli.prompt_for_config({}, intro_key="config_intro_add")

        panel_fit.assert_called_once()
        self.assertIn("现在为新账号写入上游配置", panel_fit.call_args.args[0])


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
            self.assertEqual(olb_cli.app_version(), "0.2.8")

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


class LocalizationTests(unittest.TestCase):
    def test_build_parser_help_switches_to_english(self):
        with lang_env("en"):
            parser = olb_cli.build_parser()

        help_text = parser.format_help()
        start_help = parser._subparsers._group_actions[0].choices["start"].format_help()
        account_help = parser._subparsers._group_actions[0].choices["account"].format_help()

        self.assertIn("--lang {en,zh}", help_text)
        self.assertIn("set command language", help_text)
        self.assertIn("commands", help_text)
        self.assertIn("run bridge in background", start_help)
        self.assertIn("account (a)", help_text)
        self.assertIn("list (ls)", account_help)
        self.assertIn("use (switch)", account_help)

    def test_build_parser_help_switches_to_chinese(self):
        with lang_env("zh"):
            parser = olb_cli.build_parser()

        help_text = parser.format_help()
        start_help = parser._subparsers._group_actions[0].choices["start"].format_help()
        account_help = parser._subparsers._group_actions[0].choices["account"].format_help()

        self.assertIn("--lang {en,zh}", help_text)
        self.assertIn("设置命令语言", help_text)
        self.assertIn("命令", help_text)
        self.assertIn("以后台模式运行 bridge", start_help)
        self.assertIn("account (a)", help_text)
        self.assertIn("list (ls)", account_help)
        self.assertIn("use (switch)", account_help)

    def test_show_accounts_uses_localized_column_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(Path(tmp))
            olb_cli.save_config(
                paths,
                {
                    "active_account": "default",
                    "accounts": {
                        "default": {
                            "upstream_base": "https://example.com/v1",
                            "upstream_key": "default-key",
                            "reasoning_effort": "xhigh",
                        }
                    },
                },
            )
            table = mock.Mock()

            with (
                lang_env("zh"),
                mock.patch.object(olb_cli, "Table", return_value=table),
                mock.patch.object(olb_cli.console, "print"),
            ):
                olb_cli.show_accounts(paths)

        self.assertEqual(
            [call.args[0] for call in table.add_column.call_args_list],
            ["账号名", "当前账号", "API 请求地址", "推理强度等级", "API Key"],
        )

    def test_show_config_uses_localized_field_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(Path(tmp))
            olb_cli.save_config(
                paths,
                {
                    "active_account": "default",
                    "accounts": {
                        "default": {
                            "upstream_base": "https://example.com/v1",
                            "upstream_key": "default-key",
                            "reasoning_effort": "xhigh",
                            "reasoning_effort_format": "openai",
                            "upstream_model": "gpt-5.4",
                        }
                    },
                },
            )
            table = mock.Mock()

            with (
                lang_env("en"),
                mock.patch.object(olb_cli, "Table", return_value=table),
                mock.patch.object(olb_cli.console, "print"),
            ):
                olb_cli.show_config(paths)

        self.assertEqual(
            [call.args[0] for call in table.add_row.call_args_list[:7]],
            [
                "Active Account",
                "Saved Accounts",
                "API Request URL",
                "Reasoning Effort Level",
                "Reasoning Effort Format",
                "Upstream Model",
                "API Key",
            ],
        )


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


class ConfigStorageTests(unittest.TestCase):
    def test_load_config_migrates_legacy_single_account_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(Path(tmp))
            paths.root.mkdir(parents=True, exist_ok=True)
            paths.config_file.write_text(
                '{"upstream_base":"https://example.com/v1","upstream_key":"test-key","reasoning_effort":"medium"}\n',
                encoding="utf-8",
            )

            config = olb_cli.load_config(paths)

        self.assertEqual(config["active_account"], "default")
        self.assertEqual(
            config["accounts"]["default"],
            {
                "upstream_base": "https://example.com/v1",
                "upstream_key": "test-key",
                "reasoning_effort": "medium",
            },
        )

    def test_save_config_removes_file_when_no_accounts_left(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(Path(tmp))
            paths.root.mkdir(parents=True, exist_ok=True)
            paths.config_file.write_text('{"active_account":"default","accounts":{"default":{"upstream_base":"https://example.com/v1"}}}\n', encoding="utf-8")

            olb_cli.save_config(paths, {"active_account": "", "accounts": {}})

            self.assertFalse(paths.config_file.exists())


class InternalBridgeTests(unittest.TestCase):
    def test_cli_entry_command_uses_module_in_python_mode(self):
        with mock.patch.object(olb_cli.sys, "frozen", False, create=True):
            command = olb_cli.cli_entry_command()

        self.assertEqual(command, [olb_cli.sys.executable, "-m", "olb_cli"])

    def test_cli_entry_command_uses_current_binary_when_frozen(self):
        with mock.patch.object(olb_cli.sys, "frozen", True, create=True):
            command = olb_cli.cli_entry_command()

        self.assertEqual(command, [olb_cli.sys.executable])

    def test_main_dispatches_internal_bridge_command(self):
        with mock.patch.object(olb_cli, "run_embedded_bridge", return_value=0) as run_embedded_bridge:
            exit_code = olb_cli.main([olb_cli.INTERNAL_BRIDGE_COMMAND, "--cert", "cert.pem", "--key", "key.pem"])

        self.assertEqual(exit_code, 0)
        run_embedded_bridge.assert_called_once_with(["--cert", "cert.pem", "--key", "key.pem"])


class RunStartTests(unittest.TestCase):
    def test_run_start_prints_init_notice_when_config_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(Path(tmp))
            config = {"upstream_base": "https://example.com/v1", "upstream_key": "test-key", "reasoning_effort": "medium"}

            with (
                lang_env("zh"),
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

    def test_run_start_prints_english_notice_when_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(Path(tmp))
            config = {"upstream_base": "https://example.com/v1", "upstream_key": "test-key", "reasoning_effort": "medium"}

            with (
                lang_env("en"),
                mock.patch.object(olb_cli.console, "print") as console_print,
                mock.patch.object(olb_cli, "ensure_config", return_value=config),
                mock.patch.object(olb_cli, "run_enable"),
                mock.patch.object(olb_cli, "start_proxy", return_value=0),
            ):
                exit_code = olb_cli.run_start(paths)

        self.assertEqual(exit_code, 0)
        console_print.assert_called_once_with(
            "No config detected. Starting interactive initialization first, then running enable and start."
        )

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


class AccountCommandTests(unittest.TestCase):
    def test_run_account_add_keeps_current_active_account(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(Path(tmp))
            olb_cli.save_config(
                paths,
                {
                    "active_account": "default",
                    "accounts": {
                        "default": {
                            "upstream_base": "https://example.com/v1",
                            "upstream_key": "default-key",
                            "reasoning_effort": "medium",
                        }
                    },
                },
            )
            new_account = {
                "upstream_base": "https://work.example/v1",
                "upstream_key": "work-key",
                "reasoning_effort": "high",
            }

            with (
                mock.patch.object(olb_cli, "prompt_for_config", return_value=new_account) as prompt_for_config,
                mock.patch.object(olb_cli.console, "print") as console_print,
            ):
                exit_code = olb_cli.run_account_add(paths, "work")

            saved = olb_cli.load_config(paths)

        self.assertEqual(exit_code, 0)
        self.assertEqual(saved["active_account"], "default")
        self.assertEqual(saved["accounts"]["work"], new_account)
        prompt_for_config.assert_called_once_with({}, intro_key="config_intro_add")
        console_print.assert_called_once_with("account added: work")

    def test_run_account_edit_defaults_to_active_account(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(Path(tmp))
            olb_cli.save_config(
                paths,
                {
                    "active_account": "work",
                    "accounts": {
                        "work": {
                            "upstream_base": "https://work.example/v1",
                            "upstream_key": "work-key",
                            "reasoning_effort": "medium",
                        }
                    },
                },
            )
            updated_account = {
                "upstream_base": "https://work.example/v2",
                "upstream_key": "work-key-2",
                "reasoning_effort": "high",
            }

            with (
                mock.patch.object(olb_cli, "prompt_for_config", return_value=updated_account) as prompt_for_config,
                mock.patch.object(olb_cli.console, "print") as console_print,
            ):
                exit_code = olb_cli.run_account_edit(paths)

            saved = olb_cli.load_config(paths)

        self.assertEqual(exit_code, 0)
        self.assertEqual(saved["accounts"]["work"], updated_account)
        prompt_for_config.assert_called_once_with(
            {
                "upstream_base": "https://work.example/v1",
                "upstream_key": "work-key",
                "reasoning_effort": "medium",
            },
            intro_key="config_intro_edit",
        )
        console_print.assert_called_once_with("account updated: work")

    def test_run_account_delete_switches_active_account_when_needed(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(Path(tmp))
            olb_cli.save_config(
                paths,
                {
                    "active_account": "default",
                    "accounts": {
                        "default": {
                            "upstream_base": "https://example.com/v1",
                            "upstream_key": "default-key",
                            "reasoning_effort": "medium",
                        },
                        "work": {
                            "upstream_base": "https://work.example/v1",
                            "upstream_key": "work-key",
                            "reasoning_effort": "high",
                        },
                    },
                },
            )

            with mock.patch.object(olb_cli.console, "print") as console_print:
                exit_code = olb_cli.run_account_delete(paths, "default")

            saved = olb_cli.load_config(paths)

        self.assertEqual(exit_code, 0)
        self.assertEqual(saved["active_account"], "work")
        self.assertNotIn("default", saved["accounts"])
        console_print.assert_has_calls(
            [
                mock.call("account deleted: default"),
                mock.call("active account switched to work"),
            ]
        )

    def test_run_account_switch_updates_active_account(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(Path(tmp))
            olb_cli.save_config(
                paths,
                {
                    "active_account": "default",
                    "accounts": {
                        "default": {
                            "upstream_base": "https://example.com/v1",
                            "upstream_key": "default-key",
                            "reasoning_effort": "medium",
                        },
                        "work": {
                            "upstream_base": "https://work.example/v1",
                            "upstream_key": "work-key",
                            "reasoning_effort": "high",
                        },
                    },
                },
            )

            with mock.patch.object(olb_cli.console, "print") as console_print:
                exit_code = olb_cli.run_account_switch(paths, "work")

            saved = olb_cli.load_config(paths)

        self.assertEqual(exit_code, 0)
        self.assertEqual(saved["active_account"], "work")
        console_print.assert_called_once_with("active account switched to work")

    def test_run_account_switch_prompts_restart_for_running_bridge(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(Path(tmp))
            work_config = {
                "upstream_base": "https://work.example/v1",
                "upstream_key": "work-key",
                "reasoning_effort": "high",
            }
            olb_cli.save_config(
                paths,
                {
                    "active_account": "default",
                    "accounts": {
                        "default": {
                            "upstream_base": "https://example.com/v1",
                            "upstream_key": "default-key",
                            "reasoning_effort": "medium",
                        },
                        "work": work_config,
                    },
                },
            )

            with (
                mock.patch.object(olb_cli.console, "print") as console_print,
                mock.patch.object(olb_cli, "running_bridge_pid", return_value=456),
                mock.patch.object(olb_cli.Confirm, "ask", return_value=True) as confirm_ask,
                mock.patch.object(olb_cli, "stop_proxy", return_value=0) as stop_proxy,
                mock.patch.object(olb_cli, "start_proxy", return_value=0) as start_proxy,
            ):
                exit_code = olb_cli.run_account_switch(paths, "work")

            saved = olb_cli.load_config(paths)

        self.assertEqual(exit_code, 0)
        self.assertEqual(saved["active_account"], "work")
        console_print.assert_called_once_with("active account switched to work")
        confirm_ask.assert_called_once_with(
            "bridge is running (PID 456). Restart it now in background to apply account work?",
            default=True,
        )
        stop_proxy.assert_called_once_with(paths)
        start_proxy.assert_called_once_with(paths, work_config, background=True)

    def test_run_account_switch_skips_restart_when_declined(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(Path(tmp))
            olb_cli.save_config(
                paths,
                {
                    "active_account": "default",
                    "accounts": {
                        "default": {
                            "upstream_base": "https://example.com/v1",
                            "upstream_key": "default-key",
                            "reasoning_effort": "medium",
                        },
                        "work": {
                            "upstream_base": "https://work.example/v1",
                            "upstream_key": "work-key",
                            "reasoning_effort": "high",
                        },
                    },
                },
            )

            with (
                mock.patch.object(olb_cli.console, "print"),
                mock.patch.object(olb_cli, "running_bridge_pid", return_value=456),
                mock.patch.object(olb_cli.Confirm, "ask", return_value=False) as confirm_ask,
                mock.patch.object(olb_cli, "stop_proxy") as stop_proxy,
                mock.patch.object(olb_cli, "start_proxy") as start_proxy,
            ):
                exit_code = olb_cli.run_account_switch(paths, "work")

            saved = olb_cli.load_config(paths)

        self.assertEqual(exit_code, 0)
        self.assertEqual(saved["active_account"], "work")
        confirm_ask.assert_called_once()
        stop_proxy.assert_not_called()
        start_proxy.assert_not_called()

    def test_main_account_defaults_to_list(self):
        paths = make_paths(Path("/tmp/olb-test"))
        with (
            mock.patch.object(olb_cli, "get_paths", return_value=paths),
            mock.patch.object(olb_cli, "run_account_list", return_value=0) as run_account_list,
            mock.patch.object(olb_cli.sys, "argv", ["olb", "account"]),
        ):
            exit_code = olb_cli.main()

        self.assertEqual(exit_code, 0)
        run_account_list.assert_called_once_with(paths)

    def test_main_short_account_alias_defaults_to_list(self):
        paths = make_paths(Path("/tmp/olb-test"))
        with (
            mock.patch.object(olb_cli, "get_paths", return_value=paths),
            mock.patch.object(olb_cli, "run_account_list", return_value=0) as run_account_list,
            mock.patch.object(olb_cli.sys, "argv", ["olb", "a"]),
        ):
            exit_code = olb_cli.main()

        self.assertEqual(exit_code, 0)
        run_account_list.assert_called_once_with(paths)

    def test_main_account_ls_alias_dispatches_list(self):
        paths = make_paths(Path("/tmp/olb-test"))
        with (
            mock.patch.object(olb_cli, "get_paths", return_value=paths),
            mock.patch.object(olb_cli, "run_account_list", return_value=0) as run_account_list,
            mock.patch.object(olb_cli.sys, "argv", ["olb", "account", "ls"]),
        ):
            exit_code = olb_cli.main()

        self.assertEqual(exit_code, 0)
        run_account_list.assert_called_once_with(paths)

    def test_main_account_use_dispatches_switch_flow(self):
        paths = make_paths(Path("/tmp/olb-test"))
        with (
            mock.patch.object(olb_cli, "get_paths", return_value=paths),
            mock.patch.object(olb_cli, "run_account_switch", return_value=0) as run_account_switch,
            mock.patch.object(olb_cli.sys, "argv", ["olb", "a", "use", "work"]),
        ):
            exit_code = olb_cli.main()

        self.assertEqual(exit_code, 0)
        run_account_switch.assert_called_once_with(paths, "work")


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
            mock.patch.object(olb_cli, "cli_entry_command", return_value=["/tmp/olb"]),
        ):
            command = olb_cli.build_proxy_command(Path("/tmp/test.crt"), Path("/tmp/test.key"), env)

        self.assertEqual(command[0], "sudo")
        self.assertTrue(command[1].startswith("--preserve-env="))
        self.assertEqual(
            command[2:8],
            ["/tmp/olb", olb_cli.INTERNAL_BRIDGE_COMMAND, "--cert", "/tmp/test.crt", "--key", "/tmp/test.key"],
        )
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
            mock.patch.object(olb_cli, "cli_entry_command", return_value=["python3", "-m", "olb_cli"]),
        ):
            command = olb_cli.build_proxy_command(Path("/tmp/test.crt"), Path("/tmp/test.key"), env)

        self.assertEqual(
            command,
            [
                "python3",
                "-m",
                "olb_cli",
                olb_cli.INTERNAL_BRIDGE_COMMAND,
                "--cert",
                "/tmp/test.crt",
                "--key",
                "/tmp/test.key",
            ],
        )

    def test_build_proxy_command_appends_pid_file(self):
        env = {
            "OLB_LISTEN_PORT": "8443",
            "OLB_UPSTREAM_BASE": "https://example.com/v1",
            "OLB_UPSTREAM_KEY": "test-key",
        }

        with (
            mock.patch.object(olb_cli, "detect_os", return_value="linux"),
            mock.patch.object(olb_cli.os, "geteuid", return_value=1000, create=True),
            mock.patch.object(olb_cli, "cli_entry_command", return_value=["python3", "-m", "olb_cli"]),
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
                mock.patch.object(olb_cli.subprocess, "Popen", return_value=process) as popen,
                mock.patch.object(olb_cli, "wait_for_background_start", return_value=0) as wait_for_background_start,
            ):
                exit_code = olb_cli.start_proxy(paths, config, background=True)

        self.assertEqual(exit_code, 0)
        build_proxy_command.assert_called_once_with(
            Path("/tmp/test.crt"),
            Path("/tmp/test.key"),
            {
                "OLB_LISTEN_HOST": "127.0.0.1",
                "OLB_LISTEN_PORT": "8443",
                "OLB_LOG_PATH": str(paths.root / "bridge.log"),
                "OLB_LOG_MAX_BYTES": olb_cli.DEFAULT_BACKGROUND_LOG_MAX_BYTES,
                "OLB_LOG_BACKUP_COUNT": olb_cli.DEFAULT_BACKGROUND_LOG_BACKUP_COUNT,
            },
            pid_file=paths.root / "bridge.pid",
        )
        popen.assert_called_once()
        self.assertEqual(popen.call_args.kwargs["stdout"], subprocess.DEVNULL)
        self.assertEqual(popen.call_args.kwargs["stderr"], subprocess.DEVNULL)
        wait_for_background_start.assert_called_once_with(paths, process, paths.root / "bridge.log")

    def test_start_proxy_background_with_sudo_reuses_same_prompt_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(Path(tmp))
            config = {"upstream_base": "https://example.com/v1", "upstream_key": "test-key", "reasoning_effort": "medium"}

            with (
                mock.patch.object(olb_cli, "running_bridge_pid", return_value=None),
                mock.patch.object(olb_cli, "validate_upstream"),
                mock.patch.object(olb_cli, "ensure_domain_cert", return_value=(Path("/tmp/test.crt"), Path("/tmp/test.key"))),
                mock.patch.object(
                    olb_cli,
                    "env_from_config",
                    return_value={"OLB_LISTEN_HOST": "127.0.0.1", "OLB_LISTEN_PORT": "443"},
                ),
                mock.patch.object(
                    olb_cli,
                    "build_proxy_command",
                    return_value=["sudo", "--preserve-env=OLB_LISTEN_PORT", "python", "-m", "olb_cli"],
                ),
                mock.patch.object(olb_cli, "detect_os", return_value="linux"),
                mock.patch.object(olb_cli, "prepare_background_launch") as prepare_background_launch,
                mock.patch.object(olb_cli, "launch_background_with_sudo") as launch_background_with_sudo,
                mock.patch.object(olb_cli.subprocess, "Popen") as popen,
                mock.patch.object(olb_cli, "wait_for_background_start", return_value=0) as wait_for_background_start,
            ):
                exit_code = olb_cli.start_proxy(paths, config, background=True)

        self.assertEqual(exit_code, 0)
        prepare_background_launch.assert_called_once_with(["sudo", "--preserve-env=OLB_LISTEN_PORT", "python", "-m", "olb_cli"])
        self.assertEqual(launch_background_with_sudo.call_args.args[0], ["sudo", "--preserve-env=OLB_LISTEN_PORT", "python", "-m", "olb_cli"])
        self.assertEqual(launch_background_with_sudo.call_args.args[2], paths.root / "bridge.log")
        self.assertEqual(launch_background_with_sudo.call_args.args[1]["OLB_LOG_PATH"], str(paths.root / "bridge.log"))
        self.assertEqual(
            launch_background_with_sudo.call_args.args[1]["OLB_LOG_MAX_BYTES"],
            olb_cli.DEFAULT_BACKGROUND_LOG_MAX_BYTES,
        )
        self.assertEqual(
            launch_background_with_sudo.call_args.args[1]["OLB_LOG_BACKUP_COUNT"],
            olb_cli.DEFAULT_BACKGROUND_LOG_BACKUP_COUNT,
        )
        popen.assert_not_called()
        wait_for_background_start.assert_called_once_with(paths, None, paths.root / "bridge.log")

    def test_prepare_background_launch_refreshes_sudo_credentials(self):
        with mock.patch.object(olb_cli, "run_command") as run_command:
            olb_cli.prepare_background_launch(["sudo", "--preserve-env=OLB_LISTEN_PORT", "python"])

        run_command.assert_called_once_with(["sudo", "-v"])

    def test_launch_background_with_sudo_uses_non_interactive_sudo_after_refresh(self):
        with mock.patch.object(olb_cli, "run_command") as run_command:
            olb_cli.launch_background_with_sudo(
                ["sudo", "--preserve-env=OLB_LISTEN_PORT", "python", "-m", "olb_cli"],
                {"OLB_LISTEN_PORT": "443", "OLB_LOG_PATH": "/tmp/bridge.log"},
                Path("/tmp/bridge.log"),
            )

        run_command.assert_called_once()
        self.assertEqual(
            run_command.call_args.args[0][:4],
            ["sudo", "-n", "--preserve-env=OLB_LISTEN_PORT", "sh"],
        )
        self.assertIn(">/dev/null 2>&1 </dev/null &", run_command.call_args.args[0][5])


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
            lang_env("zh"),
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

            with lang_env("zh"), mock.patch.object(olb_cli.console, "print") as console_print:
                exit_code = olb_cli.stop_proxy(paths)

        self.assertEqual(exit_code, 0)
        console_print.assert_called_once_with("bridge 未运行")

    def test_stop_proxy_terminates_running_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(Path(tmp))
            paths.root.mkdir(parents=True, exist_ok=True)
            (paths.root / "bridge.pid").write_text("456\n", encoding="utf-8")

            with (
                lang_env("zh"),
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

    def test_stop_proxy_uses_english_output_when_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(Path(tmp))

            with lang_env("en"), mock.patch.object(olb_cli.console, "print") as console_print:
                exit_code = olb_cli.stop_proxy(paths)

        self.assertEqual(exit_code, 0)
        console_print.assert_called_once_with("bridge is not running")

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
            lang_env("zh"),
            mock.patch.object(olb_cli.subprocess, "run", side_effect=FileNotFoundError),
            mock.patch.object(olb_cli.shutil, "which", return_value=None),
            mock.patch.object(olb_cli, "detect_os", return_value="windows"),
        ):
            with self.assertRaises(olb_cli.CliError) as exc:
                olb_cli.run_command(["openssl", "version"])

        self.assertIn("Windows 请先安装 OpenSSL", str(exc.exception))


if __name__ == "__main__":
    unittest.main()
