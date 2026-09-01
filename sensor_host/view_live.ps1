# view_live.ps1 — real-time 16-ch EMG viewer on Windows
# Streams the newest emg_*.bin on the Orange Pi via SSH, decodes 16 channels,
# and plots a rolling window (default 5 s) refreshing every 200 ms.
#
# Usage:
#   .\view_live.ps1                       # defaults
#   .\view_live.ps1 -Window 3             # show last 3 seconds
#   .\view_live.ps1 -RefreshMs 100        # faster updates (more CPU)
#   .\view_live.ps1 -Host 172.16.212.170  # different host

param(
    [switch]$Listen,                           # TCP server mode (ESP32 → Windows direct)
    [int]$Port          = 3333,
    [string]$Record,                           # record to this file (sensor-host .bin format)
    [switch]$RecordAuto,                       # auto-name emg_DIRECT_TIMESTAMP.bin
    [string]$Host_      = "172.16.212.170",   # SSH-tail mode
    [string]$User       = "orangepi",
    [string]$DataDir    = "/home/orangepi/sensor_host/data",
    [double]$Window     = 5.0,
    [int]$RefreshMs     = 250
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$viewer    = Join-Path $scriptDir "emg_live_win.py"

if (-not (Test-Path $viewer)) {
    Write-Host "missing $viewer"
    exit 1
}

if ($Listen) {
    $cmd = @("--listen", "--port", $Port, "--window", $Window, "--refresh-ms", $RefreshMs)
    if ($Record)     { $cmd += @("--record", $Record) }
    if ($RecordAuto) { $cmd += @("--record-auto") }
    python $viewer @cmd
} else {
    python $viewer `
        --host $Host_ `
        --user $User `
        --data-dir $DataDir `
        --window $Window `
        --refresh-ms $RefreshMs
}
