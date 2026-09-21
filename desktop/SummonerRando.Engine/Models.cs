using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;

namespace SummonerRando.Engine;

/// <summary>Typed views over the engine's JSON output. Parsing is defensive:
/// missing keys never throw, they surface as defaults.</summary>
public static class JsonHelp
{
    public static string? Str(this JsonElement e, string name)
        => e.ValueKind == JsonValueKind.Object && e.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.String
            ? v.GetString() : null;

    public static int? Int(this JsonElement e, string name)
        => e.ValueKind == JsonValueKind.Object && e.TryGetProperty(name, out var v) &&
           v.ValueKind == JsonValueKind.Number && v.TryGetInt32(out var i) ? i : null;

    public static long? Long(this JsonElement e, string name)
        => e.ValueKind == JsonValueKind.Object && e.TryGetProperty(name, out var v) &&
           v.ValueKind == JsonValueKind.Number && v.TryGetInt64(out var i) ? i : null;

    public static bool? Bool(this JsonElement e, string name)
        => e.ValueKind == JsonValueKind.Object && e.TryGetProperty(name, out var v) &&
           (v.ValueKind == JsonValueKind.True || v.ValueKind == JsonValueKind.False) ? v.GetBoolean() : null;

    public static JsonElement? Prop(this JsonElement e, string name)
        => e.ValueKind == JsonValueKind.Object && e.TryGetProperty(name, out var v) ? v : null;
}

public sealed class TransformInfo
{
    public string Name { get; init; } = "";
    public string Label { get; init; } = "";
    public string Description { get; init; } = "";
}

public sealed class ModeInfo
{
    public string Key { get; init; } = "";
    public string Label { get; init; } = "";
    public string Blurb { get; init; } = "";
    public string Risk { get; init; } = "";
    public IReadOnlyList<string> Transforms { get; init; } = Array.Empty<string>();
    public JsonElement? Options { get; init; }
    public bool HasBinary { get; init; }

    public string Display => Label.Length > 0 ? Label : Key;
}

public sealed class OptionChoice
{
    public string? Value { get; init; }
    public string Display { get; init; } = "";
}

public sealed class OptionSpec
{
    public string Key { get; init; } = "";
    public string Type { get; init; } = "int";
    public JsonElement Default { get; init; }
    public int? Min { get; init; }
    public int? Max { get; init; }
    public string Label { get; init; } = "";
    public string Help { get; init; } = "";
    public IReadOnlyList<OptionChoice> Choices { get; init; } = Array.Empty<OptionChoice>();

    public int DefaultInt => Default.ValueKind == JsonValueKind.Number && Default.TryGetInt32(out var i) ? i : 0;
    public bool DefaultBool => Default.ValueKind == JsonValueKind.True;
    public string? DefaultChoice => Default.ValueKind == JsonValueKind.String ? Default.GetString() : null;
}

public sealed class PendingInfo
{
    public string Key { get; init; } = "";
    public string Reason { get; init; } = "";
    public string BlockedBy { get; init; } = "";
}

public sealed class BinaryInfo
{
    public string Key { get; init; } = "";
    public string Label { get; init; } = "";
    public string Help { get; init; } = "";
    public string Va { get; init; } = "";
    public string Expects { get; init; } = "";
}

public sealed class ListPayload
{
    public IReadOnlyList<ModeInfo> Modes { get; init; } = Array.Empty<ModeInfo>();
    public IReadOnlyList<string> Transforms { get; init; } = Array.Empty<string>();
    public IReadOnlyDictionary<string, TransformInfo> Info { get; init; } = new Dictionary<string, TransformInfo>();
    public IReadOnlyDictionary<string, IReadOnlyDictionary<string, OptionSpec>> Options { get; init; }
        = new Dictionary<string, IReadOnlyDictionary<string, OptionSpec>>();
    public IReadOnlyList<string> OptionAware { get; init; } = Array.Empty<string>();
    public IReadOnlyList<PendingInfo> Pending { get; init; } = Array.Empty<PendingInfo>();
    public IReadOnlyDictionary<string, BinaryInfo> Binary { get; init; } = new Dictionary<string, BinaryInfo>();

    public ModeInfo? Mode(string key) => Modes.FirstOrDefault(m => m.Key == key);

    public static ListPayload Parse(JsonElement root)
    {
        var modes = new List<ModeInfo>();
        var modesEl = root.Prop("modes");
        if (modesEl is JsonElement me && me.ValueKind == JsonValueKind.Object)
        {
            var ordered = new List<string>();
            if (root.Prop("mode_order") is JsonElement mo && mo.ValueKind == JsonValueKind.Array)
                ordered.AddRange(mo.EnumerateArray().Where(x => x.ValueKind == JsonValueKind.String).Select(x => x.GetString()!));
            // any modes not listed in mode_order still get shown, at the end
            foreach (var p in me.EnumerateObject())
                if (!ordered.Contains(p.Name))
                    ordered.Add(p.Name);

            foreach (var key in ordered)
            {
                if (!me.TryGetProperty(key, out var m) || m.ValueKind != JsonValueKind.Object)
                    continue;
                var tf = new List<string>();
                if (m.Prop("transforms") is JsonElement tfa && tfa.ValueKind == JsonValueKind.Array)
                    tf.AddRange(tfa.EnumerateArray().Where(x => x.ValueKind == JsonValueKind.String).Select(x => x.GetString()!));
                bool hasBinary = m.Prop("binary") is JsonElement b && b.ValueKind == JsonValueKind.Array && b.GetArrayLength() > 0;
                modes.Add(new ModeInfo
                {
                    Key = key,
                    Label = m.Str("label") ?? key,
                    Blurb = m.Str("blurb") ?? "",
                    Risk = m.Str("risk") ?? "",
                    Transforms = tf,
                    Options = m.Prop("options"),
                    HasBinary = hasBinary,
                });
            }
        }

        var transforms = new List<string>();
        if (root.Prop("transforms") is JsonElement te && te.ValueKind == JsonValueKind.Array)
            transforms.AddRange(te.EnumerateArray().Where(x => x.ValueKind == JsonValueKind.String).Select(x => x.GetString()!));

        var info = new Dictionary<string, TransformInfo>();
        if (root.Prop("info") is JsonElement ie && ie.ValueKind == JsonValueKind.Object)
        {
            foreach (var p in ie.EnumerateObject())
            {
                string label = p.Name, desc = "";
                if (p.Value.ValueKind == JsonValueKind.Array)
                {
                    var arr = p.Value.EnumerateArray().ToList();
                    if (arr.Count > 0 && arr[0].ValueKind == JsonValueKind.String) label = arr[0].GetString()!;
                    if (arr.Count > 1 && arr[1].ValueKind == JsonValueKind.String) desc = arr[1].GetString()!;
                }
                info[p.Name] = new TransformInfo { Name = p.Name, Label = label, Description = desc };
            }
        }

        var options = new Dictionary<string, IReadOnlyDictionary<string, OptionSpec>>();
        if (root.Prop("options") is JsonElement oe && oe.ValueKind == JsonValueKind.Object)
        {
            foreach (var tp in oe.EnumerateObject())
            {
                var specs = new Dictionary<string, OptionSpec>();
                if (tp.Value.ValueKind == JsonValueKind.Object)
                {
                    foreach (var op in tp.Value.EnumerateObject())
                    {
                        var s = op.Value;
                        var choices = new List<OptionChoice>();
                        if (s.Prop("choices") is JsonElement ch && ch.ValueKind == JsonValueKind.Array)
                        {
                            foreach (var c in ch.EnumerateArray())
                            {
                                choices.Add(c.ValueKind == JsonValueKind.Null
                                    ? new OptionChoice { Value = null, Display = "(seeded random pick)" }
                                    : new OptionChoice { Value = c.GetString(), Display = c.GetString() ?? "(blank)" });
                            }
                        }
                        specs[op.Name] = new OptionSpec
                        {
                            Key = op.Name,
                            Type = s.Str("type") ?? "int",
                            Default = s.Prop("default") ?? default,
                            Min = s.Int("min"),
                            Max = s.Int("max"),
                            Label = s.Str("label") ?? op.Name,
                            Help = s.Str("help") ?? "",
                            Choices = choices,
                        };
                    }
                }
                options[tp.Name] = specs;
            }
        }

        var optionAware = new List<string>();
        if (root.Prop("option_aware") is JsonElement oa && oa.ValueKind == JsonValueKind.Array)
            optionAware.AddRange(oa.EnumerateArray().Where(x => x.ValueKind == JsonValueKind.String).Select(x => x.GetString()!));
        if (optionAware.Count == 0)
            optionAware.AddRange(options.Keys);

        var pending = new List<PendingInfo>();
        if (root.Prop("pending") is JsonElement pe && pe.ValueKind == JsonValueKind.Object)
        {
            foreach (var p in pe.EnumerateObject())
                pending.Add(new PendingInfo
                {
                    Key = p.Name,
                    Reason = p.Value.Str("reason") ?? "",
                    BlockedBy = p.Value.Str("blocked_by") ?? "",
                });
        }

        var binary = new Dictionary<string, BinaryInfo>();
        if (root.Prop("binary") is JsonElement be && be.ValueKind == JsonValueKind.Object)
        {
            foreach (var p in be.EnumerateObject())
                binary[p.Name] = new BinaryInfo
                {
                    Key = p.Name,
                    Label = p.Value.Str("label") ?? p.Name,
                    Help = p.Value.Str("help") ?? "",
                    Va = p.Value.Str("va") ?? "",
                    Expects = p.Value.Str("expects") ?? "",
                };
        }

        return new ListPayload
        {
            Modes = modes,
            Transforms = transforms,
            Info = info,
            Options = options,
            OptionAware = optionAware,
            Pending = pending,
            Binary = binary,
        };
    }
}

public sealed class IdentifyPayload
{
    public string Path { get; init; } = "";
    public string Game { get; init; } = "";
    public bool Supported { get; init; }
    public string Reason { get; init; } = "";
    public string VolumeId { get; init; } = "";
    public string BootElf { get; init; } = "";
    public long Bytes { get; init; }
    public int VppCount { get; init; }
    public IReadOnlyList<int> VppVersions { get; init; } = Array.Empty<int>();
    public string? TablesOffset { get; init; }
    public int? TablesEntries { get; init; }

    public string VppVersionText => VppVersions.Count == 0 ? "?" : string.Join("/", VppVersions);

    public static IdentifyPayload Parse(JsonElement root)
    {
        var vers = new List<int>();
        if (root.Prop("vpp_versions") is JsonElement vv && vv.ValueKind == JsonValueKind.Array)
            foreach (var v in vv.EnumerateArray())
                if (v.ValueKind == JsonValueKind.Number && v.TryGetInt32(out var i)) vers.Add(i);

        string? tablesOffset = null;
        int? tablesEntries = null;
        if (root.Prop("tables") is JsonElement tb && tb.ValueKind == JsonValueKind.Object)
        {
            tablesOffset = tb.Str("offset");
            tablesEntries = tb.Int("entries");
        }

        return new IdentifyPayload
        {
            Path = root.Str("path") ?? "",
            Game = root.Str("game") ?? "Unknown",
            Supported = root.Bool("supported") ?? false,
            Reason = root.Str("reason") ?? "",
            VolumeId = root.Str("volume_id") ?? "",
            BootElf = root.Str("boot_elf") ?? "",
            Bytes = root.Long("bytes") ?? 0,
            VppCount = root.Int("vpp_count") ?? 0,
            VppVersions = vers,
            TablesOffset = tablesOffset,
            TablesEntries = tablesEntries,
        };
    }
}

public sealed class BuildReportRow
{
    public string Transform { get; init; } = "";
    public int Changed { get; init; }
    public IReadOnlyList<string> Notes { get; init; } = Array.Empty<string>();
    public long ImpactBytes { get; init; }
}

public sealed class BuildResult
{
    public bool Dry { get; init; }
    public string Mode { get; init; } = "";
    public string Seed { get; init; } = "";
    public string? Dst { get; init; }
    public string? Name { get; init; }
    public string? DstSha256 { get; init; }
    public string? SrcSha256 { get; init; }
    public long SrcBytes { get; init; }
    public long DstBytes { get; init; }
    public bool SizePreserved { get; init; }
    public int Edits { get; init; }
    public long ChangedBytesTotal { get; init; }
    public bool WritesFile { get; init; }
    public IReadOnlyList<string> Transforms { get; init; } = Array.Empty<string>();
    public IReadOnlyList<BuildReportRow> Reports { get; init; } = Array.Empty<BuildReportRow>();

    public static BuildResult Parse(JsonElement root)
    {
        var transforms = new List<string>();
        if (root.Prop("transforms") is JsonElement t && t.ValueKind == JsonValueKind.Array)
            transforms.AddRange(t.EnumerateArray().Where(x => x.ValueKind == JsonValueKind.String).Select(x => x.GetString()!));

        var reports = new List<BuildReportRow>();
        if (root.Prop("reports") is JsonElement rs && rs.ValueKind == JsonValueKind.Array)
        {
            foreach (var r in rs.EnumerateArray())
            {
                var notes = new List<string>();
                if (r.Prop("notes") is JsonElement ns && ns.ValueKind == JsonValueKind.Array)
                    notes.AddRange(ns.EnumerateArray().Where(x => x.ValueKind == JsonValueKind.String).Select(x => x.GetString()!));
                reports.Add(new BuildReportRow
                {
                    Transform = r.Str("transform") ?? "",
                    Changed = r.Int("changed") ?? 0,
                    Notes = notes,
                    ImpactBytes = r.Long("impact_bytes") ?? 0,
                });
            }
        }

        // build emits "edits"; dry-run emits "edit_total"
        int edits = root.Int("edits") ?? root.Int("edit_total") ?? reports.Sum(r => r.Changed);

        return new BuildResult
        {
            Dry = root.Bool("dry") ?? false,
            Mode = root.Str("mode") ?? "",
            Seed = root.Str("seed") ?? "",
            Dst = root.Str("dst"),
            Name = root.Str("name"),
            DstSha256 = root.Str("dst_sha256"),
            SrcSha256 = root.Str("src_sha256"),
            SrcBytes = root.Long("src_bytes") ?? 0,
            DstBytes = root.Long("dst_bytes") ?? root.Long("src_bytes") ?? 0,
            SizePreserved = root.Bool("size_preserved") ?? true,
            Edits = edits,
            ChangedBytesTotal = root.Long("changed_bytes_total") ?? 0,
            WritesFile = root.Bool("writes_file") ?? !(root.Bool("dry") ?? false),
            Transforms = transforms,
            Reports = reports,
        };
    }
}

public static class SeedsPayload
{
    public static IReadOnlyList<string> Parse(JsonElement root)
    {
        var list = new List<string>();
        if (root.Prop("seeds") is JsonElement s && s.ValueKind == JsonValueKind.Array)
            list.AddRange(s.EnumerateArray().Where(x => x.ValueKind == JsonValueKind.String).Select(x => x.GetString()!));
        return list;
    }
}
