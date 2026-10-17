package com.example.ores;
/** A config wrapper: each option a no-argument boolean read from storage the jar doesn't hold. */
public class ModConfig {
    private java.util.Map<String, Boolean> values;
    public boolean silver() { return values.get("silver"); }
    public boolean tin() { return values.get("tin"); }
    public boolean ruby() { return values.get("ruby"); }
}
