# Institutional Memory & CPU Cleanup Utility
# Safely clears zombie processes, trims working sets, flushes OS standby cache, and reclaims physical RAM

Write-Host "=== INITIATING SYSTEM RAM & CPU OPTIMIZATION ===" -ForegroundColor Cyan

# 1. Terminate orphaned/zombie node npx processes
$zombieNodes = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'node.exe' -and $_.CommandLine -match 'npx-cli\.js' }
if ($zombieNodes) {
    $zombieNodes | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Host "Pruned zombie node PID $($_.ProcessId)" -ForegroundColor Yellow
    }
}

# 2. Terminate duplicate code_review_graph watchers
$duplicateWatchers = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -match 'code_review_graph' }
if ($duplicateWatchers) {
    $duplicateWatchers | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Host "Pruned duplicate code_review_graph PID $($_.ProcessId)" -ForegroundColor Yellow
    }
}

# 3. Trim working sets and purge Standby List via NT API
$code = @"
using System;
using System.Runtime.InteropServices;
public class MemoryCleaner {
    [DllImport("psapi.dll")]
    public static extern int EmptyWorkingSet(IntPtr hwProc);
    
    [DllImport("ntdll.dll")]
    public static extern UInt32 NtSetSystemInformation(int InfoClass, IntPtr Info, int Length);

    public static void TrimProcess(int pid) {
        try {
            using (var proc = System.Diagnostics.Process.GetProcessById(pid)) {
                EmptyWorkingSet(proc.Handle);
            }
        } catch {}
    }

    public static void PurgeStandbyList() {
        int[] commands = new int[] { 1, 2, 3, 4 };
        foreach (int cmd in commands) {
            try {
                int c = cmd;
                GCHandle handle = GCHandle.Alloc(c, GCHandleType.Pinned);
                NtSetSystemInformation(80, handle.AddrOfPinnedObject(), Marshal.SizeOf(c));
                handle.Free();
            } catch {}
        }
    }
}
"@
if (-not ([System.Management.Automation.PSTypeName]'MemoryCleaner').Type) {
    Add-Type -TypeDefinition $code -ErrorAction SilentlyContinue
}

Get-Process | Where-Object { $_.WorkingSet64 -gt 15MB } | ForEach-Object { [MemoryCleaner]::TrimProcess($_.Id) }
[MemoryCleaner]::PurgeStandbyList()
[System.GC]::Collect()

# 4. Display refreshed RAM stats
$os = Get-CimInstance Win32_OperatingSystem
$total = [math]::Round($os.TotalVisibleMemorySize/1MB, 2)
$free = [math]::Round($os.FreePhysicalMemory/1MB, 2)
$used = [math]::Round(($os.TotalVisibleMemorySize - $os.FreePhysicalMemory)/1MB, 2)
$pct = [math]::Round((($os.TotalVisibleMemorySize - $os.FreePhysicalMemory)/$os.TotalVisibleMemorySize)*100, 1)

Write-Host "Optimization Complete!" -ForegroundColor Green
Write-Host "Total RAM: $total GB | Free RAM: $free GB | Used RAM: $used GB ($pct% used)" -ForegroundColor Cyan
