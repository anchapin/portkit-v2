package com.example.cmod;
import com.example.clib.Colors;
import java.util.HashMap;
import java.util.Map;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockBehaviour.Properties;
// A registry helper looping over a library list the reading can't hold: its run doesn't finish.
public class CHelper {
  public static String LAST = "";
  public static Map<String, Object> registerFlags(String base) {
    LAST = base;
    Map<String, Object> map = new HashMap<>();
    for (String color : Colors.SORTED) {
      String name = base + "_" + color;
      map.put(color, CRegistry.BLOCKS.register(name, () -> new Block(Properties.of())));
      if (color.length() > 3) map.put(color + "_x", name);
      if (color.length() > 4) map.put(color + "_y", name);
    }
    return map;
  }
}
