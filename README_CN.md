# openai-local-bridge

[English README](./README.md)

`openai-local-bridge` 用于在本机将 `api.openai.com` 请求桥接到第三方 OpenAI-compatible 接口，以实现 Trae、AI Assistant 中 GPT Codex 使用第三方 API。

## 前置环境

- `OpenSSL`：执行 `olb enable` 或 `olb start` 时需要它来生成本地证书。Windows 请先安装 [OpenSSL](https://slproweb.com/products/Win32OpenSSL.html)，并确认 `openssl.exe` 所在目录已加入 `PATH`。

运行前检查：

```bash
openssl version
```

## 安装

如果想直接使用自带 Python 运行时的独立二进制包，可以从 GitHub Releases 下载对应平台压缩包。此方式不再依赖本机 `Git`、`Python`、`uv`、`npm`，但执行 `olb enable` / `olb start` 仍然需要 `OpenSSL`。

### 方式 1：`uv`

```bash
uv tool install openai-local-bridge
```

### 方式 2：`pip`

```bash
python -m pip install --user openai-local-bridge
```

### 方式 3：`npm`

```bash
npm install -g @duanluan/openai-local-bridge
```

npm 包会在安装阶段从 GitHub Releases 下载当前平台对应的独立二进制文件，所以运行时不再依赖 `Python` 或 `uv`。

### 方式 4：`curl` / PowerShell

Linux / macOS：

```bash
curl -fsSL https://raw.githubusercontent.com/duanluan/openai-local-bridge/main/install.sh | bash
```

Windows PowerShell：

```powershell
irm https://raw.githubusercontent.com/duanluan/openai-local-bridge/main/install.ps1 | iex
```

### 方式 5：独立二进制包

从 GitHub Releases 下载对应平台压缩包，解压后直接运行 `olb`：

- `olb-linux-x86_64.tar.gz`
- `olb-macos-x86_64.tar.gz`
- `olb-macos-arm64.tar.gz`
- `olb-windows-x86_64.zip`

## 快速开始

最直接的用法就是：

```bash
olb start
```

后台启动：

```bash
olb start --background
```

如果本机还没有配置，`olb start` 会先进入初始化，再继续执行启用和启动；交互式会采集：

- `Base URL`
- `API Key`
- `推理强度`

如果你只想单独修改配置，可以执行：

```bash
olb init
```

关闭接管：

```bash
olb disable
```

关闭当前运行中的 bridge：

```bash
olb stop
```

## 常用命令

命令说明：

- `olb`：未配置时进入初始化，已配置时显示状态
- `init`：首次初始化或重新配置
- `config`：查看当前配置
- `config-path`：查看配置文件路径
- `status`：查看当前状态
- `enable`：安装证书、处理 hosts，并在支持的平台上处理 NSS
- `disable`：取消 hosts 接管
- `start`：未初始化时先进入初始化，然后执行 `enable` 并直接启动 bridge
- `start --background`：以后台模式启动 bridge，并将日志写到配置目录
- `stop`：停止当前 bridge 进程，包括后台运行中的实例

## 包装脚本入口

如果你是在仓库目录里直接使用，也可以：

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

这些入口最终都会转发到同一个 CLI。

如果通过 npm 安装，`olb` 会直接启动当前平台对应的内置二进制文件。当前支持 Linux x64、macOS x64、macOS arm64、Windows x64。

## 在客户端中使用

以 Trae 为例，建议分两个阶段：

### 阶段 1：先在客户端里完成模型添加

1. 保持本项目未接管，执行：

   ```bash
   olb disable
   ```

2. 确认当前机器可以正常访问官方 OpenAI。
3. 在客户端中添加模型，例如：
   - 服务商：`OpenAI`
   - 模型：`自定义模型`
   - 模型 ID：`gpt-5.4`
   - API Key：官方 OpenAI Key

### 阶段 2：再启用 bridge 接管后续请求

```bash
olb start
```

然后在客户端中选择你刚才添加的模型即可。

## 常见问题

### `olb` 默认会做什么

- 如果还没有配置文件：进入初始化
- 如果已经配置完成：显示当前状态

### `olb status` 可以看什么

通常重点关注这些字段：

- `hosts`：是否已接管
- `root_ca`：根证书是否存在
- `nss`：NSS 状态
- `listener`：本地监听是否已启动
- `listen_addr`：监听地址
- `config`：配置文件位置

### 其他软件也被影响了

这是当前方案的正常表现，因为接管的是系统级 `api.openai.com`。

立即恢复：

```bash
olb disable
```

### 模型调用失败

优先检查：

- `Base URL` 是否正确
- `API Key` 是否正确
- 上游是否兼容 OpenAI 接口
- 你配置的上游模型是否真实存在

### Windows 写 hosts 或导入证书失败

通常是权限不足。请使用有足够权限的终端再执行。

### Windows 提示 `missing command: openssl`

当前实现要求本机已安装 OpenSSL。请先安装 OpenSSL，并确认终端里可以直接执行：

```powershell
openssl version
```

### Linux / macOS 启动失败

如果你使用默认 `443` 端口，系统可能要求更高权限。可直接按提示执行，或改用更高端口。

## 配置文件

CLI 会把配置写到用户目录下的配置文件中。

查看路径：

```bash
olb config-path
```

查看当前配置：

```bash
olb config
```

## 安全提示

使用前请注意：

- 本项目会在本机安装本地证书
- 本项目会修改系统 hosts
- 不使用时建议执行 `olb disable`
