package org.violetmoon.zeta.module;

import java.util.Locale;

// Zeta's module naming (TentativeModule#from), reduced to the strings.
public final class TentativeModule {
    public static String from(Class<?> clazz, String declared) {
        String name = declared.isEmpty()
                ? clazz.getSimpleName().replaceAll("Module$", "").replaceAll("(?<=.)([A-Z])", " $1")
                : declared;
        return name.toLowerCase(Locale.ROOT).replace(" ", "_");
    }
}
