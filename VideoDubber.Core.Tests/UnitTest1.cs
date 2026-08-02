using System;
using System.IO;
using VideoDubber.Core;
using Xunit;

namespace VideoDubber.Core.Tests
{
    public class SubtitleEngineTests
    {
        [Fact]
        public void KhmerSyllableTokenizer_KeepsWordsIntact()
        {
            string text = "ឥឡូវនេះតើអ្នកអាចឱ្យខ្ញុំសម្ភារៈកូនរបស់ខ្ញុំ?";
            string wrapped = KhmerSyllableTokenizer.WrapText(text, 20);

            Assert.NotNull(wrapped);
            Assert.Contains("សម្ភារៈ", wrapped);
            Assert.Contains("របស់", wrapped);
            Assert.DoesNotContain("សម្ភារ\nៈ", wrapped);
        }

        [Fact]
        public void SubtitleRenderer_GeneratesPngOverlay()
        {
            var cfg = new SubtitleConfig
            {
                Font = "Kantumruy Pro",
                Preset = "Outline",
                Size = 4.5,
                Opacity = 100,
                Outline = 0.3,
                PosY = 62
            };

            string outPng = Path.Combine(Path.GetTempPath(), "test_skia_overlay.png");
            if (File.Exists(outPng)) File.Delete(outPng);

            SubtitleRenderer.RenderSubtitlePngOverlay("ឥឡូវនេះតើអ្នក\nអាចឱ្យខ្ញុំ\nសម្ភារៈកូនរបស់ខ្ញុំ?", cfg, outPng, 1080, 1920);

            Assert.True(File.Exists(outPng));
            Assert.True(new FileInfo(outPng).Length > 0);

            if (File.Exists(outPng)) File.Delete(outPng);
        }
    }
}