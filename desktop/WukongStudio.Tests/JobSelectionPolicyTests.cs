using WukongStudio.Core;

namespace WukongStudio.Tests;

public sealed class JobSelectionPolicyTests
{
    [Fact]
    public void KeepsCurrentSelectionWhenJobStillExists()
    {
        var jobs = new[] { Job("running", "running"), Job("selected", "success") };

        Assert.Equal("selected", JobSelectionPolicy.Choose(jobs, "selected"));
    }

    [Fact]
    public void PrefersActiveJobWhenNothingIsSelected()
    {
        var jobs = new[] { Job("latest-success", "success"), Job("active", "running"), Job("queued", "queued") };

        Assert.Equal("active", JobSelectionPolicy.Choose(jobs, null));
    }

    [Fact]
    public void FallsBackToQueuedThenMostRecentJob()
    {
        var queuedJobs = new[] { Job("success", "success"), Job("queued", "queued") };
        var completedJobs = new[] { Job("latest", "success"), Job("older", "failed") };

        Assert.Equal("queued", JobSelectionPolicy.Choose(queuedJobs, null));
        Assert.Equal("latest", JobSelectionPolicy.Choose(completedJobs, "missing"));
    }

    private static StudioJob Job(string id, string status) =>
        new(id, id, status, null, null, []);
}
