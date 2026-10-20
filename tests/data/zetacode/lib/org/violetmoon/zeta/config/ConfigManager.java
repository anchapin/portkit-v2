package org.violetmoon.zeta.config;

import org.violetmoon.zeta.module.ZetaCategory;
import org.violetmoon.zeta.module.ZetaModule;

// The option builders of Zeta's ConfigManager: a category option defaulting
// to true, a module option defaulting to the module's enabledByDefault.
public class ConfigManager {
    static void category(ZetaCategory category, ValueDefinition.Builder b) {
        b.name(category.name).defaultValue(true);
    }

    static void module(ZetaModule module, ValueDefinition.Builder b) {
        b.defaultValue(module.enabledByDefault());
    }
}
