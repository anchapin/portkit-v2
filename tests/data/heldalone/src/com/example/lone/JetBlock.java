package com.example.lone;

import net.minecraft.core.BlockPos;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.BaseEntityBlock;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.EnumProperty;
import net.minecraft.world.phys.BlockHitResult;

/** One enum state and nothing else: it starts IDLE (registered) and only
 * the block's own use changes it. */
public class JetBlock extends BaseEntityBlock {
    public static final EnumProperty<Mode> MODE = EnumProperty.create("mode", Mode.class);

    public JetBlock(Properties p) {
        super(p);
        registerDefaultState(getStateDefinition().any().setValue(MODE, Mode.IDLE));
    }

    @Override
    protected InteractionResult useWithoutItem(BlockState s, Level level, BlockPos pos, Player pl, BlockHitResult r) {
        level.setBlock(pos, s.setValue(MODE, Mode.FLAME), 3);
        return InteractionResult.SUCCESS;
    }

    @Override
    public BlockEntity newBlockEntity(BlockPos pos, BlockState state) { return null; }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder b) { b.add(MODE); }
}
