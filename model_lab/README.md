# Model Lab

This directory contains experimental ML and strategy modeling work for the land intelligence platform.

The goal of the model lab is to explore:

- layout strategy models
- road graph generation
- layout ranking
- training datasets from simulation

## Safety Rules

The model lab must NEVER modify production code.

Allowed:

    model_lab → backend imports

Not allowed:

    backend → model_lab imports

## Architecture

    parcel
    ↓
    strategy model
    ↓
    layout engine
    ↓
    constraint solver
    ↓
    layout scoring
    ↓
    training dataset

## Output Data

Each simulation produces:

- parcel geometry
- layout strategy
- road graph
- lot layout
- layout score

These become training data for future models.
