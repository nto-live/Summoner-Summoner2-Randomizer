# pcsx2_ctl.ps1 - inspect / screenshot / key-inject an already-running PCSX2 in Session 0.
#
# Session 0 has no interactive desktop, but the HWNDs are real: PrintWindow() can render a
# window into a bitmap, and SendInput() injects at the driver level (real WM_KEYDOWN/WM_KEYUP),
# which is what SDL's Windows backend needs - PostMessage() alone is not enough.
#
# Usage:
#   powershell -File pcsx2_ctl.ps1 windows -Pid 2680
#   powershell -File pcsx2_ctl.ps1 shot    -Pid 2680 -Out F:\rando\S1\out\shot.png
#   powershell -File pcsx2_ctl.ps1 keys    -Pid 2680 -Keys Return,K -HoldMs 120 -GapMs 400
#   powershell -File pcsx2_ctl.ps1 keys    -Pid 2680 -Keys Down -Repeat 12 -HoldMs 60
param(
    [Parameter(Mandatory=$true)][string]$Action,
    [int]$TargetPid = 0,
    [string]$Out = "F:\rando\S1\out\shot.png",
    [string[]]$Keys = @("Return"),
    [int]$HoldMs = 120,
    [int]$GapMs = 400,
    [int]$Repeat = 1
)
$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @"
using System;
using System.Text;
using System.Drawing;
using System.Collections.Generic;
using System.Runtime.InteropServices;

public class P2 {
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr p);
    [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr parent, EnumProc cb, IntPtr p);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint flags);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern IntPtr SetFocus(IntPtr h);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
    [DllImport("user32.dll")] public static extern IntPtr GetFocus();
    [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr h);
    [DllImport("user32.dll")] public static extern bool AttachThreadInput(uint a, uint b, bool f);
    [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
    [DllImport("user32.dll")] public static extern uint SendInput(uint n, INPUT[] inputs, int size);
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
    public delegate bool EnumProc(IntPtr h, IntPtr p);

    [StructLayout(LayoutKind.Sequential)]
    public struct INPUT { public uint type; public InputUnion U; }
    [StructLayout(LayoutKind.Explicit)]
    public struct InputUnion {
        [FieldOffset(0)] public KEYBDINPUT ki;
        [FieldOffset(0)] public MOUSEINPUT mi;
        [FieldOffset(0)] public HARDWAREINPUT hi;
    }
    [StructLayout(LayoutKind.Sequential)]
    public struct KEYBDINPUT { public ushort wVk; public ushort wScan; public uint dwFlags; public uint time; public IntPtr dwExtraInfo; }
    [StructLayout(LayoutKind.Sequential)]
    public struct MOUSEINPUT { public int dx; public int dy; public uint mouseData; public uint dwFlags; public uint time; public IntPtr dwExtraInfo; }
    [StructLayout(LayoutKind.Sequential)]
    public struct HARDWAREINPUT { public uint uMsg; public ushort wParamL; public ushort wParamH; }

    public const uint INPUT_KEYBOARD = 1;
    public const uint KEYEVENTF_KEYUP = 0x0002;
    public const uint KEYEVENTF_SCANCODE = 0x0008;
    public const uint KEYEVENTF_EXTENDEDKEY = 0x0001;

    public class WinInfo { public IntPtr H; public uint Pid; public string Title, Cls; public int W, Ht; public bool Visible; }

    static string Text(IntPtr h) { var s = new StringBuilder(512); GetWindowText(h, s, 512); return s.ToString(); }
    static string Cls(IntPtr h) { var s = new StringBuilder(256); GetClassName(h, s, 256); return s.ToString(); }

    public static List<WinInfo> All() {
        var l = new List<WinInfo>();
        EnumWindows((h, p) => {
            uint pid; GetWindowThreadProcessId(h, out pid);
            RECT r; GetWindowRect(h, out r);
            l.Add(new WinInfo { H = h, Pid = pid, Title = Text(h), Cls = Cls(h), W = r.R - r.L, Ht = r.B - r.T, Visible = IsWindowVisible(h) });
            return true;
        }, IntPtr.Zero);
        return l;
    }

    public static List<WinInfo> Children(IntPtr parent) {
        var l = new List<WinInfo>();
        EnumChildWindows(parent, (h, p) => {
            uint pid; GetWindowThreadProcessId(h, out pid);
            RECT r; GetWindowRect(h, out r);
            l.Add(new WinInfo { H = h, Pid = pid, Title = Text(h), Cls = Cls(h), W = r.R - r.L, Ht = r.B - r.T, Visible = IsWindowVisible(h) });
            return true;
        }, IntPtr.Zero);
        return l;
    }

    public static string Shot(IntPtr h, string path) {
        RECT r; GetWindowRect(h, out r);
        int w = r.R - r.L, ht = r.B - r.T;
        if (w <= 0 || ht <= 0) return "no size " + w + "x" + ht;
        using (var bmp = new Bitmap(w, ht))
        using (var g = Graphics.FromImage(bmp)) {
            IntPtr dc = g.GetHdc();
            bool ok = PrintWindow(h, dc, 2);
            g.ReleaseHdc(dc);
            if (!ok) return "PrintWindow false";
            bmp.Save(path, System.Drawing.Imaging.ImageFormat.Png);
            return "saved " + w + "x" + ht;
        }
    }

    public static string Focus(IntPtr h) {
        uint fgPid;
        uint fgThread = GetWindowThreadProcessId(GetForegroundWindow(), out fgPid);
        uint myThread = GetCurrentThreadId();
        AttachThreadInput(myThread, fgThread, true);
        ShowWindow(h, 5);           // SW_SHOW
        BringWindowToTop(h);
        bool ok = SetForegroundWindow(h);
        IntPtr prev = SetFocus(h);
        AttachThreadInput(myThread, fgThread, false);
        return "SetForegroundWindow=" + ok + " SetFocus(prev=" + prev + ") foreground=" + GetForegroundWindow() + " want=" + h;
    }

    public static uint Key(ushort vk, ushort scan, bool up) {
        var inp = new INPUT[1];
        inp[0].type = INPUT_KEYBOARD;
        inp[0].U.ki.wVk = vk;
        inp[0].U.ki.wScan = scan;
        inp[0].U.ki.dwFlags = KEYEVENTF_SCANCODE | (up ? KEYEVENTF_KEYUP : 0);
        return SendInput(1, inp, Marshal.SizeOf(typeof(INPUT)));
    }
}
"@ -ReferencedAssemblies System.Drawing

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
                $vk = [int][char]$c
                # scan code table for letters A-Z (US layout)
                $scanTable = @{ 'A'=0x1E; 'B'=0x30; 'C'=0x2E; 'D'=0x20; 'E'=0x12; 'F'=0x21; 'G'=0x22; 'H'=0x23;
                                'I'=0x17; 'J'=0x24; 'K'=0x25; 'L'=0x26; 'M'=0x32; 'N'=0x31; 'O'=0x18; 'P'=0x19;
                                'Q'=0x10; 'R'=0x13; 'S'=0x1F; 'T'=0x14; 'U'=0x16; 'V'=0x2F; 'W'=0x11; 'X'=0x2D;
                                'Y'=0x15; 'Z'=0x2C }
                if ($scanTable.ContainsKey($c)) { return @($vk, $scanTable[$c]) } else { throw "no scan code for $name" }
            }
            throw "unknown key: $name"
        }
    }
}

$proc = if ($TargetPid -gt 0) { Get-Process -Id $TargetPid } else { Get-Process pcsx2* | Select-Object -First 1 }
if (-not $proc) { throw "no PCSX2 process" }
Write-Output "pid $($proc.Id) $($proc.ProcessName)  cpu=$($proc.CPU)"
Write-Output "foreground hwnd now: $([P2]::GetForegroundWindow())"

$wins = [P2]::All() | Where-Object { $_.Pid -eq $proc.Id }
Write-Output "--- top-level windows ---"
$wins | ForEach-Object { Write-Output ("  hwnd={0,-10} vis={1,-5} {2,5}x{3,-5} class='{4}' title='{5}'" -f $_.H, $_.Visible, $_.W, $_.Ht, $_.Cls, $_.Title) }

switch ($Action) {
    "windows" { foreach ($w in $wins) { $kids = [P2]::Children($w.H); foreach ($k in $kids) { Write-Output ("    child hwnd={0,-10} vis={1,-5} {2,5}x{3,-5} class='{4}' title='{5}'" -f $k.H, $k.Visible, $k.W, $k.Ht, $k.Cls, $k.Title) } } }
    "shot" {
        $target = $wins | Where-Object { $_.W -gt 50 -and $_.Ht -gt 50 } | Sort-Object { $_.W * $_.Ht } -Descending | Select-Object -First 1
        if (-not $target) { Write-Output "no big window"; exit 1 }
        Write-Output "target hwnd=$($target.H) $($target.W)x$($target.Ht) class='$($target.Cls)'"
        Write-Output "capture: $([P2]::Shot($target.H, $Out))"
        $k = [P2]::Children($target.H) | Where-Object { $_.W -gt 100 -and $_.Ht -gt 100 } | Sort-Object { $_.W * $_.Ht } -Descending | Select-Object -First 1
        if ($k) {
            $childOut = [System.IO.Path]::ChangeExtension($Out, $null) + "-child.png"
            Write-Output "child  hwnd=$($k.H) $($k.W)x$($k.Ht) class='$($k.Cls)' -> $([P2]::Shot($k.H, $childOut))"
        }
    }
    "keys" {
        $target = $wins | Where-Object { $_.W -gt 50 -and $_.Ht -gt 50 } | Sort-Object { $_.W * $_.Ht } -Descending | Select-Object -First 1
        if (-not $target) { Write-Output "no big window"; exit 1 }
        Write-Output "focus: $([P2]::Focus($target.H))"
        Start-Sleep -Milliseconds 300
        for ($r = 1; $r -le $Repeat; $r++) {
            foreach ($k in $Keys) {
                $vkScan = Get-VkScan $k
                [P2]::Key($vkScan[0], $vkScan[1], $false) | Out-Null
                Start-Sleep -Milliseconds $HoldMs
                [P2]::Key($vkScan[0], $vkScan[1], $true) | Out-Null
                Write-Output "  sent $k (vk=0x$('{0:X2}' -f $vkScan[0]) scan=0x$('{0:X2}' -f $vkScan[1]))"
                Start-Sleep -Milliseconds $GapMs
            }
        }
    }
}

