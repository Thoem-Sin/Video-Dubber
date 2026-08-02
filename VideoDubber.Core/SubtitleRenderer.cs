using System;
using System.IO;
using SkiaSharp;
using SkiaSharp.HarfBuzz;

namespace VideoDubber.Core
{
    public static class SubtitleRenderer
    {
        private static bool IsKhmerText(string text)
        {
            if (string.IsNullOrEmpty(text)) return false;
            foreach (char c in text)
            {
                if (c >= 0x1780 && c <= 0x17FF)
                    return true;
            }
            return false;
        }

        private static bool IsKnownKhmerFont(string fontName)
        {
            if (string.IsNullOrEmpty(fontName)) return false;
            string name = fontName.ToLowerInvariant();
            return name.Contains("kantumruy") || name.Contains("khmer") || name.Contains("leelawadee") || name.Contains("daunpenh") || name.Contains("moul") || name.Contains("siemreap") || name.Contains("battambang");
        }

        private static SKTypeface GetBestTypeface(string fontName, string fontPath, string text, bool bold = true, bool italic = false)
        {
            string kantumruyFile = FontManager.GetKantumruyPath();
            bool isKhmer = IsKhmerText(text);

            SKFontStyleWeight weight = bold ? SKFontStyleWeight.Bold : SKFontStyleWeight.Normal;
            SKFontStyleSlant slant = italic ? SKFontStyleSlant.Italic : SKFontStyleSlant.Upright;
            SKFontStyle style = new SKFontStyle(weight, SKFontStyleWidth.Normal, slant);

            if (isKhmer && !IsKnownKhmerFont(fontName))
            {
                if (!string.IsNullOrEmpty(kantumruyFile) && File.Exists(kantumruyFile))
                {
                    try
                    {
                        var tfK = SKTypeface.FromFile(kantumruyFile);
                        if (tfK != null) return SKTypeface.FromFamilyName(tfK.FamilyName, style) ?? tfK;
                    }
                    catch { }
                }
            }

            if (!string.IsNullOrEmpty(fontPath) && File.Exists(fontPath))
            {
                try
                {
                    var tf = SKTypeface.FromFile(fontPath);
                    if (tf != null) return SKTypeface.FromFamilyName(tf.FamilyName, style) ?? tf;
                }
                catch { }
            }

            string resolvedPath = FontManager.ResolveFontPath(fontName, null);
            if (File.Exists(resolvedPath))
            {
                try
                {
                    var tf = SKTypeface.FromFile(resolvedPath);
                    if (tf != null) return SKTypeface.FromFamilyName(tf.FamilyName, style) ?? tf;
                }
                catch { }
            }

            if (!string.IsNullOrEmpty(kantumruyFile) && File.Exists(kantumruyFile))
            {
                try
                {
                    var tfKantumruy = SKTypeface.FromFile(kantumruyFile);
                    if (tfKantumruy != null) return SKTypeface.FromFamilyName(tfKantumruy.FamilyName, style) ?? tfKantumruy;
                }
                catch { }
            }

            return SKTypeface.FromFamilyName(fontName, style) ?? SKTypeface.Default;
        }

        private static float MeasureLine(SKShaper shaper, string line, SKPaint paint)
        {
            try
            {
                var result = shaper.Shape(line, paint);
                if (result != null && result.Width > 0)
                    return result.Width;
            }
            catch { }
            return paint.MeasureText(line);
        }

        private static void DrawTextLine(SKCanvas canvas, SKShaper shaper, string line, float x, float y, SKPaint paint)
        {
            try
            {
                canvas.DrawShapedText(shaper, line, x, y, paint);
            }
            catch
            {
                canvas.DrawText(line, x, y, paint);
            }
        }

        private static SKColor ParseColor(string hex, byte alpha, SKColor defaultColor)
        {
            if (!string.IsNullOrWhiteSpace(hex) && SKColor.TryParse(hex, out var c))
            {
                return new SKColor(c.Red, c.Green, c.Blue, alpha);
            }
            return new SKColor(defaultColor.Red, defaultColor.Green, defaultColor.Blue, alpha);
        }

        private static SKPaint CreateTextPaint(SKTypeface typeface, float fontSize, SKColor color, SubtitleConfig cfg, SKPaintStyle style = SKPaintStyle.Fill, float strokeWidth = 0)
        {
            var p = new SKPaint
            {
                Typeface = typeface,
                TextSize = fontSize,
                Color = color,
                Style = style,
                IsAntialias = true,
                SubpixelText = true,
                FakeBoldText = cfg.Bold,
                TextSkewX = cfg.Italic ? -0.25f : 0f
            };
            if (strokeWidth > 0)
            {
                p.StrokeWidth = strokeWidth;
            }
            return p;
        }

        /// <summary>
        /// Renders subtitle caption onto a SkiaSharp SKCanvas with 100% bit-for-bit parity, Kantumruy Pro font weight, & HarfBuzz complex script text shaping.
        /// </summary>
        public static void RenderSubtitle(SKCanvas canvas, string text, SubtitleConfig cfg, int width, int height)
        {
            if (string.IsNullOrWhiteSpace(text) || cfg == null || !cfg.Enabled)
                return;

            using var typeface = GetBestTypeface(cfg.Font, cfg.FontPath, text, cfg.Bold, cfg.Italic);
            using var shaper = new SKShaper(typeface);

            float fontSize = Math.Max(16f, (float)(height * (cfg.Size / 100.0)));
            float targetFontSize = fontSize;
            byte alpha = (byte)Math.Clamp((int)(255 * (cfg.Opacity / 100.0)), 0, 255);

            float maxAllowedWidth = width * 0.94f;
            float minSingleLineSize = 12f;

            using var basePaint = CreateTextPaint(typeface, fontSize, SKColors.White, cfg);

            if (cfg.MaxChars <= 0)
            {
                // ── UNCONSTRAINED 1-SINGLE-LINE MODE (No max_chars wrapping) ─────────────
                string singleText = text?.Replace("\n", " ")?.Trim() ?? string.Empty;
                lines = new[] { singleText };

                float shrinkSize = fontSize;
                float singleLineW = MeasureLine(shaper, singleText, basePaint);

                while (singleLineW > maxAllowedWidth && shrinkSize > 8f)
                {
                    shrinkSize = Math.Max(8f, shrinkSize * 0.94f);
                    basePaint.TextSize = shrinkSize;
                    singleLineW = MeasureLine(shaper, singleText, basePaint);
                }

                fontSize = shrinkSize;
            }
            else
            {
                // ── EXPLICIT MULTI-LINE WRAP MODE (User set MaxChars > 0) ─────────────
                string wrappedText = KhmerSyllableTokenizer.WrapText(text, cfg.MaxChars);
                lines = wrappedText.Split('\n');

                float maxLineWidth = 0;
                foreach (var line in lines)
                {
                    float w = MeasureLine(shaper, line, basePaint);
                    if (w > maxLineWidth) maxLineWidth = w;
                }

                while (maxLineWidth > maxAllowedWidth && fontSize > 12f)
                {
                    fontSize = Math.Max(12f, fontSize * 0.92f);
                    basePaint.TextSize = fontSize;
                    wrappedText = KhmerSyllableTokenizer.WrapText(text, cfg.MaxChars);
                    lines = wrappedText.Split('\n');

                    maxLineWidth = 0;
                    foreach (var line in lines)
                    {
                        float w = MeasureLine(shaper, line, basePaint);
                        if (w > maxLineWidth) maxLineWidth = w;
                    }
                }
            }

            float fontSpacing = basePaint.FontSpacing;
            float totalTextHeight = lines.Length * fontSpacing;

            float posYPct = (float)cfg.PosY;
            float targetCenterY = (float)(height * (posYPct / 100.0));
            float startY = targetCenterY - (totalTextHeight / 2.0f) + basePaint.TextSize;


            string preset = cfg.Preset ?? "Outline";
            SKColor fillCol = ParseColor(cfg.TextColor, alpha, SKColors.White);
            SKColor strokeCol = ParseColor(cfg.OutlineColor, alpha, SKColors.Black);

            if (preset.Equals("YellowBox", StringComparison.OrdinalIgnoreCase) ||
                preset.Equals("GreenBox", StringComparison.OrdinalIgnoreCase) ||
                preset.Equals("RedHighlight", StringComparison.OrdinalIgnoreCase))
            {
                SKColor boxColor = new SKColor(0, 0, 0, (byte)(255 * 0.72 * (cfg.Opacity / 100.0)));
                SKColor defaultTextCol = new SKColor(255, 255, 0, alpha);

                if (preset.Equals("GreenBox", StringComparison.OrdinalIgnoreCase))
                {
                    boxColor = new SKColor(0, 77, 32, (byte)(255 * 0.85 * (cfg.Opacity / 100.0)));
                    defaultTextCol = new SKColor(255, 255, 255, alpha);
                }
                else if (preset.Equals("RedHighlight", StringComparison.OrdinalIgnoreCase))
                {
                    boxColor = new SKColor(128, 0, 0, (byte)(255 * 0.85 * (cfg.Opacity / 100.0)));
                    defaultTextCol = new SKColor(255, 255, 255, alpha);
                }

                SKColor textCol = !string.IsNullOrWhiteSpace(cfg.TextColor) && !cfg.TextColor.Equals("#FFFFFF", StringComparison.OrdinalIgnoreCase)
                    ? fillCol : defaultTextCol;

                float padX = Math.Max(12f, fontSize * 0.35f);
                float padY = Math.Max(6f, fontSize * 0.18f);
                float cornerR = Math.Max(4f, fontSize * 0.15f);

                float boxX0 = (width - maxLineWidth) / 2.0f - padX;
                float boxY0 = targetCenterY - (totalTextHeight / 2.0f) - padY;
                float boxX1 = (width + maxLineWidth) / 2.0f + padX;
                float boxY1 = targetCenterY + (totalTextHeight / 2.0f) + padY;

                using var boxPaint = new SKPaint
                {
                    Color = boxColor,
                    Style = SKPaintStyle.Fill,
                    IsAntialias = true
                };

                canvas.DrawRoundRect(new SKRect(boxX0, boxY0, boxX1, boxY1), cornerR, cornerR, boxPaint);

                using var textPaint = CreateTextPaint(typeface, fontSize, textCol, cfg);

                float currentY = startY;
                foreach (var line in lines)
                {
                    float lw = MeasureLine(shaper, line, textPaint);
                    float lx = (width - lw) / 2.0f;
                    DrawTextLine(canvas, shaper, line, lx, currentY, textPaint);
                    currentY += fontSpacing;
                }
            }
            else if (preset.Equals("WhiteText", StringComparison.OrdinalIgnoreCase))
            {
                using var textPaint = CreateTextPaint(typeface, fontSize, fillCol, cfg);

                float currentY = startY;
                foreach (var line in lines)
                {
                    float lw = MeasureLine(shaper, line, textPaint);
                    float lx = (width - lw) / 2.0f;
                    DrawTextLine(canvas, shaper, line, lx, currentY, textPaint);
                    currentY += fontSpacing;
                }
            }
            else if (preset.Equals("TikTokYellow", StringComparison.OrdinalIgnoreCase))
            {
                SKColor yellowCol = !string.IsNullOrWhiteSpace(cfg.TextColor) && !cfg.TextColor.Equals("#FFFFFF", StringComparison.OrdinalIgnoreCase)
                    ? fillCol : new SKColor(255, 230, 0, alpha);

                float strokeW = Math.Max(4f, Math.Max(fontSize * 0.16f, (float)(height * (cfg.Outline / 100.0) * 1.3)));

                using var strokePaint = CreateTextPaint(typeface, fontSize, strokeCol, cfg, SKPaintStyle.Stroke, strokeW);
                using var fillPaint = CreateTextPaint(typeface, fontSize, yellowCol, cfg, SKPaintStyle.Fill);

                float currentY = startY;
                foreach (var line in lines)
                {
                    float lw = MeasureLine(shaper, line, fillPaint);
                    float lx = (width - lw) / 2.0f;
                    DrawTextLine(canvas, shaper, line, lx, currentY, strokePaint);
                    DrawTextLine(canvas, shaper, line, lx, currentY, fillPaint);
                    currentY += fontSpacing;
                }
            }
            else if (preset.Equals("CyberCyan", StringComparison.OrdinalIgnoreCase))
            {
                SKColor cyanCol = !string.IsNullOrWhiteSpace(cfg.TextColor) && !cfg.TextColor.Equals("#FFFFFF", StringComparison.OrdinalIgnoreCase)
                    ? fillCol : new SKColor(0, 255, 255, alpha);
                SKColor glowCol = ParseColor(cfg.OutlineColor, (byte)(alpha * 0.85), new SKColor(0, 51, 102));

                float strokeW = Math.Max(4f, Math.Max(fontSize * 0.14f, (float)(height * (cfg.Outline / 100.0))));

                using var glowPaint = CreateTextPaint(typeface, fontSize, glowCol, cfg, SKPaintStyle.Stroke, strokeW);
                glowPaint.MaskFilter = SKMaskFilter.CreateBlur(SKBlurStyle.Normal, strokeW * 0.6f);

                using var textPaint = CreateTextPaint(typeface, fontSize, cyanCol, cfg);

                float currentY = startY;
                foreach (var line in lines)
                {
                    float lw = MeasureLine(shaper, line, textPaint);
                    float lx = (width - lw) / 2.0f;
                    DrawTextLine(canvas, shaper, line, lx, currentY, glowPaint);
                    DrawTextLine(canvas, shaper, line, lx, currentY, textPaint);
                    currentY += fontSpacing;
                }
            }
            else if (preset.Equals("Glow", StringComparison.OrdinalIgnoreCase))
            {
                float strokeW = Math.Max(3f, Math.Max(fontSize * 0.12f, (float)(height * (cfg.Outline / 100.0))));
                SKColor glowCol = ParseColor(cfg.OutlineColor, (byte)(alpha * 0.65), SKColors.Black);

                using var glowPaint = CreateTextPaint(typeface, fontSize, glowCol, cfg, SKPaintStyle.Stroke, strokeW);
                glowPaint.MaskFilter = SKMaskFilter.CreateBlur(SKBlurStyle.Normal, strokeW * 0.5f);

                using var textPaint = CreateTextPaint(typeface, fontSize, fillCol, cfg);

                float currentY = startY;
                foreach (var line in lines)
                {
                    float lw = MeasureLine(shaper, line, textPaint);
                    float lx = (width - lw) / 2.0f;
                    DrawTextLine(canvas, shaper, line, lx, currentY, glowPaint);
                    DrawTextLine(canvas, shaper, line, lx, currentY, textPaint);
                    currentY += fontSpacing;
                }
            }
            else // Outline (default)
            {
                float strokeW = Math.Max(3f, Math.Max(fontSize * 0.12f, (float)(height * (cfg.Outline / 100.0))));

                using var strokePaint = CreateTextPaint(typeface, fontSize, strokeCol, cfg, SKPaintStyle.Stroke, strokeW);
                using var fillPaint = CreateTextPaint(typeface, fontSize, fillCol, cfg, SKPaintStyle.Fill);

                float currentY = startY;
                foreach (var line in lines)
                {
                    float lw = MeasureLine(shaper, line, fillPaint);
                    float lx = (width - lw) / 2.0f;
                    DrawTextLine(canvas, shaper, line, lx, currentY, strokePaint);
                    DrawTextLine(canvas, shaper, line, lx, currentY, fillPaint);
                    currentY += fontSpacing;
                }
            }
        }

        /// <summary>
        /// Render subtitle phrase to a transparent RGBA PNG file on disk for FFmpeg overlay export.
        /// </summary>
        public static void RenderSubtitlePngOverlay(string text, SubtitleConfig cfg, string outputPngPath, int width = 1080, int height = 1920)
        {
            using var bitmap = new SKBitmap(width, height, SKColorType.Rgba8888, SKAlphaType.Premul);
            using var canvas = new SKCanvas(bitmap);
            canvas.Clear(SKColors.Empty);

            RenderSubtitle(canvas, text, cfg, width, height);

            string? dir = System.IO.Path.GetDirectoryName(outputPngPath);
            if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir))
                Directory.CreateDirectory(dir);

            using var image = SKImage.FromBitmap(bitmap);
            using var data = image.Encode(SKEncodedImageFormat.Png, 100);
            using var stream = File.OpenWrite(outputPngPath);
            data.SaveTo(stream);
        }
    }
}
