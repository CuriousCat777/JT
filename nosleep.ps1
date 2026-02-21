# Prevents your Windows PC from sleeping — no installs or admin rights needed.
# Uses the Windows SetThreadExecutionState API to tell the OS "I'm still busy."
# Usage: powershell -ExecutionPolicy Bypass -File nosleep.ps1
# To stop: Ctrl+C

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class SleepPreventer {
    [DllImport("kernel32.dll")]
    public static extern uint SetThreadExecutionState(uint esFlags);
}
"@

$ES_CONTINUOUS        = [uint32]"0x80000000"
$ES_SYSTEM_REQUIRED   = [uint32]"0x00000001"
$ES_DISPLAY_REQUIRED  = [uint32]"0x00000002"

Write-Host "Keeping your computer awake... Press Ctrl+C to stop."

while ($true) {
    [SleepPreventer]::SetThreadExecutionState(
        $ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED -bor $ES_DISPLAY_REQUIRED
    ) | Out-Null
    Start-Sleep -Seconds 59
}
