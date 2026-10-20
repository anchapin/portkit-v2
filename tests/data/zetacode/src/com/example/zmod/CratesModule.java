package com.example.zmod;

import org.violetmoon.zeta.config.Config;
import org.violetmoon.zeta.module.ZetaLoadModule;
import org.violetmoon.zeta.module.ZetaModule;

@ZetaLoadModule(category = "building")
public class CratesModule extends ZetaModule {
    @Config(flag = "apple_crate")
    public static boolean enableApple = true;
    @Config(flag = "pre_end")
    public static boolean preEnd = false;
    @Config(flag = "sack")
    public static boolean sack;
    @Config(flag = "computed")
    public static boolean computed = Boolean.getBoolean("computed");
    @Config(flag = "inst_flag")
    public boolean inst = true;
    @Config(name = "No flag")
    public static boolean plain = true;
}
