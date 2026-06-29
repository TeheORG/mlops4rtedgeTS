param(
    [Parameter(Mandatory = $true)]
    [string]$Variant,

    [string]$Image = "mlops4rtedge-esp32-virtual:latest",
    [string]$Platform = "linux/amd64",
    [string]$DrainSeconds = "",
    [switch]$BuildImage
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

if ($BuildImage) {
    docker build `
        --platform $Platform `
        -f (Join-Path $PSScriptRoot "Dockerfile") `
        -t $Image `
        $repoRoot
    if ($LASTEXITCODE -ne 0) {
        throw "docker build failed with exit code $LASTEXITCODE"
    }
}

$containerPython = "/opt/esp32-virt-venv/bin/python3"
$makeArgs = @(
    "script7-virtualESP32",
    "VARIANT=$Variant",
    "PYTHON=$containerPython",
    "PYTHON_LOCAL=$containerPython"
)
if ($DrainSeconds -ne "") {
    $makeArgs += "DRAIN_SECONDS=$DrainSeconds"
}

docker run --rm -it `
    --platform $Platform `
    -v "${repoRoot}:/workspace" `
    -w /workspace `
    --tmpfs /tmp:exec,size=512m `
    -e F07_IDF_RUNNER=native `
    $Image `
    make @makeArgs
if ($LASTEXITCODE -ne 0) {
    throw "docker run failed with exit code $LASTEXITCODE"
}
