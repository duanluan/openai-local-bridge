# openai-local-bridge

[中文说明](./README_CN.md)

`openai-local-bridge` routes local `api.openai.com` requests to a third-party OpenAI-compatible endpoint, allowing tools such as Trae and AI Assistant to use GPT Codex through a non-OpenAI API.

## Prerequisites

- `Git`
- `Python`
- `uv`: optional, but recommended. When available, the npm launcher prefers it so the latest CLI can be run directly.
- `OpenSSL`: required when running `olb enable` or `olb start` to generate local certificates. On Windows, install [OpenSSL](https://slproweb.com/products/Win32OpenSSL.html) first and make sure the directory containing `openssl.exe` is in `PATH`.

Check your environment:

```bash
git --version
python --version
openssl version
```

## Installation

Optional mirror URLs:

- `https://gitclone.com/github.com/duanluan/openai-local-bridge.git`
- `https://wget.la/https://github.com/duanluan/openai-local-bridge.git`
- `https://hk.gh-proxy.org/https://github.com/duanluan/openai-local-bridge.git`
- `https://ghfast.top/https://github.com/duanluan/openai-local-bridge.git`
- `https://githubfast.com/duanluan/openai-local-bridge.git`

### Method 1: `uv`

```bash
uv tool install git+https://github.com/duanluan/openai-local-bridge.git
```

### Method 2: `pip`

```bash
python -m pip install --user git+https://github.com/duanluan/openai-local-bridge.git
```

### Method 3: `npm`

```bash
npm install -g git+https://github.com/duanluan/openai-local-bridge.git
```

### Method 4: `curl` / PowerShell

Linux / macOS:

```bash
curl -fsSL https://raw.githubusercontent.com/duanluan/openai-local-bridge/main/install.sh | bash
```

Windows PowerShell:

```powershell
irm https://raw.githubusercontent.com/duanluan/openai-local-bridge/main/install.ps1 | iex
```

## Quick Start

The most direct way to use it is:

```bash
olb start
```

Run it in the background:

```bash
olb start --background
```

If the machine has not been configured yet, `olb start` first runs initialization, then continues with enablement and startup. In interactive mode, it asks for:

- `Base URL`
- `API Key`
- `Reasoning effort`

If you only want to update the configuration, run:

```bash
olb init
```

To stop the takeover:

```bash
olb disable
```

To stop a running bridge process:

```bash
olb stop
```

## Common Commands

Command overview:

- `olb`: runs initialization when no config exists; otherwise shows the current status
- `init`: initial setup or reconfiguration
- `config`: show the current configuration
- `config-path`: show the configuration file path
- `status`: show the current status
- `enable`: install certificates, update hosts, and manage NSS on supported platforms
- `disable`: remove the hosts takeover
- `start`: if not initialized, run setup first, then execute `enable` and start the bridge immediately
- `start --background`: start the bridge in the background and write logs to the config directory
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

If you install through npm from GitHub or a compatible proxy, `olb` prefers to run from the package that is already installed locally. When `uv` is available, it first tries `uv tool run --from <local package dir> olb`; otherwise it falls back to Python plus `pip --user <local package dir>`. This means runtime execution does not need to access GitHub again.

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

The CLI writes its configuration to a file under your user configuration directory.

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
