package com.example.deco;

import java.util.Locale;
import net.minecraft.util.StringRepresentable;

/** The two halves of a two-block table (as Storage Drawers' EnumFramingTablePart). */
public enum TwinPart implements StringRepresentable {
    LEFT, RIGHT;

    @Override
    public String getSerializedName() { return this.name().toLowerCase(Locale.ROOT); }
}
