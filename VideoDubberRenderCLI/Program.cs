using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using Newtonsoft.Json;
using VideoDubber.Core;

namespace VideoDubberRenderCLI
{
    class Program
    {
        static int Main(string[] args)
        {
            try
            {
                string mode = "preview";
                string text = string.Empty;
                string jsonConfig = string.Empty;
                string outputPath = string.Empty;
                string srtPath = string.Empty;
                string outDir = string.Empty;
                int width = 1080;
                int height = 1920;

                for (int i = 0; i < args.Length; i++)
                {
                    if      (args[i] == "--mode"   && i + 1 < args.Length) mode       = args[++i];
                    else if (args[i] == "--text"   && i + 1 < args.Length) text       = args[++i];
                    else if (args[i] == "--config" && i + 1 < args.Length) jsonConfig = args[++i];
                    else if (args[i] == "--out"    && i + 1 < args.Length) outputPath = args[++i];
                    else if (args[i] == "--srt"    && i + 1 < args.Length) srtPath    = args[++i];
                    else if (args[i] == "--out-dir"&& i + 1 < args.Length) outDir     = args[++i];
                    else if (args[i] == "--width"  && i + 1 < args.Length) int.TryParse(args[++i], out width);
                    else if (args[i] == "--height" && i + 1 < args.Length) int.TryParse(args[++i], out height);
                }

                SubtitleConfig cfg = string.IsNullOrEmpty(jsonConfig)
                    ? new SubtitleConfig()
                    : JsonConvert.DeserializeObject<SubtitleConfig>(jsonConfig) ?? new SubtitleConfig();

                if (mode == "batch")
                {
                    return RunBatch(cfg, srtPath, outDir, width, height);
                }
                else
                {
                    // preview mode (default)
                    if (string.IsNullOrEmpty(outputPath))
                    {
                        Console.Error.WriteLine("Error: Missing --out parameter");
                        return 1;
                    }
                    SubtitleRenderer.RenderSubtitlePngOverlay(text, cfg, outputPath, width, height);
                    Console.WriteLine($"SUCCESS: {outputPath}");
                    return 0;
                }
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"ERROR: {ex.Message}");
                return 1;
            }
        }

        /// <summary>
        /// Batch mode: parse SRT, render one PNG per subtitle segment, print JSON manifest to stdout.
        /// JSON manifest format: [{"idx":0,"path":"...","start":1.0,"end":3.5}, ...]
        /// </summary>
        static int RunBatch(SubtitleConfig cfg, string srtPath, string outDir, int width, int height)
        {
            if (string.IsNullOrEmpty(srtPath) || !File.Exists(srtPath))
            {
                Console.Error.WriteLine($"Error: SRT file not found: {srtPath}");
                return 1;
            }
            if (string.IsNullOrEmpty(outDir))
            {
                Console.Error.WriteLine("Error: Missing --out-dir parameter for batch mode");
                return 1;
            }
            Directory.CreateDirectory(outDir);

            var segments = ParseSrt(srtPath);
            var manifest = new List<object>();

            for (int i = 0; i < segments.Count; i++)
            {
                var seg = segments[i];
                string pngPath = Path.Combine(outDir, $"sub_{i}.png");
                SubtitleRenderer.RenderSubtitlePngOverlay(seg.Text, cfg, pngPath, width, height);
                manifest.Add(new { idx = i, path = pngPath, start = seg.Start, end = seg.End });
            }

            Console.WriteLine(JsonConvert.SerializeObject(manifest));
            return 0;
        }

        // ── Minimal SRT parser ──────────────────────────────────────────────
        record SrtSegment(string Text, double Start, double End);

        static List<SrtSegment> ParseSrt(string srtPath)
        {
            var segments = new List<SrtSegment>();
            var lines = File.ReadAllLines(srtPath, Encoding.UTF8);

            int i = 0;
            while (i < lines.Length)
            {
                // Skip index line (digits only)
                while (i < lines.Length && !Regex.IsMatch(lines[i].Trim(), @"^\d+$")) i++;
                if (i >= lines.Length) break;
                i++; // skip index

                // Timestamp line
                if (i >= lines.Length) break;
                var tsLine = lines[i++].Trim();
                var tsParts = tsLine.Split(new[] { "-->" }, StringSplitOptions.RemoveEmptyEntries);
                if (tsParts.Length < 2) continue;
                double start = ParseSrtTime(tsParts[0].Trim());
                double end   = ParseSrtTime(tsParts[1].Trim());

                // Text lines until blank line
                var textLines = new List<string>();
                while (i < lines.Length && lines[i].Trim() != "")
                {
                    textLines.Add(lines[i].Trim());
                    i++;
                }
                i++; // skip blank separator

                if (textLines.Count > 0)
                    segments.Add(new SrtSegment(string.Join("\n", textLines), start, end));
            }
            return segments;
        }

        static double ParseSrtTime(string t)
        {
            // Format: HH:MM:SS,mmm  or  HH:MM:SS.mmm
            t = t.Replace(',', '.');
            var parts = t.Split(':');
            if (parts.Length != 3) return 0;
            double.TryParse(parts[0], out double h);
            double.TryParse(parts[1], out double m);
            double.TryParse(parts[2], System.Globalization.NumberStyles.Float,
                System.Globalization.CultureInfo.InvariantCulture, out double s);
            return h * 3600 + m * 60 + s;
        }
    }
}
