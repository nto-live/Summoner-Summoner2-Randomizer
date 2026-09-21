using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using SummonerRando.Engine;

namespace SummonerRando.Desktop;

/// <summary>
/// The whole UI. It shells out to cli.py: no HTTP server, no browser.
/// It takes an ISO, lets you choose what to randomize, and returns a new ISO,
/// always showing the seed.
/// </summary>
public sealed class MainForm : Form
{
    // Transforms that change progression or pacing rather than looks. Purely a
    // presentation label for the feature grid ("gameplay" vs "visual").
    private static readonly HashSet<string> Gameplay = new(StringComparer.Ordinal)
    {
        "cutscene_bypass", "dialogue_blank", "fade_instant",
        "xp_boost", "xp_nerf", "xp_scale",
        "levelcap_raise", "levelcap_set",
        "ring_hunt", "permadeath", "economy_squeeze",
    };

    private readonly EngineClient? _engine;
    private readonly string? _engineError;

    private ListPayload? _list;
    private IdentifyPayload? _identify;
    private bool _discSupported;
    private bool _busy;
    private bool _outTouched;
    private bool _settingOut;
    private readonly Dictionary<string, Dictionary<string, object?>> _optValues = new(StringComparer.Ordinal);

    // controls
    private readonly TextBox _txtIso = new();
    private readonly Button _btnBrowse = new();
    private readonly Label _lblIdentify = new();
    private readonly ComboBox _cmbMode = new();
    private readonly Label _lblMode = new();
    private readonly TextBox _txtSeed = new();
    private readonly Button _btnSeed = new();
    private readonly DataGridView _dgv = new();
    private readonly Panel _optScroll = new();
    private readonly TableLayoutPanel _optHost = new();
    private readonly TextBox _txtOut = new();
    private readonly Button _btnOut = new();
    private readonly Button _btnDry = new();
    private readonly Button _btnBuild = new();
    private readonly ProgressBar _bar = new();
    private readonly Label _lblStatus = new();
    private readonly TextBox _txtLog = new();
    private readonly TextBox _txtResult = new();
    private readonly TextBox _txtPending = new();

    public MainForm(string[]? args = null)
    {
        string? engineOverride = null;
        if (args is not null)
            for (int i = 0; i < args.Length - 1; i++)
                if (args[i] == "--engine")
                    engineOverride = args[i + 1];

        try
        {
            _engine = new EngineClient(engineOverride);
        }
        catch (Exception ex)
        {
            _engineError = ex.Message;
        }

        BuildUi();
    }

    // ------------------------------------------------------------------ UI

    private void BuildUi()
    {
        Text = "Summoner Randomizer";
        ClientSize = new Size(1160, 840);
        MinimumSize = new Size(980, 720);
        StartPosition = FormStartPosition.CenterScreen;
        Font = new Font("Segoe UI", 9f);

        var root = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 1,
            RowCount = 2,
            Padding = new Padding(8),
        };
        root.RowStyles.Add(new RowStyle(SizeType.Percent, 62f));
        root.RowStyles.Add(new RowStyle(SizeType.Percent, 38f));

        root.Controls.Add(BuildTop(), 0, 0);
        root.Controls.Add(BuildBottom(), 0, 1);
        Controls.Add(root);

        // events
        _btnBrowse.Click += (_, _) => BrowseIso();
        _cmbMode.SelectedIndexChanged += (_, _) => ApplyMode();
        _btnSeed.Click += async (_, _) => await RandomizeSeedAsync();
        _txtSeed.TextChanged += (_, _) => UpdateTitleAndOut();
        _btnOut.Click += (_, _) => PickOutput();
        _btnDry.Click += async (_, _) => await RunBuildAsync(dryRun: true);
        _btnBuild.Click += async (_, _) => await RunBuildAsync(dryRun: false);
        _dgv.CurrentCellDirtyStateChanged += (_, _) =>
        {
            if (_dgv.IsCurrentCellDirty) _dgv.CommitEdit(DataGridViewDataErrorContexts.Commit);
        };
        _dgv.CellValueChanged += (_, e) =>
        {
            if (e.RowIndex >= 0 && e.ColumnIndex == _dgv.Columns["On"]!.Index)
                OnFeatureToggled();
        };
        _txtOut.TextChanged += (_, _) => { if (!_settingOut) _outTouched = true; };

        SetRunning(false);
        SetBuildEnabled(false);
    }

    private Control BuildTop()
    {
        var top = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 5 };
        top.RowStyles.Add(new RowStyle(SizeType.Absolute, 104f));  // disc
        top.RowStyles.Add(new RowStyle(SizeType.Absolute, 116f));  // mode + seed
        top.RowStyles.Add(new RowStyle(SizeType.Percent, 100f));   // features | options
        top.RowStyles.Add(new RowStyle(SizeType.Absolute, 58f));   // output
        top.RowStyles.Add(new RowStyle(SizeType.Absolute, 46f));   // run bar

        top.Controls.Add(BuildDiscGroup(), 0, 0);
        top.Controls.Add(BuildModeGroup(), 0, 1);
        top.Controls.Add(BuildFeatureSplit(), 0, 2);
        top.Controls.Add(BuildOutputGroup(), 0, 3);
        top.Controls.Add(BuildRunBar(), 0, 4);
        return top;
    }

    private Control BuildDiscGroup()
    {
        var gb = new GroupBox { Text = "Disc image", Dock = DockStyle.Fill };
        var t = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 3, RowCount = 2, Padding = new Padding(6) };
        t.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 70f));
        t.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100f));
        t.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 90f));

        t.Controls.Add(new Label { Text = "ISO file", TextAlign = ContentAlignment.MiddleLeft, Dock = DockStyle.Fill }, 0, 0);
        _txtIso.Dock = DockStyle.Fill;
        _txtIso.PlaceholderText = @"e.g. F:\rando\S1\iso\Summoner.iso";
        t.Controls.Add(_txtIso, 1, 0);
        _btnBrowse.Text = "Browse\u2026";
        _btnBrowse.Dock = DockStyle.Fill;
        t.Controls.Add(_btnBrowse, 2, 0);

        _lblIdentify.Dock = DockStyle.Fill;
        _lblIdentify.Text = "No disc selected.";
        _lblIdentify.ForeColor = SystemColors.GrayText;
        _lblIdentify.AutoEllipsis = false;
        t.Controls.Add(_lblIdentify, 1, 1);
        t.SetColumnSpan(_lblIdentify, 2);

        gb.Controls.Add(t);
        return gb;
    }

    private Control BuildModeGroup()
    {
        var gb = new GroupBox { Text = "Mode and seed", Dock = DockStyle.Fill };
        var t = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 3, RowCount = 3, Padding = new Padding(6) };
        t.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 70f));
        t.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100f));
        t.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 110f));
        t.RowStyles.Add(new RowStyle(SizeType.Absolute, 30f));
        t.RowStyles.Add(new RowStyle(SizeType.Absolute, 30f));
        t.RowStyles.Add(new RowStyle(SizeType.Percent, 100f));

        t.Controls.Add(new Label { Text = "Mode", TextAlign = ContentAlignment.MiddleLeft, Dock = DockStyle.Fill }, 0, 0);
        _cmbMode.Dock = DockStyle.Fill;
        _cmbMode.DropDownStyle = ComboBoxStyle.DropDownList;
        _cmbMode.Enabled = false;
        t.Controls.Add(_cmbMode, 1, 0);
        t.SetColumnSpan(_cmbMode, 2);

        t.Controls.Add(new Label { Text = "Seed", TextAlign = ContentAlignment.MiddleLeft, Dock = DockStyle.Fill }, 0, 1);
        _txtSeed.Dock = DockStyle.Fill;
        _txtSeed.Font = new Font("Consolas", 10f);
        _txtSeed.CharacterCasing = CharacterCasing.Upper;
        t.Controls.Add(_txtSeed, 1, 1);

        _btnSeed.Text = "Random seed";
        _btnSeed.Dock = DockStyle.Fill;
        t.Controls.Add(_btnSeed, 2, 1);

        _lblMode.Text = "";
        _lblMode.Dock = DockStyle.Fill;
        _lblMode.ForeColor = SystemColors.GrayText;
        _lblMode.TextAlign = ContentAlignment.TopLeft;
        t.Controls.Add(_lblMode, 0, 2);
        t.SetColumnSpan(_lblMode, 3);

        gb.Controls.Add(t);
        return gb;
    }

    private Control BuildFeatureSplit()
    {
        var split = new SplitContainer { Dock = DockStyle.Fill, Orientation = Orientation.Vertical };

        // SplitterDistance must NOT be set in an initializer. At construction the container is
        // still ~150 px wide, so the value is silently clamped to (Width - Panel2MinSize) and
        // then scales proportionally as the form grows - which crushed the Options pane to
        // ~190 px, clipped the option controls off the right edge, and collapsed the help
        // column to zero width. Apply it once the control actually has a real width.
        var placed = false;
        split.SizeChanged += (_, __) =>
        {
            if (placed || split.Width < 400) return;
            placed = true;
            split.Panel1MinSize = 360;
            split.Panel2MinSize = 330;
            var span = split.Width - split.SplitterWidth;
            var want = (int)(span * 0.53);
            want = Math.Max(split.Panel1MinSize, Math.Min(want, span - split.Panel2MinSize));
            split.SplitterDistance = want;
        };

        var gbF = new GroupBox { Text = "Features  (untick to exclude, tick to add)", Dock = DockStyle.Fill };
        _dgv.Dock = DockStyle.Fill;
        _dgv.AllowUserToAddRows = false;
        _dgv.AllowUserToDeleteRows = false;
        _dgv.AllowUserToResizeRows = false;
        _dgv.RowHeadersVisible = false;
        _dgv.SelectionMode = DataGridViewSelectionMode.FullRowSelect;
        _dgv.MultiSelect = false;
        _dgv.AutoSizeRowsMode = DataGridViewAutoSizeRowsMode.AllCells;
        _dgv.EditMode = DataGridViewEditMode.EditOnEnter;
        _dgv.BackgroundColor = SystemColors.Window;
        _dgv.BorderStyle = BorderStyle.None;
        _dgv.ColumnHeadersHeightSizeMode = DataGridViewColumnHeadersHeightSizeMode.AutoSize;
        _dgv.Columns.Add(new DataGridViewCheckBoxColumn { Name = "On", HeaderText = "", Width = 34, Resizable = DataGridViewTriState.False });
        _dgv.Columns.Add(new DataGridViewTextBoxColumn { Name = "Feature", HeaderText = "Feature", ReadOnly = true, Width = 190 });
        _dgv.Columns.Add(new DataGridViewTextBoxColumn { Name = "Kind", HeaderText = "Kind", ReadOnly = true, Width = 78 });
        _dgv.Columns.Add(new DataGridViewTextBoxColumn
        {
            Name = "Desc",
            HeaderText = "What it does",
            ReadOnly = true,
            AutoSizeMode = DataGridViewAutoSizeColumnMode.Fill,
            DefaultCellStyle = new DataGridViewCellStyle { WrapMode = DataGridViewTriState.True },
        });
        gbF.Controls.Add(_dgv);

        var gbO = new GroupBox { Text = "Options", Dock = DockStyle.Fill };
        _optScroll.Dock = DockStyle.Fill;
        _optScroll.AutoScroll = true;
        _optHost.Dock = DockStyle.Top;
        _optHost.AutoSize = true;
        _optHost.AutoSizeMode = AutoSizeMode.GrowAndShrink;
        _optHost.ColumnCount = 1;
        _optHost.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100f));
        _optScroll.Controls.Add(_optHost);
        gbO.Controls.Add(_optScroll);

        split.Panel1.Controls.Add(gbF);
        split.Panel2.Controls.Add(gbO);
        return split;
    }

    private Control BuildOutputGroup()
    {
        var gb = new GroupBox { Text = "Output ISO", Dock = DockStyle.Fill };
        var t = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 3, RowCount = 1, Padding = new Padding(6) };
        t.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 70f));
        t.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100f));
        t.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 110f));

        t.Controls.Add(new Label { Text = "Save as", TextAlign = ContentAlignment.MiddleLeft, Dock = DockStyle.Fill }, 0, 0);
        _txtOut.Dock = DockStyle.Fill;
        t.Controls.Add(_txtOut, 1, 0);
        _btnOut.Text = "Choose\u2026";
        _btnOut.Dock = DockStyle.Fill;
        t.Controls.Add(_btnOut, 2, 0);

        gb.Controls.Add(t);
        return gb;
    }

    private Control BuildRunBar()
    {
        var p = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 5, RowCount = 1, Padding = new Padding(2) };
        p.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 110f));
        p.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 120f));
        p.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 150f));
        p.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100f));
        p.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 110f));

        _btnDry.Text = "Dry run";
        _btnDry.Dock = DockStyle.Fill;
        p.Controls.Add(_btnDry, 0, 0);

        _btnBuild.Text = "Build ISO";
        _btnBuild.Dock = DockStyle.Fill;
        _btnBuild.Font = new Font("Segoe UI", 9f, FontStyle.Bold);
        p.Controls.Add(_btnBuild, 1, 0);

        _bar.Style = ProgressBarStyle.Marquee;
        _bar.MarqueeAnimationSpeed = 0;
        _bar.Dock = DockStyle.Fill;
        p.Controls.Add(_bar, 2, 0);

        _lblStatus.Dock = DockStyle.Fill;
        _lblStatus.TextAlign = ContentAlignment.MiddleLeft;
        _lblStatus.Text = "Ready.";
        p.Controls.Add(_lblStatus, 3, 0);

        var quit = new Button { Text = "Close", Dock = DockStyle.Fill };
        quit.Click += (_, _) => Close();
        p.Controls.Add(quit, 4, 0);
        return p;
    }

    private Control BuildBottom()
    {
        var t = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 2, RowCount = 1 };
        t.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 62f));
        t.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 38f));

        var gbLog = new GroupBox { Text = "Log  (engine progress)", Dock = DockStyle.Fill };
        _txtLog.Dock = DockStyle.Fill;
        _txtLog.Multiline = true;
        _txtLog.ReadOnly = true;
        _txtLog.ScrollBars = ScrollBars.Vertical;
        _txtLog.WordWrap = false;
        _txtLog.Font = new Font("Consolas", 9f);
        _txtLog.BackColor = Color.FromArgb(24, 24, 28);
        _txtLog.ForeColor = Color.Gainsboro;
        gbLog.Controls.Add(_txtLog);

        var right = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 2 };
        right.RowStyles.Add(new RowStyle(SizeType.Percent, 58f));
        right.RowStyles.Add(new RowStyle(SizeType.Percent, 42f));

        var gbRes = new GroupBox { Text = "Result", Dock = DockStyle.Fill };
        _txtResult.Dock = DockStyle.Fill;
        _txtResult.Multiline = true;
        _txtResult.ReadOnly = true;
        _txtResult.ScrollBars = ScrollBars.Vertical;
        _txtResult.WordWrap = true;
        _txtResult.Font = new Font("Consolas", 9f);
        gbRes.Controls.Add(_txtResult);

        var gbPend = new GroupBox { Text = "Not implemented (blocked) \u2014 engine's report", Dock = DockStyle.Fill };
        _txtPending.Dock = DockStyle.Fill;
        _txtPending.Multiline = true;
        _txtPending.ReadOnly = true;
        _txtPending.ScrollBars = ScrollBars.Vertical;
        _txtPending.WordWrap = true;
        _txtPending.Font = new Font("Consolas", 8.25f);
        _txtPending.ForeColor = SystemColors.GrayText;
        gbPend.Controls.Add(_txtPending);

        right.Controls.Add(gbRes, 0, 0);
        right.Controls.Add(gbPend, 0, 1);

        t.Controls.Add(gbLog, 0, 0);
        t.Controls.Add(right, 1, 0);
        return t;
    }

    // -------------------------------------------------------------- startup

    protected override async void OnLoad(EventArgs e)
    {
        base.OnLoad(e);

        if (_engine is null)
        {
            Log("Engine not found.");
            Log(_engineError ?? "Unknown error.");
            SetStatus("Engine not found \u2014 cannot continue.");
            MessageBox.Show(this,
                _engineError ?? "Unknown error.",
                "Engine not found", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return;
        }

        Log("Engine dir: " + _engine.EngineDir);
        Log("Python:     " + _engine.PythonExe);

        await LoadListAsync();
        await RandomizeSeedAsync();
    }

    private async Task LoadListAsync()
    {
        SetStatus("Reading engine metadata\u2026");
        var res = await RunSafeAsync(new[] { "--list" });
        if (res?.Json is not JsonElement json || !res.Ok)
        {
            Log("--list failed (exit " + (res?.ExitCode.ToString() ?? "?") + ")");
            SetStatus("Could not read engine metadata.");
            return;
        }

        _list = ListPayload.Parse(json);

        _cmbMode.Items.Clear();
        foreach (var m in _list.Modes)
            _cmbMode.Items.Add(m);
        _cmbMode.DisplayMember = nameof(ModeInfo.Display);
        _cmbMode.Enabled = _cmbMode.Items.Count > 0;

        PopulateFeatures();

        if (_cmbMode.Items.Count > 0)
            _cmbMode.SelectedIndex = IndexOfMode("vanilla");

        _txtPending.Text = BuildPendingText(_list);
        Log($"Loaded {_list.Modes.Count} modes, {_list.Transforms.Count} transforms, " +
            $"{_list.OptionAware.Count} option-aware, {_list.Pending.Count} pending.");
        SetStatus("Ready.");
    }

    private int IndexOfMode(string key)
    {
        if (_list is null) return 0;
        for (int i = 0; i < _cmbMode.Items.Count; i++)
            if (_cmbMode.Items[i] is ModeInfo m && m.Key == key) return i;
        return 0;
    }

    private void PopulateFeatures()
    {
        if (_list is null) return;
        _dgv.Rows.Clear();
        foreach (var name in _list.Transforms)
        {
            var info = _list.Info.TryGetValue(name, out var ti) ? ti : new TransformInfo { Name = name, Label = name };
            var kind = Gameplay.Contains(name) ? "gameplay" : "visual";
            int idx = _dgv.Rows.Add(false, info.Label, kind, info.Description);
            _dgv.Rows[idx].Tag = name;
        }
    }

    // ------------------------------------------------------------------ mode

    private void ApplyMode()
    {
        if (_list is null || _cmbMode.SelectedItem is not ModeInfo m)
            return;

        var set = new HashSet<string>(m.Transforms, StringComparer.Ordinal);
        foreach (DataGridViewRow row in _dgv.Rows)
            row.Cells["On"].Value = row.Tag is string n && set.Contains(n);

        // Reset per-transform option values to schema defaults, then overlay
        // whatever this mode pins.
        _optValues.Clear();
        foreach (var t in _list.OptionAware)
        {
            if (!_list.Options.TryGetValue(t, out var schema)) continue;
            var d = new Dictionary<string, object?>(StringComparer.Ordinal);
            foreach (var kv in schema)
                d[kv.Key] = DefaultValue(kv.Value);
            _optValues[t] = d;
        }
        if (m.Options is JsonElement mo && mo.ValueKind == JsonValueKind.Object)
        {
            foreach (var tp in mo.EnumerateObject())
            {
                if (!_optValues.TryGetValue(tp.Name, out var d)) continue;
                if (tp.Value.ValueKind != JsonValueKind.Object) continue;
                foreach (var op in tp.Value.EnumerateObject())
                    d[op.Name] = op.Value.ValueKind switch
                    {
                        JsonValueKind.Number when op.Value.TryGetInt32(out var iv) => iv,
                        JsonValueKind.True => true,
                        JsonValueKind.False => false,
                        JsonValueKind.String => op.Value.GetString(),
                        _ => null,
                    };
            }
        }

        _lblMode.Text = m.Blurb + (m.Risk.Length > 0 ? $"   [risk: {m.Risk}]" : "");
        _txtResult.Text = "";
        RebuildOptions();
        UpdateTitleAndOut();
        Log($"Mode: {m.Display}" + (m.HasBinary ? "  [also patches the executable]" : ""));
        Log(m.Blurb);
    }

    private static object? DefaultValue(OptionSpec s) => s.Type switch
    {
        "bool" => s.DefaultBool,
        "choice" => s.DefaultChoice,
        _ => s.DefaultInt,
    };

    private void OnFeatureToggled()
    {
        RebuildOptions();
        UpdateTitleAndOut();
    }

    // --------------------------------------------------------------- options

    private HashSet<string> CheckedTransforms()
    {
        var set = new HashSet<string>(StringComparer.Ordinal);
        foreach (DataGridViewRow row in _dgv.Rows)
            if (row.Tag is string n && row.Cells["On"].Value is true)
                set.Add(n);
        return set;
    }

    private void RebuildOptions()
    {
        if (_list is null) return;
        _optHost.SuspendLayout();
        _optHost.Controls.Clear();
        _optHost.RowStyles.Clear();
        _optHost.RowCount = 0;

        var checkedSet = CheckedTransforms();
        int shown = 0;
        foreach (var t in _list.OptionAware.OrderBy(x => x, StringComparer.Ordinal))
        {
            if (!checkedSet.Contains(t)) continue;
            if (!_list.Options.TryGetValue(t, out var schema) || schema.Count == 0) continue;

            var title = _list.Info.TryGetValue(t, out var ti) ? ti.Label : t;
            var gb = new GroupBox { Text = title, Dock = DockStyle.Top, AutoSize = true, AutoSizeMode = AutoSizeMode.GrowAndShrink, Padding = new Padding(8) };
            var tbl = new TableLayoutPanel { Dock = DockStyle.Top, AutoSize = true, AutoSizeMode = AutoSizeMode.GrowAndShrink, ColumnCount = 3 };
            tbl.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 175f));
            tbl.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 120f));
            tbl.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100f));

            foreach (var kv in schema)
                AddOptionRow(tbl, t, kv.Value);

            gb.Controls.Add(tbl);
            _optHost.Controls.Add(gb);
            _optHost.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            shown++;
        }

        if (shown == 0)
        {
            var note = new Label
            {
                Text = "No option-aware features are active.\nTick XP control, Level cap control, Permadeath, or Ring Hunt to see their dials.",
                AutoSize = true,
                ForeColor = SystemColors.GrayText,
                Padding = new Padding(8),
                Dock = DockStyle.Top,
            };
            _optHost.Controls.Add(note);
            _optHost.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        }

        _optHost.ResumeLayout(true);
    }

    private void AddOptionRow(TableLayoutPanel tbl, string transform, OptionSpec spec)
    {
        if (!_optValues.TryGetValue(transform, out var store))
        {
            store = new Dictionary<string, object?>(StringComparer.Ordinal);
            _optValues[transform] = store;
        }
        if (!store.ContainsKey(spec.Key))
            store[spec.Key] = DefaultValue(spec);

        int row = tbl.RowCount;
        tbl.RowCount = row + 1;
        tbl.RowStyles.Add(new RowStyle(SizeType.AutoSize));

        if (spec.Type == "bool")
        {
            var cb = new CheckBox
            {
                Text = spec.Label,
                Checked = store[spec.Key] is true,
                AutoSize = true,
                Margin = new Padding(3, 6, 3, 3),
            };
            cb.CheckedChanged += (_, _) => store[spec.Key] = cb.Checked;
            tbl.Controls.Add(cb, 0, row);
            tbl.SetColumnSpan(cb, 2);
            if (spec.Help.Length > 0)
                tbl.Controls.Add(HelpLabel(spec.Help), 2, row);
            return;
        }

        tbl.Controls.Add(new Label { Text = spec.Label, AutoSize = true, TextAlign = ContentAlignment.MiddleLeft, Margin = new Padding(3, 8, 3, 3) }, 0, row);

        if (spec.Type == "choice")
        {
            var cmb = new ComboBox { DropDownStyle = ComboBoxStyle.DropDownList, Width = 170, Margin = new Padding(3, 4, 3, 3) };
            foreach (var c in spec.Choices)
                cmb.Items.Add(c);
            cmb.DisplayMember = nameof(OptionChoice.Display);
            var want = store[spec.Key] as string;
            int sel = 0;
            for (int i = 0; i < cmb.Items.Count; i++)
                if (cmb.Items[i] is OptionChoice oc && oc.Value == want) { sel = i; break; }
            if (cmb.Items.Count > 0) cmb.SelectedIndex = sel;
            cmb.SelectedIndexChanged += (_, _) =>
            {
                if (cmb.SelectedItem is OptionChoice oc) store[spec.Key] = oc.Value;
            };
            tbl.Controls.Add(cmb, 1, row);
        }
        else // int
        {
            var num = new NumericUpDown
            {
                Minimum = spec.Min ?? 0,
                Maximum = spec.Max ?? 100000,
                Width = 90,
                Margin = new Padding(3, 4, 3, 3),
            };
            int want = store[spec.Key] is int iv ? iv : spec.DefaultInt;
            num.Value = Math.Clamp(want, (int)num.Minimum, (int)num.Maximum);
            num.ValueChanged += (_, _) => store[spec.Key] = (int)num.Value;
            tbl.Controls.Add(num, 1, row);
        }

        if (spec.Help.Length > 0)
            tbl.Controls.Add(HelpLabel(spec.Help), 2, row);
    }

    private static Label HelpLabel(string text) => new()
    {
        Text = text,
        AutoSize = true,
        MaximumSize = new Size(360, 0),
        ForeColor = SystemColors.GrayText,
        Margin = new Padding(3, 8, 3, 3),
    };

    private string BuildOptionsJson(HashSet<string> checkedSet)
    {
        if (_list is null) return "{}";
        var payload = new Dictionary<string, Dictionary<string, object?>>(StringComparer.Ordinal);
        var schema = _list.Options;
        foreach (var t in checkedSet)
        {
            if (!schema.TryGetValue(t, out var specs)) continue;
            if (!_optValues.TryGetValue(t, out var store)) continue;
            var d = new Dictionary<string, object?>(StringComparer.Ordinal);
            foreach (var key in specs.Keys)
            {
                if (!store.TryGetValue(key, out var v)) continue;
                if (v is null) continue;              // blank choice => let the engine seed it
                if (v is string sv && sv.Length == 0) continue;
                d[key] = v;
            }
            if (d.Count > 0) payload[t] = d;
        }
        return payload.Count == 0 ? "{}" : JsonSerializer.Serialize(payload);
    }

    // ------------------------------------------------------------------ seed

    private async Task RandomizeSeedAsync()
    {
        if (_engine is null) return;
        SetStatus("Fetching a seed\u2026");
        var res = await RunSafeAsync(new[] { "--seeds", "1" });
        if (res?.Json is JsonElement json && res.Ok)
        {
            var seeds = SeedsPayload.Parse(json);
            if (seeds.Count > 0)
            {
                _txtSeed.Text = seeds[0];
                Log("New seed: " + seeds[0]);
                SetStatus("Ready.");
                return;
            }
        }
        SetStatus("Could not fetch a seed.");
    }

    private void UpdateTitleAndOut()
    {
        var seed = _txtSeed.Text.Trim();
        Text = seed.Length > 0 ? $"Summoner Randomizer \u2014 seed {seed}" : "Summoner Randomizer";

        if (_engine is null) return;
        if (_outTouched && _txtOut.Text.Trim().Length > 0) return;

        var mode = _cmbMode.SelectedItem is ModeInfo m ? m.Key : "custom";
        var iso = _txtIso.Text.Trim();
        var stem = iso.Length > 0 ? Path.GetFileNameWithoutExtension(iso) : "Summoner";
        string name = $"{stem}-{mode}-{(seed.Length > 0 ? seed : "SUMMONER")}.iso";
        _settingOut = true;
        try { _txtOut.Text = Path.Combine(_engine.WorkOutDir, name); }
        finally { _settingOut = false; }
    }

    // ---------------------------------------------------------------- browse

    private async void BrowseIso()
    {
        using var dlg = new OpenFileDialog
        {
            Title = "Choose a Summoner disc image",
            Filter = "Disc images (*.iso)|*.iso|All files (*.*)|*.*",
            CheckFileExists = true,
        };
        if (dlg.ShowDialog(this) != DialogResult.OK) return;

        _txtIso.Text = dlg.FileName;
        UpdateTitleAndOut();
        await IdentifyAsync(dlg.FileName);
    }

    private async Task IdentifyAsync(string iso)
    {
        if (_engine is null) return;
        _identify = null;
        _discSupported = false;
        SetBuildEnabled(false);
        _lblIdentify.ForeColor = SystemColors.GrayText;
        _lblIdentify.Text = "Reading the disc\u2026";
        SetStatus("Identifying disc\u2026");

        var res = await RunSafeAsync(new[] { "--identify", iso });
        if (res?.Json is not JsonElement json)
        {
            _lblIdentify.Text = "Could not read the disc (engine gave no JSON).";
            _lblIdentify.ForeColor = Color.Firebrick;
            SetStatus("Identify failed.");
            return;
        }

        var info = IdentifyPayload.Parse(json);
        _identify = info;
        _discSupported = info.Supported;

        _lblIdentify.Text = IdentifyBanner(info);
        _lblIdentify.ForeColor = info.Supported ? Color.DarkGreen : Color.Firebrick;

        SetBuildEnabled(info.Supported);
        SetStatus(info.Supported ? "Disc ready." : "Disc not supported \u2014 Build is disabled.");
        Log($"Identify: {info.Game} supported={info.Supported} vpp=v{info.VppVersionText} ({res.ExitCode})");
    }

    private static string IdentifyBanner(IdentifyPayload info)
    {
        var vol = info.VolumeId.Length > 0 ? info.VolumeId : "(no known volume id)";
        var tbl = info.TablesOffset is not null ? $"{info.TablesOffset} ({info.TablesEntries} entries)" : "\u2014";
        var head = info.Supported ? $"{info.Game} \u2022 VPP v{info.VppVersionText} \u2022 SUPPORTED" : $"{info.Game} \u2022 VPP v{info.VppVersionText} \u2022 NOT SUPPORTED";
        return head + Environment.NewLine +
            $"volume {vol} \u2022 boot {info.BootElf} \u2022 {info.VppCount} archives \u2022 tables {tbl}" +
            (info.Reason.Length > 0 ? Environment.NewLine + "reason: " + info.Reason : "");
    }

    // ----------------------------------------------------- headless UI probe
    //
    // The console harness (SummonerRando.Harness) uses the members below to
    // exercise the real window in a session with no desktop: it builds the
    // form, feeds it real engine payloads and renders/dumps it. Nothing here
    // runs during normal use, so the user-facing behaviour is unchanged.

    /// <summary>
    /// Populates the mode list, the feature grid, the options panel and the
    /// blocked-features pane from an already-parsed <c>--list</c> payload,
    /// exactly as the app does when it has just read the engine. This is the
    /// "a disc/list is available" state used for headless screenshots.
    /// </summary>
    public void HarnessApplyList(ListPayload list, string? modeKey = null)
    {
        ArgumentNullException.ThrowIfNull(list);
        _list = list;

        _cmbMode.BeginUpdate();
        _cmbMode.Items.Clear();
        foreach (var m in _list.Modes)
            _cmbMode.Items.Add(m);
        _cmbMode.DisplayMember = nameof(ModeInfo.Display);
        _cmbMode.Enabled = _cmbMode.Items.Count > 0;
        _cmbMode.EndUpdate();

        PopulateFeatures();

        if (_cmbMode.Items.Count > 0)
            _cmbMode.SelectedIndex = IndexOfMode(modeKey ?? "vanilla");

        _txtPending.Text = BuildPendingText(_list);
        Log($"Loaded {_list.Modes.Count} modes, {_list.Transforms.Count} transforms, " +
            $"{_list.OptionAware.Count} option-aware, {_list.Pending.Count} pending.");
        SetStatus("Ready.");
    }

    /// <summary>Applies a parsed <c>--identify</c> result, as the app does after
    /// a disc is chosen (used headlessly; no disc is opened here).</summary>
    public void HarnessApplyIdentify(IdentifyPayload info)
    {
        ArgumentNullException.ThrowIfNull(info);
        _identify = info;
        _discSupported = info.Supported;
        _lblIdentify.Text = IdentifyBanner(info);
        _lblIdentify.ForeColor = info.Supported ? Color.DarkGreen : Color.Firebrick;
        SetBuildEnabled(info.Supported);
        SetStatus(info.Supported ? "Disc ready." : "Disc not supported \u2014 Build is disabled.");
    }

    /// <summary>Writes a line into the on-screen log box (headless render helper).</summary>
    public void HarnessLog(string line) => Log(line);

    /// <summary>Applies a seed exactly as RandomizeSeedAsync does after the
    /// engine answers <c>--seeds 1</c> (headless helper; same code path).</summary>
    public void HarnessApplySeed(string seed)
    {
        _txtSeed.Text = seed;
        Log("New seed: " + seed);
        SetStatus("Ready.");
    }

    /// <summary>The root layout panel, for harness render fallbacks.</summary>
    public Control? HarnessRoot => Controls.Count > 0 ? Controls[0] : null;

    /// <summary>Current status line text (headless assertions).</summary>
    public string HarnessStatus => _lblStatus.Text;

    // ----------------------------------------------------------------- build

    private void PickOutput()
    {
        using var dlg = new SaveFileDialog
        {
            Title = "Where should the new ISO go?",
            Filter = "Disc images (*.iso)|*.iso|All files (*.*)|*.*",
            FileName = Path.GetFileName(_txtOut.Text.Trim()),
            InitialDirectory = SafeDir(_txtOut.Text.Trim()),
            OverwritePrompt = true,
        };
        if (dlg.ShowDialog(this) != DialogResult.OK) return;
        _settingOut = true;
        try { _txtOut.Text = dlg.FileName; _outTouched = true; }
        finally { _settingOut = false; }
    }

    private static string SafeDir(string file)
    {
        try
        {
            var d = Path.GetDirectoryName(file);
            return d is not null && Directory.Exists(d) ? d : "";
        }
        catch { return ""; }
    }

    private async Task RunBuildAsync(bool dryRun)
    {
        if (_engine is null || _list is null || _busy) return;

        var iso = _txtIso.Text.Trim();
        if (iso.Length == 0 || !File.Exists(iso))
        {
            Fail("Pick an ISO file first.");
            return;
        }
        if (!_discSupported)
        {
            Fail("This disc is not supported; nothing can be built.");
            return;
        }

        var seed = _txtSeed.Text.Trim();
        if (seed.Length == 0)
        {
            Fail("Enter a seed (or press Random seed).");
            return;
        }

        var modeKey = _cmbMode.SelectedItem is ModeInfo m ? m.Key : "custom";
        var modeSet = new HashSet<string>(_list.Mode(modeKey)?.Transforms ?? (IReadOnlyList<string>)Array.Empty<string>(), StringComparer.Ordinal);
        var checkedSet = CheckedTransforms();
        var exclude = modeSet.Where(t => !checkedSet.Contains(t)).ToList();
        var include = checkedSet.Where(t => !modeSet.Contains(t)).ToList();
        var optionsJson = BuildOptionsJson(checkedSet);

        var outPath = _txtOut.Text.Trim();
        if (outPath.Length == 0)
        {
            UpdateTitleAndOut();
            outPath = _txtOut.Text.Trim();
        }

        if (!dryRun && File.Exists(outPath))
        {
            var ow = MessageBox.Show(this,
                "Overwrite this file?\n\n" + outPath,
                "Output exists", MessageBoxButtons.YesNo, MessageBoxIcon.Warning);
            if (ow != DialogResult.Yes) return;
        }

        var args = EngineClient.BuildArgs(iso, modeKey, seed, outPath, dryRun, include, exclude, optionsJson);

        _txtResult.Text = "";
        _txtLog.Clear();
        Log($"==== {(dryRun ? "DRY RUN" : "BUILD")} ====");
        Log($"seed={seed}  mode={modeKey}");
        Log($"features ({checkedSet.Count}): {string.Join(", ", checkedSet.OrderBy(x => x, StringComparer.Ordinal))}");
        if (exclude.Count > 0) Log($"excluded: {string.Join(", ", exclude.OrderBy(x => x, StringComparer.Ordinal))}");
        if (include.Count > 0) Log($"added:    {string.Join(", ", include.OrderBy(x => x, StringComparer.Ordinal))}");
        if (optionsJson != "{}") Log($"options:  {optionsJson}");
        if (!dryRun) Log($"output:   {outPath}");

        SetRunning(true);
        SetButtonsEnabled(false);
        SetStatus(dryRun ? "Dry run\u2026" : "Building ISO\u2026 (this copies the whole disc)");

        try
        {
            var res = await RunSafeAsync(args);
            HandleBuildResult(res, dryRun, seed, modeKey, outPath);
        }
        catch (Exception ex)
        {
            Log("EXCEPTION: " + ex.Message);
            Fail(ex.Message);
        }
        finally
        {
            SetRunning(false);
            SetButtonsEnabled(true);
            SetBuildEnabled(_discSupported);
        }
    }

    private void HandleBuildResult(EngineRunResult? res, bool dryRun, string seed, string modeKey, string outPath)
    {
        if (res is null)
        {
            Fail("The engine did not run.");
            return;
        }

        if (res.Json is not JsonElement json)
        {
            var tail = Tail(res.Stderr, 800);
            Fail($"Engine returned no JSON (exit {res.ExitCode})." + (tail.Length > 0 ? "\n\n" + tail : ""));
            return;
        }

        if (res.ExitCode != 0)
        {
            var err = res.EngineError ?? $"Engine failed (exit {res.ExitCode}).";
            Fail(err);
            return;
        }

        var b = BuildResult.Parse(json);
        var sb = new StringBuilder();
        sb.AppendLine("SEED       " + (b.Seed.Length > 0 ? b.Seed : seed));
        sb.AppendLine("MODE       " + (b.Mode.Length > 0 ? b.Mode : modeKey));
        sb.AppendLine("KIND       " + (dryRun ? "DRY RUN (nothing written)" : "BUILD"));

        if (!dryRun)
        {
            sb.AppendLine("OUTPUT     " + (b.Dst ?? outPath));
            sb.AppendLine("EDITS      " + b.Edits);
            if (!string.IsNullOrEmpty(b.DstSha256))
                sb.AppendLine("SHA-256    " + b.DstSha256);
            sb.AppendLine("SIZE       " + Human(b.SrcBytes) + " -> " + Human(b.DstBytes) +
                          (b.SizePreserved ? "  (preserved)" : "  (CHANGED)"));
        }
        else
        {
            sb.AppendLine("EDITS      " + b.Edits + "  (would change)");
            sb.AppendLine("BYTES      " + b.ChangedBytesTotal.ToString("N0") + " of the data blob");
        }

        sb.AppendLine();
        sb.AppendLine("Per feature:");
        foreach (var r in b.Reports)
        {
            var note = r.Notes.Count > 0 ? "  \u2014 " + string.Join("; ", r.Notes) : "";
            sb.AppendLine($"  {r.Transform,-24} {r.Changed,6} edits{note}");
        }
        if (b.Reports.Count == 0)
            sb.AppendLine("  (no transform reports)");

        _txtResult.Text = sb.ToString();
        Log($"exit={res.ExitCode}");
        Log(dryRun
            ? $"Dry run complete: {b.Edits} edits would be made."
            : $"Built {b.Name ?? Path.GetFileName(outPath)}: {b.Edits} edits, sha256 {b.DstSha256}");
        SetStatus(dryRun ? "Dry run done." : "Build done.");
    }

    private void Fail(string msg)
    {
        _txtResult.Text = "FAILED" + Environment.NewLine + Environment.NewLine + msg;
        Log("FAILED: " + msg);
        SetStatus("Failed.");
    }

    // ------------------------------------------------------------- plumbing

    private async Task<EngineRunResult?> RunSafeAsync(IReadOnlyList<string> args)
    {
        if (_engine is null) return null;
        var progress = new Progress<string>(Log);
        try
        {
            return await _engine.RunAsync(args, progress, CancellationToken.None);
        }
        catch (Exception ex)
        {
            Log("EXCEPTION: " + ex.Message);
            return new EngineRunResult { ExitCode = -1, Stderr = ex.Message };
        }
    }

    private void Log(string line)
    {
        if (InvokeRequired) { BeginInvoke(new Action<string>(Log), line); return; }
        var text = line.Replace("\r", "").Replace("\n", " ");
        _txtLog.AppendText(text + "\r\n");
        if (_txtLog.TextLength > 400_000)
            _txtLog.Text = _txtLog.Text.Substring(_txtLog.TextLength - 200_000);
        _txtLog.SelectionStart = _txtLog.TextLength;
        _txtLog.ScrollToCaret();
    }

    private void SetStatus(string s)
    {
        if (InvokeRequired) { BeginInvoke(new Action<string>(SetStatus), s); return; }
        _lblStatus.Text = s;
    }

    private void SetRunning(bool running)
    {
        _busy = running;
        _bar.MarqueeAnimationSpeed = running ? 30 : 0;
    }

    private void SetButtonsEnabled(bool enabled)
    {
        _btnDry.Enabled = enabled;
        _btnBuild.Enabled = enabled && _discSupported;
        _btnSeed.Enabled = enabled;
        _btnBrowse.Enabled = enabled;
        _btnOut.Enabled = enabled;
    }

    private void SetBuildEnabled(bool enabled)
    {
        _btnBuild.Enabled = enabled && !_busy;
        _btnDry.Enabled = enabled && !_busy;
    }

    private static string Human(long bytes)
    {
        string[] u = { "B", "KB", "MB", "GB", "TB" };
        double v = bytes;
        int i = 0;
        while (v >= 1024 && i < u.Length - 1) { v /= 1024; i++; }
        return v.ToString(i == 0 ? "N0" : "N1") + " " + u[i];
    }

    private static string Tail(string s, int max)
        => s.Length <= max ? s : s.Substring(s.Length - max);

    private static string BuildPendingText(ListPayload list)
    {
        if (list.Pending.Count == 0) return "(nothing reported as blocked)";
        var sb = new StringBuilder();
        foreach (var p in list.Pending.OrderBy(p => p.Key, StringComparer.Ordinal))
        {
            sb.Append(p.Key);
            if (p.BlockedBy.Length > 0) sb.Append("  \u2014 blocked by: ").Append(p.BlockedBy);
            sb.AppendLine();
            if (p.Reason.Length > 0) sb.Append("    ").AppendLine(p.Reason);
        }
        return sb.ToString().TrimEnd();
    }
}
