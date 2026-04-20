"""Harness layer: orchestration entry points are exposed via submodules.

Importers should reach for the concrete module (e.g. ``evo.harness.pipeline``)
to avoid pulling the full agent graph into leaf paths like
``evo.harness.react``.
"""
