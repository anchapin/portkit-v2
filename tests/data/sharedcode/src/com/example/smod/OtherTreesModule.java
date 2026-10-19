package com.example.smod;
import com.example.ilib.IModule;
import java.util.ArrayList;
import java.util.List;
// A list one method adds to that the reader never runs: what it holds isn't known in full.
public class OtherTreesModule extends IModule {
  public static final List<Tree> others = new ArrayList<>();
  public void register() { others.add(new Tree("pink")); }
  public void later() { others.add(new Tree(String.valueOf(System.nanoTime()))); }
}
