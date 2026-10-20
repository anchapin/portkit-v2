package com.example.zmod;

import org.violetmoon.zeta.module.ZetaLoadModule;
import org.violetmoon.zeta.module.ZetaModule;

@ZetaLoadModule(category = "building")
public class SlabsModule extends ZetaModule {
    @ZetaLoadModule(clientReplacement = true)
    public static class Client extends SlabsModule {
    }
}
