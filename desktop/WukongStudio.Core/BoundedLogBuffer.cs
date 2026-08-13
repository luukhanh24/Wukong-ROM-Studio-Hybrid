using System.Text;

namespace WukongStudio.Core;

public sealed record LogBufferChange(string AppendText, bool RequiresFullRender);

public sealed class BoundedLogBuffer
{
    private const double TrimTargetRatio = 0.75;
    private readonly StringBuilder _buffer = new();

    public BoundedLogBuffer(int maxCharacters)
    {
        if (maxCharacters < 1)
        {
            throw new ArgumentOutOfRangeException(nameof(maxCharacters));
        }
        MaxCharacters = maxCharacters;
    }

    public int Length => _buffer.Length;
    public int MaxCharacters { get; }

    public LogBufferChange Append(string text, bool reset = false)
    {
        if (reset)
        {
            _buffer.Clear();
        }
        if (!string.IsNullOrEmpty(text))
        {
            _buffer.Append(text);
        }

        var trimmed = TrimToLimit();
        return new LogBufferChange(
            reset || trimmed ? string.Empty : text,
            reset || trimmed);
    }

    public void Clear() => _buffer.Clear();

    public string Snapshot() => _buffer.ToString();

    public string Filter(string query)
    {
        if (string.IsNullOrWhiteSpace(query))
        {
            return Snapshot();
        }

        var result = new StringBuilder();
        using var reader = new StringReader(_buffer.ToString());
        while (reader.ReadLine() is { } line)
        {
            if (line.Contains(query, StringComparison.OrdinalIgnoreCase))
            {
                result.AppendLine(line);
            }
        }
        return result.ToString();
    }

    private bool TrimToLimit()
    {
        if (_buffer.Length <= MaxCharacters)
        {
            return false;
        }

        // Create headroom so a full console render is not triggered for every
        // small chunk once the buffer reaches its limit.
        var trimTarget = Math.Max(1, (int)(MaxCharacters * TrimTargetRatio));
        var removeCount = _buffer.Length - trimTarget;
        while (removeCount < _buffer.Length && _buffer[removeCount] != '\n')
        {
            removeCount++;
        }
        if (removeCount < _buffer.Length)
        {
            removeCount++;
        }
        _buffer.Remove(0, removeCount);
        return true;
    }
}
