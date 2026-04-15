$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

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
        'zh:missing_runtime' { return '缺少命令：uv、python 或 python3' }
        'en:missing_runtime' { return 'missing command: uv, python, or python3' }
        default { return $Key }
    }
}

function Invoke-OlbCli {
    param([string[]]$CliArgs)

    if (Get-Command uv -ErrorAction SilentlyContinue) {
        Push-Location $ScriptDir
        try {
            & uv run olb @CliArgs
            exit $LASTEXITCODE
        } finally {
            Pop-Location
        }
    }

    foreach ($candidate in @('python', 'python3')) {
        if (Get-Command $candidate -ErrorAction SilentlyContinue) {
            Push-Location $ScriptDir
            try {
                & $candidate -m olb_cli @CliArgs
                exit $LASTEXITCODE
            } finally {
                Pop-Location
            }
        }
    }

    throw (Get-Text 'missing_runtime')
}

Invoke-OlbCli -CliArgs $args
