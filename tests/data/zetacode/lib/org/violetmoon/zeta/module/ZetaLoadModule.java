package org.violetmoon.zeta.module;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

// Stand-in for Zeta 1.1-40's annotation: the same elements and defaults.
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface ZetaLoadModule {
    String category() default "";
    String name() default "";
    String description() default "";
    String[] antiOverlap() default {};
    boolean enabledByDefault() default true;
    boolean clientReplacement() default false;
    int loadPhase() default 0;
}
