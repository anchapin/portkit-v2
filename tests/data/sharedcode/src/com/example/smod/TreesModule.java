package com.example.smod;
import com.example.ilib.IModule;
import java.util.ArrayList;
import java.util.List;
// Quark's BlossomTreesModule shape: a static final list one module's register fills.
public class TreesModule extends IModule {
  public static final List<Tree> trees = new ArrayList<>();
  public void register() {
    trees.add(new Tree("blue"));
    trees.add(new Tree("red"));
  }
  public void setup() {
    for (Tree t : trees) System.out.println(t.name);
  }
}
