using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using SummonerRando.Engine;

namespace SummonerRando.Harness;

// Console harness: proves the GUI's engine plumbing without a desktop session.
// It runs the real cli.py and parses the output with the exact same code the
// WinForms app uses.
//
// Three modes:
//   (no flags)                engine plumbing run (as before)
//   --screenshot <out.png>    render the real MainForm headlessly to a PNG
//   --dump-ui <out.json>      dump the MainForm control tree as JSON
//
// Both UI modes accept: [--state empty|populated] [--mode <key>] [--iso <path>]
//                       [--width W] [--height H]
internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        try
        {
            if (args.Length > 0 && args[0] == "--screenshot")
                return UiProof.RunScreenshot(args.Skip(1).ToArray());
            if (args.Length > 0 && args[0] == "--dump-ui")
                return UiProof.RunDumpUi(args.Skip(1).ToArray());
            return EngineHarnessAsync(args).GetAwaiter().GetResult();
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine("HARNESS ERROR: " + ex);
            return 1;
        }
    }

    private static async Task<int> EngineHarnessAsync(string[] args)
    {
        string iso = args.Length > 0 ? args[0] : @"F:\rando\S1\iso\Summoner.iso";
        string? unsupported = args.Length > 1 ? args[1] : null;

        EngineClient engine;
        try { engine = new EngineClient(); }
        catch (Exception ex) { Console.WriteLine("ENGINE NOT FOUND: " + ex.Message); return 3; }

        Console.WriteLine("engine dir : " + engine.EngineDir);
        Console.WriteLine("python     : " + engine.PythonExe);
        Console.WriteLine();

        var log = new Progress<string>(m => Console.WriteLine("   | " + m));

        // ---- --list ---------------------------------------------------------
        Console.WriteLine("== --list ==");
        var lr = await engine.ListAsync(log);
        Console.WriteLine($"exit={lr.ExitCode} json={(lr.Json is not null)}");
        if (lr.Json is not JsonElement lj) { Console.WriteLine("no JSON"); return 1; }
        var list = ListPayload.Parse(lj);
        Console.WriteLine($"  modes        : {list.Modes.Count}  (raw mode_order count check)");
        Console.WriteLine($"  transforms   : {list.Transforms.Count}");
        Console.WriteLine($"  option-aware : {string.Join(", ", list.OptionAware)}");
        Console.WriteLine($"  pending      : {list.Pending.Count}");
        Console.WriteLine($"  binary       : {string.Join(", ", list.Binary.Keys)}");
        foreach (var m in list.Modes.Take(3))
            Console.WriteLine($"    mode {m.Key,-14} tf={m.Transforms.Count} risk='{m.Risk}'");
        var any = list.Modes.FirstOrDefault(m => m.Key == "progression");
        if (any is not null)
            Console.WriteLine($"    progression defaults -> {any.Options}");
        var rh = list.Modes.FirstOrDefault(m => m.Key == "ring_hunt_any");
        Console.WriteLine($"    ring_hunt_any options -> {(rh?.Options?.ToString() ?? "(none)")}");
        var sample = list.Info.TryGetValue("ring_hunt", out var ti) ? ti : null;
        Console.WriteLine($"    info[ring_hunt] label='{sample?.Label}' desc.len={sample?.Description.Length}");
        Console.WriteLine();

        // cross-check: parsed transform list must equal raw JSON list
        if (lj.Prop("transforms") is JsonElement rawTf && rawTf.ValueKind == JsonValueKind.Array)
        {
            var raw = rawTf.EnumerateArray().Select(x => x.GetString()!).OrderBy(x => x).ToList();
            var parsed = list.Transforms.OrderBy(x => x).ToList();
            Console.WriteLine($"  transform list parse matches raw: {raw.SequenceEqual(parsed)}");
        }
        Console.WriteLine();

        // ---- --identify -----------------------------------------------------
        Console.WriteLine("== --identify " + iso + " ==");
        var ir = await engine.IdentifyAsync(iso, log);
        Console.WriteLine($"exit={ir.ExitCode} json={(ir.Json is not null)}");
        if (ir.Json is JsonElement ij)
        {
            var idp = IdentifyPayload.Parse(ij);
            Console.WriteLine($"  game={idp.Game} supported={idp.Supported} vpp=v{idp.VppVersionText} archives={idp.VppCount}");
            Console.WriteLine($"  volume='{idp.VolumeId}' tables={idp.TablesOffset}/{idp.TablesEntries} bytes={idp.Bytes:N0}");
            Console.WriteLine($"  reason: {idp.Reason}");
        }
        Console.WriteLine();

        if (unsupported is not null)
        {
            Console.WriteLine("== --identify (expected unsupported) " + unsupported + " ==");
            var ur = await engine.IdentifyAsync(unsupported, log);
            if (ur.Json is JsonElement uj)
            {
                var up = IdentifyPayload.Parse(uj);
                Console.WriteLine($"  exit={ur.ExitCode} game={up.Game} supported={up.Supported} reason={up.Reason}");
            }
            Console.WriteLine();
        }

        // ---- --seeds --------------------------------------------------------
        Console.WriteLine("== --seeds 1 ==");
        var sr = await engine.SeedsAsync(1, log);
        if (sr.Json is JsonElement sj)
        {
            var seeds = SeedsPayload.Parse(sj);
            Console.WriteLine($"  seeds={string.Join(",", seeds)}");
        }
        Console.WriteLine();

        // ---- dry run --------------------------------------------------------
        var outIso = Path.Combine(engine.WorkOutDir, "harness-dryrun.iso");
        var bargs = EngineClient.BuildArgs(iso, "doors", "HARNESS1", outIso, dryRun: true,
            exclude: null, include: null, optionsJson: null);
        Console.WriteLine("== --build ... --dry-run ==");
        Console.WriteLine("  argv: " + string.Join(" ", bargs));
        var br = await engine.RunAsync(bargs, log);
        Console.WriteLine($"exit={br.ExitCode} json={(br.Json is not null)}");
        if (br.Json is JsonElement bj)
        {
            var b = BuildResult.Parse(bj);
            Console.WriteLine($"  dry={b.Dry} seed={b.Seed} mode={b.Mode} edits={b.Edits} changedBytes={b.ChangedBytesTotal:N0} writesFile={b.WritesFile}");
            foreach (var r in b.Reports)
                Console.WriteLine($"    {r.Transform,-20} {r.Changed,5} {string.Join("; ", r.Notes)}");
            Console.WriteLine($"  output file exists (should be False): {File.Exists(outIso)}");
        }

        // options plumbing sanity: build the JSON the GUI would send
        var optsProbe = new Dictionary<string, Dictionary<string, object?>>
        {
            ["xp_scale"] = new() { ["percent"] = 250 },
            ["ring_hunt"] = new() { ["anchor"] = "any-ring", ["count"] = 2 },
        };
        Console.WriteLine("  options JSON sample: " + JsonSerializer.Serialize(optsProbe));
        Console.WriteLine();
        Console.WriteLine("HARNESS OK");
        return 0;
    }
}
