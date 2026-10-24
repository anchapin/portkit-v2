package team.chisel.common;
// Stands in for Chisel's carving registry calls inside addBlocks
// (Carving.chisel.addVariation(...)): code that registers nothing the
// variation reading looks at and that the reading need not follow.
public class Helper {
    public static Object[] TABLE;
    public static void addGroup(String name) { TABLE[name.length()].hashCode(); }
}
