# Build a Lambda layer zip on Windows using Docker (Amazon Linux).
# Requires Docker Desktop.
#
# Usage:
#   .\build-layer.ps1 -PythonVersion 3.12
#
# Output: dist\office365-library.zip

param(
    [string]$PythonVersion = "3.12"
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$OutDir = Join-Path $ScriptDir "dist"
$LayerDir = Join-Path $OutDir "layer"
$PythonDir = Join-Path $LayerDir "python"
$ZipPath = Join-Path $OutDir "office365-library.zip"

if (Test-Path $LayerDir) { Remove-Item -Recurse -Force $LayerDir }
New-Item -ItemType Directory -Force -Path $PythonDir | Out-Null

Write-Host "Installing dependencies for Python $PythonVersion (Amazon Linux)..."

docker run --rm `
  -v "${ScriptDir}:/src" `
  -v "${PythonDir}:/out" `
  "public.ecr.aws/lambda/python:${PythonVersion}" `
  bash -c "pip install -r /src/requirements.txt -t /out --no-cache-dir"

Write-Host "Creating layer zip..."
if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }
Compress-Archive -Path (Join-Path $LayerDir "python") -DestinationPath $ZipPath

Write-Host "Done: $ZipPath"
Write-Host ""
Write-Host "Upload this zip as a Lambda layer. Expected structure inside the zip:"
Write-Host "  python/msal/"
Write-Host "  python/office365/"
Write-Host "  python/boto3/"
