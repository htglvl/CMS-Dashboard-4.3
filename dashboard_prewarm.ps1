param(
    [switch]$Start,
    [switch]$Stop,
    [int]$OwnerProcessId = 0,
    [int]$IntervalSeconds = 86400,
    [int]$BrowserTimeoutSeconds = 120
)

$ErrorActionPreference = 'Stop'
$projectDirectory = $PSScriptRoot
$hash = [System.Security.Cryptography.SHA256]::Create()
try {
    $key = [BitConverter]::ToString($hash.ComputeHash(
        [Text.Encoding]::UTF8.GetBytes($projectDirectory.ToLowerInvariant())
    )).Replace('-', '').Substring(0, 24)
} finally { $hash.Dispose() }
$mutexName = "Local\CMSPrewarm-$key"
$stopName = "Local\CMSPrewarmStop-$key"

if ($Stop) {
    try {
        $signal = [Threading.EventWaitHandle]::OpenExisting($stopName)
        try { [void]$signal.Set() } finally { $signal.Dispose() }
    } catch [Threading.WaitHandleCannotBeOpenedException] { }
    exit 0
}

if ($Start) {
    # This short-lived process was invoked directly by the launcher cmd.exe.
    $launcherId = (Get-CimInstance Win32_Process -Filter "ProcessId=$PID").ParentProcessId
    $launcher = Get-Process -Id $launcherId
    $arguments = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -OwnerProcessId {1} -IntervalSeconds {2} -BrowserTimeoutSeconds {3}' -f $PSCommandPath, $launcher.Id, $IntervalSeconds, $BrowserTimeoutSeconds
    Start-Process -FilePath "$PSHOME\powershell.exe" -ArgumentList $arguments -WindowStyle Hidden | Out-Null
    exit 0
}

if ($OwnerProcessId -le 0 -or $IntervalSeconds -le 0 -or $BrowserTimeoutSeconds -le 0) {
    throw 'An owner process and positive timing values are required.'
}
$mutex = [Threading.Mutex]::new($false, $mutexName)
$ownsMutex = $false
$signal = $null
$browserProcess = $null
try {
    try { $ownsMutex = $mutex.WaitOne(0) }
    catch [Threading.AbandonedMutexException] { $ownsMutex = $true }
    if (-not $ownsMutex) { exit 0 }

    $owner = Get-Process -Id $OwnerProcessId -ErrorAction SilentlyContinue
    if (-not $owner) { exit 0 }
    # Keep the process handle so PID reuse cannot attach us to another launcher.
    $null = $owner.Handle
    $signal = [Threading.EventWaitHandle]::new($false, [Threading.EventResetMode]::ManualReset, $stopName)
    [void]$signal.Reset()
    $logDirectory = Join-Path $projectDirectory 'logs'
    [void][IO.Directory]::CreateDirectory($logDirectory)
    $logFile = Join-Path $logDirectory 'dashboard-prewarm.log'
    $profileDirectory = Join-Path $env:TEMP "cms-dashboard-prewarm-$key"
    $browser = @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
        "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe"
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $browser) { Add-Content $logFile 'Chrome or Edge not found; prewarmer stopped.'; exit 0 }

    while (-not $owner.HasExited -and -not $signal.WaitOne(0)) {
        Add-Content $logFile "[$(Get-Date -Format o)] Prewarming dashboard."
        try {
            $browserArguments = '--headless=new --disable-gpu --no-first-run --no-default-browser-check --user-data-dir="{0}" --virtual-time-budget=30000 --dump-dom http://127.0.0.1:8501/home' -f $profileDirectory
            $browserProcess = Start-Process -FilePath $browser -ArgumentList $browserArguments -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDirectory 'prewarm-browser.html') -RedirectStandardError (Join-Path $logDirectory 'prewarm-browser.log')
            $deadline = [DateTime]::UtcNow.AddSeconds($BrowserTimeoutSeconds)
            while (-not $browserProcess.HasExited -and [DateTime]::UtcNow -lt $deadline -and -not $owner.HasExited -and -not $signal.WaitOne(1000)) { }
        } catch {
            Add-Content $logFile "[$(Get-Date -Format o)] Browser failed: $($_.Exception.Message)"
        } finally {
            if ($browserProcess) {
                if (-not $browserProcess.HasExited) {
                    & taskkill.exe /PID $browserProcess.Id /T /F 2>&1 | Out-Null
                }
                $browserProcess.Dispose()
                $browserProcess = $null
            }
        }
        $nextRun = [DateTime]::UtcNow.AddSeconds($IntervalSeconds)
        while ([DateTime]::UtcNow -lt $nextRun -and -not $owner.HasExited -and -not $signal.WaitOne(1000)) { }
    }
    Add-Content $logFile "[$(Get-Date -Format o)] Prewarmer stopped."
} finally {
    if ($signal) { $signal.Dispose() }
    if ($ownsMutex) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
