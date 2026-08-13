namespace WukongStudio.Core;

public enum StudioLogFilter
{
    All,
    Important,
    WarningsAndErrors,
    Errors,
}

public enum StudioLogLineKind
{
    Normal,
    Stage,
    Command,
    Warning,
    Error,
    Success,
    Technical,
}

public sealed record StudioLogLine(string Text, StudioLogLineKind Kind);

public static class StudioLogPresentation
{
    private const string EventPrefix = "@@STUDIO_EVENT@@";

    public static IReadOnlyList<StudioLogLine> Build(
        string raw,
        string? query = null,
        StudioLogFilter filter = StudioLogFilter.All,
        bool includeTechnical = false)
    {
        var result = new List<StudioLogLine>();
        string? previous = null;
        var normalizedQuery = query?.Trim();

        foreach (var rawLine in raw.Replace("\r\n", "\n", StringComparison.Ordinal).Split('\n'))
        {
            var line = PresentLine(rawLine.TrimEnd('\r'), includeTechnical);
            if (line is null || !MatchesFilter(line, filter))
            {
                continue;
            }
            if (!string.IsNullOrWhiteSpace(normalizedQuery)
                && !line.Text.Contains(normalizedQuery, StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }
            if (string.Equals(previous, line.Text, StringComparison.Ordinal))
            {
                continue;
            }
            if (line.Text.Length == 0 && previous is null or "")
            {
                continue;
            }

            result.Add(line);
            previous = line.Text;
        }

        while (result.Count > 0 && result[^1].Text.Length == 0)
        {
            result.RemoveAt(result.Count - 1);
        }
        return result;
    }

    public static StudioLogLine? PresentLine(string rawLine, bool includeTechnical = false)
    {
        if (rawLine.StartsWith(EventPrefix, StringComparison.Ordinal))
        {
            return includeTechnical
                ? new StudioLogLine(rawLine, StudioLogLineKind.Technical)
                : null;
        }
        if (rawLine.Contains("ZIP progress:", StringComparison.OrdinalIgnoreCase))
        {
            return includeTechnical
                ? new StudioLogLine(rawLine, StudioLogLineKind.Technical)
                : null;
        }
        if (rawLine.Length == 0)
        {
            return new StudioLogLine(string.Empty, StudioLogLineKind.Normal);
        }

        var lower = rawLine.ToLowerInvariant();
        if (rawLine.StartsWith("===", StringComparison.Ordinal)
            || rawLine.StartsWith("---", StringComparison.Ordinal))
        {
            return new StudioLogLine(rawLine, StudioLogLineKind.Stage);
        }
        if (lower.Contains("exception", StringComparison.Ordinal)
            || lower.Contains("traceback", StringComparison.Ordinal)
            || lower.Contains("fatal", StringComparison.Ordinal)
            || lower.Contains("failed", StringComparison.Ordinal)
            || lower.Contains("error", StringComparison.Ordinal)
            || lower.Contains("thất bại", StringComparison.Ordinal)
            || lower.Contains("lỗi", StringComparison.Ordinal))
        {
            return new StudioLogLine(rawLine, StudioLogLineKind.Error);
        }
        if (lower.Contains("warning", StringComparison.Ordinal)
            || lower.Contains("warn:", StringComparison.Ordinal)
            || lower.Contains("missing", StringComparison.Ordinal)
            || lower.Contains("skipped", StringComparison.Ordinal)
            || lower.Contains("skip ", StringComparison.Ordinal)
            || lower.Contains("cảnh báo", StringComparison.Ordinal)
            || lower.Contains("bỏ qua", StringComparison.Ordinal))
        {
            return new StudioLogLine(rawLine, StudioLogLineKind.Warning);
        }
        if (lower.Contains("cmd:", StringComparison.Ordinal)
            || lower.StartsWith("command:", StringComparison.Ordinal))
        {
            return new StudioLogLine(rawLine, StudioLogLineKind.Command);
        }
        if (lower.Contains("everything is ok", StringComparison.Ordinal)
            || lower.Contains("success", StringComparison.Ordinal)
            || lower.Contains("completed", StringComparison.Ordinal)
            || lower.Contains("cleaned workspace", StringComparison.Ordinal)
            || lower.Contains("hoàn tất", StringComparison.Ordinal)
            || lower.Contains("thành công", StringComparison.Ordinal)
            || lower.StartsWith("done ", StringComparison.Ordinal)
            || lower.EndsWith(" done", StringComparison.Ordinal))
        {
            return new StudioLogLine(rawLine, StudioLogLineKind.Success);
        }
        return new StudioLogLine(rawLine, StudioLogLineKind.Normal);
    }

    public static bool MatchesFilter(StudioLogLine line, StudioLogFilter filter) => filter switch
    {
        StudioLogFilter.Important => line.Kind is not StudioLogLineKind.Normal,
        StudioLogFilter.WarningsAndErrors => line.Kind is StudioLogLineKind.Warning or StudioLogLineKind.Error,
        StudioLogFilter.Errors => line.Kind == StudioLogLineKind.Error,
        _ => true,
    };
}
