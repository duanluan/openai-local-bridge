$ErrorActionPreference = 'Stop'

$RepoUrl = 'https://github.com/duanluan/openai-local-bridge'
$PackageRef = "git+$RepoUrl.git"

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
    throw 'missing command: python or py'
}

function Install-WithUv {
    & uv tool install --refresh $PackageRef
}

function Install-WithPip {
    param([string]$PythonCommand)
    & $PythonCommand -m pip install --user --upgrade $PackageRef
}

if (Get-Command uv -ErrorAction SilentlyContinue) {
    Write-Info 'using uv tool install'
    Install-WithUv
    Write-Info 'installed successfully, try: olb'
    exit $LASTEXITCODE
}

$python = Get-PythonCommand
try {
    & $python -m pip --version *> $null
} catch {
    throw 'missing installer: uv or pip'
}

Write-Info 'using pip --user install'
Install-WithPip -PythonCommand $python
Write-Info 'installed successfully, ensure your Scripts directory is in PATH, then run: olb'
exit $LASTEXITCODE
