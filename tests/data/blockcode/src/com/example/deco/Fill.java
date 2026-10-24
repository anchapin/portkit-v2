package com.example.deco;

import java.util.Locale;
import net.minecraft.util.StringRepresentable;

/** What a lying log holds; serialized lowercase, as mods write it. */
public enum Fill implements StringRepresentable {
    EMPTY, MOSS, WATERLOGGED;

    @Override
    public String getSerializedName() { return this.name().toLowerCase(Locale.ROOT); }
}
