package com.example.clinit;
import com.example.clinitext.Ext;
import net.neoforged.neoforge.registries.DeferredRegister;
// Types registered in a class initializer, under names the run can't spell.
public class Types {
  static final DeferredRegister REGISTER = DeferredRegister.createBlocks("clinit");
  public static final Object PLAIN = new TypeBuilder<>(PlainEntity::new).build(Ext.name());
  public static final Object BIN = compat(new TypeBuilder<>(BinEntity::new)).without(Ext.cap()).build(Ext.name());
  public static final Object FORKED = forked();
  static <T extends net.minecraft.world.level.block.entity.BlockEntity> TypeBuilder<T> compat(TypeBuilder<T> b) {
    Compat.addCaps(b); return b; }
  static Object forked() {
    TypeBuilder<BinEntity> b = new TypeBuilder<>(BinEntity::new);
    if (Ext.flag()) b.with("extra");
    return b.build(Ext.name()); } }
