using WukongStudio.Core;

namespace WukongStudio.Tests;

public sealed class ContentSyncProgressProtocolTests
{
    [Fact]
    public void ParsesUploadProgressEvent()
    {
        const string line = """
            {"stage":"content-progress","phase":"upload","packId":"MOD/ColorOS_16.0.5","packIndex":2,"packCount":4,"bytes":536870912,"totalBytes":1073741824,"speedBytesPerSecond":12582912.5,"etaSeconds":42.5,"percent":50}
            """;

        var parsed = ContentSyncProgressProtocol.TryParse(line, out var progress);

        Assert.True(parsed);
        Assert.NotNull(progress);
        Assert.Equal("upload", progress.Phase);
        Assert.Equal("MOD/ColorOS_16.0.5", progress.PackId);
        Assert.Equal(2, progress.PackIndex);
        Assert.Equal(4, progress.PackCount);
        Assert.Equal(536870912, progress.Bytes);
        Assert.Equal(1073741824, progress.TotalBytes);
        Assert.Equal(12582912.5, progress.SpeedBytesPerSecond);
        Assert.Equal(42.5, progress.EtaSeconds);
        Assert.Equal(50, progress.Percent);
    }

    [Fact]
    public void ParsesProgressEventWithNullOptionalNumbers()
    {
        const string line = """
            {"stage":"content-progress","phase":"archive","packId":"MOD/ColorOS_16.0.5","packIndex":1,"packCount":7,"bytes":null,"totalBytes":null,"speedBytesPerSecond":null,"etaSeconds":null,"percent":null}
            """;

        var parsed = ContentSyncProgressProtocol.TryParse(line, out var progress);

        Assert.True(parsed);
        Assert.NotNull(progress);
        Assert.Equal("archive", progress.Phase);
        Assert.Equal(0, progress.Bytes);
        Assert.Equal(0, progress.TotalBytes);
        Assert.Equal(0, progress.SpeedBytesPerSecond);
        Assert.Null(progress.EtaSeconds);
        Assert.Equal(0, progress.Percent);
    }

    [Theory]
    [InlineData("not json")]
    [InlineData("{\"stage\":\"index\"}")]
    [InlineData("{\"stage\":\"content-progress\",\"phase\":\"upload\"}")]
    public void IgnoresNonProgressOutput(string line)
    {
        Assert.False(ContentSyncProgressProtocol.TryParse(line, out var progress));
        Assert.Null(progress);
    }

    [Theory]
    [InlineData("{\"stage\":\"index\",\"changed\":[]}", 0)]
    [InlineData("{\"stage\":\"index\",\"changed\":[\"MOD/v1\",\"TWRP/v1\"]}", 2)]
    public void ReadsChangedPackCount(string line, int expected)
    {
        Assert.True(ContentSyncProgressProtocol.TryReadChangedPackCount(line, out var count));
        Assert.Equal(expected, count);
    }
}
