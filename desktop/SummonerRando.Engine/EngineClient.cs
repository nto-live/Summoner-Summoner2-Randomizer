using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace SummonerRando.Engine;

/// <summary>Result of a single cli.py invocation.</summary>
public sealed class EngineRunResult
{
    public int ExitCode { get; init; }
    public string Stdout { get; init; } = "";
    public string Stderr { get; init; } = "";
    public JsonElement? Json { get; init; }
    public string? JsonParseError { get; init; }
    public string CommandLine { get; init; } = "";

    public bool Ok => ExitCode == 0;

    /// <summary>The engine's "error" string, if it emitted one.</summary>
    public string? EngineError
    {
        get
        {
            if (Json is JsonElement j && j.ValueKind == JsonValueKind.Object &&
                j.TryGetProperty("error", out var e) && e.ValueKind == JsonValueKind.String)
                return e.GetString();
            return null;
        }
    }
}

/// <summary>
/// Thin, typed wrapper that runs the Summoner Randomizer engine (cli.py) as a
/// subprocess: one JSON document on stdout, "#progress ..." lines on stderr.
/// No HTTP, no server.
/// </summary>
public sealed class EngineClient
{
    public string EngineDir { get; }
    public string PythonExe { get; }
    public string CliPath => Path.Combine(EngineDir, EngineLocator.CliFileName);
    public string WorkOutDir => Path.Combine(EngineDir, "work", "out");

    /// <summary>
    /// The frozen engine (summoner-engine.exe), when one is shipped next to the app. Using it
    /// means the end user needs no Python at all - which is the whole point of the portable
    /// bundle. An explicitly supplied pythonExe overrides it, so development keeps using cli.py.
    /// </summary>
    public string? FrozenEngineExe { get; }

    public bool UsesFrozenEngine => FrozenEngineExe is not null;

    public EngineClient(string? engineDir = null, string? pythonExe = null)
    {
        EngineDir = EngineLocator.Resolve(engineDir);
        var frozen = Path.Combine(EngineDir, EngineLocator.FrozenEngineFileName);
        FrozenEngineExe = (pythonExe is null && File.Exists(frozen)) ? frozen : null;
        PythonExe = !string.IsNullOrWhiteSpace(pythonExe)
            ? pythonExe!
            : (Environment.GetEnvironmentVariable("SUMMONER_RANDO_PYTHON") is { Length: > 0 } p ? p : "python");
    }

    // ----- high level helpers ----------------------------------------------

    public Task<EngineRunResult> ListAsync(IProgress<string>? progress = null, CancellationToken ct = default)
        => RunAsync(new[] { "--list" }, progress, ct);

    public Task<EngineRunResult> IdentifyAsync(string iso, IProgress<string>? progress = null, CancellationToken ct = default)
        => RunAsync(new[] { "--identify", iso }, progress, ct);

    public Task<EngineRunResult> SeedsAsync(int count, IProgress<string>? progress = null, CancellationToken ct = default)
        => RunAsync(new[] { "--seeds", count.ToString() }, progress, ct);

    /// <summary>Builds the --build argument vector. Exposed for tests/harness.</summary>
    public static List<string> BuildArgs(
        string iso, string mode, string seed, string outPath, bool dryRun,
        IEnumerable<string>? include = null, IEnumerable<string>? exclude = null,
        string? optionsJson = null)
    {
        var args = new List<string>
        {
            "--build", iso,
            "--mode", mode,
            "--seed", seed,
            "--out", outPath,
        };
        if (dryRun) args.Add("--dry-run");
        if (exclude is not null)
            foreach (var t in exclude) { args.Add("--exclude"); args.Add(t); }
        if (include is not null)
            foreach (var t in include) { args.Add("--include"); args.Add(t); }
        if (!string.IsNullOrWhiteSpace(optionsJson) && optionsJson != "{}")
        {
            args.Add("--options");
            args.Add(optionsJson!);
        }
        return args;
    }

    // ----- core runner ------------------------------------------------------

    public async Task<EngineRunResult> RunAsync(
        IReadOnlyList<string> args,
        IProgress<string>? progress = null,
        CancellationToken ct = default)
    {
        var psi = new ProcessStartInfo
        {
            FileName = FrozenEngineExe ?? PythonExe,
            WorkingDirectory = EngineDir,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
        };
        if (FrozenEngineExe is null)
            psi.ArgumentList.Add(CliPath);
        foreach (var a in args)
            psi.ArgumentList.Add(a);

        // Deterministic, UTF-8 safe child.
        psi.Environment["PYTHONIOENCODING"] = "utf-8";
        psi.Environment["PYTHONUTF8"] = "1";
        psi.Environment["PYTHONDONTWRITEBYTECODE"] = "1";

        string cmdline = DescribeCommand(psi);
        progress?.Report("$ " + cmdline);

        using var proc = new Process { StartInfo = psi };
        try
        {
            if (!proc.Start())
                return new EngineRunResult { ExitCode = -1, Stderr = "Failed to start engine: " + psi.FileName, CommandLine = cmdline };
        }
        catch (Exception ex)
        {
            return new EngineRunResult
            {
                ExitCode = -1,
                Stderr = $"Failed to start \"{PythonExe}\": {ex.Message}",
                CommandLine = cmdline,
            };
        }

        var stdoutTask = proc.StandardOutput.ReadToEndAsync();
        var stderrSb = new StringBuilder();

        try
        {
            string? line;
            while ((line = await proc.StandardError.ReadLineAsync(ct).ConfigureAwait(false)) is not null)
            {
                if (line.StartsWith("#progress ", StringComparison.Ordinal))
                    progress?.Report(line.Substring("#progress ".Length).Trim());
                else if (line.Length > 0)
                    progress?.Report(line);
                stderrSb.AppendLine(line);
            }

            await proc.WaitForExitAsync(ct).ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            TryKill(proc);
            throw;
        }

        var stdout = await stdoutTask.ConfigureAwait(false);

        JsonElement? json = null;
        string? parseError = null;
        try
        {
            json = ParseLastJsonObject(stdout);
        }
        catch (Exception ex)
        {
            parseError = ex.Message;
        }

        return new EngineRunResult
        {
            ExitCode = proc.ExitCode,
            Stdout = stdout,
            Stderr = stderrSb.ToString(),
            Json = json,
            JsonParseError = parseError,
            CommandLine = cmdline,
        };
    }

    private static void TryKill(Process proc)
    {
        try { if (!proc.HasExited) proc.Kill(entireProcessTree: true); }
        catch { /* best effort */ }
    }

    /// <summary>
    /// The engine prints exactly one JSON document on stdout. Be forgiving:
    /// scan the lines back to front and take the last one that parses.
    /// </summary>
    public static JsonElement? ParseLastJsonObject(string stdout)
    {
        if (string.IsNullOrWhiteSpace(stdout))
            return null;

        var lines = stdout.Replace("\r\n", "\n").Split('\n');
        for (int i = lines.Length - 1; i >= 0; i--)
        {
            var trimmed = lines[i].Trim();
            if (trimmed.Length == 0) continue;
            if (trimmed[0] != '{' && trimmed[0] != '[') continue;
            try
            {
                using var doc = JsonDocument.Parse(trimmed);
                return doc.RootElement.Clone();
            }
            catch (JsonException)
            {
                // not the JSON line; keep looking
            }
        }
        return null;
    }

    private static string DescribeCommand(ProcessStartInfo psi)
    {
        var sb = new StringBuilder(psi.FileName);
        foreach (var a in psi.ArgumentList)
            sb.Append(' ').Append(Quote(a));
        return sb.ToString();
    }

    private static string Quote(string s)
        => s.Length > 0 && s.IndexOf(' ') >= 0 ? "\"" + s + "\"" : s;
}
