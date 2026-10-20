package com.example.zmod;

import org.violetmoon.zeta.config.Config;
import org.violetmoon.zeta.module.ZetaLoadModule;
import org.violetmoon.zeta.module.ZetaModule;

@ZetaLoadModule(category = "building", enabledByDefault = false)
public class LegacyModule extends ZetaModule {
    @Config(flag = "legacy_extra")
    public static boolean enableExtra = true;
}
