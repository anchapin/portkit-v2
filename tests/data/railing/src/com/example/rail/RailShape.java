package com.example.rail;

import java.util.Locale;
import net.minecraft.util.StringRepresentable;

/** A railing's shape; serialized lowercase, as mods write it. */
public enum RailShape implements StringRepresentable {
    SHORT, TALL, CONNECTED;

    @Override
    public String getSerializedName() { return this.name().toLowerCase(Locale.ROOT); }
}
