package org.violetmoon.quark.base.proxy;

/** Subscribes the handler, as Quark's proxy hands it to Zeta's load bus. */
public class CommonProxy {
    public Object handler() { return org.violetmoon.quark.base.handler.QuarkRemapHandler.class; }
}
