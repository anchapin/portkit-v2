package a;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Function;

/** A cache of one function, as Immersive Engineering's CachedVoxelShapes is. */
public class Memo<K> {
    private final Map<K, int[]> cache = new ConcurrentHashMap<>();
    private final Function<K, int[]> creator;

    public Memo(Function<K, int[]> creator) {
        this.creator = creator;
    }

    public int[] get(K k) {
        return cache.computeIfAbsent(k, this::make);
    }

    private int[] make(K k) {
        return creator.apply(k);
    }
}
