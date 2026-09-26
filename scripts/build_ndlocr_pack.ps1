param(
    [string]$Python = ".venv-build\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

function Invoke-Python {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$CommandArgs)
    & $Python @CommandArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed with exit code $LASTEXITCODE"
    }
}

if ($Python -eq ".venv-build\Scripts\python.exe" -and -not (Test-Path $Python)) {
    py -3.12 -m venv .venv-build
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create .venv-build"
    }
}

Invoke-Python -m pip install -r requirements-build.txt
Invoke-Python -m pip install -r requirements-ndlocr.txt

$ndlVersion = "1.3.1"
$ndlArchive = "build\ndlocr-lite-$ndlVersion-source.zip"
$ndlExtractRoot = "build\ndlocr-source"
$ndlSource = Join-Path $ndlExtractRoot "ndlocr-lite-$ndlVersion"
$ndlSourceUrl = "https://github.com/ndl-lab/ndlocr-lite/archive/refs/tags/$ndlVersion.zip"
$ndlSourceSha256 = "e510d3a7b878395ea9de0bdd365711b699e5fd430b5c7e23a40e918e913fd1f2"

Remove-Item -Recurse -Force build\ndlocr-source, build\ndlocr-dist, build\ndlocr-app, build\ndlocr-pack -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path build -Force | Out-Null
Invoke-WebRequest -Uri $ndlSourceUrl -OutFile $ndlArchive
$downloadedNdlHash = (Get-FileHash $ndlArchive -Algorithm SHA256).Hash.ToLower()
if ($downloadedNdlHash -ne $ndlSourceSha256) {
    throw "NDLOCR-Lite source archive hash mismatch: $downloadedNdlHash"
}
Expand-Archive -Path $ndlArchive -DestinationPath $ndlExtractRoot -Force
if (-not (Test-Path "$ndlSource\src\ocr.py")) {
    throw "NDLOCR-Lite source was not extracted"
}

$ndlArgs = @(
    "-m", "PyInstaller",
    "--noconfirm", "--clean", "--noupx", "--onedir", "--console",
    "--name", "PoENaviNdlOcr",
    "--distpath", "build\ndlocr-dist",
    "--workpath", "build\ndlocr-app",
    "--paths", "$ndlSource\src",
    "--add-data", "$ndlSource\src\model;model",
    "--add-data", "$ndlSource\src\config;config",
    "--add-data", "$ndlSource\LICENCE;.",
    "--add-data", "$ndlSource\LICENCE_DEPENDENCEIES;.",
    "scripts\ndlocr_lite_entry.py"
)
Invoke-Python @ndlArgs
if (-not (Test-Path build\ndlocr-dist\PoENaviNdlOcr\PoENaviNdlOcr.exe)) {
    throw "Self-contained NDLOCR-Lite helper was not built"
}
Invoke-Python scripts\verify_ndlocr_helper.py `
    --helper "build\ndlocr-dist\PoENaviNdlOcr\PoENaviNdlOcr.exe" `
    --image "tests\fixtures\poetore\poe2\desecration\reported-spear-physical-read-failed.png"

$ocrPackName = "PoENavi-HighAccuracyOCR"
$ocrPackZip = "$ocrPackName.zip"
$ocrPackSha = "$ocrPackZip.sha256"
$ocrPackRoot = "build\ndlocr-pack\$ocrPackName"
New-Item -ItemType Directory -Path $ocrPackRoot -Force | Out-Null
Copy-Item "build\ndlocr-dist\PoENaviNdlOcr" "$ocrPackRoot\PoENaviNdlOcr" -Recurse
$licenseDir = "$ocrPackRoot\THIRD_PARTY_LICENSES\NDLOCR-Lite-$ndlVersion"
New-Item -ItemType Directory -Path $licenseDir -Force | Out-Null
Copy-Item "$ndlSource\LICENCE" "$licenseDir\LICENCE.txt"
Copy-Item "$ndlSource\LICENCE_DEPENDENCEIES" "$licenseDir\LICENCE_DEPENDENCIES.txt"

Remove-Item $ocrPackZip, $ocrPackSha -ErrorAction SilentlyContinue
$ocrPackCode = "import shutil; shutil.make_archive('$ocrPackName', 'zip', root_dir='build/ndlocr-pack', base_dir='$ocrPackName')"
$ocrPackArgs = @("-c", $ocrPackCode)
Invoke-Python @ocrPackArgs
if (-not (Test-Path $ocrPackZip)) {
    throw "High-accuracy OCR pack was not created"
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
$ocrArchive = [System.IO.Compression.ZipFile]::OpenRead((Resolve-Path $ocrPackZip))
try {
    $ocrEntryNames = @($ocrArchive.Entries | ForEach-Object { $_.FullName.Replace("\", "/") })
    foreach ($requiredName in @("PoENaviNdlOcr.exe", "deim-s-1024x1024.onnx", "parseq-ndl-24x256-30-tiny-189epoch-tegaki3-r8data-202604.onnx", "parseq-ndl-24x384-50-tiny-300epoch-tegaki3-r8data-202604.onnx", "parseq-ndl-24x768-100-tiny-153epoch-tegaki3-r8data-202604.onnx", "LICENCE.txt", "LICENCE_DEPENDENCIES.txt")) {
        if (-not ($ocrEntryNames | Where-Object { $_ -match "(^|/)$([regex]::Escape($requiredName))$" })) {
            throw "High-accuracy OCR pack audit failed: missing $requiredName"
        }
    }
    $unsafeEntries = @($ocrEntryNames | Where-Object {
        $_ -match "(^|/)\.\.(/|$)" -or $_ -match "^[A-Za-z]:" -or $_.StartsWith("/")
    })
    if ($unsafeEntries.Count -gt 0) {
        throw "High-accuracy OCR pack audit failed: unsafe paths: $($unsafeEntries -join ', ')"
    }
}
finally {
    $ocrArchive.Dispose()
}

$ocrPackHash = (Get-FileHash $ocrPackZip -Algorithm SHA256).Hash.ToLower()
Set-Content -Path $ocrPackSha -Value "$ocrPackHash  $ocrPackZip" -Encoding ascii
Write-Output "Built immutable high-accuracy OCR pack"
Write-Output "  ZIP: $((Resolve-Path $ocrPackZip).Path)"
Write-Output "  SHA256: $((Resolve-Path $ocrPackSha).Path)"
