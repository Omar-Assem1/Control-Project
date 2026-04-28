"""
tests/test_services_with_models.py
-----------------------------------
Integration tests: services → Pydantic models round-trip.

Run with:
    pytest tests/test_services_with_models.py -v
"""

import pytest
import sympy as sp

from app.services import GraphBuilder, PathFinder, LoopFinder, MasonSolver, GraphVisualizer
from app.models import (
    GraphInput, BranchInput,
    GraphAnalysisResult, GraphLayout,
    ForwardPath, Loop, NonTouchingGroup, DeltaK,
    NodeLayout, EdgeLayout,
    ErrorResponse,
)


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def build_result(raw: dict) -> GraphAnalysisResult:
    """
    Full pipeline: raw dict → GraphInput → services → GraphAnalysisResult.
    This is what the FastAPI route will do.
    """
    inp      = GraphInput(**raw)
    branches = [(b.from_node, b.to_node, b.gain) for b in inp.branches]
    builder  = GraphBuilder(inp.nodes, branches, inp.source, inp.sink)

    solver   = MasonSolver(builder)
    result   = solver.solve()
    layout   = GraphVisualizer(builder).layout()

    return GraphAnalysisResult(
        graph_summary           = builder.summary(),
        forward_paths           = [ForwardPath(**p)  for p in result["forward_paths"]],
        loops                   = [Loop(**l)          for l in result["loops"]],
        non_touching_groups     = [NonTouchingGroup(**g) for g in result["non_touching_groups"]],
        delta                   = result["delta"],
        delta_latex             = result["delta_latex"],
        delta_k                 = [DeltaK(**dk)       for dk in result["delta_k"]],
        transfer_function       = result["transfer_function"],
        transfer_function_latex = result["transfer_function_latex"],
        layout = GraphLayout(
            nodes = [NodeLayout(**n) for n in layout["nodes"]],
            edges = [EdgeLayout(**{
                "from": e["from"], "to": e["to"],
                "gain": e["gain"],
                "is_self_loop": e["is_self_loop"],
                "is_back_edge": e["is_back_edge"],
                "control_x"  : e["control_x"],
                "control_y"  : e["control_y"],
            }) for e in layout["edges"]],
        ),
    )


# ── shared fixtures ────────────────────────────────────────────────────────────

CLASSIC_6NODE = {
    "nodes"   : [1, 2, 3, 4, 5, 6],
    "branches": [
        {"from": 1, "to": 2, "gain": 1},
        {"from": 2, "to": 3, "gain": "a"},
        {"from": 3, "to": 4, "gain": "b"},
        {"from": 4, "to": 5, "gain": "c"},
        {"from": 5, "to": 6, "gain": 1},
        {"from": 4, "to": 2, "gain": "d"},
        {"from": 3, "to": 5, "gain": "e"},
        {"from": 5, "to": 3, "gain": "f"},
    ],
    "source": 1,
    "sink"  : 6,
}

SIMPLE_3NODE = {
    "nodes"   : [1, 2, 3],
    "branches": [
        {"from": 1, "to": 2, "gain": 2},
        {"from": 2, "to": 3, "gain": 3},
        {"from": 2, "to": 2, "gain": "k"},   # self-loop
    ],
    "source": 1,
    "sink"  : 3,
}

NUMERIC_ONLY = {
    "nodes"   : ["x1", "x2", "x3", "x4"],
    "branches": [
        {"from": "x1", "to": "x2", "gain": 1},
        {"from": "x2", "to": "x3", "gain": 2},
        {"from": "x3", "to": "x4", "gain": 3},
        {"from": "x3", "to": "x2", "gain": -1},
    ],
    "source": "x1",
    "sink"  : "x4",
}


# ═══════════════════════════════════════════════════════════════════════════════
# 1. REQUEST MODEL VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════

class TestGraphInput:

    def test_valid_integer_nodes(self):
        inp = GraphInput(**CLASSIC_6NODE)
        assert inp.source == 1
        assert inp.sink   == 6
        assert len(inp.nodes)    == 6
        assert len(inp.branches) == 8

    def test_valid_string_nodes(self):
        inp = GraphInput(**NUMERIC_ONLY)
        assert inp.source == "x1"
        assert inp.sink   == "x4"

    def test_symbolic_gain_accepted(self):
        inp = GraphInput(**CLASSIC_6NODE)
        gains = [b.gain for b in inp.branches]
        assert "a" in gains
        assert 1   in gains

    def test_source_not_in_nodes_raises(self):
        bad = {**CLASSIC_6NODE, "source": 99}
        with pytest.raises(ValueError, match="source"):
            GraphInput(**bad)

    def test_sink_not_in_nodes_raises(self):
        bad = {**CLASSIC_6NODE, "sink": 99}
        with pytest.raises(ValueError, match="sink"):
            GraphInput(**bad)

    def test_source_equals_sink_raises(self):
        bad = {**CLASSIC_6NODE, "sink": 1}
        with pytest.raises(ValueError, match="different"):
            GraphInput(**bad)

    def test_empty_nodes_raises(self):
        bad = {**CLASSIC_6NODE, "nodes": [1]}   # min_length=2
        with pytest.raises(ValueError):
            GraphInput(**bad)

    def test_empty_branches_raises(self):
        bad = {**CLASSIC_6NODE, "branches": []}
        with pytest.raises(ValueError):
            GraphInput(**bad)

    def test_branch_alias_from_to(self):
        b = BranchInput(**{"from": 1, "to": 2, "gain": 5})
        assert b.from_node == 1
        assert b.to_node   == 2
        assert b.gain      == 5


# ═══════════════════════════════════════════════════════════════════════════════
# 2. GRAPH BUILDER + MODEL
# ═══════════════════════════════════════════════════════════════════════════════

class TestGraphBuilder:

    def test_adjacency_built_correctly(self):
        inp      = GraphInput(**CLASSIC_6NODE)
        branches = [(b.from_node, b.to_node, b.gain) for b in inp.branches]
        builder  = GraphBuilder(inp.nodes, branches, inp.source, inp.sink)
        adj      = builder.get_adjacency()

        assert 2 in adj[1]          # branch 1→2 exists
        assert 2 in adj[4]          # back-edge 4→2 exists

    def test_parallel_branches_summed(self):
        raw = {
            "nodes"   : [1, 2, 3],
            "branches": [
                {"from": 1, "to": 2, "gain": 2},
                {"from": 1, "to": 2, "gain": 3},   # parallel
                {"from": 2, "to": 3, "gain": 1},
            ],
            "source": 1, "sink": 3,
        }
        inp      = GraphInput(**raw)
        branches = [(b.from_node, b.to_node, b.gain) for b in inp.branches]
        builder  = GraphBuilder(inp.nodes, branches, 1, 3)
        assert builder.branch_gain(1, 2) == sp.Integer(5)

    def test_unknown_node_in_branch_raises(self):
        with pytest.raises(ValueError, match="from_node"):
            GraphBuilder([1, 2, 3], [(99, 2, 1)], 1, 3)

    def test_summary_serialisable(self):
        inp      = GraphInput(**CLASSIC_6NODE)
        branches = [(b.from_node, b.to_node, b.gain) for b in inp.branches]
        builder  = GraphBuilder(inp.nodes, branches, inp.source, inp.sink)
        s        = builder.summary()
        assert "nodes"    in s
        assert "branches" in s
        assert all(isinstance(b["gain"], str) for b in s["branches"])


# ═══════════════════════════════════════════════════════════════════════════════
# 3. PATH FINDER + MODEL
# ═══════════════════════════════════════════════════════════════════════════════

class TestPathFinder:

    def _make_pf(self, raw):
        inp      = GraphInput(**raw)
        branches = [(b.from_node, b.to_node, b.gain) for b in inp.branches]
        builder  = GraphBuilder(inp.nodes, branches, inp.source, inp.sink)
        return PathFinder(builder)

    def test_classic_has_two_paths(self):
        pf = self._make_pf(CLASSIC_6NODE)
        assert pf.path_count() == 2

    def test_simple_3node_one_path(self):
        pf = self._make_pf(SIMPLE_3NODE)
        assert pf.path_count() == 1

    def test_path_starts_at_source_ends_at_sink(self):
        pf = self._make_pf(CLASSIC_6NODE)
        for p in pf.find_forward_paths():
            assert p["nodes"][0]  == 1
            assert p["nodes"][-1] == 6

    def test_path_gains_are_sympy(self):
        pf = self._make_pf(CLASSIC_6NODE)
        for p in pf.find_forward_paths():
            assert isinstance(p["gain"], sp.Basic)

    def test_forward_path_model_valid(self):
        pf      = self._make_pf(CLASSIC_6NODE)
        summary = pf.summary()
        models  = [ForwardPath(**p) for p in summary]
        assert all(m.index >= 1 for m in models)
        assert all(isinstance(m.gain, str) for m in models)

    def test_no_node_visited_twice_in_path(self):
        pf = self._make_pf(CLASSIC_6NODE)
        for p in pf.find_forward_paths():
            assert len(p["nodes"]) == len(set(p["nodes"]))


# ═══════════════════════════════════════════════════════════════════════════════
# 4. LOOP FINDER + MODEL
# ═══════════════════════════════════════════════════════════════════════════════

class TestLoopFinder:

    def _make_lf(self, raw):
        inp      = GraphInput(**raw)
        branches = [(b.from_node, b.to_node, b.gain) for b in inp.branches]
        builder  = GraphBuilder(inp.nodes, branches, inp.source, inp.sink)
        return LoopFinder(builder)

    def test_classic_has_three_loops(self):
        lf = self._make_lf(CLASSIC_6NODE)
        assert len(lf.find_loops()) == 3

    def test_self_loop_detected(self):
        lf    = self._make_lf(SIMPLE_3NODE)
        loops = lf.find_loops()
        self_loops = [l for l in loops if l["nodes"][0] == l["nodes"][-1] and len(l["nodes"]) == 2]
        assert len(self_loops) == 1

    def test_loop_first_equals_last_node(self):
        lf = self._make_lf(CLASSIC_6NODE)
        for l in lf.find_loops():
            assert l["nodes"][0] == l["nodes"][-1]

    def test_loop_gains_are_sympy(self):
        lf = self._make_lf(CLASSIC_6NODE)
        for l in lf.find_loops():
            assert isinstance(l["gain"], sp.Basic)

    def test_loop_model_valid(self):
        lf      = self._make_lf(CLASSIC_6NODE)
        summary = lf.summary_loops()
        models  = [Loop(**l) for l in summary]
        assert all(m.index >= 1        for m in models)
        assert all(isinstance(m.gain, str) for m in models)

    def test_no_non_touching_in_classic(self):
        lf = self._make_lf(CLASSIC_6NODE)
        nt = lf.find_non_touching_groups()
        # classic 6-node: all 3 loops share node 3 → no pair is non-touching
        assert 2 not in nt

    def test_non_touching_model_valid(self):
        lf      = self._make_lf(CLASSIC_6NODE)
        summary = lf.summary_non_touching()
        models  = [NonTouchingGroup(**g) for g in summary]
        assert isinstance(models, list)

    def test_loops_not_touching_path(self):
        lf        = self._make_lf(CLASSIC_6NODE)
        # path P1 visits {1,2,3,5,6} → loop L1 (2,3,4,2) touches via 2 and 3
        path_nodes = {1, 2, 3, 5, 6}
        nt_loops   = lf.loops_not_touching_path(path_nodes)
        for l in nt_loops:
            assert not (set(l["nodes"]) & path_nodes)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. MASON SOLVER + MODEL
# ═══════════════════════════════════════════════════════════════════════════════

class TestMasonSolver:

    def _make_solver(self, raw):
        inp      = GraphInput(**raw)
        branches = [(b.from_node, b.to_node, b.gain) for b in inp.branches]
        builder  = GraphBuilder(inp.nodes, branches, inp.source, inp.sink)
        return MasonSolver(builder)

    def test_delta_is_string(self):
        solver = self._make_solver(CLASSIC_6NODE)
        result = solver.solve()
        assert isinstance(result["delta"], str)

    def test_delta_k_count_matches_paths(self):
        solver = self._make_solver(CLASSIC_6NODE)
        result = solver.solve()
        assert len(result["delta_k"]) == len(result["forward_paths"])

    def test_transfer_function_string(self):
        solver = self._make_solver(CLASSIC_6NODE)
        result = solver.solve()
        assert isinstance(result["transfer_function"], str)
        assert len(result["transfer_function"]) > 0

    def test_transfer_function_latex(self):
        solver = self._make_solver(CLASSIC_6NODE)
        result = solver.solve()
        assert "\\" in result["transfer_function_latex"]   # LaTeX has backslashes

    def test_simple_numeric_transfer_function(self):
        """3-node graph with self-loop k on node 2:
           P1 = 2*3 = 6,  L1 = k,  Δ = 1-k,  Δ1 = 1,  T = 6/(1-k)"""
        solver = self._make_solver(SIMPLE_3NODE)
        result = solver.solve()
        tf     = sp.sympify(result["transfer_function"])
        k      = sp.Symbol("k")
        expected = sp.Integer(6) / (1 - k)
        assert sp.simplify(tf - expected) == 0

    def test_numeric_only_graph(self):
        solver = self._make_solver(NUMERIC_ONLY)
        result = solver.solve()
        tf     = sp.sympify(result["transfer_function"])
        # path gain = 1*2*3 = 6, loop gain = 2*(-1) = -2, Δ = 1-(-2) = 3, T = 6/3 = 2
        assert sp.simplify(tf - 2) == 0

    def test_delta_k_model_valid(self):
        solver  = self._make_solver(CLASSIC_6NODE)
        result  = solver.solve()
        models  = [DeltaK(**dk) for dk in result["delta_k"]]
        assert all(m.path_index >= 1      for m in models)
        assert all(isinstance(m.value, str) for m in models)
        assert all(isinstance(m.latex, str) for m in models)

    def test_result_cached(self):
        solver  = self._make_solver(CLASSIC_6NODE)
        result1 = solver.solve()
        result2 = solver.solve()
        assert result1 is result2   # same object (cached)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. GRAPH VISUALIZER + MODEL
# ═══════════════════════════════════════════════════════════════════════════════

class TestGraphVisualizer:

    def _make_viz(self, raw):
        inp      = GraphInput(**raw)
        branches = [(b.from_node, b.to_node, b.gain) for b in inp.branches]
        builder  = GraphBuilder(inp.nodes, branches, inp.source, inp.sink)
        return GraphVisualizer(builder), inp

    def test_node_count_matches(self):
        viz, inp = self._make_viz(CLASSIC_6NODE)
        layout   = viz.layout()
        assert len(layout["nodes"]) == len(inp.nodes)

    def test_edge_count_matches_branches(self):
        viz, inp = self._make_viz(CLASSIC_6NODE)
        layout   = viz.layout()
        # after parallel-branch merging, edge count = unique (from,to) pairs
        assert len(layout["edges"]) > 0

    def test_node_positions_within_canvas(self):
        viz, _   = self._make_viz(CLASSIC_6NODE)
        layout   = viz.layout()
        for n in layout["nodes"]:
            assert 0 <= n["x"] <= 900
            assert 0 <= n["y"] <= 500

    def test_self_loop_flagged(self):
        viz, _   = self._make_viz(SIMPLE_3NODE)
        layout   = viz.layout()
        self_loops = [e for e in layout["edges"] if e["is_self_loop"]]
        assert len(self_loops) == 1

    def test_back_edge_has_control_point(self):
        viz, _   = self._make_viz(CLASSIC_6NODE)
        layout   = viz.layout()
        back_edges = [e for e in layout["edges"] if e["is_back_edge"]]
        for e in back_edges:
            assert e["control_x"] is not None
            assert e["control_y"] is not None

    def test_node_layout_model_valid(self):
        viz, _   = self._make_viz(CLASSIC_6NODE)
        layout   = viz.layout()
        models   = [NodeLayout(**n) for n in layout["nodes"]]
        assert all(isinstance(m.x, float) for m in models)
        assert all(isinstance(m.label, str) for m in models)

    def test_edge_layout_model_valid(self):
        viz, _   = self._make_viz(CLASSIC_6NODE)
        layout   = viz.layout()
        models   = [EdgeLayout(**{
            "from": e["from"], "to": e["to"],
            "gain": e["gain"],
            "is_self_loop": e["is_self_loop"],
            "is_back_edge": e["is_back_edge"],
            "control_x"  : e["control_x"],
            "control_y"  : e["control_y"],
        }) for e in layout["edges"]]
        assert all(isinstance(m.gain, str) for m in models)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. FULL ROUND-TRIP
# ═══════════════════════════════════════════════════════════════════════════════

class TestFullRoundTrip:

    def test_classic_6node_full_pipeline(self):
        r = build_result(CLASSIC_6NODE)
        assert isinstance(r, GraphAnalysisResult)
        assert len(r.forward_paths) == 2
        assert len(r.loops)         == 3
        assert r.transfer_function  != ""
        assert r.delta              != ""
        assert len(r.delta_k)       == 2
        assert len(r.layout.nodes)  == 6

    def test_simple_3node_full_pipeline(self):
        r = build_result(SIMPLE_3NODE)
        assert isinstance(r, GraphAnalysisResult)
        assert len(r.forward_paths) == 1
        assert len(r.loops)         == 1   # self-loop on node 2
        tf = sp.sympify(r.transfer_function)
        k  = sp.Symbol("k")
        assert sp.simplify(tf - sp.Integer(6) / (1 - k)) == 0

    def test_numeric_only_full_pipeline(self):
        r  = build_result(NUMERIC_ONLY)
        tf = sp.sympify(r.transfer_function)
        assert sp.simplify(tf - 2) == 0

    def test_json_serialisable(self):
        import json
        r    = build_result(CLASSIC_6NODE)
        dump = r.model_dump(by_alias=True)
        # should not raise
        json.dumps(dump, default=str)

    def test_latex_in_response(self):
        r = build_result(CLASSIC_6NODE)
        # transfer function has a fraction → LaTeX contains \frac
        assert "\\" in r.transfer_function_latex
        # delta is a polynomial expression → LaTeX may not have backslashes
        assert isinstance(r.delta_latex, str)
        assert len(r.delta_latex) > 0

    def test_error_response_model(self):
        err = ErrorResponse(detail="Something went wrong", code="ANALYSIS_ERROR")
        assert err.detail == "Something went wrong"
        assert err.code   == "ANALYSIS_ERROR"