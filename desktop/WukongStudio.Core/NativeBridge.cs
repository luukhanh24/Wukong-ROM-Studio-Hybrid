using System.Text.Json;

namespace WukongStudio.Core;

public sealed record NativeBridgeRequest(string Id, string Action, JsonElement Payload);

public sealed record NativeBridgeResponse(string Id, bool Ok, object? Result, string? Error)
{
    public static NativeBridgeResponse Success(string id, object? result = null) => new(id, true, result, null);
    public static NativeBridgeResponse Failure(string id, string error) => new(id, false, null, error);
}

public static class NativeBridgeProtocol
{
    public static readonly IReadOnlySet<string> AllowedActions = new HashSet<string>(StringComparer.Ordinal)
    {
        "pickRom",
        "pickRomFolder",
        "openFolder",
        "copyText",
        "showNotification",
        "getDesktopState",
        "configureTelegram",
        "restartBackend",
        "openLogs",
        "openOutput",
    };

    public static NativeBridgeRequest Parse(string json)
    {
        var request = JsonSerializer.Deserialize<NativeBridgeRequest>(json, JsonOptions)
            ?? throw new InvalidDataException("Native bridge request is empty.");
        if (!Guid.TryParse(request.Id, out _))
        {
            throw new InvalidDataException("Native bridge request ID is invalid.");
        }
        if (!AllowedActions.Contains(request.Action))
        {
            throw new InvalidDataException($"Native bridge action is not allowed: {request.Action}");
        }
        return request;
    }

    public static string Serialize(NativeBridgeResponse response) => JsonSerializer.Serialize(response, JsonOptions);

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNameCaseInsensitive = true,
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
    };
}
