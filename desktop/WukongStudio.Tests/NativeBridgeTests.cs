using System.IO;
using System.Text.Json;
using WukongStudio.Core;

namespace WukongStudio.Tests;

public sealed class NativeBridgeTests
{
    [Fact]
    public void ParsesAllowedAction()
    {
        var id = Guid.NewGuid().ToString();
        var request = NativeBridgeProtocol.Parse(JsonSerializer.Serialize(new
        {
            id,
            action = "pickRom",
            payload = new { },
        }));
        Assert.Equal(id, request.Id);
    }

    [Fact]
    public void RejectsUnknownAction()
    {
        var json = JsonSerializer.Serialize(new
        {
            id = Guid.NewGuid().ToString(),
            action = "readFile",
            payload = new { path = @"C:\secret.txt" },
        });
        Assert.Throws<InvalidDataException>(() => NativeBridgeProtocol.Parse(json));
    }
}
