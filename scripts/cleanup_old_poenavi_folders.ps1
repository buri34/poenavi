param(
    [Parameter(Mandatory = $true)]
    [string]$Root,
    [Parameter(Mandatory = $true)]
    [string]$ProtectPath,
    [ValidateRange(1, 20)]
    [int]$KeepSnapshots = 3,
    [ValidateRange(0, 20)]
    [int]$KeepBuildOutputs = 1,
    [switch]$PreviewOnly
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$snapshotPattern = '^poenavi-windows-[0-9a-f]{7,10}$'
$incompletePattern = '^poenavi-windows-[0-9a-f]{7,10}-incomplete-[0-9]{8}-[0-9]{4,6}$'
$outputPattern = '^poenavi-build-output-[0-9a-f]{7,10}-[0-9]{8}-[0-9]{6}$'
$pathTrimCharacters = [char[]]"\/"

function Resolve-Folder([string]$Path, [string]$Label) {
    $resolved = Resolve-Path -LiteralPath $Path -ErrorAction Stop
    $item = Get-Item -LiteralPath $resolved.Path -Force -ErrorAction Stop
    if (-not $item.PSIsContainer) {
        throw "$Label is not a folder: $Path"
    }
    return $item.FullName.TrimEnd($pathTrimCharacters)
}

function Get-FreeBytes([string]$Path) {
    try {
        $qualifier = Split-Path -Qualifier $Path
        if (-not $qualifier) {
            return $null
        }
        return (Get-PSDrive -Name $qualifier.TrimEnd(':')).Free
    }
    catch {
        return $null
    }
}

$resolvedRoot = Resolve-Folder $Root "Cleanup root"
$resolvedProtect = Resolve-Folder $ProtectPath "Protected snapshot"
$driveRoot = [System.IO.Path]::GetPathRoot($resolvedRoot).TrimEnd($pathTrimCharacters)
if (-not $driveRoot -or $resolvedRoot -eq $driveRoot) {
    throw "Refusing to use a drive root as the cleanup root: $resolvedRoot"
}

$protectedItem = Get-Item -LiteralPath $resolvedProtect -Force
if ($protectedItem.Parent.FullName.TrimEnd($pathTrimCharacters) -ne $resolvedRoot) {
    throw "Protected snapshot must be a direct child of the cleanup root"
}
if ($protectedItem.Name -notmatch $snapshotPattern) {
    throw "Protected folder is not a commit snapshot: $($protectedItem.Name)"
}

$folders = @(Get-ChildItem -LiteralPath $resolvedRoot -Directory -Force)
$snapshots = @($folders | Where-Object { $_.Name -match $snapshotPattern })
$incomplete = @($folders | Where-Object { $_.Name -match $incompletePattern })
$buildOutputs = @($folders | Where-Object { $_.Name -match $outputPattern })

$keptSnapshots = @(
    $snapshots |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First $KeepSnapshots
)
$keptSnapshotPaths = @($keptSnapshots | ForEach-Object { $_.FullName })
if ($resolvedProtect -notin $keptSnapshotPaths) {
    $keptSnapshotPaths += $resolvedProtect
}

$keptOutputs = @(
    $buildOutputs |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First $KeepBuildOutputs
)
$keptOutputPaths = @($keptOutputs | ForEach-Object { $_.FullName })

$candidates = @(
    $snapshots | Where-Object { $_.FullName -notin $keptSnapshotPaths }
    $incomplete
    $buildOutputs | Where-Object { $_.FullName -notin $keptOutputPaths }
) | Sort-Object FullName -Unique

foreach ($candidate in $candidates) {
    $parent = $candidate.Parent.FullName.TrimEnd($pathTrimCharacters)
    $allowedName = (
        $candidate.Name -match $snapshotPattern -or
        $candidate.Name -match $incompletePattern -or
        $candidate.Name -match $outputPattern
    )
    if ($parent -ne $resolvedRoot -or -not $allowedName) {
        throw "Safety check rejected cleanup target: $($candidate.FullName)"
    }
    if (($candidate.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Safety check rejected a linked folder: $($candidate.FullName)"
    }
    if ($candidate.FullName.TrimEnd($pathTrimCharacters) -eq $resolvedProtect) {
        throw "Safety check attempted to target the protected snapshot"
    }
}

Write-Host "PoENavi SMB cleanup" -ForegroundColor Cyan
Write-Host "Root: $resolvedRoot"
Write-Host "Protected current snapshot: $resolvedProtect" -ForegroundColor Green
Write-Host "Keeping $($keptSnapshotPaths.Count) snapshot folder(s) and $($keptOutputPaths.Count) build output folder(s)."
foreach ($path in @($keptSnapshotPaths + $keptOutputPaths) | Sort-Object -Unique) {
    Write-Host "  KEEP: $([System.IO.Path]::GetFileName($path))" -ForegroundColor Green
}
Write-Host "Other PoENavi folders, including diagnostics and test images, are not targeted."
Write-Host ""

if ($candidates.Count -eq 0) {
    Write-Host "No old PoENavi snapshot or build output folder needs cleanup." -ForegroundColor Green
    exit 0
}

Write-Host "Folders selected for permanent deletion: $($candidates.Count)" -ForegroundColor Yellow
foreach ($candidate in $candidates) {
    Write-Host "  $($candidate.Name)"
}

if ($PreviewOnly) {
    Write-Host ""
    Write-Host "Preview only. Nothing was deleted." -ForegroundColor Green
    exit 0
}

Write-Host ""
Write-Host "WARNING: Deletion from this SMB share is permanent and does not use the Recycle Bin." -ForegroundColor Red
$confirmation = Read-Host "Type DELETE to permanently remove only the folders listed above"
if ($confirmation -cne "DELETE") {
    Write-Host "Cancelled. Nothing was deleted." -ForegroundColor Green
    exit 0
}

$freeBefore = Get-FreeBytes $resolvedRoot
$failures = @()
foreach ($candidate in $candidates) {
    try {
        Write-Host "Deleting $($candidate.Name)..."
        Remove-Item -LiteralPath $candidate.FullName -Recurse -Force -ErrorAction Stop
    }
    catch {
        $failures += "$($candidate.Name): $($_.Exception.Message)"
    }
}

$freeAfter = Get-FreeBytes $resolvedRoot
if ($null -ne $freeBefore -and $null -ne $freeAfter -and $freeAfter -ge $freeBefore) {
    $freedGiB = [math]::Round(($freeAfter - $freeBefore) / 1GB, 2)
    Write-Host "Freed approximately $freedGiB GiB." -ForegroundColor Green
}

if ($failures.Count -gt 0) {
    Write-Host "Some folders could not be deleted:" -ForegroundColor Red
    $failures | ForEach-Object { Write-Host "  $_" }
    exit 1
}

Write-Host "Cleanup completed. Deleted $($candidates.Count) folder(s)." -ForegroundColor Green
