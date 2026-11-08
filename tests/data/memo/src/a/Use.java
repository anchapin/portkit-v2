package a;

public class Use {
    static final Memo<Key> MEMO = new Memo<>(Use::twice);
    static final Leaky<Key> LEAKY = new Leaky<>(Use::twice);

    static int[] twice(Key k) {
        return new int[]{k.n * 2};
    }

    /** Asked twice, after a branch on an unknown: the cache answers the function's value. */
    public static int[] memo(boolean any) {
        int[] first = MEMO.get(new Key(3));
        if (any) {
            return MEMO.get(new Key(3));
        }
        return first;
    }

    public static int[] leaky(boolean any) {
        int[] first = LEAKY.get(new Key(3));
        if (any) {
            return LEAKY.get(new Key(3));
        }
        return first;
    }
}
