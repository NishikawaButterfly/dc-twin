# Plain-Language Explainer

I wrote most of the documentation in this repository for people who already know what a UPS is. This page is for everyone else. If you can read a train timetable, you can follow what the simulator shows. I will use the bundled composite scenario, `REF-DC-2N-001`, as the running example. It is the same run shown in the README screenshot of the web explorer.

One thing before we start. Everything here is fictional. The equipment ratings, the failure times, the ten-minute story: all invented for this repository. The simulator is a reasoning tool, not a window into any real site.

## The path power takes

A data center is a building full of computers, and the computers need electricity every second of every day. The interesting part is not the computers. It is the chain of equipment between the public grid and the plug. The model calls this chain a path, and it is built from a handful of standard pieces.

The **utility** is the connection to the public electrical grid. It is the same electricity that reaches your home, arriving through a much larger cable. On a normal day, all the power comes from here.

The **generator** is a large engine, usually diesel, that sits idle next to the building. When the grid goes away, the generator starts and takes over. Starting takes time, typically some seconds, and in this model a generator can also simply fail to start. That possibility drives the whole example below.

The **UPS** (uninterruptible power supply) is a big battery with electronics around it. Its job is to bridge gaps. When the grid fails, the UPS carries the load instantly while the generator starts. The catch is that a battery is finite. It buys minutes, not hours.

The **transfer switch** decides which source feeds the equipment downstream: the grid or the generator. Think of a railway switch that routes a track one way or the other. In the other docs it appears as ATS or STS, which are two flavors of the same idea.

The **PDU** (power distribution unit) takes one large feed and splits it into many smaller circuits for the computer racks. A very large, very supervised power strip.

The **load** is anything that consumes power. In this model a load is just a number: a demand in watts that must be served. The reference loads stand in for racks of servers.

The modeled paths also contain transformers and switchgear. They change voltage levels and let operators isolate sections. For this page it is enough to know that they pass power along and can be taken out of service.

## What 2N means

Engineers write N for the amount of equipment you need. 2N means you build all of it twice. Two complete, independent paths from the grid to the computers, called A and B, and either one alone can carry everything. The loads are dual-cord: each plugs into both paths, like a laptop with two chargers on two different wall sockets.

The reference design is 2N. Two paths of 2 MW each, two loads of 800 kW each, and 120 kWh of usable battery energy on each path. Normally the paths share the work, 800 kW each. Comfortable.

Redundancy has a quiet weakness, though. It protects you only while both copies exist. The moment one path is down for maintenance, you are running on a single path, and the design is temporarily as fragile as one with no redundancy at all. That is exactly when the reference scenario chooses to strike.

## Ten minutes, second by second

The composite scenario lasts ten minutes. In the live explorer it is listed as "PDU B maintenance, utility A loss, generator failure, and path B restoration". Here is the story it tells.

For the first minute, nothing happens. Both paths share the 1.6 MW of total demand.

Just after the one-minute mark, path B goes into planned maintenance. This is deliberate, the kind of work real facilities schedule all the time. Both loads move to path A, which now carries the full 1.6 MW by itself. Still fine. That is what 2N is for.

At the two-minute mark, path A loses its utility. The grid connection is gone, and the only healthy path just lost its normal source. UPS A takes over instantly and starts draining.

Fifteen seconds later, generator A was supposed to be running. The scenario declares that it failed to start. Now there is no grid on path A, no generator on path A, and path B is still open for maintenance. The battery is the only thing keeping the computers on, and it is emptying at 1.6 MW.

At 336 seconds the battery crosses its 20% mark and the model raises a low-energy alarm. At 390 seconds it reaches zero. Every watt of demand becomes unserved. The room, in effect, goes dark.

At 420 seconds the maintenance on path B ends, and at 422 seconds the loads are transferred back to it. Service returns. The outage lasted 32 seconds.

## The battery clock

The number I care most about in that story is 390. It is not arbitrary. UPS A holds 120 kWh of usable energy and is drained at 1.6 MW, and division tells you how long that lasts: 270 seconds. The drain started at second 120, so the battery dies at second 390. The docs call this stretch the autonomy window, the time the battery can carry the load alone.

Why does the exact second matter? Because the whole outcome is a race between two clocks. One clock counts down the battery. The other counts up to the moment someone restores a path. In this scenario the battery loses the race by 32 seconds, and everything in the results table follows from those two timestamps. Move the restoration two minutes earlier and there is no outage at all. Shrink the battery and the outage grows. The simulator exists to make that race explicit and checkable instead of a gut feeling.

## What the numbers mean, and what they do not

The explorer shows four headline numbers for this run.

Demanded energy, 266.7 kWh, is everything the loads asked for over the ten minutes. Served energy, 252.4 kWh, is what they actually received. Unserved energy, 14.2 kWh, is the gap, which is exactly 32 seconds of 1.6 MW. The service ratio, 94.7%, is simply served divided by demanded.

Now the important caveat. That 94.7% describes this artificial ten-minute story and nothing else. It is not the availability of a facility. It is not an SLA, an uptime figure, or a prediction of how often outages happen, because the scenario does not know how often any of these events occur in reality. I fed the model one deliberately bad ten minutes, and it told me exactly how bad. A different scenario produces a different ratio. Comparing designs under the same scenario is meaningful. Quoting the ratio as a quality grade for a data center is not.

## Why the same result hash matters

Every run ends with a hash, a short fingerprint computed from the full result. The rule the engine commits to is simple: same inputs and same model version, same hash, always.

That buys a reviewer something concrete. You do not have to trust my table. You can run the scenario on your own machine, or press "Replay and verify" in the explorer, and check that your fingerprint matches mine. If I had fudged a number, or if the result depended on my operating system or on the order some directory listing happened to return, the hashes would not match. Determinism turns "believe me" into "check me". The hand calculations in [REFERENCE_SCENARIO.md](REFERENCE_SCENARIO.md) let you verify the arithmetic with a pocket calculator too.

## What this tool does not do

Three honest sentences. The simulator does no electrical physics: no voltages, no currents, no power-flow equations, only the bookkeeping of whether enough capacity connects sources to loads. It cannot tell you whether real equipment would trip, arc, or survive any of these events, so it is useless for protection, safety, or compliance work. And nothing here touches a live system: every topology, rating, and failure in this repository is hand-authored fiction, built so the reasoning can be public without any real site being in it.

If this page made sense, the [README](../README.md) and the [reference scenario](REFERENCE_SCENARIO.md) are the natural next steps.
