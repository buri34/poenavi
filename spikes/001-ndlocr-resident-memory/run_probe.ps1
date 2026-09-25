param(
    [int]$RepeatCount = 5,
    [int]$IdleSeconds = 300
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$version = "1.3.1"
$sourceHash = "e510d3a7b878395ea9de0bdd365711b699e5fd430b5c7e23a40e918e913fd1f2"
$probeRoot = Join-Path $env:LOCALAPPDATA "PoENavi\NdlocrResidentMemoryProbe"
$cacheRoot = Join-Path $probeRoot "cache-$version"
$runsRoot = Join-Path $probeRoot "runs"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$runRoot = Join-Path $runsRoot $timestamp
$control = Join-Path $runRoot "control"
$archive = Join-Path $cacheRoot "ndlocr-lite-$version.zip"
$sourceRoot = Join-Path $cacheRoot "ndlocr-lite-$version"
$venv = Join-Path $cacheRoot "venv"
$python = Join-Path $venv "Scripts\python.exe"
$helperRoot = Join-Path $cacheRoot "dist\PoENaviNdlOcrResidentProbe"
$helper = Join-Path $helperRoot "PoENaviNdlOcrResidentProbe.exe"
$serverSource = Join-Path $PSScriptRoot "ndlocr_resident_server.py"
$localServerSource = Join-Path $cacheRoot "ndlocr_resident_server.py"
$fixtureSource = Join-Path $repo "tests\fixtures\poetore\poe2\desecration\reported-spear-physical-read-failed.png"
$fixture = Join-Path $runRoot "reported-spear-physical-read-failed.png"

function Write-Utf8NoBom {
    param([string]$Path, [string]$Value)
    [System.IO.File]::WriteAllText($Path, $Value, [System.Text.UTF8Encoding]::new($false))
}

function Get-MemorySample {
    param([int]$ProcessId, [string]$Stage, [double]$ElapsedSeconds)
    $item = Get-Process -Id $ProcessId -ErrorAction Stop
    return [ordered]@{
        stage = $Stage
        elapsed_seconds = [Math]::Round($ElapsedSeconds, 3)
        working_set_mib = [Math]::Round($item.WorkingSet64 / 1MB, 2)
        private_memory_mib = [Math]::Round($item.PrivateMemorySize64 / 1MB, 2)
        peak_working_set_mib = [Math]::Round($item.PeakWorkingSet64 / 1MB, 2)
        cpu_seconds = [Math]::Round($item.CPU, 3)
        thread_count = $item.Threads.Count
        handle_count = $item.HandleCount
    }
}

function Wait-JsonFile {
    param([string]$Path, [int]$TimeoutSeconds)
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (Test-Path -LiteralPath $Path -PathType Leaf) {
            return Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
        }
        Start-Sleep -Milliseconds 100
    }
    throw "Timed out waiting for $Path"
}

if ($RepeatCount -lt 2) { throw "RepeatCount must be at least 2." }
if ($IdleSeconds -lt 0) { throw "IdleSeconds cannot be negative." }
if (-not (Test-Path -LiteralPath $fixtureSource -PathType Leaf)) { throw "Fixture not found: $fixtureSource" }

New-Item -ItemType Directory -Path $cacheRoot, $runRoot, $control -Force | Out-Null
Copy-Item -LiteralPath $serverSource -Destination $localServerSource -Force
Copy-Item -LiteralPath $fixtureSource -Destination $fixture -Force
$bootstrap = Join-Path $repo "scripts\ensure_windows_build_tools.ps1"
$toolOutput = @(& $bootstrap)
$buildPython = $toolOutput[-1].Python
if (-not (Test-Path -LiteralPath $buildPython -PathType Leaf)) {
    throw "Python 3.12 bootstrap failed."
}

if (-not (Test-Path -LiteralPath $archive -PathType Leaf)) {
    Write-Host "Downloading pinned NDLOCR-Lite $version source..."
    Invoke-WebRequest -Uri "https://github.com/ndl-lab/ndlocr-lite/archive/refs/tags/$version.zip" -OutFile $archive
}
$actualHash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLower()
if ($actualHash -ne $sourceHash) { throw "NDLOCR source hash mismatch: $actualHash" }
if (-not (Test-Path -LiteralPath $sourceRoot -PathType Container)) {
    Expand-Archive -LiteralPath $archive -DestinationPath $cacheRoot
}
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    & $buildPython -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw "Failed to create probe environment." }
}
$requirementsHash = (Get-FileHash (Join-Path $repo "requirements-ndlocr.txt") -Algorithm SHA256).Hash.ToLower()
$readyMarker = Join-Path $venv ".ready-$requirementsHash"
if (-not (Test-Path -LiteralPath $readyMarker -PathType Leaf)) {
    Write-Host "Preparing pinned NDLOCR probe dependencies (first run only)..."
    & $python -m pip install --disable-pip-version-check -r (Join-Path $repo "requirements-ndlocr.txt") "PyInstaller==6.22.0"
    if ($LASTEXITCODE -ne 0) { throw "Failed to install probe dependencies." }
    New-Item -ItemType File -Path $readyMarker -Force | Out-Null
}

$serverHash = (Get-FileHash -LiteralPath $localServerSource -Algorithm SHA256).Hash.ToLower()
$builtMarker = Join-Path $helperRoot ".server-$serverHash"
if (-not (Test-Path -LiteralPath $helper -PathType Leaf) -or -not (Test-Path -LiteralPath $builtMarker -PathType Leaf)) {
    Write-Host "Building the independent persistent NDLOCR probe..."
    Remove-Item (Join-Path $cacheRoot "dist"), (Join-Path $cacheRoot "build") -Recurse -Force -ErrorAction SilentlyContinue
    & $python -m PyInstaller --noconfirm --clean --noupx --onedir --console `
        --name PoENaviNdlOcrResidentProbe `
        --distpath (Join-Path $cacheRoot "dist") `
        --workpath (Join-Path $cacheRoot "build") `
        --paths (Join-Path $sourceRoot "src") `
        --add-data "$(Join-Path $sourceRoot 'src\model');model" `
        --add-data "$(Join-Path $sourceRoot 'src\config');config" `
        $localServerSource
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $helper -PathType Leaf)) {
        throw "Persistent NDLOCR probe build failed."
    }
    New-Item -ItemType File -Path $builtMarker -Force | Out-Null
}

$samples = [System.Collections.Generic.List[object]]::new()
$requests = [System.Collections.Generic.List[object]]::new()
$watch = [System.Diagnostics.Stopwatch]::StartNew()
$process = Start-Process -FilePath $helper -ArgumentList @("--control-dir", "`"$control`"") -WindowStyle Hidden -PassThru
try {
    $readyPath = Join-Path $control "ready.json"
    $nextSample = 0.0
    while (-not (Test-Path -LiteralPath $readyPath -PathType Leaf)) {
        if ($process.HasExited) { throw "Probe exited during model startup with code $($process.ExitCode)." }
        if ($watch.Elapsed.TotalSeconds -ge 120) { throw "Timed out loading NDLOCR models." }
        if ($watch.Elapsed.TotalSeconds -ge $nextSample) {
            $samples.Add((Get-MemorySample $process.Id "startup" $watch.Elapsed.TotalSeconds))
            $nextSample += 0.25
        }
        Start-Sleep -Milliseconds 50
    }
    $ready = Wait-JsonFile $readyPath 2
    $wallStartupMs = $watch.Elapsed.TotalMilliseconds
    $samples.Add((Get-MemorySample $process.Id "ready" $watch.Elapsed.TotalSeconds))

    for ($index = 1; $index -le $RepeatCount; $index++) {
        $responsePath = Join-Path $control ("response-{0:D2}.json" -f $index)
        $requestPath = Join-Path $control ("request-{0:D2}.json" -f $index)
        $request = [ordered]@{ image = $fixture; response = $responsePath }
        Write-Utf8NoBom $requestPath ($request | ConvertTo-Json -Depth 4)
        $response = Wait-JsonFile $responsePath 120
        if (-not $response.ok) { throw "NDLOCR request failed: $($response.error)" }
        $requests.Add([ordered]@{
            index = $index
            inference_ms = [double]$response.elapsed_ms
            expected_text_found = [bool]$response.expected_text_found
            minimum_confidence = $response.minimum_confidence
        })
        $samples.Add((Get-MemorySample $process.Id ("request_{0}" -f $index) $watch.Elapsed.TotalSeconds))
    }

    $idleStarted = [System.Diagnostics.Stopwatch]::StartNew()
    $idlePoints = @(0, 30, 60, 180, 300) | Where-Object { $_ -le $IdleSeconds }
    if ($idlePoints[-1] -ne $IdleSeconds) { $idlePoints += $IdleSeconds }
    foreach ($point in $idlePoints) {
        while ($idleStarted.Elapsed.TotalSeconds -lt $point) { Start-Sleep -Milliseconds 200 }
        $samples.Add((Get-MemorySample $process.Id ("idle_{0}s" -f $point) $watch.Elapsed.TotalSeconds))
    }

    $summary = [ordered]@{
        schema_version = 1
        engine = "NDLOCR-Lite $version persistent spike"
        process_id = $process.Id
        model_startup_ms = [double]$ready.startup_ms
        wall_startup_ms = [Math]::Round($wallStartupMs, 3)
        repeat_count = $RepeatCount
        idle_seconds = $IdleSeconds
        all_expected_text_found = @($requests | Where-Object { -not $_.expected_text_found }).Count -eq 0
        requests = $requests
        memory_samples = $samples
    }
    $summaryPath = Join-Path $runRoot "summary.json"
    Write-Utf8NoBom $summaryPath ($summary | ConvertTo-Json -Depth 8)

    $peakWorking = ($samples | Measure-Object peak_working_set_mib -Maximum).Maximum
    $peakPrivate = ($samples | Measure-Object private_memory_mib -Maximum).Maximum
    $requestRows = ($requests | ForEach-Object { "<tr><td>$($_.index)</td><td>$($_.inference_ms)</td><td>$($_.expected_text_found)</td><td>$($_.minimum_confidence)</td></tr>" }) -join "`n"
    $memoryRows = ($samples | ForEach-Object { "<tr><td>$($_.stage)</td><td>$($_.elapsed_seconds)</td><td>$($_.working_set_mib)</td><td>$($_.private_memory_mib)</td><td>$($_.peak_working_set_mib)</td><td>$($_.cpu_seconds)</td></tr>" }) -join "`n"
    $html = @"
<!doctype html><meta charset="utf-8"><title>NDLOCR常駐RAM検証</title>
<style>body{font-family:Segoe UI,sans-serif;max-width:1100px;margin:32px auto;padding:0 20px}table{border-collapse:collapse;width:100%;margin:16px 0}th,td{border:1px solid #bbb;padding:6px;text-align:right}th:first-child,td:first-child{text-align:left}.ok{color:#087f23;font-weight:bold}</style>
<h1>NDLOCR常駐RAM検証</h1><p class="ok">物理64%認識: $($summary.all_expected_text_found)</p>
<ul><li>モデル読込: $($summary.model_startup_ms) ms</li><li>最大Working Set: $peakWorking MiB</li><li>最大Private Memory: $peakPrivate MiB</li><li>アイドル計測: $IdleSeconds 秒</li></ul>
<h2>連続OCR</h2><table><tr><th>回</th><th>推論 ms</th><th>物理64%</th><th>最低信頼度</th></tr>$requestRows</table>
<h2>メモリ推移</h2><table><tr><th>段階</th><th>経過秒</th><th>Working Set MiB</th><th>Private MiB</th><th>Peak Working MiB</th><th>CPU秒</th></tr>$memoryRows</table>
<p>独立検証ツールの結果です。PoENavi本体のOCR動作は変更していません。</p>
"@
    $reportPath = Join-Path $runRoot "report.html"
    Write-Utf8NoBom $reportPath $html
    Write-Host "Summary: $summaryPath" -ForegroundColor Green
    Write-Host "Report:  $reportPath" -ForegroundColor Green
    Start-Process $reportPath
}
finally {
    Write-Utf8NoBom (Join-Path $control "shutdown.json") "{}"
    if (-not $process.HasExited) {
        if (-not $process.WaitForExit(5000)) { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
    }
}
