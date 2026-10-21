package com.example.render;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.state.BlockState;
// Takes its answer from another method: unread.
public class AskingBlock extends Block {
  public AskingBlock(Properties p) { super(p); }
  static RenderShape pick() { return RenderShape.MODEL; }
  public RenderShape getRenderShape(BlockState s) { return pick(); }
}
