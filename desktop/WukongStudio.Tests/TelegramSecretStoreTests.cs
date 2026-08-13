using WukongStudio.Core;

namespace WukongStudio.Tests;

public sealed class TelegramSecretStoreTests
{
    [Fact]
    public void DpapiRoundTripDoesNotStorePlaintext()
    {
        using var workspace = new TestWorkspace();
        var store = new TelegramSecretStore(workspace.Layout);
        var credentials = new TelegramCredentials("1234567890:abcdefghijklmnopqrstuvwxyz", "99887766");
        store.Save(credentials);

        Assert.Equal(credentials, store.Load());
        var encrypted = File.ReadAllText(Path.Combine(workspace.Layout.SecretsRoot, "telegram.dat"));
        Assert.DoesNotContain(credentials.BotToken, encrypted);
        Assert.DoesNotContain(credentials.ChatId, encrypted);
    }

    [Fact]
    public void ImportsLegacyEnvironmentIntoDpapiStore()
    {
        using var workspace = new TestWorkspace();
        var environmentPath = Path.Combine(workspace.Root, "telegram.env");
        File.WriteAllText(environmentPath,
            "WUKONG_TELEGRAM_BOT_TOKEN=1234567890:abcdefghijklmnopqrstuvwxyz\n"
            + "WUKONG_TELEGRAM_CHAT_ID=99887766\n"
            + "WUKONG_TELEGRAM_TIMEOUT=20\n");
        var store = new TelegramSecretStore(workspace.Layout);

        Assert.True(store.TryImportLegacyEnvironment(environmentPath));
        Assert.Equal(
            new TelegramCredentials("1234567890:abcdefghijklmnopqrstuvwxyz", "99887766"),
            store.Load());
    }

    [Fact]
    public void LegacyImportDoesNotOverwriteExistingSecret()
    {
        using var workspace = new TestWorkspace();
        var environmentPath = Path.Combine(workspace.Root, "telegram.env");
        File.WriteAllText(environmentPath,
            "WUKONG_TELEGRAM_BOT_TOKEN=1111111111:legacytokenabcdefghijklmnop\n"
            + "WUKONG_TELEGRAM_CHAT_ID=11111111\n");
        var store = new TelegramSecretStore(workspace.Layout);
        var existing = new TelegramCredentials("2222222222:currenttokenabcdefghijkl", "22222222");
        store.Save(existing);

        Assert.False(store.TryImportLegacyEnvironment(environmentPath));
        Assert.Equal(existing, store.Load());
    }
}
