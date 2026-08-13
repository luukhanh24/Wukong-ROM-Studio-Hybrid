using System.Text.Json;

namespace WukongStudio.Core;

public sealed record StudioBuildRecipe(
    int SchemaVersion,
    string Id,
    string Name,
    bool Locked,
    string UpdatedAt,
    StudioBuildProfile Profile)
{
    public const int CurrentSchemaVersion = 1;
}

public sealed class StudioBuildRecipeStore(StudioLayout layout)
{
    public IReadOnlyList<StudioBuildRecipe> List()
    {
        Directory.CreateDirectory(layout.RecipesRoot);
        return Directory.EnumerateFiles(layout.RecipesRoot, "*.json", SearchOption.TopDirectoryOnly)
            .Select(Read)
            .Where(recipe => recipe is not null)
            .Cast<StudioBuildRecipe>()
            .OrderBy(recipe => recipe.Name, StringComparer.CurrentCultureIgnoreCase)
            .ToArray();
    }

    public StudioBuildRecipe Save(
        string name,
        StudioBuildProfile profile,
        string? id = null,
        bool? locked = null)
    {
        var existing = string.IsNullOrWhiteSpace(id) ? null : Get(id);
        if (existing?.Locked == true)
        {
            throw new InvalidOperationException("Recipe is locked. Unlock it before overwriting.");
        }
        var recipeId = existing?.Id ?? Guid.NewGuid().ToString("N");
        var recipe = new StudioBuildRecipe(
            StudioBuildRecipe.CurrentSchemaVersion,
            recipeId,
            string.IsNullOrWhiteSpace(name) ? profile.Name : name.Trim(),
            locked ?? existing?.Locked ?? false,
            DateTimeOffset.UtcNow.ToString("O"),
            profile);
        AtomicFile.WriteJson(PathFor(recipeId), recipe);
        return recipe;
    }

    public StudioBuildRecipe SetLocked(string id, bool locked)
    {
        var recipe = GetRequired(id) with
        {
            Locked = locked,
            UpdatedAt = DateTimeOffset.UtcNow.ToString("O"),
        };
        AtomicFile.WriteJson(PathFor(recipe.Id), recipe);
        return recipe;
    }

    public void Delete(string id)
    {
        var recipe = GetRequired(id);
        if (recipe.Locked)
        {
            throw new InvalidOperationException("Recipe is locked. Unlock it before deleting.");
        }
        File.Delete(PathFor(recipe.Id));
    }

    public StudioBuildRecipe Import(string sourcePath)
    {
        var json = File.ReadAllText(sourcePath);
        try
        {
            var imported = JsonSerializer.Deserialize<StudioBuildRecipe>(json, JsonOptions);
            if (imported is not null
                && imported.Profile is not null
                && imported.SchemaVersion == StudioBuildRecipe.CurrentSchemaVersion)
            {
                return Save(imported.Name, imported.Profile, locked: imported.Locked);
            }
        }
        catch (JsonException)
        {
        }
        var profile = StudioBuildProfile.Parse(json);
        return Save(profile.Name, profile);
    }

    public void Export(string id, string destinationPath) =>
        AtomicFile.WriteJson(destinationPath, GetRequired(id));

    public StudioBuildRecipe? Get(string id) => Read(PathFor(id));

    private StudioBuildRecipe GetRequired(string id) => Get(id)
        ?? throw new FileNotFoundException("Build recipe was not found.", id);

    private string PathFor(string id)
    {
        if (id.Length != 32 || id.Any(character => !Uri.IsHexDigit(character)))
        {
            throw new InvalidDataException("Build recipe id is invalid.");
        }
        return Path.Combine(layout.RecipesRoot, id.ToLowerInvariant() + ".json");
    }

    private static StudioBuildRecipe? Read(string path)
    {
        if (!File.Exists(path))
        {
            return null;
        }
        try
        {
            var recipe = JsonSerializer.Deserialize<StudioBuildRecipe>(File.ReadAllText(path), JsonOptions);
            return recipe?.SchemaVersion == StudioBuildRecipe.CurrentSchemaVersion ? recipe : null;
        }
        catch (JsonException)
        {
            return null;
        }
    }

    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        PropertyNameCaseInsensitive = true,
        WriteIndented = true,
    };
}
