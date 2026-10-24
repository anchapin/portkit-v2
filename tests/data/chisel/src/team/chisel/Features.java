package team.chisel;
import net.minecraft.block.Block;
import net.minecraft.block.material.Material;
import team.chisel.api.block.BlockCreator;
import team.chisel.api.block.ChiselBlockFactory;
import team.chisel.api.block.VariationData;
import team.chisel.common.Helper;
import team.chisel.common.block.BlockCarvable;
import team.chisel.common.block.BlockCarvableCarpet;

// The shape of Chisel 1.12/dev team.chisel.Features: one enum constant per
// feature, its blocks made by builder chains in a constant-specific
// addBlocks; a required mod in the constructor; ANCIENT_STONE commented out
// as in Chisel's source, so its blockstate ships with no feature.
public enum Features {
    ALUMINUM {
        @Override
        void addBlocks(ChiselBlockFactory factory) {
            factory.newBlock(Material.ROCK, "blockAluminum", null, beaconBaseProvider)
                    .setParentFolder("metals/aluminum")
                    .newVariation("caution")
                    .next("crate")
                    .build(b -> b.setHardness(1.0F));
        }
    },
    /*ANCIENT_STONE ("thaumcraft") {
        @Override
        void addBlocks(ChiselBlockFactory factory) {
            factory.newBlock(Material.ROCK, "ancient_stone", provider).newVariation("cracked").build();
        }
    },*/
    ANDESITE {
        @Override
        void addBlocks(ChiselBlockFactory factory) {
            Helper.addGroup("andesite");
            factory.newBlock(Material.ROCK, "andesite", provider)
                    .newVariation("cracked")
                    .next("bricks-soft")
                    .next("circularct")
                    .next("pillar")
                    .next("encased")
                    .next("screenMetallic")
                    .addOreDict("stoneAndesite")
                    .build(b -> b.setHardness(1.5F));
        }
    },
    BLOODMAGIC("bloodmagic") {
        @Override
        void addBlocks(ChiselBlockFactory factory) {
            factory.newBlock(Material.ROCK, "bloodmagic", provider).newVariation("brick").build();
        }
    },
    CARPET {
        @Override
        void addBlocks(ChiselBlockFactory factory) {
            for (String c : COLORS) {
                factory.newBlock(Material.CARPET, "carpet_" + c, new ChiselBlockProvider<>(BlockCarvableCarpet::new, BlockCarvableCarpet.class))
                        .newVariation("legacy").build();
            }
        }
    },
    MARBLE {
        @Override
        void addBlocks(ChiselBlockFactory factory) {
            factory.newBlock(Material.ROCK, "marble", BlockCarvable::new, BlockCarvable.class)
                    .newVariation("raw")
                    .next("a1-stonecarving")
                    .build();
        }
    };

    private static final String[] COLORS = { "white", "black" };

    private static final BlockCreator<BlockCarvable> creator = BlockCarvable::new;
    private static final ChiselBlockProvider<BlockCarvable> provider = new ChiselBlockProvider<>(creator, BlockCarvable.class);
    private static final BlockCreator<BlockCarvable> beaconBaseCreator = (mat, index, maxVariation, data) -> new BlockCarvable(mat, index, maxVariation, data) { };
    private static final ChiselBlockProvider<BlockCarvable> beaconBaseProvider = new ChiselBlockProvider<>(beaconBaseCreator, BlockCarvable.class);

    private static class ChiselBlockProvider<T extends Block> implements team.chisel.api.block.BlockProvider<T> {
        private final BlockCreator<T> creator;
        private final Class<T> blockClass;
        ChiselBlockProvider(BlockCreator<T> creator, Class<T> blockClass) { this.creator = creator; this.blockClass = blockClass; }
        @Override public T createBlock(Material mat, int index, int maxVariation, VariationData... data) { return creator.createBlock(mat, index, maxVariation, data); }
        @Override public Class<T> getBlockClass() { return blockClass; }
    }

    public static void loadBlocks(Object registry) {
        ChiselBlockFactory factory = ChiselBlockFactory.newFactory(registry, Chisel.MOD_ID);
        for (Features f : values()) {
            f.addBlocks(factory);
        }
    }

    private Features parent;
    private String requiredMod;
    Features() { this(null, null); }
    Features(String requiredMod) { this(requiredMod, null); }
    Features(String requiredMod, Features parent) { this.requiredMod = requiredMod; this.parent = parent; }

    void addBlocks(ChiselBlockFactory factory) { }
}
