package com.example.lone;

import java.util.Locale;
import net.minecraft.util.StringRepresentable;

/** A device's mode; serialized lowercase, as mods write it. */
public enum Mode implements StringRepresentable {
    IDLE, FLAME, TIMEOUT;

    @Override
    public String getSerializedName() { return this.name().toLowerCase(Locale.ROOT); }
}
