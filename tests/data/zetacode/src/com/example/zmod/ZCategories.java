package com.example.zmod;

import org.violetmoon.zeta.module.ZetaCategory;

public final class ZCategories {
    // Decided at run time, as Quark's ODDITIES_ID is (Zeta.isProduction).
    public static final String ODDITIES_ID = Boolean.getBoolean("production") ? "zmododdities" : "zmod";

    public static void init() {
        new ZetaCategory("building", null);
        new ZetaCategory("addons", null, "othermod");
        new ZetaCategory("oddities", null, ODDITIES_ID);
    }
}
