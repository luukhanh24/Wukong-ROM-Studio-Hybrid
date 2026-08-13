namespace WukongStudio.Core;

public static class JobSelectionPolicy
{
    public static string? Choose(IReadOnlyList<StudioJob> jobs, string? selectedJobId)
    {
        if (!string.IsNullOrWhiteSpace(selectedJobId)
            && jobs.Any(job => string.Equals(job.Id, selectedJobId, StringComparison.Ordinal)))
        {
            return selectedJobId;
        }

        return jobs.FirstOrDefault(job => job.Status is "running" or "packaging")?.Id
            ?? jobs.FirstOrDefault(job => job.Status == "queued")?.Id
            ?? jobs.FirstOrDefault()?.Id;
    }
}
