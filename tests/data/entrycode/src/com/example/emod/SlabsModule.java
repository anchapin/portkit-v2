package com.example.emod;
import com.example.elib.Event;
// A module's register method: the variant registry comes from the event it is handed.
public class SlabsModule { public void register(Event e) { e.variants().make("stone"); } }
