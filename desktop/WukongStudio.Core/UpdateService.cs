using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text.Json;

namespace WukongStudio.Core;

public sealed record StudioUpdateManifest(
    string Version,
    string Url,
    long Size,
    string Sha256,
    bool RequireAuthenticode = false);

public sealed class UpdateService(StudioLayout layout, HttpClient? httpClient = null) : IDisposable
{
    private readonly HttpClient _client = httpClient ?? new HttpClient();
    private readonly bool _ownsClient = httpClient is null;

    public static StudioUpdateManifest ParseManifest(string json)
    {
        var manifest = JsonSerializer.Deserialize<StudioUpdateManifest>(json, new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true,
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        }) ?? throw new InvalidDataException("Update manifest is empty.");
        if (!Version.TryParse(manifest.Version, out _)
            || !Uri.TryCreate(manifest.Url, UriKind.Absolute, out var uri)
            || uri.Scheme != Uri.UriSchemeHttps
            || manifest.Size <= 0
            || manifest.Sha256.Length != 64
            || !manifest.Sha256.All(Uri.IsHexDigit))
        {
            throw new InvalidDataException("Update manifest is invalid.");
        }
        return manifest;
    }

    public async Task<StudioUpdateManifest> GetManifestAsync(
        Uri manifestUri,
        CancellationToken cancellationToken = default)
    {
        if (manifestUri.Scheme != Uri.UriSchemeHttps)
        {
            throw new InvalidDataException("Update manifest must use HTTPS.");
        }
        using var response = await _client.GetAsync(manifestUri, cancellationToken);
        response.EnsureSuccessStatusCode();
        return ParseManifest(await response.Content.ReadAsStringAsync(cancellationToken));
    }

    public async Task<string> DownloadAsync(StudioUpdateManifest manifest, CancellationToken cancellationToken = default)
    {
        layout.EnsureWritableDirectories();
        var uri = new Uri(manifest.Url);
        if (uri.Scheme != Uri.UriSchemeHttps)
        {
            throw new InvalidDataException("Updates must use HTTPS.");
        }
        var destination = Path.Combine(layout.UpdatesRoot, $"WukongStudio-{manifest.Version}.exe");
        var temporary = destination + ".download";
        try
        {
            using var response = await _client.GetAsync(uri, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
            response.EnsureSuccessStatusCode();
            await using (var input = await response.Content.ReadAsStreamAsync(cancellationToken))
            await using (var output = new FileStream(temporary, FileMode.Create, FileAccess.Write, FileShare.None, 1024 * 1024, true))
            {
                await input.CopyToAsync(output, cancellationToken);
            }
            await ValidatePackageAsync(temporary, manifest, cancellationToken);
            File.Move(temporary, destination, overwrite: true);
            return destination;
        }
        finally
        {
            if (File.Exists(temporary))
            {
                File.Delete(temporary);
            }
        }
    }

    public static async Task ValidatePackageAsync(
        string path,
        StudioUpdateManifest manifest,
        CancellationToken cancellationToken = default)
    {
        var info = new FileInfo(path);
        if (!info.Exists || info.Length != manifest.Size)
        {
            throw new InvalidDataException("Update package size does not match its manifest.");
        }
        var hash = await ContentPackService.ComputeSha256Async(path, cancellationToken);
        if (!hash.Equals(manifest.Sha256, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidDataException("Update package SHA-256 does not match its manifest.");
        }
        if (manifest.RequireAuthenticode)
        {
            try
            {
#pragma warning disable SYSLIB0057
                using var certificate = new X509Certificate2(X509Certificate.CreateFromSignedFile(path));
#pragma warning restore SYSLIB0057
                using var chain = new X509Chain
                {
                    ChainPolicy =
                    {
                        RevocationMode = X509RevocationMode.Online,
                        RevocationFlag = X509RevocationFlag.ExcludeRoot,
                    },
                };
                if (!chain.Build(certificate))
                {
                    throw new CryptographicException("The Authenticode certificate chain is not trusted.");
                }
            }
            catch (CryptographicException exception)
            {
                throw new InvalidDataException("Update package does not contain an Authenticode signature.", exception);
            }
        }
    }

    public void Dispose()
    {
        if (_ownsClient)
        {
            _client.Dispose();
        }
    }
}
