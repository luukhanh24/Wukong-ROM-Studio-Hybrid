using System.Collections.ObjectModel;

namespace WukongStudio.Core;

public static class ObservableCollectionReconciler
{
    public static void ReconcileByKey<TItem, TSource, TKey>(
        ObservableCollection<TItem> target,
        IReadOnlyList<TSource> source,
        Func<TItem, TKey> itemKey,
        Func<TSource, TKey> sourceKey,
        Func<TSource, TItem> create,
        Action<TItem, TSource> update)
        where TKey : notnull
    {
        var sourceKeys = source.Select(sourceKey).ToHashSet();
        if (sourceKeys.Count != source.Count)
        {
            throw new InvalidDataException("Collection source contains duplicate keys.");
        }

        for (var index = target.Count - 1; index >= 0; index--)
        {
            if (!sourceKeys.Contains(itemKey(target[index])))
            {
                target.RemoveAt(index);
            }
        }

        for (var index = 0; index < source.Count; index++)
        {
            var sourceItem = source[index];
            var key = sourceKey(sourceItem);
            TItem targetItem;
            if (index < target.Count && EqualityComparer<TKey>.Default.Equals(itemKey(target[index]), key))
            {
                targetItem = target[index];
            }
            else
            {
                var existingIndex = FindIndex(target, index + 1, item =>
                    EqualityComparer<TKey>.Default.Equals(itemKey(item), key));
                if (existingIndex >= 0)
                {
                    target.Move(existingIndex, index);
                    targetItem = target[index];
                }
                else
                {
                    targetItem = create(sourceItem);
                    target.Insert(index, targetItem);
                }
            }
            update(targetItem, sourceItem);
        }
    }

    private static int FindIndex<T>(IReadOnlyList<T> items, int startIndex, Func<T, bool> predicate)
    {
        for (var index = startIndex; index < items.Count; index++)
        {
            if (predicate(items[index]))
            {
                return index;
            }
        }
        return -1;
    }
}
