using System.Security.Cryptography;
using System.Text.Json;

namespace WukongStudio.Core;

public sealed record HybridCredentials(
    string GitHubRepository,
    string GitHubToken,
    string RcloneConfig,
    string RcloneRemote = "wukong-gdrive");

public sealed class HybridSecretStore(StudioLayout layout)
{
    private readonly string _path = Path.Combine(layout.SecretsRoot, "hybrid.dat");
    private static readonly byte[] Entropy = "WukongStudio.Hybrid.v1"u8.ToArray();

    public void Save(HybridCredentials credentials)
    {
        if (string.IsNullOrWhiteSpace(credentials.GitHubRepository)
            || !credentials.GitHubRepository.Contains('/')
            || string.IsNullOrWhiteSpace(credentials.GitHubToken)
            || string.IsNullOrWhiteSpace(credentials.RcloneConfig))
        {
            throw new InvalidDataException("GitHub repository, token and rclone configuration are required.");
        }
        layout.EnsureWritableDirectories();
        var plain = JsonSerializer.SerializeToUtf8Bytes(credentials);
        var encrypted = ProtectedData.Protect(plain, Entropy, DataProtectionScope.CurrentUser);
        var temporary = _path + ".tmp";
        try
        {
            File.WriteAllBytes(temporary, encrypted);
            File.Move(temporary, _path, overwrite: true);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(plain);
            File.Delete(temporary);
        }
    }

    public HybridCredentials? Load()
    {
        if (!File.Exists(_path)) return null;
        var plain = ProtectedData.Unprotect(File.ReadAllBytes(_path), Entropy, DataProtectionScope.CurrentUser);
        try
        {
            return JsonSerializer.Deserialize<HybridCredentials>(plain);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(plain);
        }
    }

    public void Delete() => File.Delete(_path);
}
