using System.Collections.ObjectModel;
using System.Collections.Specialized;
using WukongStudio.Core;

namespace WukongStudio.Tests;

public sealed class ObservableCollectionReconcilerTests
{
    [Fact]
    public void StableKeysDoNotRecreateCollectionItems()
    {
        var first = new TestItem("job-1", "old");
        var second = new TestItem("job-2", "old");
        var items = new ObservableCollection<TestItem> { first, second };
        var collectionChanges = 0;
        items.CollectionChanged += (_, _) => collectionChanges++;

        ObservableCollectionReconciler.ReconcileByKey(
            items,
            new[] { new TestSource("job-1", "new-1"), new TestSource("job-2", "new-2") },
            item => item.Id,
            source => source.Id,
            source => new TestItem(source.Id, source.Value),
            (item, source) => item.Value = source.Value);

        Assert.Same(first, items[0]);
        Assert.Same(second, items[1]);
        Assert.Equal("new-1", items[0].Value);
        Assert.Equal("new-2", items[1].Value);
        Assert.Equal(0, collectionChanges);
    }

    [Fact]
    public void ReorderedKeysMoveExistingItems()
    {
        var first = new TestItem("job-1", "first");
        var second = new TestItem("job-2", "second");
        var items = new ObservableCollection<TestItem> { first, second };
        var actions = new List<NotifyCollectionChangedAction>();
        items.CollectionChanged += (_, args) => actions.Add(args.Action);

        ObservableCollectionReconciler.ReconcileByKey(
            items,
            new[] { new TestSource("job-2", "updated"), new TestSource("job-1", "first") },
            item => item.Id,
            source => source.Id,
            source => new TestItem(source.Id, source.Value),
            (item, source) => item.Value = source.Value);

        Assert.Same(second, items[0]);
        Assert.Same(first, items[1]);
        Assert.Equal("updated", second.Value);
        Assert.Equal([NotifyCollectionChangedAction.Move], actions);
    }

    private sealed record TestSource(string Id, string Value);

    private sealed class TestItem(string id, string value)
    {
        public string Id { get; } = id;
        public string Value { get; set; } = value;
    }
}
