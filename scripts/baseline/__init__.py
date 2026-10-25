"""Source-agnostic price-baseline pipeline.

One loader per source (sources/), each returning listings in the common
schema (schema.py); shared cleaning (cleaning.py); a time adjustment between
sources (adjust.py); and the coverage report (coverage.py). build.py runs it.

    nlp-service/.venv/Scripts/python -m scripts.baseline.build

Nothing here touches the database or the network.
"""
