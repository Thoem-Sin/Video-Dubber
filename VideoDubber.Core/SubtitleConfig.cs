using System;

namespace VideoDubber.Core
{
    public class SubtitleConfig
    {
        public bool Enabled { get; set; } = true;
        public string Preset { get; set; } = "Outline"; // Outline, YellowBox, WhiteText, Glow, TikTokYellow, CyberCyan, RedHighlight, GreenBox
        public string Font { get; set; } = "Kantumruy Pro";
        public string FontPath { get; set; } = string.Empty;
        public double Size { get; set; } = 4.5; // percentage of video height
        public double Opacity { get; set; } = 100.0; // 0..100
        public double Outline { get; set; } = 0.3; // percentage of video height
        public double PosY { get; set; } = 62.0; // percentage from top
        public int MaxChars { get; set; } = 36;  // subtitle wrap width (chars per line)
        public string TextColor { get; set; } = "#FFFFFF";
        public string OutlineColor { get; set; } = "#000000";
        public bool Bold { get; set; } = true;
        public bool Italic { get; set; } = false;
    }
}
