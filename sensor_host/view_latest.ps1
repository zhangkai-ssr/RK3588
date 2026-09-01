# view_latest.ps1 — pull the latest EMG dump from Orange Pi and open viewer
# Usage:
#   .\view_latest.ps1                  # latest emg_*.bin from data/
#   .\view_latest.ps1 -Round 1         # /tmp/round1_emg.npz
#   .\view_latest.ps1 -Live            # live tail mode (requires .bin file)

param(
    [string]$Host_  = "172.16.212.170",
    [string]$User  = "orangepi",
    [int]$Round    = 0,
    [switch]$Live,
    [double]$Window = 5.0,
    [ValidateSet("raw","hpf","notch","both")]
    [string]$Filter = "raw"
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$viewer    = Join-Path $scriptDir "emg_viewer.py"

if ($Round -gt 0) {
    $remote = "/tmp/round${Round}_emg.npz"
    $local  = Join-Path $scriptDir "round${Round}_emg.npz"
    Write-Host "Pulling round $Round NPZ..."
    & scp "${User}@${Host_}:${remote}" $local
    if ($LASTEXITCODE -ne 0) { Write-Host "scp failed"; exit 1 }
    python $viewer --file $local --window $Window --filter $Filter
    return
}

if ($Live) {
    # Live tail: need a directory of .bin files locally OR mount remote.
    # Simpler: poll the latest .bin via scp every refresh.
    Write-Host "Live mode: pulling latest emg_*.bin every 2 s..."
    while ($true) {
        $latest = ssh "${User}@${Host_}" "ls -t /home/orangepi/sensor_host/data/emg_*.bin 2>/dev/null | head -1"
        if ($latest) {
            $local = Join-Path $scriptDir "live_emg.bin"
            & scp "${User}@${Host_}:${latest}" $local 2>$null
            # Show the latest pulled snapshot
            Start-Process -NoNewWindow -Wait -FilePath "python" `
                -ArgumentList @($viewer, "--file", $local, "--window", $Window,
                                "--filter", $Filter, "--save",
                                (Join-Path $scriptDir "live_emg.png"), "--no-show")
            # Display the PNG inline (simplest portable approach)
            Start-Process (Join-Path $scriptDir "live_emg.png")
        }
        Start-Sleep -Seconds 5
    }
    return
}

# Default: pull latest emg_*.bin and view
$latest = ssh "${User}@${Host_}" "ls -t /home/orangepi/sensor_host/data/emg_*.bin 2>/dev/null | head -1"
if (-not $latest) {
    Write-Host "No emg_*.bin found on $Host_. Try -Round 1 for the Phase3 reports."
    exit 1
}
Write-Host "Pulling $latest..."
$local = Join-Path $scriptDir "latest_emg.bin"
& scp "${User}@${Host_}:${latest}" $local
if ($LASTEXITCODE -ne 0) { Write-Host "scp failed"; exit 1 }
python $viewer --file $local --window $Window --filter $Filter
