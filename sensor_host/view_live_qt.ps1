# view_live_qt.ps1 — real-time 16-ch EMG viewer (PyQtGraph backend)
#
# Faster than the matplotlib version (view_live.ps1 -Listen) because
# PyQtGraph uses Qt's QPainter / OpenGL for rendering instead of matplotlib's
# CPU-only redraw. Targets 30 fps at 2 kHz / 16 channels.
#
# Usage:
#   .\view_live_qt.ps1                       # just view
#   .\view_live_qt.ps1 -RecordAuto           # also record to emg_DIRECT_*.bin
#   .\view_live_qt.ps1 -Record run1.bin      # record to a named file
#   .\view_live_qt.ps1 -Window 3 -Decimate 1 # 3 s history, no decimation

param(
    [int]$Port          = 3333,
    [string]$Record,
    [switch]$RecordAuto,
    [double]$Window     = 5.0,
    [int]$RefreshMs     = 33,
    [int]$Decimate      = 2
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$viewer    = Join-Path $scriptDir "emg_live_qt.py"

$cmd = @("--port", $Port, "--window", $Window,
         "--refresh-ms", $RefreshMs, "--decimate", $Decimate)
if ($Record)     { $cmd += @("--record", $Record) }
if ($RecordAuto) { $cmd += @("--record-auto") }
python $viewer @cmd
