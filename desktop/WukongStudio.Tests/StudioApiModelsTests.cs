using System.Text.Json;
using WukongStudio.Core;

namespace WukongStudio.Tests;

public sealed class StudioApiModelsTests
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        PropertyNameCaseInsensitive = true,
    };

    [Fact]
    public void DeviceModelReadsBackendProductName()
    {
        const string json = """
            {
              "name": "OnePlus Ace 5",
              "product_name": "PKG110",
              "soc": "86xx",
              "SuperSize": 14578294784,
              "GroupSize": 14574100480,
              "Partitions": ["my_company", "my_preload"]
            }
            """;

        var device = JsonSerializer.Deserialize<StudioDevice>(json, JsonOptions);

        Assert.NotNull(device);
        Assert.Equal("PKG110", device.ProductName);
        Assert.Equal(14578294784, device.SuperSize);
        Assert.Equal(["my_company", "my_preload"], device.Partitions);
    }

    [Fact]
    public void JobModelReadsOperationalMetadata()
    {
        const string json = """
            {
              "id": "job-1",
              "versionName": "PKG110_16.0.5",
              "status": "running",
              "currentStep": "apply_mod",
              "outputZip": null,
              "steps": [
                {
                  "id": "package_zip",
                  "status": "running",
                  "details": {"progress": 45, "progressMessage": "ZIP 50%"}
                }
              ],
              "createdAt": "2026-07-13T10:00:00+00:00",
              "startedAt": "2026-07-13T10:01:00+00:00",
              "finishedAt": null,
              "error": null,
              "workspace": "C:\\WukongROMStudio\\Workspace\\PKG110_16.0.5"
            }
            """;

        var job = JsonSerializer.Deserialize<StudioJob>(json, JsonOptions);

        Assert.NotNull(job);
        Assert.Equal("2026-07-13T10:01:00+00:00", job.StartedAt);
        Assert.Equal("C:\\WukongROMStudio\\Workspace\\PKG110_16.0.5", job.Workspace);
        Assert.Equal(45, job.Progress);
        Assert.Equal("ZIP 50%", job.ProgressMessage);
    }

    [Fact]
    public void JobModelReadsProgressMessageFromActiveNonPackageStep()
    {
        const string json = """
            {
              "id": "job-apply-mod",
              "versionName": "PKG110_16.0.8",
              "status": "running",
              "currentStep": "apply_mod",
              "outputZip": null,
              "steps": [
                {
                  "id": "apply_mod",
                  "status": "running",
                  "details": {"progress": 67, "progressMessage": "Đóng gói services.jar"}
                },
                {
                  "id": "package_zip",
                  "status": "pending",
                  "details": {}
                }
              ]
            }
            """;

        var job = JsonSerializer.Deserialize<StudioJob>(json, JsonOptions);

        Assert.NotNull(job);
        Assert.Equal("Đóng gói services.jar", job.ProgressMessage);
    }

    [Fact]
    public void BootstrapModelReadsDefaultDebloatPaths()
    {
        const string json = """
            {
              "name": "Wukong ROM Studio",
              "settings": {
                "roots": [],
                "locale": "vi",
                "theme": "light",
                "defaultPreset": "lite",
                "notifyTelegram": true,
                "debloatPaths": null,
                "stageCacheEnabled": true,
                "stageCacheMaxGb": 24,
                "studioVersions": {"ColorOS_16.0.7":"V8.5"},
                "zipValidationMode": "deep"
              },
              "devices": [],
              "modVersions": [],
              "modsByVersion": {},
              "mods": [],
              "presetDefaultsByVersion": {},
              "presetDefaults": {},
              "jobs": [],
              "artifacts": [],
              "steps": [],
              "diagnostics": {},
              "defaultDebloatPaths": ["my_stock\\app\\Browser"],
              "deviceCatalogPath": "C:\\WukongROMStudio\\Data\\devices_sizes.json",
              "stageCache": {
                "enabled": true,
                "root": "C:\\WukongROMStudio\\Data\\Cache\\Payload",
                "maximumBytes": 25769803776,
                "totalBytes": 1024,
                "entryCount": 1,
                "totalHits": 2,
                "entries": []
              }
            }
            """;

        var bootstrap = JsonSerializer.Deserialize<StudioBootstrap>(json, JsonOptions);

        Assert.NotNull(bootstrap);
        Assert.Equal(["my_stock\\app\\Browser"], bootstrap.DefaultDebloatPaths);
        Assert.Equal("C:\\WukongROMStudio\\Data\\devices_sizes.json", bootstrap.DeviceCatalogPath);
        Assert.Equal(24, bootstrap.Settings.StageCacheMaxGb);
        Assert.Equal("V8.5", bootstrap.Settings.StudioVersions!["ColorOS_16.0.7"]);
        Assert.Equal("deep", bootstrap.Settings.ZipValidationMode);
        Assert.Equal(1, bootstrap.StageCache!.EntryCount);
    }

    [Fact]
    public void DeviceCatalogResponseReadsCanonicalJsonKeys()
    {
        const string json = """
            {
              "storagePath": "C:\\WukongROMStudio\\Data\\devices_sizes.json",
              "devices": [
                {
                  "product_name": "PJZ110",
                  "name": "OnePlus 13",
                  "soc": "87xx",
                  "SuperSize": 15354134528,
                  "GroupSize": 15349940224,
                  "Partitions": ["my_company"]
                }
              ]
            }
            """;

        var response = JsonSerializer.Deserialize<StudioDevicesResponse>(json, JsonOptions);

        Assert.NotNull(response);
        Assert.Single(response.Devices);
        Assert.Equal("PJZ110", response.Devices[0].ProductName);
        Assert.EndsWith("devices_sizes.json", response.StoragePath);
    }

    [Fact]
    public void RomRenamePreviewReadsPerFileStatus()
    {
        const string json = """
            {
              "entries": [
                {
                  "sourcePath": "D:\\ROM\\download.zip",
                  "sourceName": "download.zip",
                  "versionName": "PKG110_16.0.8.300(CN01)",
                  "targetPath": "D:\\ROM\\PKG110_16.0.8.300(CN01).zip",
                  "targetName": "PKG110_16.0.8.300(CN01).zip",
                  "status": "ready",
                  "warning": null,
                  "error": null
                }
              ],
              "total": 1,
              "ready": 1,
              "unchanged": 0,
              "errors": 0,
              "canApply": true
            }
            """;

        var preview = JsonSerializer.Deserialize<StudioRomRenamePreview>(json, JsonOptions);

        Assert.NotNull(preview);
        Assert.True(preview.CanApply);
        Assert.Equal("download.zip", preview.Entries[0].SourceName);
        Assert.Equal("PKG110_16.0.8.300(CN01).zip", preview.Entries[0].TargetName);
    }
}
