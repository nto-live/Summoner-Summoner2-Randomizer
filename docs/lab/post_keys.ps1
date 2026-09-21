# post_keys.ps1 - drive PCSX2 in Session 0 with *posted window messages*.
#
# SendInput needs a foreground window, and Session 0 has none (foreground=0). So instead we
# post the message sequence a focused window would receive, straight to the window handle:
#   WM_ACTIVATE (WA_ACTIVE) -> WM_SETFOCUS -> WM_KEYDOWN/WM_KEYUP
# Qt delivers WM_KEYDOWN to the QWindow that receives it, and SDL's Windows backend accepts
# WM_KEYDOWN when its window believes it has focus - so faking activation is the trick.
#
# Usage:
#   powershell -File post_keys.ps1 -List
#   powershell -File post_keys.ps1 -Hwnd 4653310 -Keys F8
#   powershell -File post_keys.ps1 -Hwnd 4653310 -Keys Return,K -HoldMs 120 -GapMs 500
param(
    [int]$Hwnd = 0,
    [string[]]$Keys = @("F8"),
    [int]$HoldMs = 120,
    [int]$GapMs = 500,
    [switch]$List,
    [switch]$NoActivate
)
$ErrorActionPreference = "Stop"

# -File passes arrays as one comma-joined string; split it back out.
$Keys = @($Keys | ForEach-Object { $_ -split ',' } | Where-Object { $_ -ne '' })

Add-Type -TypeDefinition @"
using System;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;

public class K2 {
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr p);
    [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr parent, EnumProc cb, IntPtr p);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint msg, IntPtr w, IntPtr l);
    [DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr h, uint msg, IntPtr w, IntPtr l);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
    public delegate bool EnumProc(IntPtr h, IntPtr p);

    public class W { public IntPtr H; public uint Pid; public string Title, Cls; public int Wd, Ht; }

    public static List<W> All(IntPtr parent) {
        var l = new List<W>();
        EnumProc cb = (h, p) => {
            uint pid; GetWindowThreadProcessId(h, out pid);
            RECT r; GetWindowRect(h, out r);
            var t = new StringBuilder(512); GetWindowText(h, t, 512);
            var c = new StringBuilder(256); GetClassName(h, c, 256);
            l.Add(new W { H = h, Pid = pid, Title = t.ToString(), Cls = c.ToString(), Wd = r.R - r.L, Ht = r.B - r.T });
            return true;
        };
        if (parent == IntPtr.Zero) EnumWindows(cb, IntPtr.Zero); else EnumChildWindows(parent, cb, IntPtr.Zero);
        return l;
    }

    public const uint WM_ACTIVATE = 0x0006, WM_SETFOCUS = 0x0007, WM_KILLFOCUS = 0x0008,
                      WM_KEYDOWN = 0x0100, WM_KEYUP = 0x0101, WM_CHAR = 0x0102, WM_SYSKEYDOWN = 0x0104;

    public static void Activate(IntPtr h) {
        PostMessage(h, WM_ACTIVATE, (IntPtr)1, IntPtr.Zero);   // WA_ACTIVE
        PostMessage(h, WM_SETFOCUS, IntPtr.Zero, IntPtr.Zero);
    }

    public static void Key(IntPtr h, int vk, int scan, bool up, bool system) {
        long lp = 1 | ((long)(scan & 0xFF) << 16) | (up ? (1L << 30) | (1L << 31) : 0);
        uint msg = system ? (up ? WM_KEYUP : WM_SYSKEYDOWN) : (up ? WM_KEYUP : WM_KEYDOWN);
        PostMessage(h, msg, (IntPtr)vk, (IntPtr)lp);
    }
}
"@

function Get-VkScan([string]$name) {
    switch ($name.ToLower()) {
        "return"   { return @(0x0D, 0x1C) }
        "enter"    { return @(0x0D, 0x1C) }
        "space"    { return @(0x20, 0x39) }
        "escape"   { return @(0x1B, 0x01) }
        "up"       { return @(0x26, 0x48) }
        "down"     { return @(0x28, 0x50) }
        "left"     { return @(0x25, 0x4B) }
        "right"    { return @(0x27, 0x4D) }
        "backspace"{ return @(0x08, 0x0E) }
        "tab"      { return @(0x09, 0x0F) }
        "f1"       { return @(0x70, 0x3B) }
        "f2"       { return @(0x71, 0x3C) }
        "f3"       { return @(0x72, 0x3D) }
        "f4"       { return @(0x73, 0x3E) }
        "f5"       { return @(0x74, 0x3F) }
        "f6"       { return @(0x75, 0x40) }
        "f7"       { return @(0x76, 0x41) }
        "f8"       { return @(0x77, 0x42) }
        "f9"       { return @(0x78, 0x43) }
        "f10"      { return @(0x79, 0x44) }
        "f11"      { return @(0x7A, 0x57) }
        "f12"      { return @(0x7B, 0x58) }
        default {
            if ($name.Length -eq 1) {
                $c = [char]::ToUpper($name[0])
                $scanTable = @{ 'A'=0x1E; 'B'=0x30; 'C'=0x2E; 'D'=0x20; 'E'=0x12; 'F'=0x21; 'G'=0x22; 'H'=0x23;
                                'I'=0x17; 'J'=0x24; 'K'=0x25; 'L'=0x26; 'M'=0x32; 'N'=0x31; 'O'=0x18; 'P'=0x19;
                                'Q'=0x10; 'R'=0x13; 'S'=0x1F; 'T'=0x14; 'U'=0x16; 'V'=0x2F; 'W'=0x11; 'X'=0x2D;
                                'Y'=0x15; 'Z'=0x2C }
                if ($scanTable.ContainsKey($c.ToString())) { return @([int][char]$c, $scanTable[$c.ToString()]) } else { throw "no scan code for $name" }
            }
            throw "unknown key: $name"
        }
    }
}

$proc = Get-Process pcsx2* -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $proc) { throw "no PCSX2 process running" }

$tops = [K2]::All([IntPtr]::Zero) | Where-Object { $_.Pid -eq $proc.Id }
Write-Output "pid $($proc.Id) windows:"
$all = @()
foreach ($t in $tops) {
    Write-Output ("  TOP   hwnd={0,-10} {1,5}x{2,-5} class='{3}' title='{4}'" -f $t.H, $t.Wd, $t.Ht, $t.Cls, $t.Title)
    $all += $t
    foreach ($k in ([K2]::All($t.H))) {
        Write-Output ("    CH  hwnd={0,-10} {1,5}x{2,-5} class='{3}' title='{4}'" -f $k.H, $k.Wd, $k.Ht, $k.Cls, $k.Title)
        $all += $k
    }
}
if ($List) { exit 0 }

if ($Hwnd -eq 0) {
    # pick the display widget: the largest child/top window that is square-ish and big
    $target = $all | Where-Object { $_.Wd -gt 300 -and $_.Ht -gt 300 } | Sort-Object { $_.Wd * $_.Ht } -Descending | Select-Object -First 1
} else {
    $target = $all | Where-Object { $_.H -eq $Hwnd } | Select-Object -First 1
}
if (-not $target) { throw "no target window" }
Write-Output "target hwnd=$($target.H) $($target.Wd)x$($target.Ht) class='$($target.Cls)' title='$($target.Title)'"

if (-not $NoActivate) {
    [K2]::Activate($target.H)
    Start-Sleep -Milliseconds 400
    Write-Output "posted WM_ACTIVATE + WM_SETFOCUS"
}

for ($r = 1; $r -le 1; $r++) {
    foreach ($k in $Keys) {
        $vkScan = Get-VkScan $k
        [K2]::Key($target.H, $vkScan[0], $vkScan[1], $false, $false)
        Start-Sleep -Milliseconds $HoldMs
        [K2]::Key($target.H, $vkScan[0], $vkScan[1], $true, $false)
        Write-Output ("  posted {0} (vk=0x{1:X2} scan=0x{2:X2})" -f $k, $vkScan[0], $vkScan[1])
        Start-Sleep -Milliseconds $GapMs
    }
}
