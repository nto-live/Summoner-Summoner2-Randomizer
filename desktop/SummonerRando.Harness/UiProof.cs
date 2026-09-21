using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using System.Windows.Forms;
using SummonerRando.Desktop;
using SummonerRando.Engine;

namespace SummonerRando.Harness;

/// <summary>
/// Headless UI proof. Builds the real MainForm and renders it with
/// Control.DrawToBitmap (no display, no Application.Run, never Show()n), then
/// dumps the control tree as JSON so the layout can be proof-read from a
/// script. Works in Session 0 where nothing ever paints on screen.
/// </summary>
internal static class UiProof
{
    private const int WM_PRINT = 0x0317;
    private const int PRF_NONCLIENT = 0x00000002;
    private const int PRF_CLIENT = 0x00000004;
    private const int PRF_ERASEBKGND = 0x00000008;
    private const int PRF_CHILDREN = 0x00000010;

    [DllImport("user32.dll", CharSet = CharSet.Auto)]
    private static extern IntPtr SendMessage(IntPtr hWnd, int msg, IntPtr wParam, IntPtr lParam);

    [StructLayout(LayoutKind.Sequential)]
    private struct RECT { public int Left, Top, Right, Bottom; }

    [StructLayout(LayoutKind.Sequential)]
    private struct POINT { public int X, Y; }

    [DllImport("user32.dll")] private static extern bool GetWindowRect(IntPtr hWnd, out RECT r);
    [DllImport("user32.dll")] private static extern bool ClientToScreen(IntPtr hWnd, ref POINT p);

    private sealed class Opts
    {
        public string Out = "";
        public string State = "empty";
        public string? Mode = null;
        public string? Iso = null;
        public int Width = 1200;
        public int Height = 900;
        public bool Stamp = true;
        public int? Splitter = null;
    }

    // ------------------------------------------------------------- entry points

    public static int RunScreenshot(string[] rest)
    {
        var o = Parse(rest);
        if (o.Out.Length == 0)
            o.Out = Path.Combine(DefaultOutDir(), $"screenshot-{o.State}.png");
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(o.Out))!);

        Console.WriteLine("== --screenshot ==");
        Console.WriteLine("cmd    : " + Environment.CommandLine);
        Console.WriteLine("state  : " + o.State);

        var form = BuildForm(o);

        ForceHandles(form);
        form.PerformLayout();
        ApplyDiagnostics(o, form);
        Pump();
        Console.WriteLine($"form   : {form.Width}x{form.Height} (client {form.ClientSize.Width}x{form.ClientSize.Height}) " +
                          $"title='{form.Text}'");
        Console.WriteLine("handle : created=" + form.IsHandleCreated);

        var bmp = Render(form, new Rectangle(0, 0, form.Width, form.Height), out string method);

        var (distinct, topArgb, topCount, total) = Analyse(bmp);
        double topFrac = total == 0 ? 1.0 : (double)topCount / total;
        Console.WriteLine($"render : {method} ({bmp.Width}x{bmp.Height}, {total:N0} px)");
        Console.WriteLine($"colours: {distinct} distinct; most common " +
                          $"#{topArgb & 0xFFFFFF:X6} = {topFrac:P2} of the image");

        // Native EDIT controls (TextBox / ComboBox edit field) do not answer
        // WM_PRINT in this session, so they come out as flat rectangles. Keep
        // the untouched render as *.raw.png and stamp the real .Text/colour/
        // font of any control that did not paint, so the picture is readable.
        if (o.Stamp)
        {
            using var raw = (Bitmap)bmp.Clone();
            int stamped = StampUnpaintedEditText(bmp, form, ClientOrigin(form));
            if (stamped > 0)
            {
                string rawPath = Path.Combine(Path.GetDirectoryName(Path.GetFullPath(o.Out))!,
                                              Path.GetFileNameWithoutExtension(o.Out) + ".raw.png");
                raw.Save(rawPath, ImageFormat.Png);
                var (sd, sc, sn, st) = Analyse(bmp);
                Console.WriteLine($"stamp  : {stamped} EDIT control(s) did not paint under WM_PRINT; " +
                                  $"their real Text/Font/ForeColor was stamped in.");
                Console.WriteLine($"         untouched render: {rawPath}");
                Console.WriteLine($"colours: {sd} distinct after stamping (top #{sc & 0xFFFFFF:X6} " +
                                  $"{(st == 0 ? 1 : (double)sn / st):P2})");
                distinct = sd; topArgb = sc; topCount = sn; total = st;
                topFrac = st == 0 ? 1 : (double)sn / st;
            }
        }

        // If the first render came out (near) blank, try the fallbacks and keep
        // whichever gives a richer image.
        // (SUMMONER_UI_FORCE_FALLBACK=1 exercises this path on purpose.)
        if (Environment.GetEnvironmentVariable("SUMMONER_UI_FORCE_FALLBACK") == "1") distinct = 0;
        if (distinct <= 2)
        {
            Console.WriteLine("render : primary looked blank -> trying fallbacks");
            Point? restampOrigin = null;

            if (form.HarnessRoot is Control root)
            {
                var alt = Render(root, new Rectangle(0, 0, root.Width, root.Height), out string m2);
                var (d2, c2, n2, t2) = Analyse(alt);
                Console.WriteLine($"render : fallback root panel: {m2} {alt.Width}x{alt.Height} " +
                                  $"colours={d2} top=#{c2 & 0xFFFFFF:X6} {(t2 == 0 ? 1 : (double)n2 / t2):P2}");
                if (d2 > distinct) { bmp.Dispose(); bmp = alt; distinct = d2; topArgb = c2; topCount = n2; total = t2; topFrac = t2 == 0 ? 1 : (double)n2 / t2; restampOrigin = new Point(0, 0); }
                else alt.Dispose();
            }

            var wm = WmPrintRender(form);
            var (d3, c3, n3, t3) = Analyse(wm);
            Console.WriteLine($"render : fallback WM_PRINT: colours={d3} top=#{c3 & 0xFFFFFF:X6} {(t3 == 0 ? 1 : (double)n3 / t3):P2}");
            if (d3 > distinct)
            {
                bmp.Dispose(); bmp = wm; distinct = d3; topArgb = c3; topCount = n3; total = t3;
                topFrac = t3 == 0 ? 1 : (double)n3 / t3;
                restampOrigin = ClientOrigin(form);
            }
            else wm.Dispose();

            // a fallback bitmap is a fresh render, so the EDIT-control text has
            // to be stamped into it again
            if (o.Stamp && restampOrigin is Point ro)
            {
                int again = StampUnpaintedEditText(bmp, form, ro);
                if (again > 0)
                {
                    var (dd, cc, nn, tt) = Analyse(bmp);
                    distinct = dd; topArgb = cc; topCount = nn; total = tt;
                    topFrac = tt == 0 ? 1 : (double)nn / tt;
                    Console.WriteLine($"stamp  : re-stamped {again} EDIT control(s) into the fallback render " +
                                      $"(colours={dd})");
                }
            }
        }

        bmp.Save(o.Out, ImageFormat.Png);
        Console.WriteLine($"saved  : {o.Out} ({new FileInfo(o.Out).Length:N0} bytes)");
        Console.WriteLine($"verdict: {(distinct > 2 && topFrac < 0.99 ? "REAL IMAGE (not blank)" : "SUSPECT: near-blank")} " +
                          $"distinct={distinct} topFraction={topFrac:P2}");
        bmp.Dispose();
        form.Dispose();
        return distinct > 2 && topFrac < 0.99 ? 0 : 2;
    }

    public static int RunDumpUi(string[] rest)
    {
        var o = Parse(rest);
        if (o.Out.Length == 0)
            o.Out = Path.Combine(DefaultOutDir(), $"ui-{o.State}.json");
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(o.Out))!);

        Console.WriteLine("== --dump-ui ==");
        Console.WriteLine("cmd    : " + Environment.CommandLine);
        Console.WriteLine("state  : " + o.State);

        var form = BuildForm(o);
        ForceHandles(form);
        form.PerformLayout();
        ApplyDiagnostics(o, form);
        Pump();

        var sb = new StringBuilder();
        using (var w = new Utf8JsonWriter(new FileStream(o.Out, FileMode.Create, FileAccess.Write), new JsonWriterOptions { Indented = true }))
        {
            w.WriteStartObject();
            w.WriteString("generatedBy", "SummonerRando.Harness --dump-ui");
            w.WriteString("state", o.State);
            w.WriteString("visibilityNote",
                "Headless mode never Show()s the form, so Control.Visible returns the effective " +
                "value and is false for every control underneath it. The PNG proof shows what " +
                "really renders; bounds/text/items/enabled below are exact.");
            w.WriteString("formTitle", form.Text);
            w.WriteNumber("formWidth", form.Width);
            w.WriteNumber("formHeight", form.Height);
            w.WriteNumber("clientWidth", form.ClientSize.Width);
            w.WriteNumber("clientHeight", form.ClientSize.Height);
            w.WriteString("status", form.HarnessStatus);
            WriteNode(w, form, "control");
            w.WriteEndObject();
        }

        long bytes = new FileInfo(o.Out).Length;
        Console.WriteLine($"saved  : {o.Out} ({bytes:N0} bytes)");
        Console.WriteLine($"nodes  : {CountNodes(form)}");
        form.Dispose();
        return 0;
    }

    // ------------------------------------------------------------------ building

    private static MainForm BuildForm(Opts o)
    {
        var form = new MainForm(Array.Empty<string>());
        form.BackColor = SystemColors.Control;
        if (o.Width > 0 && o.Height > 0)
        {
            // A headless session (Session 0) exposes a tiny virtual screen
            // (1024x768), and Windows/WinForms clamps a top-level window to the
            // screen's max track size. Lift the explicit MaximumSize so the
            // requested size is honoured where the OS allows it.
            form.MaximumSize = new Size(o.Width + 200, o.Height + 200);
            form.MinimumSize = Size.Empty;
            form.ClientSize = new Size(o.Width, o.Height);
        }

        if (o.State == "populated")
        {
            var engine = new EngineClient();
            form.HarnessLog("$ python cli.py --list");
            var lr = engine.ListAsync().GetAwaiter().GetResult();
            if (lr.Json is not JsonElement lj)
                throw new InvalidOperationException("engine --list returned no JSON (exit " + lr.ExitCode + ")");
            var list = ListPayload.Parse(lj);
            string modeKey = o.Mode ?? "ring_hunt";
            form.HarnessApplyList(list, modeKey);
            form.HarnessLog($"$ python cli.py --list  (exit {lr.ExitCode})");
            Console.WriteLine($"populate: {list.Modes.Count} modes, {list.Transforms.Count} transforms, " +
                              $"mode={modeKey}, status='{form.HarnessStatus}'");

            // Same as OnLoad does: ask the engine for one seed and apply it.
            var sr = engine.SeedsAsync(1).GetAwaiter().GetResult();
            if (sr.Json is JsonElement sj)
            {
                var seeds = SeedsPayload.Parse(sj);
                if (seeds.Count > 0)
                {
                    form.HarnessApplySeed(seeds[0]);
                    Console.WriteLine($"seed   : {seeds[0]}  (from python cli.py --seeds 1)");
                }
            }

            if (o.Iso is not null)
            {
                var ir = engine.IdentifyAsync(o.Iso).GetAwaiter().GetResult();
                if (ir.Json is JsonElement ij)
                {
                    var idp = IdentifyPayload.Parse(ij);
                    form.HarnessApplyIdentify(idp);
                    Console.WriteLine($"identify: {idp.Game} supported={idp.Supported}");
                }
            }
        }
        else if (o.State != "empty")
        {
            throw new ArgumentException("unknown --state '" + o.State + "' (use empty|populated)");
        }

        return form;
    }

    private static Opts Parse(string[] a)
    {
        var o = new Opts();
        for (int i = 0; i < a.Length; i++)
        {
            string arg = a[i];
            switch (arg)
            {
                case "--state": if (i + 1 < a.Length) o.State = a[++i]; break;
                case "--mode": if (i + 1 < a.Length) o.Mode = a[++i]; break;
                case "--iso": if (i + 1 < a.Length) o.Iso = a[++i]; break;
                case "--width": if (i + 1 < a.Length) int.TryParse(a[++i], out o.Width); break;
                case "--height": if (i + 1 < a.Length) int.TryParse(a[++i], out o.Height); break;
                case "--no-stamp": o.Stamp = false; break;
                case "--splitter": if (i + 1 < a.Length && int.TryParse(a[++i], out int sd)) o.Splitter = sd; break;
                default:
                    if (!arg.StartsWith("--") && o.Out.Length == 0) o.Out = arg;
                    break;
            }
        }
        return o;
    }

    /// <summary>Harness-only layout experiments (never used by the app).</summary>
    private static void ApplyDiagnostics(Opts o, Form form)
    {
        if (o.Splitter is not int sd) return;
        foreach (var c in AllControls(form))
            if (c is SplitContainer sc)
            {
                int before = sc.SplitterDistance;
                try { sc.SplitterDistance = sd; } catch (Exception ex) { Console.WriteLine("splitter: " + ex.Message); }
                Console.WriteLine($"splitter: {before} -> {sc.SplitterDistance} (requested {sd})");
            }
        ForceHandles(form);
        form.PerformLayout();
    }

    private static IEnumerable<Control> AllControls(Control root)
    {
        foreach (Control c in root.Controls)
        {
            yield return c;
            foreach (var sub in AllControls(c)) yield return sub;
        }
    }

    private static string DefaultOutDir() => Path.Combine(RepoDesktopDir(), "_ui");

    /// <summary>Walk up from the harness bin folder to the desktop\ folder.</summary>
    private static string RepoDesktopDir()
    {
        var d = new DirectoryInfo(AppContext.BaseDirectory);
        for (int i = 0; i < 12 && d is not null; i++, d = d.Parent)
            if (Directory.Exists(Path.Combine(d.FullName, "SummonerRando.Desktop")) &&
                Directory.Exists(Path.Combine(d.FullName, "SummonerRando.Harness")))
                return d.FullName;
        return AppContext.BaseDirectory;
    }

    // ------------------------------------------------------------------ rendering

    /// <summary>Force creation of window handles for the form and every child,
    /// top-down. Touching .Handle creates it even though the form is never shown.</summary>
    private static void ForceHandles(Control c)
    {
        try { _ = c.Handle; } catch { /* keep going */ }
        foreach (Control ch in c.Controls) ForceHandles(ch);
        try { c.PerformLayout(); } catch { /* keep going */ }
    }

    private static void Pump()
    {
        // Process anything already queued (layout, paint requests). Harmless
        // without Application.Run.
        try { Application.DoEvents(); } catch { /* ignore */ }
    }

    private static Bitmap Render(Control c, Rectangle rect, out string method)
    {
        var bmp = new Bitmap(Math.Max(1, rect.Width), Math.Max(1, rect.Height));
        using (var g = Graphics.FromImage(bmp))
            g.Clear(c.BackColor);
        try
        {
            c.DrawToBitmap(bmp, rect);
            method = "DrawToBitmap(" + c.GetType().Name + ")";
        }
        catch (Exception ex)
        {
            method = "DrawToBitmap threw: " + ex.Message;
            Console.WriteLine("render : " + method);
        }
        return bmp;
    }

    /// <summary>Offset of the form's client area inside its window bitmap.</summary>
    private static Point ClientOrigin(Form form)
    {
        if (!GetWindowRect(form.Handle, out RECT wr)) return new Point(0, 0);
        var p = new POINT { X = 0, Y = 0 };
        if (!ClientToScreen(form.Handle, ref p)) return new Point(0, 0);
        return new Point(p.X - wr.Left, p.Y - wr.Top);
    }

    /// <summary>Walks the tree yielding every control with its client-relative origin.</summary>
    private static IEnumerable<(Control ctl, int x, int y)> WalkClient(Control root)
    {
        foreach (Control c in root.Controls)
        {
            yield return (c, c.Left, c.Top);
            foreach (var sub in DescendClient(c, c.Left, c.Top))
                yield return sub;
        }
    }

    private static IEnumerable<(Control ctl, int x, int y)> DescendClient(Control parent, int px, int py)
    {
        foreach (Control c in parent.Controls)
        {
            int x = px + c.Left, y = py + c.Top;
            yield return (c, x, y);
            foreach (var sub in DescendClient(c, x, y))
                yield return sub;
        }
    }

    /// <summary>
    /// Native EDIT controls ignore WM_PRINT unless they have really painted on
    /// screen, so in a display-less session their text is missing from the
    /// bitmap. For each such control that came out flat, draw its *own*
    /// Text/Font/ForeColor into the bitmap so the layout can be proof-read.
    /// </summary>
    private static int StampUnpaintedEditText(Bitmap bmp, Form form, Point origin)
    {
        int stamped = 0;
        foreach (var (ctl, x, y) in WalkClient(form))
        {
            string text;
            Rectangle target;
            Font font;
            Color fore;
            TextFormatFlags flags;

            if (ctl is TextBoxBase tb)
            {
                if (tb.TextLength == 0) continue;
                text = tb.Text; font = tb.Font; fore = tb.ForeColor;
                target = new Rectangle(origin.X + x + 2, origin.Y + y + 2,
                                       Math.Max(1, ctl.Width - 4), Math.Max(1, ctl.Height - 4));
                flags = tb.Multiline
                    ? TextFormatFlags.NoPrefix | TextFormatFlags.Left | TextFormatFlags.Top | TextFormatFlags.WordBreak
                    : TextFormatFlags.NoPrefix | TextFormatFlags.Left | TextFormatFlags.VerticalCenter | TextFormatFlags.SingleLine;
            }
            else if (ctl is ComboBox cb)
            {
                if (string.IsNullOrEmpty(cb.Text)) continue;
                text = cb.Text; font = cb.Font; fore = cb.ForeColor;
                target = new Rectangle(origin.X + x + 3, origin.Y + y + 3,
                                       Math.Max(1, ctl.Width - 25), Math.Max(1, ctl.Height - 6));
                flags = TextFormatFlags.NoPrefix | TextFormatFlags.Left | TextFormatFlags.VerticalCenter | TextFormatFlags.SingleLine;
            }
            else continue;

            if (target.Width < 2 || target.Height < 2) continue;
            if (!RegionIsFlat(bmp, target)) continue;   // it painted for real; leave it alone

            var clip = Rectangle.Intersect(target, new Rectangle(0, 0, bmp.Width, bmp.Height));
            if (clip.Width < 2 || clip.Height < 2) continue;
            using var g = Graphics.FromImage(bmp);
            g.SetClip(clip);
            TextRenderer.DrawText(g, text, font, target, fore, flags);
            stamped++;
        }
        return stamped;
    }

    /// <summary>True when a region holds at most a couple of flat colours (i.e.
    /// the control painted its background but not its content).</summary>
    private static bool RegionIsFlat(Bitmap bmp, Rectangle r)
    {
        r = Rectangle.Intersect(r, new Rectangle(0, 0, bmp.Width, bmp.Height));
        if (r.Width < 2 || r.Height < 2) return false;
        var seen = new HashSet<int>();
        for (int y = r.Top; y < r.Bottom; y += 2)
            for (int x = r.Left; x < r.Right; x += 2)
            {
                seen.Add(bmp.GetPixel(x, y).ToArgb());
                if (seen.Count > 3) return false;
            }
        return true;
    }

    private static Bitmap WmPrintRender(Control c)
    {
        var bmp = new Bitmap(Math.Max(1, c.Width), Math.Max(1, c.Height));
        using (var g = Graphics.FromImage(bmp))
        {
            g.Clear(c.BackColor);
            IntPtr hdc = g.GetHdc();
            try
            {
                SendMessage(c.Handle, WM_PRINT, hdc,
                    (IntPtr)(PRF_CLIENT | PRF_NONCLIENT | PRF_ERASEBKGND | PRF_CHILDREN));
            }
            finally { g.ReleaseHdc(hdc); }
        }
        return bmp;
    }

    /// <summary>Distinct-colour count plus the dominant colour and its share.</summary>
    private static (int distinct, uint topArgb, int topCount, int total) Analyse(Bitmap bmp)
    {
        var rect = new Rectangle(0, 0, bmp.Width, bmp.Height);
        var data = bmp.LockBits(rect, ImageLockMode.ReadOnly, PixelFormat.Format32bppArgb);
        try
        {
            int stride = data.Stride;
            var buf = new byte[stride * bmp.Height];
            Marshal.Copy(data.Scan0, buf, 0, buf.Length);

            var counts = new Dictionary<uint, int>(1024);
            for (int y = 0; y < bmp.Height; y++)
            {
                int row = y * stride;
                for (int x = 0; x < bmp.Width; x++)
                {
                    int off = row + x * 4;
                    uint c = (uint)(buf[off] | (buf[off + 1] << 8) | (buf[off + 2] << 16) | (buf[off + 3] << 24));
                    counts.TryGetValue(c, out int n);
                    counts[c] = n + 1;
                }
            }

            uint top = 0; int topCount = -1;
            foreach (var kv in counts)
                if (kv.Value > topCount) { topCount = kv.Value; top = kv.Key; }

            return (counts.Count, top, Math.Max(topCount, 0), bmp.Width * bmp.Height);
        }
        finally { bmp.UnlockBits(data); }
    }

    // -------------------------------------------------------------------- dumping

    private static void WriteNode(Utf8JsonWriter w, Control c, string? propertyName = null)
    {
        if (propertyName is null) w.WriteStartObject();
        else w.WriteStartObject(propertyName);

        w.WriteString("type", c.GetType().Name);
        w.WriteString("fullType", c.GetType().FullName);
        w.WriteString("name", c.Name ?? "");
        w.WriteString("text", Trunc(c.Text, 400));
        w.WriteStartObject("bounds");
        w.WriteNumber("x", c.Left); w.WriteNumber("y", c.Top);
        w.WriteNumber("w", c.Width); w.WriteNumber("h", c.Height);
        w.WriteEndObject();
        w.WriteBoolean("visible", c.Visible);
        w.WriteBoolean("enabled", c.Enabled);
        w.WriteString("dock", c.Dock.ToString());
        w.WriteString("anchor", c.Anchor.ToString());
        w.WriteNumber("tabIndex", c.TabIndex);
        w.WriteString("backColor", "#" + (c.BackColor.ToArgb() & 0xFFFFFF).ToString("X6"));
        w.WriteString("foreColor", "#" + (c.ForeColor.ToArgb() & 0xFFFFFF).ToString("X6"));

        switch (c)
        {
            case ComboBox cb:
                w.WriteNumber("itemCount", cb.Items.Count);
                w.WriteNumber("selectedIndex", cb.SelectedIndex);
                // GetItemText honours DisplayMember, so we see what the user sees
                w.WriteString("selectedItem", cb.SelectedIndex >= 0 ? cb.GetItemText(cb.SelectedItem) ?? "" : "");
                WriteStrings(w, "items", cb.Items.Cast<object?>().Select(o => cb.GetItemText(o) ?? ""));
                break;

            case ListBox lb:
                w.WriteNumber("itemCount", lb.Items.Count);
                w.WriteNumber("selectedIndex", lb.SelectedIndex);
                w.WriteString("selectedItem", lb.SelectedIndex >= 0 ? lb.GetItemText(lb.SelectedItem) ?? "" : "");
                WriteStrings(w, "items", lb.Items.Cast<object?>().Select(o => lb.GetItemText(o) ?? ""));
                break;

            case DataGridView dgv:
                w.WriteNumber("rowCount", dgv.Rows.Count);
                w.WriteNumber("columnCount", dgv.Columns.Count);
                w.WriteStartArray("columns");
                foreach (DataGridViewColumn col in dgv.Columns)
                {
                    w.WriteStartObject();
                    w.WriteString("name", col.Name);
                    w.WriteString("header", col.HeaderText);
                    w.WriteNumber("width", col.Width);
                    w.WriteString("valueType", col.ValueType?.Name ?? "");
                    w.WriteEndObject();
                }
                w.WriteEndArray();

                // first few rows, as text, for the structural check
                int rowLimit = Math.Min(6, dgv.Rows.Count);
                w.WriteStartArray("rows");
                for (int r = 0; r < rowLimit; r++)
                {
                    var row = dgv.Rows[r];
                    w.WriteStartObject();
                    w.WriteNumber("index", r);
                    w.WriteString("tag", row.Tag?.ToString() ?? "");
                    w.WriteStartArray("cells");
                    foreach (DataGridViewCell cell in row.Cells)
                        w.WriteStringValue(cell.Value?.ToString() ?? "");
                    w.WriteEndArray();
                    w.WriteEndObject();
                }
                w.WriteEndArray();
                WriteStrings(w, "rowTags", dgv.Rows.Cast<DataGridViewRow>().Select(r => r.Tag?.ToString() ?? "").Take(200));
                break;

            case NumericUpDown nud:
                w.WriteNumber("value", nud.Value);
                w.WriteNumber("minimum", nud.Minimum);
                w.WriteNumber("maximum", nud.Maximum);
                break;

            case CheckBox chk:
                w.WriteBoolean("checked", chk.Checked);
                break;

            case ProgressBar pb:
                w.WriteNumber("value", pb.Value);
                w.WriteString("style", pb.Style.ToString());
                break;

            case SplitContainer sc:
                w.WriteNumber("splitterDistance", sc.SplitterDistance);
                w.WriteString("orientation", sc.Orientation.ToString());
                break;

            case TableLayoutPanel tlp:
                w.WriteNumber("rowCount", tlp.RowCount);
                w.WriteNumber("columnCount", tlp.ColumnCount);
                w.WriteString("growStyle", tlp.GrowStyle.ToString());
                break;

            case TextBoxBase tb:
                w.WriteBoolean("multiline", tb.Multiline);
                w.WriteBoolean("readOnly", tb.ReadOnly);
                w.WriteNumber("textLength", tb.TextLength);
                w.WriteNumber("maxLength", tb.MaxLength);
                break;

            case GroupBox gb:
                w.WriteNumber("paddingLeft", gb.Padding.Left);
                break;
        }

        w.WriteNumber("controlCount", c.Controls.Count);
        w.WriteStartArray("controls");
        foreach (Control child in c.Controls) WriteNode(w, child);
        w.WriteEndArray();

        w.WriteEndObject();
    }

    private static void WriteStrings(Utf8JsonWriter w, string name, IEnumerable<string> items)
    {
        // item count + first few items only; the full list can be thousands long
        var list = items.ToList();
        w.WriteStartObject(name);
        w.WriteNumber("count", list.Count);
        w.WriteStartArray("sample");
        foreach (var s in list.Take(8)) w.WriteStringValue(Trunc(s, 160));
        w.WriteEndArray();
        w.WriteEndObject();
    }

    private static int CountNodes(Control c)
    {
        int n = 1;
        foreach (Control ch in c.Controls) n += CountNodes(ch);
        return n;
    }

    private static string Trunc(string s, int max)
        => s.Length <= max ? s : s.Substring(0, max) + "\u2026";
}
