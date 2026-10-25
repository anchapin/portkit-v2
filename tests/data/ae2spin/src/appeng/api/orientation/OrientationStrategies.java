package appeng.api.orientation;

public final class OrientationStrategies {
    private static final IOrientationStrategy none = new NoOrientationStrategy();
    private static final IOrientationStrategy full = new FacingWithSpinStrategy();

    public static IOrientationStrategy none() { return none; }
    public static IOrientationStrategy full() { return full; }
}
