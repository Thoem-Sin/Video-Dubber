using System;

namespace VideoDubber.Core
{
    public class SubtitleSegment
    {
        public int Id { get; set; }
        public double Start { get; set; }
        public double End { get; set; }
        public double Duration => Math.Round(End - Start, 2);
        public string OriginalText { get; set; } = string.Empty;
        public string TranslatedText { get; set; } = string.Empty;
        public string Text
        {
            get => !string.IsNullOrEmpty(TranslatedText) ? TranslatedText : OriginalText;
            set => TranslatedText = value;
        }
    }
}
