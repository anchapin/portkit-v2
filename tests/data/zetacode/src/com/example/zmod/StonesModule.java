package com.example.zmod;

import org.violetmoon.zeta.config.ConfigFlagManager;
import org.violetmoon.zeta.event.bus.LoadEvent;
import org.violetmoon.zeta.event.load.ZGatherAdditionalFlags;
import org.violetmoon.zeta.module.ZetaLoadModule;
import org.violetmoon.zeta.module.ZetaModule;

@ZetaLoadModule(category = "building")
public class StonesModule extends ZetaModule {
    public static boolean enablePillar = true;

    @LoadEvent
    public final void moreFlags(ZGatherAdditionalFlags event) {
        ConfigFlagManager manager = event.flagManager();
        manager.putFlag(this, "granite", true);
        manager.putFlag(this, "tuff", false);
        manager.putFlag(this, "pillar", enablePillar);
    }

    // Not a load-event handler: never called, so it puts no flag.
    public final void notSubscribed(ZGatherAdditionalFlags event) {
        event.flagManager().putFlag(this, "ghost", true);
    }
}
