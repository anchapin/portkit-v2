package com.example.zmod;

import org.violetmoon.zeta.module.ZetaLoadModule;
import org.violetmoon.zeta.module.ZetaModule;

@ZetaLoadModule(category = "building", antiOverlap = {"othermod"})
public class OverlapModule extends ZetaModule {
}
