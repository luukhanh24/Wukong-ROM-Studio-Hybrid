using WukongStudio.Core;

namespace WukongStudio.Tests;

public sealed class BoundedLogBufferTests
{
    [Fact]
    public void AppendOnlyUpdatesDoNotRequireFullRender()
    {
        var buffer = new BoundedLogBuffer(1024);

        var first = buffer.Append("first\n");
        var second = buffer.Append("second\n");

        Assert.False(first.RequiresFullRender);
        Assert.False(second.RequiresFullRender);
        Assert.Equal("second\n", second.AppendText);
        Assert.Equal("first\nsecond\n", buffer.Snapshot());
    }

    [Fact]
    public void LargeInputKeepsLatestLinesWithinLimit()
    {
        var buffer = new BoundedLogBuffer(100_000);
        var input = string.Concat(Enumerable.Range(0, 80_000).Select(index => $"line-{index:D5}\n"));

        var change = buffer.Append(input);

        Assert.True(change.RequiresFullRender);
        Assert.True(buffer.Length <= 100_000);
        Assert.DoesNotContain("line-00000", buffer.Snapshot());
        Assert.EndsWith("line-79999\n", buffer.Snapshot());
    }

    [Fact]
    public void TrimCreatesHeadroomForFollowingChunks()
    {
        var buffer = new BoundedLogBuffer(100);
        var first = buffer.Append(string.Concat(Enumerable.Range(0, 15).Select(index => $"line-{index:D2}\n")));

        var second = buffer.Append("next\n");

        Assert.True(first.RequiresFullRender);
        Assert.True(buffer.Length <= 100);
        Assert.False(second.RequiresFullRender);
        Assert.Equal("next\n", second.AppendText);
    }

    [Fact]
    public void FilterMatchesLinesWithoutChangingBuffer()
    {
        var buffer = new BoundedLogBuffer(1024);
        buffer.Append("done system\nwarning vendor\ndone product\n");

        var filtered = buffer.Filter("done");

        Assert.Equal($"done system{Environment.NewLine}done product{Environment.NewLine}", filtered);
        Assert.Equal("done system\nwarning vendor\ndone product\n", buffer.Snapshot());
    }
}
