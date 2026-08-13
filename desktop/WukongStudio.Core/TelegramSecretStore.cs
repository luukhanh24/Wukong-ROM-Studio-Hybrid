using System.Security.Cryptography;
using System.Text.Json;

namespace WukongStudio.Core;

public sealed record TelegramCredentials(string BotToken, string ChatId);

public sealed class TelegramSecretStore(StudioLayout layout)
{
    private readonly string _path = Path.Combine(layout.SecretsRoot, "telegram.dat");
    private static readonly byte[] Entropy = "WukongStudio.Telegram.v1"u8.ToArray();

    public void Save(TelegramCredentials credentials)
    {
        layout.EnsureWritableDirectories();
        var plain = JsonSerializer.SerializeToUtf8Bytes(credentials);
        var encrypted = ProtectedData.Protect(plain, Entropy, DataProtectionScope.CurrentUser);
        var temporary = _path + ".tmp";
        File.WriteAllBytes(temporary, encrypted);
        File.Move(temporary, _path, overwrite: true);
        CryptographicOperations.ZeroMemory(plain);
    }

    public TelegramCredentials? Load()
    {
        if (!File.Exists(_path))
        {
            return null;
        }

        var encrypted = File.ReadAllBytes(_path);
        var plain = ProtectedData.Unprotect(encrypted, Entropy, DataProtectionScope.CurrentUser);
        try
        {
            return JsonSerializer.Deserialize<TelegramCredentials>(plain);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(plain);
        }
    }

    public bool TryImportLegacyEnvironment(string environmentPath)
    {
        if (File.Exists(_path) || !File.Exists(environmentPath))
        {
            return false;
        }

        var values = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var rawLine in File.ReadLines(environmentPath))
        {
            var line = rawLine.Trim();
            if (line.Length == 0 || line.StartsWith('#'))
            {
                continue;
            }
            if (line.StartsWith("export ", StringComparison.Ordinal))
            {
                line = line[7..].TrimStart();
            }
            var separator = line.IndexOf('=');
            if (separator <= 0)
            {
                continue;
            }
            var key = line[..separator].Trim();
            var value = line[(separator + 1)..].Trim();
            if (value.Length >= 2
                && ((value[0] == '"' && value[^1] == '"')
                    || (value[0] == '\'' && value[^1] == '\'')))
            {
                value = value[1..^1];
            }
            values[key] = value;
        }

        values.TryGetValue("WUKONG_TELEGRAM_BOT_TOKEN", out var token);
        values.TryGetValue("WUKONG_TELEGRAM_CHAT_ID", out var chatId);
        token = token?.Trim();
        chatId = chatId?.Trim();
        if (string.IsNullOrWhiteSpace(token) || token.Length < 20 || string.IsNullOrWhiteSpace(chatId))
        {
            return false;
        }

        Save(new TelegramCredentials(token, chatId));
        return true;
    }

    public void Delete() => File.Delete(_path);
}
