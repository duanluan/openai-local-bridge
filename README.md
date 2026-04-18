# openai-local-bridge

[中文说明](./README_CN.md)

`openai-local-bridge` routes local `api.openai.com` requests to a third-party OpenAI-compatible endpoint, allowing tools such as Trae and AI Assistant to use GPT Codex through a non-OpenAI API.

## Prerequisites

- `OpenSSL`: required when running `olb enable` or `olb start` to generate local certificates. On Windows, install [OpenSSL](https://slproweb.com/products/Win32OpenSSL.html) first and make sure the directory containing `openssl.exe` is in `PATH`.

Runtime check:

```bash
openssl version
```

## Installation

If you want a standalone binary with the Python runtime bundled, download the platform archive from GitHub Releases. Those archives do not require `Git`, `Python`, `uv`, or `npm`; only `OpenSSL` is still needed for `olb enable` / `olb start`.

### Method 1: `uv`

```bash
uv tool install openai-local-bridge
```

### Method 2: `pip`

```bash
python -m pip install --user openai-local-bridge
```

### Method 3: `npm`

```bash
npm install -g @duanluan/openai-local-bridge
```

The npm package downloads the matching standalone binary from GitHub Releases during installation, so runtime use does not require `Python` or `uv`.

### Method 4: `curl` / PowerShell

Linux / macOS:

```bash
curl -fsSL https://raw.githubusercontent.com/duanluan/openai-local-bridge/main/install.sh | bash
```

Windows PowerShell:

```powershell
irm https://raw.githubusercontent.com/duanluan/openai-local-bridge/main/install.ps1 | iex
```

### Method 5: standalone binary

Download the matching archive from GitHub Releases, then unpack and run `olb` directly:

- `olb-linux-x86_64.tar.gz`
- `olb-macos-x86_64.tar.gz`
- `olb-macos-arm64.tar.gz`
- `olb-windows-x86_64.zip`

## Quick Start

The most direct way to use it is:

```bash
olb start
```

`start` now runs in the background by default. If you want foreground output for debugging:

```bash
olb start --debug
olb start -d
```

Background logs are written to `bridge.log` under the config directory and rotate automatically at 1 MiB with 3 backup files.

If the machine has not been configured yet, `olb start` first runs initialization, then continues with enablement and startup. In interactive mode, it asks for:

- `Base URL`
- `API Key`
- `Reasoning effort`

If you only want to update the active account configuration, run:

```bash
olb init
```

To add another upstream account:

```bash
olb account add work
```

To use another active account for `olb start`:

```bash
olb account use work
```

To stop the takeover:

```bash
olb disable
```

To stop a running bridge process:

```bash
olb stop
```

To restart the bridge and keep the current run mode:

```bash
olb restart
```

To inspect the local setup without making changes:

```bash
olb doctor
```

To follow the log, showing the latest 10 lines first:

```bash
olb log
```

## Common Commands

Command overview:

- `olb`: runs initialization when no config exists; otherwise shows the current status
- `init`: initial setup or reconfiguration of the active account
- `config`: show the active account configuration
- `config-path`: show the configuration file path
- `a`: shorthand for `account`
- `account list` / `account ls`: list saved accounts
- `account add <name>`: add a new account
- `account edit [name]`: edit the active account or the named account
- `account delete <name>`: delete an account
- `account use <name>`: use the selected account as active
- `status`: show the current status
- `enable`: install certificates, update hosts, and manage NSS on supported platforms
- `disable`: remove the hosts takeover
- `start`: if not initialized, run setup first, then execute `enable` and start the bridge in the background
- `start --debug` / `start -d`: run the bridge in the foreground for debugging
- `restart`: restart the bridge; when no flag is passed it keeps the current run mode
- `restart --debug` / `restart -d`: restart the bridge in the foreground
- `reload`: legacy alias for `restart`
- `doctor`: inspect local bridge setup without making changes
- `-v` / `-V` / `--version`: print the installed version
- `log`: follow the log file and show the latest 10 lines first
- `stop`: stop the current bridge process, including one started in the background

## Wrapper Script Entry Points

If you are running directly from the repository, you can also use:

### Linux / macOS

```bash
./openai-local-bridge.sh <command>
```

### Windows PowerShell

```powershell
.\openai-local-bridge.ps1 <command>
```

### Windows BAT

```bat
openai-local-bridge.bat <command>
```

All of these entry points forward to the same CLI.

If you install through npm, `olb` starts the bundled platform binary directly. Supported npm targets are Linux x64, macOS x64, macOS arm64, and Windows x64.

## Using It in a Client

Using Trae as an example, the recommended flow is split into two phases.

### Phase 1: Add the model in the client first

1. Keep this project disabled:

   ```bash
   olb disable
   ```

2. Confirm that the machine can reach the official OpenAI service.
3. Add the model in the client, for example:
   - Provider: `OpenAI`
   - Model: `Custom model`
   - Model ID: `gpt-5.4`
   - API Key: your official OpenAI key

### Phase 2: Enable the bridge for subsequent requests

```bash
olb start
```

Then choose the model you just added in the client.

## FAQ

### What does `olb` do by default?

- If no configuration file exists, it starts initialization.
- If configuration is already complete, it shows the current status.

### What can I check with `olb status`?

These fields are usually the most important:

- `hosts`: whether takeover is active
- `root_ca`: whether the root certificate exists
- `nss`: NSS status
- `listener`: whether the local listener is running
- `listen_addr`: listening address
- `config`: configuration file location

### Other software is affected too

That is expected with the current approach, because the takeover happens at the system level for `api.openai.com`.

Restore normal behavior immediately:

```bash
olb disable
```

### Model requests fail

Check these items first:

- Whether `Base URL` is correct
- Whether `API Key` is correct
- Whether the upstream service is OpenAI-compatible
- Whether the upstream model you configured actually exists

### Failed to modify `hosts` or import certificates on Windows

This is usually a permission issue. Run the command again in a terminal with sufficient privileges.

### Windows says `missing command: openssl`

The current implementation requires OpenSSL to be installed locally. Install OpenSSL first, then confirm that this works in your terminal:

```powershell
openssl version
```

### Startup fails on Linux / macOS

If you use the default port `443`, the system may require elevated privileges. Follow the prompt, or switch to a higher port.

## Configuration File

The CLI writes its configuration to a file under your user configuration directory. The file stores the active account plus all saved upstream accounts.

View the path:

```bash
olb config-path
```

View the current configuration:

```bash
olb config
```

## Security Notes

Before using this project, keep in mind:

- It installs a local certificate on your machine.
- It modifies the system `hosts` file.
- Run `olb disable` when you are not using it.
