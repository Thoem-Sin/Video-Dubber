using System;
using System.Collections.Generic;
using System.Text;
using System.Text.RegularExpressions;

namespace VideoDubber.Core
{
    public static class KhmerSyllableTokenizer
    {
        private static readonly Regex SyllableRegex = new Regex(
            @"[\u1780-\u17b3](?:[\u17d2][\u1780-\u17b3])?[\u17b6-\u17c5]*[\u17c6-\u17d3]*|[^\u1780-\u17d3\s]+|\s+",
            RegexOptions.Compiled
        );

        public static string FixKhmerSpelling(string text)
        {
            if (string.IsNullOrEmpty(text)) return string.Empty;
            if (Regex.IsMatch(text, @"[\u1780-\u17ff]"))
            {
                text = Regex.Replace(text, @"\s*[\u17d2]\s*", "\u17d2");
                text = Regex.Replace(text, @"\s+([\u17b4-\u17d3])", "$1");
                text = text.Replace("\u25cc", "");
                text = text.Replace("\u17d4", "");
            }
            return text.Trim();
        }

        /// <summary>
        /// Wrap text up to maxChars per line without breaking Khmer syllable clusters (e.g., 'រៀបការ').
        /// If text already contains newlines, preserves existing newlines intact.
        /// </summary>
        public static string WrapText(string text, int maxChars = 0)
        {
            if (string.IsNullOrWhiteSpace(text))
                return string.Empty;

            text = FixKhmerSpelling(text);

            if (maxChars <= 0)
                return text;

            if (text.Contains("\n"))
                return text;


            var rawLines = text.Split('\n');
            var resultLines = new List<string>();

            foreach (var rawLine in rawLines)
            {
                var lineTrimmed = rawLine.Trim();
                if (string.IsNullOrEmpty(lineTrimmed))
                    continue;

                if (lineTrimmed.Length <= maxChars)
                {
                    resultLines.Add(lineTrimmed);
                    continue;
                }

                var matches = SyllableRegex.Matches(lineTrimmed);
                var currLine = new StringBuilder();

                foreach (Match match in matches)
                {
                    string s = match.Value;
                    bool startsWithSubscriptOrVowel = s.Length > 0 && (s[0] == '\u17d2' || (s[0] >= '\u17b6' && s[0] <= '\u17c5'));

                    if (currLine.Length + s.Length > maxChars && currLine.ToString().Trim().Length > 0 && !startsWithSubscriptOrVowel)
                    {
                        resultLines.Add(currLine.ToString().Trim());
                        currLine.Clear();
                        currLine.Append(s);
                    }
                    else
                    {
                        currLine.Append(s);
                    }
                }

                if (currLine.ToString().Trim().Length > 0)
                {
                    resultLines.Add(currLine.ToString().Trim());
                }
            }

            return string.Join("\n", resultLines);
        }

        /// <summary>
        /// Wrap text based strictly on measured pixel width rather than character count.
        /// Preserves atomic Khmer syllable clusters so words are never split mid-syllable.
        /// </summary>
        public static string WrapTextByPixelWidth(string text, Func<string, float> measureFn, float maxAllowedWidth)
        {
            if (string.IsNullOrWhiteSpace(text))
                return string.Empty;

            text = FixKhmerSpelling(text);

            if (measureFn(text) <= maxAllowedWidth)
                return text;

            var rawLines = text.Split('\n');
            var resultLines = new List<string>();

            foreach (var rawLine in rawLines)
            {
                var lineTrimmed = rawLine.Trim();
                if (string.IsNullOrEmpty(lineTrimmed))
                    continue;

                if (measureFn(lineTrimmed) <= maxAllowedWidth)
                {
                    resultLines.Add(lineTrimmed);
                    continue;
                }

                var matches = SyllableRegex.Matches(lineTrimmed);
                var currLine = new StringBuilder();

                foreach (Match match in matches)
                {
                    string s = match.Value;
                    bool startsWithSubscriptOrVowel = s.Length > 0 && (s[0] == '\u17d2' || (s[0] >= '\u17b6' && s[0] <= '\u17c5'));

                    string testLine = currLine.ToString() + s;
                    if (currLine.ToString().Trim().Length > 0 && measureFn(testLine) > maxAllowedWidth && !startsWithSubscriptOrVowel)
                    {
                        resultLines.Add(currLine.ToString().Trim());
                        currLine.Clear();
                        currLine.Append(s.TrimStart());
                    }
                    else
                    {
                        currLine.Append(s);
                    }
                }

                if (currLine.ToString().Trim().Length > 0)
                {
                    resultLines.Add(currLine.ToString().Trim());
                }
            }

            return string.Join("\n", resultLines);
        }
    }
}
