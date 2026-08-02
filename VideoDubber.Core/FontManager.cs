using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using SkiaSharp;

namespace VideoDubber.Core
{
    public class FontItem
    {
        public string Name { get; set; } = string.Empty;
        public string Path { get; set; } = string.Empty;
    }

    public static class FontManager
    {
        private static List<FontItem>? _cachedFonts;
        private static readonly object _lock = new object();

        public static string GetKantumruyPath()
        {
            string baseDir = AppDomain.CurrentDomain.BaseDirectory;
            string[] candidates = new[]
            {
                Path.Combine(baseDir, "static", "fonts", "KantumruyPro.ttf"),
                Path.Combine(baseDir, "..", "static", "fonts", "KantumruyPro.ttf"),
                Path.Combine(baseDir, "..", "..", "static", "fonts", "KantumruyPro.ttf"),
                Path.Combine(baseDir, "..", "..", "..", "static", "fonts", "KantumruyPro.ttf"),
                Path.Combine(Directory.GetCurrentDirectory(), "static", "fonts", "KantumruyPro.ttf"),
                @"C:\MMO\Tool\Video Duber-V1\static\fonts\KantumruyPro.ttf"
            };

            foreach (var file in candidates)
            {
                try
                {
                    string full = Path.GetFullPath(file);
                    if (File.Exists(full))
                        return full;
                }
                catch { }
            }

            return string.Empty;
        }

        public static List<FontItem> ScanFonts(bool forceRefresh = false)
        {
            lock (_lock)
            {
                if (_cachedFonts != null && !forceRefresh)
                    return _cachedFonts;

                var fonts = new List<FontItem>();
                var byFamily = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);

                // Add Kantumruy Pro first explicitly from disk
                string kantumruyFile = GetKantumruyPath();
                if (!string.IsNullOrEmpty(kantumruyFile) && File.Exists(kantumruyFile))
                {
                    try
                    {
                        using var tf = SKTypeface.FromFile(kantumruyFile);
                        string familyName = tf?.FamilyName ?? "Kantumruy Pro";
                        byFamily[familyName] = kantumruyFile;
                        byFamily["Kantumruy Pro"] = kantumruyFile;
                    }
                    catch { }
                }

                // Scan static fonts directories
                string baseDir = AppDomain.CurrentDomain.BaseDirectory;
                string[] candidates = new[]
                {
                    Path.Combine(baseDir, "static", "fonts"),
                    Path.Combine(baseDir, "..", "static", "fonts"),
                    Path.Combine(baseDir, "..", "..", "static", "fonts"),
                    Path.Combine(baseDir, "..", "..", "..", "static", "fonts"),
                    Path.Combine(Directory.GetCurrentDirectory(), "static", "fonts"),
                    @"C:\MMO\Tool\Video Duber-V1\static\fonts"
                };

                foreach (var dir in candidates)
                {
                    try
                    {
                        string norm = Path.GetFullPath(dir);
                        if (Directory.Exists(norm))
                        {
                            foreach (var file in Directory.GetFiles(norm, "*.*"))
                            {
                                if (file.EndsWith(".ttf", StringComparison.OrdinalIgnoreCase) || file.EndsWith(".otf", StringComparison.OrdinalIgnoreCase))
                                {
                                    try
                                    {
                                        using var tf = SKTypeface.FromFile(file);
                                        if (tf != null && !string.IsNullOrEmpty(tf.FamilyName))
                                        {
                                            if (!byFamily.ContainsKey(tf.FamilyName))
                                                byFamily[tf.FamilyName] = file;
                                        }
                                    }
                                    catch { }
                                }
                            }
                        }
                    }
                    catch { }
                }

                // Scan Windows System Fonts
                string winFonts = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows), "Fonts");
                if (Directory.Exists(winFonts))
                {
                    foreach (var file in Directory.GetFiles(winFonts, "*.*"))
                    {
                        if (file.EndsWith(".ttf", StringComparison.OrdinalIgnoreCase) || file.EndsWith(".otf", StringComparison.OrdinalIgnoreCase))
                        {
                            try
                            {
                                using var tf = SKTypeface.FromFile(file);
                                if (tf != null && !string.IsNullOrEmpty(tf.FamilyName))
                                {
                                    if (!byFamily.ContainsKey(tf.FamilyName))
                                        byFamily[tf.FamilyName] = file;
                                }
                            }
                            catch { }
                        }
                    }
                }

                foreach (var kvp in byFamily)
                {
                    fonts.Add(new FontItem { Name = kvp.Key, Path = kvp.Value });
                }

                fonts.Sort((a, b) =>
                {
                    if (a.Name.Equals("Kantumruy Pro", StringComparison.OrdinalIgnoreCase)) return -1;
                    if (b.Name.Equals("Kantumruy Pro", StringComparison.OrdinalIgnoreCase)) return 1;
                    return string.Compare(a.Name, b.Name, StringComparison.OrdinalIgnoreCase);
                });

                _cachedFonts = fonts;
                return _cachedFonts;
            }
        }

        public static string ResolveFontPath(string? name, string? path)
        {
            if (!string.IsNullOrEmpty(path) && File.Exists(path))
                return path;

            string kantumruyFile = GetKantumruyPath();

            if (string.IsNullOrEmpty(name) || name.Equals("Kantumruy Pro", StringComparison.OrdinalIgnoreCase) || name.Contains("Kantumruy"))
            {
                if (!string.IsNullOrEmpty(kantumruyFile) && File.Exists(kantumruyFile))
                    return kantumruyFile;
            }

            var fonts = ScanFonts();
            if (!string.IsNullOrEmpty(name))
            {
                var match = fonts.FirstOrDefault(f => f.Name.Equals(name, StringComparison.OrdinalIgnoreCase));
                if (match != null) return match.Path;

                var partial = fonts.FirstOrDefault(f => f.Name.IndexOf(name, StringComparison.OrdinalIgnoreCase) >= 0);
                if (partial != null) return partial.Path;
            }

            if (!string.IsNullOrEmpty(kantumruyFile) && File.Exists(kantumruyFile))
                return kantumruyFile;

            return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows), "Fonts", "arial.ttf");
        }
    }
}
