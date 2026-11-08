package a;

/** A key whose class declares equals, as IE's BoundingBoxKey does. */
public class Key {
    final int n;

    public Key(int n) {
        this.n = n;
    }

    @Override
    public boolean equals(Object o) {
        return o instanceof Key k && k.n == n;
    }

    @Override
    public int hashCode() {
        return n;
    }
}
