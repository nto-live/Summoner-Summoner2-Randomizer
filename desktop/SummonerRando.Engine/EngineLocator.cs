using System;
using System.Collections.Generic;
using System.IO;

namespace SummonerRando.Engine;

/// <summary>
/// Finds the directory that holds the engine - either cli.py (the Python engine) or
/// summoner-engine.exe (the same engine, frozen for machines with no Python).
/// Order: explicit override, engine.txt next to the running exe,
/// SUMMONER_RANDO_ENGINE env var, then walk up from the app base directory.
/// </summary>
public static class EngineLocator
{
    public const string CliFileName = "cli.py";
    public const string FrozenEngineFileName = "summoner-engine.exe";

    /// <summary>True when this folder is runnable without Python.</summary>
    public static bool HasFrozenEngine(string dir) =>
        File.Exists(Path.Combine(dir, FrozenEngineFileName));

    public static string Resolve(string? overrideDir = null)
    {
        foreach (var candidate in Candidates(overrideDir))
        {
            if (string.IsNullOrWhiteSpace(candidate))
                continue;

            try
            {
                var full = Path.GetFullPath(candidate!);
                if (File.Exists(Path.Combine(full, CliFileName)) || HasFrozenEngine(full))
                    return full;
            }
            catch
            {
                // ignore malformed candidate paths
            }
        }

        throw new FileNotFoundException(
            "Could not find the engine. Ship " + FrozenEngineFileName + " next to the app, or " +
            "point the app at the folder holding " + CliFileName + " with the " +
            "SUMMONER_RANDO_ENGINE environment variable, or drop an engine.txt " +
            "file next to the exe containing the engine's folder path.");
    }

    private static IEnumerable<string?> Candidates(string? overrideDir)
    {
        if (!string.IsNullOrWhiteSpace(overrideDir))
            yield return overrideDir;

        var marker = Path.Combine(AppContext.BaseDirectory, "engine.txt");
        if (File.Exists(marker))
        {
            string? text = null;
            try { text = File.ReadAllText(marker).Trim(); } catch { /* ignore */ }
            if (!string.IsNullOrWhiteSpace(text))
                yield return text;
        }

        yield return Environment.GetEnvironmentVariable("SUMMONER_RANDO_ENGINE");

        DirectoryInfo? dir = new DirectoryInfo(AppContext.BaseDirectory);
        for (int i = 0; i < 10 && dir is not null; i++)
        {
            yield return dir.FullName;
            dir = dir.Parent;
        }
    }
}
