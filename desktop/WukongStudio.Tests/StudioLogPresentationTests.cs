using WukongStudio.Core;

namespace WukongStudio.Tests;

public sealed class StudioLogPresentationTests
{
    [Fact]
    public void DefaultViewHidesInternalEventsAndRepeatedZipProgress()
    {
        const string raw = """
            === Package ZIP ===
            @@STUDIO_EVENT@@{"type":"step","step":"package_zip"}
            [*] ZIP progress: 93%
            Everything is Ok
            """;

        var lines = StudioLogPresentation.Build(raw);

        Assert.Equal(["=== Package ZIP ===", "Everything is Ok"], lines.Select(line => line.Text));
        Assert.Equal(StudioLogLineKind.Stage, lines[0].Kind);
        Assert.Equal(StudioLogLineKind.Success, lines[1].Kind);
    }

    [Fact]
    public void TechnicalViewKeepsInternalEventsAndProgress()
    {
        const string raw = "@@STUDIO_EVENT@@{\"type\":\"step\"}\n[*] ZIP progress: 93%\n";

        var lines = StudioLogPresentation.Build(raw, includeTechnical: true);

        Assert.Equal(2, lines.Count);
        Assert.All(lines, line => Assert.Equal(StudioLogLineKind.Technical, line.Kind));
    }

    [Fact]
    public void SeverityFilterKeepsWarningsAndErrorsOnly()
    {
        const string raw = "CMD: unpack.exe\nwarning: missing config\nfailed to repack vendor\ndone system\n";

        var lines = StudioLogPresentation.Build(
            raw,
            filter: StudioLogFilter.WarningsAndErrors);

        Assert.Equal(["warning: missing config", "failed to repack vendor"], lines.Select(line => line.Text));
        Assert.Equal([StudioLogLineKind.Warning, StudioLogLineKind.Error], lines.Select(line => line.Kind));
    }

    [Fact]
    public void SearchIsCaseInsensitiveAndConsecutiveDuplicatesCollapse()
    {
        const string raw = "Processing system.img\nProcessing system.img\nDone vendor.img\n";

        var lines = StudioLogPresentation.Build(raw, query: "SYSTEM");

        Assert.Single(lines);
        Assert.Equal("Processing system.img", lines[0].Text);
    }
}
