$ErrorActionPreference = "Continue"
$imgPath = "C:\work1\JSZN\APRK3588\GJ\Orangepi5plus_1.2.0_ubuntu_jammy_server_linux5.10.160\Orangepi5plus_1.2.0_ubuntu_jammy_server_linux5.10.160.img"
$diskNumber = 1
$physicalDrive = "\\.\PhysicalDrive$diskNumber"
$logPath = "C:\work1\JSZN\APRK3588\GJ\flash_log.txt"

"=== Script Started at $(Get-Date) ===" | Out-File -FilePath $logPath -Encoding UTF8
Write-Host "===== Orange Pi 5 Plus SD Card Flasher ====="
Write-Host ""

function Log {
    param($msg)
    $line = "[$(Get-Date -Format 'HH:mm:ss')] $msg"
    Write-Host $line
    Add-Content -Path $logPath -Value $line -Encoding UTF8
}

try {
    $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    Log "Admin权限: $isAdmin"
    if (-not $isAdmin) {
        Log "错误: 需要管理员权限!"
        throw "Not admin"
    }

    Log "镜像文件: $imgPath"
    Log "目标磁盘: $physicalDrive"

    if (-not (Test-Path $imgPath)) {
        Log "错误: 镜像文件不存在!"
        throw "Image not found"
    }

    $disk = Get-Disk -Number $diskNumber
    Log "磁盘信息: $($disk.FriendlyName) | $([math]::Round($disk.Size/1GB,2))GB | $($disk.BusType)"

    if ($disk.BusType -ne "USB") {
        Log "安全错误: Disk $diskNumber 不是USB设备!"
        throw "Safety check failed"
    }
    if ($disk.Size -gt 200GB) {
        Log "安全错误: 磁盘大小超过200GB!"
        throw "Safety check failed"
    }
    Log "安全检查通过"

    Log "步骤1: 清空磁盘分区..."
    $dpScript = "$env:TEMP\dp_clean_$(Get-Random).txt"
    "select disk $diskNumber`r`nclean`r`nexit" | Out-File -FilePath $dpScript -Encoding ASCII
    $dpOut = & diskpart /s $dpScript 2>&1 | Out-String
    Log "diskpart 输出: $dpOut"
    Remove-Item $dpScript -Force -ErrorAction SilentlyContinue

    Start-Sleep -Seconds 3

    Log "步骤2: 打开镜像和物理磁盘..."
    $imgSize = (Get-Item $imgPath).Length
    Log "镜像大小: $([math]::Round($imgSize/1MB,2)) MB"

    $source = [System.IO.File]::Open($imgPath, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::Read)
    $dest = [System.IO.File]::Open($physicalDrive, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
    Log "文件句柄打开成功"

    Log "步骤3: 开始写入数据..."
    $bufferSize = 4MB
    $buffer = New-Object byte[] $bufferSize
    $totalWritten = 0
    $startTime = Get-Date
    $lastReport = $startTime

    while (($bytesRead = $source.Read($buffer, 0, $bufferSize)) -gt 0) {
        $dest.Write($buffer, 0, $bytesRead)
        $totalWritten += $bytesRead

        $now = Get-Date
        if (($now - $lastReport).TotalSeconds -ge 3) {
            $progress = [math]::Round(($totalWritten / $imgSize) * 100, 1)
            $elapsed = ($now - $startTime).TotalSeconds
            $speedMBs = if ($elapsed -gt 0) { [math]::Round(($totalWritten / 1MB) / $elapsed, 2) } else { 0 }
            $writtenMB = [math]::Round($totalWritten / 1MB, 0)
            $totalMB = [math]::Round($imgSize / 1MB, 0)
            Log "进度: $progress% ($writtenMB / $totalMB MB) - 速度: $speedMBs MB/s"
            $lastReport = $now
        }
    }

    Log "步骤4: 刷新缓冲..."
    $dest.Flush()
    $dest.Close()
    $source.Close()

    $elapsed = ((Get-Date) - $startTime).TotalSeconds
    Log "==============================="
    Log "✅ 写入完成!"
    Log "总计: $([math]::Round($totalWritten/1MB,2)) MB"
    Log "耗时: $([math]::Round($elapsed,1)) 秒"
    Log "==============================="
    Log "请安全弹出SD卡, 插入Orange Pi 5 Plus启动!"

} catch {
    Log "❌ 异常: $($_.Exception.Message)"
    Log "位置: $($_.ScriptStackTrace)"
}

Log "=== 脚本结束 ==="
Write-Host ""
Write-Host "============================================="
Write-Host "脚本已完成。请查看上方信息。"
Write-Host "日志保存在: $logPath"
Write-Host "============================================="
