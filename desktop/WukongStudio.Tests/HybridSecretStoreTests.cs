using WukongStudio.Core;

namespace WukongStudio.Tests;

public sealed class HybridSecretStoreTests
{
    [Fact]
    public void DpapiRoundTripDoesNotStorePlaintext()
    {
        using var workspace = new TestWorkspace();
        var store = new HybridSecretStore(workspace.Layout);
        var credentials = new HybridCredentials(
            "luukhanh24/Wukong-ROM-Studio-Hybrid",
            "fixture-github-token",
            "[wukong-gdrive]\ntype = drive\ntoken = fixture-secret");

        store.Save(credentials);

        Assert.Equal(credentials, store.Load());
        var encrypted = File.ReadAllText(Path.Combine(workspace.Layout.SecretsRoot, "hybrid.dat"));
        Assert.DoesNotContain(credentials.GitHubToken, encrypted, StringComparison.Ordinal);
        Assert.DoesNotContain("fixture-secret", encrypted, StringComparison.Ordinal);
    }

    [Fact]
    public void InvalidCredentialsAreRejectedBeforeWritingSecret()
    {
        using var workspace = new TestWorkspace();
        var store = new HybridSecretStore(workspace.Layout);

        Assert.Throws<InvalidDataException>(() =>
            store.Save(new HybridCredentials("invalid-repository", "token", "config")));
        Assert.Null(store.Load());
    }
}
