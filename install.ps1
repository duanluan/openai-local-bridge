$ErrorActionPreference = 'Stop'

$PackageRef = 'openai-local-bridge'

function Get-AppLanguage {
    foreach ($value in @($env:OLB_LANG, $env:LC_ALL, $env:LC_MESSAGES, $env:LANG)) {
        if ($value) {
            $normalized = $value.Split('.')[0].ToLower().Replace('-', '_')
            if ($normalized.StartsWith('zh')) {
                return 'zh'
            }
            break
        }
    }
    return 'en'
}

function Get-Text {
    param([string]$Key)

    switch ("$(Get-AppLanguage):$Key") {
        'zh:missing_python' { return '缺少命令：python 或 py' }
        'zh:using_uv' { return '使用 uv tool install' }
        'zh:installed_try_olb' { return '安装完成，试试：olb' }
        'zh:using_pip' { return '使用 pip --user install' }
        'zh:installed_scripts_dir' { return '安装完成，请确认 Scripts 目录已加入 PATH，然后执行：olb' }
        'zh:missing_installer' { return '缺少安装器：uv 或 pip' }
        'en:missing_python' { return 'missing command: python or py' }
        'en:using_uv' { return 'using uv tool install' }
        'en:installed_try_olb' { return 'installed successfully, try: olb' }
        'en:using_pip' { return 'using pip --user install' }
        'en:installed_scripts_dir' { return 'installed successfully, ensure your Scripts directory is in PATH, then run: olb' }
        'en:missing_installer' { return 'missing installer: uv or pip' }
        default { return $Key }
    }
}

function Write-Info {
    param([string]$Message)
    Write-Host $Message
}

function Get-PythonCommand {
    foreach ($candidate in @('python', 'py')) {
        if (Get-Command $candidate -ErrorAction SilentlyContinue) {
            return $candidate
        }
    }
    throw (Get-Text 'missing_python')
}

function Install-WithUv {
    & uv tool install --refresh $PackageRef
}

function Install-WithPip {
    param([string]$PythonCommand)
    & $PythonCommand -m pip install --user --upgrade $PackageRef
}

if (Get-Command uv -ErrorAction SilentlyContinue) {
    Write-Info (Get-Text 'using_uv')
    Install-WithUv
    Write-Info (Get-Text 'installed_try_olb')
    exit $LASTEXITCODE
}

$python = Get-PythonCommand
try {
    & $python -m pip --version *> $null
} catch {
    throw (Get-Text 'missing_installer')
}

Write-Info (Get-Text 'using_pip')
Install-WithPip -PythonCommand $python
Write-Info (Get-Text 'installed_scripts_dir')
exit $LASTEXITCODE
