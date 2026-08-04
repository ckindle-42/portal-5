---
id: unit-tests-scripts-game-analyze
kind: mixed
title: "Game-challenge analyzer \u2014 static + render dual-layer scoring"
sources:
- type: code
  path: tests/scripts/game_challenge_analyze.py
  commit: dc13b2d5
last_generated_commit: dc13b2d5
claims: []
confidence: high
tags:
- authored-v1
- tests
- scripts
- bench
created_at: 1785796173.594443
updated_at: 1785796173.594443
---

The game-challenge analyzer scores the game tier in two layers: static
assertions parsed from the UAT results markdown's game_challenge rows, and a
Play@k render-check that loads each saved HTML artifact headless via Playwright
and asserts a clean boot (no console or page errors), a present canvas, and N
consecutive animation frames without an exception. The two layers combine into
a model-by-band matrix with no verdict.

## Why

A game challenge has two things that can fail independently: the *content*
assertions (does the page contain the expected elements and behaviour) and the
*render* contract (does the game actually run without throwing). The static
layer alone would certify a broken animation that happens to contain the right
text; the render-check alone would certify an empty page that boots cleanly.
Running both is the whole point — a band is only believable when its artifact
passes static assertions *and* survives headless execution. Loading the saved
HTML artifact rather than re-running generation also means the check is
reproducible after the fact: the artifact is the evidence.

## Interfaces

`main` parses the game_challenge rows, drives the headless Playwright
render-check per artifact, and emits the comparative matrix with both layers.
The static and render scores are kept separate in the output so a discrepancy
between "says the right things" and "runs cleanly" is visible rather than
averaged away.

## Gotchas

The render-check requires the saved HTML artifacts to exist on disk — a run
without `--artifacts` can score only the static layer, and that partial
matrix must not be read as a full verdict.
