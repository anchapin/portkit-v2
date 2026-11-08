package a;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Function;

/** The same cache, but its map is also written by put: not a cache of one function. */
public class Leaky<K> {
    private final Map<K, int[]> cache = new ConcurrentHashMap<>();
    private final Function<K, int[]> creator;

    public Leaky(Function<K, int[]> creator) {
        this.creator = creator;
    }

    public int[] get(K k) {
        return cache.computeIfAbsent(k, this::make);
    }

    public void force(K k, int[] v) {
        cache.put(k, v);
    }

    private int[] make(K k) {
        return creator.apply(k);
    }
}
