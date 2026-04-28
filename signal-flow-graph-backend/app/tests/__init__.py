"""
tests/
------
Test suite for the Signal Flow Graph backend.

Structure
---------
test_services_with_models.py  –  Integration tests covering the full pipeline:
                                  GraphInput → services → GraphAnalysisResult

    TestGraphInput        –  Pydantic request model validation
    TestGraphBuilder      –  Adjacency construction and branch handling
    TestPathFinder        –  Forward path enumeration (DFS)
    TestLoopFinder        –  Loop detection and non-touching groups
    TestMasonSolver       –  Mason's gain formula (Δ, Δₖ, T(s))
    TestGraphVisualizer   –  Canvas layout coordinates and edge metadata
    TestFullRoundTrip     –  End-to-end pipeline with exact TF verification

Run all tests
-------------
    pytest tests/ -v

Run with coverage
-----------------
    pytest tests/ -v --cov=app --cov-report=term-missing
"""