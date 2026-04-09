[CmdletBinding()]
param(
    [ValidateSet("auto", "service", "static")]
    [string]$Mode = "auto",
    [string]$Path,
    [string]$ServiceUrl = "http://127.0.0.1:8000/",
    [switch]$NoAutoStart,
    [switch]$PrintOnly
)

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

function Resolve-IndexPath {
    param(
        [string]$ExplicitPath
    )

    if ($ExplicitPath) {
        $candidate = $ExplicitPath
        if (-not [System.IO.Path]::IsPathRooted($candidate)) {
            $candidate = Join-Path $repoRoot $candidate
        }
        if (-not (Test-Path -LiteralPath $candidate)) {
            throw "Index file not found: $candidate"
        }
        return (Resolve-Path -LiteralPath $candidate).Path
    }

    $outputRoot = Join-Path $repoRoot "output"
    if (-not (Test-Path -LiteralPath $outputRoot)) {
        throw "Output directory not found: $outputRoot"
    }

    $matches = Get-ChildItem -Path $outputRoot -Recurse -Filter index.html -File |
        Where-Object { $_.FullName -match '\\web\\index\.html$' } |
        Sort-Object LastWriteTimeUtc -Descending

    if (-not $matches) {
        throw "No exported web/index.html found under: $outputRoot"
    }

    return $matches[0].FullName
}

function Test-ServiceReady {
    param(
        [string]$BaseUrl
    )

    $healthUrl = ($BaseUrl.TrimEnd("/") + "/healthz")
    try {
        $response = Invoke-RestMethod -Uri $healthUrl -Method Get -TimeoutSec 2
        return ($response.ok -eq $true)
    } catch {
        return $false
    }
}

function Test-ServiceCompatible {
    param(
        [string]$BaseUrl
    )

    $templatesUrl = ($BaseUrl.TrimEnd("/") + "/api/pack-templates")
    try {
        $response = Invoke-WebRequest -Uri $templatesUrl -Method Get -TimeoutSec 2
        return ($response.StatusCode -eq 200)
    } catch {
        return $false
    }
}

function Get-ServiceProcessId {
    param(
        [string]$BaseUrl
    )

    try {
        $uri = [Uri]$BaseUrl
    } catch {
        return $null
    }

    $connection = Get-NetTCPConnection -State Listen -LocalPort $uri.Port -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $connection) {
        return $null
    }
    return $connection.OwningProcess
}

function Stop-ManagedService {
    param(
        [string]$BaseUrl
    )

    $procId = Get-ServiceProcessId -BaseUrl $BaseUrl
    if (-not $procId) {
        return $false
    }

    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $procId" -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        return $false
    }

    if ($process.CommandLine -and $process.CommandLine -like "*bilibili_crawler.py*serve*") {
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 500
        return $true
    }

    return $false
}

function Start-ServiceIfNeeded {
    param(
        [string]$BaseUrl,
        [switch]$DisableAutoStart
    )

    $serviceReady = Test-ServiceReady -BaseUrl $BaseUrl
    $serviceCompatible = $serviceReady -and (Test-ServiceCompatible -BaseUrl $BaseUrl)
    if ($serviceCompatible) {
        return $true
    }

    if ($DisableAutoStart) {
        return $false
    }

    if ($serviceReady -and -not $serviceCompatible) {
        Stop-ManagedService -BaseUrl $BaseUrl | Out-Null
    }

    $uri = [Uri]$BaseUrl
    $hostName = $uri.Host
    $port = $uri.Port

    Start-Process -FilePath "python" `
        -ArgumentList "bilibili_crawler.py", "serve", "--host", $hostName, "--port", "$port" `
        -WorkingDirectory $repoRoot `
        -WindowStyle Hidden | Out-Null

    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        Start-Sleep -Milliseconds 500
        if ((Test-ServiceReady -BaseUrl $BaseUrl) -and (Test-ServiceCompatible -BaseUrl $BaseUrl)) {
            return $true
        }
    }

    return $false
}

if ($Mode -eq "static") {
    $target = Resolve-IndexPath -ExplicitPath $Path
} else {
    $serviceReady = Start-ServiceIfNeeded -BaseUrl $ServiceUrl -DisableAutoStart:$NoAutoStart
    if ($serviceReady) {
        $target = $ServiceUrl
    } elseif ($Mode -eq "service") {
        throw "Service is not available: $ServiceUrl"
    } else {
        $target = Resolve-IndexPath -ExplicitPath $Path
    }
}

Write-Output $target

if (-not $PrintOnly) {
    Start-Process -FilePath $target
}
