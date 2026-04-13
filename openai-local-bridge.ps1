$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

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

    throw 'missing command: uv, python, or python3'
}

Invoke-OlbCli -CliArgs $args
