package net.neoforged.fml.common;
import java.lang.annotation.*;
import net.neoforged.api.distmarker.Dist;
// NeoForge's @Mod: the loader constructs the class once per mod id it names.
@Retention(RetentionPolicy.RUNTIME) @Target(ElementType.TYPE)
public @interface Mod { String value(); Dist[] dist() default { Dist.CLIENT, Dist.DEDICATED_SERVER }; }
