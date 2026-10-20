package org.violetmoon.zeta.module;

public class ZetaCategory {
    public final String name;
    public final String requiredMod;

    public ZetaCategory(String name, Object icon) {
        this(name, icon, null);
    }

    public ZetaCategory(String name, Object icon, String requiredMod) {
        this.name = name;
        this.requiredMod = requiredMod;
    }
}
