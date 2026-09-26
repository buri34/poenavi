param()

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$toolsRoot = Join-Path $env:LOCALAPPDATA "PoENavi\BuildTools"
$downloads = Join-Path $toolsRoot "Downloads"
New-Item -ItemType Directory -Path $downloads -Force | Out-Null

function Test-CommandExitCode {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$ArgumentList
    )

    if (-not (Test-Path $FilePath) -and $null -eq (Get-Command $FilePath -ErrorAction SilentlyContinue)) {
        return $false
    }
    $oldPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $FilePath @ArgumentList 2>$null | Out-Null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
    finally {
        $ErrorActionPreference = $oldPreference
    }
}

function Get-ExistingPython312 {
    $managed = Join-Path $toolsRoot "Python312\python.exe"
    if (Test-CommandExitCode -FilePath $managed -ArgumentList @(
        "-c", "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)"
    )) {
        return $managed
    }

    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($null -eq $launcher) {
        return $null
    }

    $oldPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $candidate = & $launcher.Source -3.12 -c "import sys; print(sys.executable)" 2>$null
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $oldPreference
    }
    if ($exitCode -eq 0 -and $candidate) {
        $candidatePath = @($candidate)[-1].Trim()
        if (Test-Path $candidatePath) {
            return $candidatePath
        }
    }
    return $null
}

function Install-ManagedPython312 {
    $version = "3.12.10"
    $url = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
    $expectedSha256 = "67b5635e80ea51072b87941312d00ec8927c4db9ba18938f7ad2d27b328b95fb"
    $installer = Join-Path $downloads "python-$version-amd64.exe"
    $target = Join-Path $toolsRoot "Python312"

    if (-not (Test-Path $installer) -or
        (Get-FileHash $installer -Algorithm SHA256).Hash.ToLower() -ne $expectedSha256) {
        Remove-Item $installer -Force -ErrorAction SilentlyContinue
        Write-Host "Downloading official Python $version for the local build environment..."
        Invoke-WebRequest -Uri $url -OutFile $installer
    }
    $actualHash = (Get-FileHash $installer -Algorithm SHA256).Hash.ToLower()
    if ($actualHash -ne $expectedSha256) {
        throw "Python installer hash mismatch: $actualHash"
    }

    New-Item -ItemType Directory -Path $target -Force | Out-Null
    $arguments = @(
        "/quiet", "InstallAllUsers=0", "TargetDir=`"$target`"", "PrependPath=0",
        "Include_launcher=0", "Include_test=0", "Include_doc=0", "Include_debug=0",
        "Include_dev=0", "Include_pip=1", "Include_tcltk=1", "Shortcuts=0"
    )
    $process = Start-Process -FilePath $installer -ArgumentList $arguments -Wait -PassThru
    if ($process.ExitCode -ne 0) {
        throw "Official Python installer failed with exit code $($process.ExitCode)"
    }
    $python = Join-Path $target "python.exe"
    if (-not (Test-CommandExitCode -FilePath $python -ArgumentList @(
        "-c", "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)"
    ))) {
        throw "Managed Python 3.12 verification failed"
    }
    return $python
}

function Test-Dotnet8Sdk {
    param([Parameter(Mandatory = $true)][string]$Dotnet)

    if (-not (Test-Path $Dotnet) -and $null -eq (Get-Command $Dotnet -ErrorAction SilentlyContinue)) {
        return $false
    }
    $oldPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $sdks = @(& $Dotnet --list-sdks 2>$null)
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $oldPreference
    }
    return $exitCode -eq 0 -and @($sdks | Where-Object { $_ -match '^8\.' }).Count -gt 0
}

function Get-ExistingDotnet8 {
    $managed = Join-Path $toolsRoot "Dotnet8\dotnet.exe"
    if (Test-Dotnet8Sdk -Dotnet $managed) {
        return $managed
    }
    $command = Get-Command dotnet.exe -ErrorAction SilentlyContinue
    if ($null -ne $command -and (Test-Dotnet8Sdk -Dotnet $command.Source)) {
        return $command.Source
    }
    return $null
}

function Install-ManagedDotnet8 {
    $version = "8.0.414"
    $url = "https://builds.dotnet.microsoft.com/dotnet/Sdk/8.0.414/dotnet-sdk-8.0.414-win-x64.zip"
    $expectedSha512 = "ae86d5d9aeff5be9db7e306e0f85f708a41cd611f3cbef99ce60a3fe48c19d18fa1137d8f632d959ebc2b032e594b6970850581dd0e2afe64b9842d59899d2d6"
    $archive = Join-Path $downloads "dotnet-sdk-$version-win-x64.zip"
    $target = Join-Path $toolsRoot "Dotnet8"

    if (-not (Test-Path $archive) -or
        (Get-FileHash $archive -Algorithm SHA512).Hash.ToLower() -ne $expectedSha512) {
        Remove-Item $archive -Force -ErrorAction SilentlyContinue
        Write-Host "Downloading official .NET SDK $version for the local build environment..."
        Invoke-WebRequest -Uri $url -OutFile $archive
    }
    $actualHash = (Get-FileHash $archive -Algorithm SHA512).Hash.ToLower()
    if ($actualHash -ne $expectedSha512) {
        throw ".NET SDK archive hash mismatch: $actualHash"
    }

    if (Test-Path $target) {
        Remove-Item -Recurse -Force $target
    }
    New-Item -ItemType Directory -Path $target -Force | Out-Null
    Expand-Archive -Path $archive -DestinationPath $target -Force
    $dotnet = Join-Path $target "dotnet.exe"
    if (-not (Test-Dotnet8Sdk -Dotnet $dotnet)) {
        throw "Managed .NET 8 SDK verification failed"
    }
    return $dotnet
}

$python = Get-ExistingPython312
if (-not $python) {
    $python = Install-ManagedPython312
}

$dotnet = Get-ExistingDotnet8
if (-not $dotnet) {
    $dotnet = Install-ManagedDotnet8
}

[PSCustomObject]@{
    Python = $python
    Dotnet = $dotnet
}
