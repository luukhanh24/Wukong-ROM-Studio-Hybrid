using System.Text.Json;

namespace WukongStudio.Core;

public sealed record ContentSyncProgressSnapshot(
    string Phase,
    string PackId,
    int PackIndex,
    int PackCount,
    long Bytes,
    long TotalBytes,
    double SpeedBytesPerSecond,
    double? EtaSeconds,
    double Percent);

public sealed record ContentSyncPreviewSnapshot(
    string PackId,
    string Target,
    IReadOnlyList<string> Added,
    IReadOnlyList<string> Modified,
    IReadOnlyList<string> Removed,
    IReadOnlyList<string> Conflicts,
    int UnchangedCount,
    int TotalFiles,
    long TotalBytes);

public static class ContentSyncProgressProtocol
{
    public static bool TryParsePreview(string line, out ContentSyncPreviewSnapshot? preview)
    {
        preview = null;
        try
        {
            using var document = JsonDocument.Parse(line);
            var root = document.RootElement;
            if (!StringValue(root, "stage").Equals("preview", StringComparison.Ordinal))
            {
                return false;
            }
            var packId = StringValue(root, "packId");
            var target = StringValue(root, "target");
            if (string.IsNullOrWhiteSpace(packId) || string.IsNullOrWhiteSpace(target))
            {
                return false;
            }
            preview = new ContentSyncPreviewSnapshot(
                packId,
                target,
                StringArray(root, "added"),
                StringArray(root, "modified"),
                StringArray(root, "removed"),
                StringArray(root, "conflicts"),
                IntValue(root, "unchangedCount", 0),
                IntValue(root, "totalFiles", 0),
                LongValue(root, "totalBytes"));
            return true;
        }
        catch (JsonException)
        {
            return false;
        }
    }

    public static bool TryReadChangedPackCount(string line, out int count)
    {
        count = 0;
        try
        {
            using var document = JsonDocument.Parse(line);
            var root = document.RootElement;
            if (!StringValue(root, "stage").Equals("index", StringComparison.Ordinal)
                || !root.TryGetProperty("changed", out var changed)
                || changed.ValueKind != JsonValueKind.Array)
            {
                return false;
            }
            count = changed.GetArrayLength();
            return true;
        }
        catch (JsonException)
        {
            return false;
        }
    }

    public static bool TryParse(string line, out ContentSyncProgressSnapshot? snapshot)
    {
        snapshot = null;
        try
        {
            using var document = JsonDocument.Parse(line);
            var root = document.RootElement;
            if (!StringValue(root, "stage").Equals("content-progress", StringComparison.Ordinal))
            {
                return false;
            }

            var phase = StringValue(root, "phase");
            var packId = StringValue(root, "packId");
            if (string.IsNullOrWhiteSpace(phase) || string.IsNullOrWhiteSpace(packId))
            {
                return false;
            }

            snapshot = new ContentSyncProgressSnapshot(
                phase,
                packId,
                IntValue(root, "packIndex", 1),
                IntValue(root, "packCount", 1),
                LongValue(root, "bytes"),
                LongValue(root, "totalBytes"),
                DoubleValue(root, "speedBytesPerSecond"),
                NullableDoubleValue(root, "etaSeconds"),
                Math.Clamp(DoubleValue(root, "percent"), 0, 100));
            return true;
        }
        catch (JsonException)
        {
            return false;
        }
    }

    private static string StringValue(JsonElement element, string name) =>
        element.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String
            ? value.GetString() ?? string.Empty
            : string.Empty;

    private static IReadOnlyList<string> StringArray(JsonElement element, string name) =>
        element.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.Array
            ? value.EnumerateArray()
                .Where(item => item.ValueKind == JsonValueKind.String)
                .Select(item => item.GetString() ?? string.Empty)
                .Where(item => item.Length > 0)
                .ToArray()
            : Array.Empty<string>();

    private static int IntValue(JsonElement element, string name, int fallback) =>
        element.TryGetProperty(name, out var value)
            && value.ValueKind == JsonValueKind.Number
            && value.TryGetInt32(out var result)
            ? result
            : fallback;

    private static long LongValue(JsonElement element, string name) =>
        element.TryGetProperty(name, out var value)
            && value.ValueKind == JsonValueKind.Number
            && value.TryGetInt64(out var result)
            ? result
            : 0;

    private static double DoubleValue(JsonElement element, string name) =>
        element.TryGetProperty(name, out var value)
            && value.ValueKind == JsonValueKind.Number
            && value.TryGetDouble(out var result)
            ? result
            : 0;

    private static double? NullableDoubleValue(JsonElement element, string name) =>
        element.TryGetProperty(name, out var value)
            && value.ValueKind == JsonValueKind.Number
            && value.TryGetDouble(out var result)
            ? result
            : null;
}
