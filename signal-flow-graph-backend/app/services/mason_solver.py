from __future__ import annotations
from typing import Any
import sympy as sp

from .graph_builder import GraphBuilder
from .path_finder   import PathFinder
from .loop_finder   import LoopFinder


class MasonSolver:


    def __init__(self, builder: GraphBuilder) -> None:
        self.builder     = builder
        self.path_finder = PathFinder(builder)
        self.loop_finder = LoopFinder(builder)
        self._result: dict | None = None

    # ── public API ────────────────────────────────────────────────────────────

    def solve(self) -> dict:
        if self._result is not None:
            return self._result

        paths = self.path_finder.find_forward_paths()
        delta = self._compute_delta(self.loop_finder)
        delta_k_list = self._compute_delta_k(paths)

        # Calculate the numerator separately to access it below
        numerator = sp.Integer(0)
        for path, dk in zip(paths, delta_k_list):
            numerator += path["gain"] * dk

        # Compute the actual transfer function object
        tf = numerator / delta

        self._result = {
            "forward_paths": self.path_finder.summary(),
            "loops": self.loop_finder.summary_loops(),
            "non_touching_groups": self.loop_finder.summary_non_touching(),
            # No sp.simplify() — preserves the 1 - L1 - L2 + ... Mason structure
            "delta": str(delta),
            "delta_latex": sp.latex(delta),
            "delta_k": [
                {
                    "path_index": i + 1,
                    "value": str(dk),
                    "latex": sp.latex(dk),
                }
                for i, dk in enumerate(delta_k_list)
            ],
            "transfer_function": f"({numerator}) / ({delta})",
            "transfer_function_latex": sp.latex(tf),
        }
        return self._result

    # ── private helpers ───────────────────────────────────────────────────────

    def _compute_delta(self, loop_finder: LoopFinder) -> sp.Expr:
        """
        Δ = 1 − L₁ + L₂ − L₃ + …

        L_n = sum of products of gains of all *n* mutually non-touching loops.
        """
        groups = loop_finder.find_non_touching_groups()
        delta  = sp.Integer(1)

        for size in sorted(groups.keys()):
            sign = sp.Integer((-1) ** size)
            for g in groups[size]:
                delta += sign * g["gain"]

        return delta

    def _compute_delta_k(self, paths: list[dict]) -> list[sp.Expr]:
        """
        For each forward path k, compute Δ_k:
            Δ_k = Δ of the graph after removing all nodes touching path k.
        We achieve this by creating a *sub-loop-finder* that only considers
        loops that do not touch path k's nodes.
        """
        delta_k_list: list[sp.Expr] = []

        for path in paths:
            path_node_set = set(path["nodes"])
            non_touching  = self.loop_finder.loops_not_touching_path(path_node_set)
            dk            = self._delta_from_loops(non_touching)
            delta_k_list.append(dk)

        return delta_k_list

    def _delta_from_loops(self, loops: list[dict]) -> sp.Expr:
        """
        Build Δ from a *subset* of loops (used for cofactor Δ_k).
        We need to find non-touching combinations within this subset.
        """
        n     = len(loops)
        delta = sp.Integer(1)

        if n == 0:
            return delta

        # sum of individual loop gains  (L1)
        for lp in loops:
            delta -= lp["gain"]

        # pairs, triples, … of non-touching loops within the subset
        from itertools import combinations as _comb

        for size in range(2, n + 1):
            sign = sp.Integer((-1) ** size)
            for combo in _comb(range(n), size):
                if self._subset_non_touching(combo, loops):
                    product = sp.Integer(1)
                    for idx in combo:
                        product *= loops[idx]["gain"]
                    delta += sign * product

        return delta

    @staticmethod
    def _subset_non_touching(combo: tuple[int, ...], loops: list[dict]) -> bool:
        """Check mutual non-touching within a subset of loops."""
        seen: set[Any] = set()
        for idx in combo:
            nodes = set(loops[idx]["nodes"])
            if nodes & seen:
                return False
            seen |= nodes
        return True

    def _compute_tf(
        self,
        paths: list[dict],
        delta: sp.Expr,
        delta_k_list: list[sp.Expr],
    ) -> sp.Expr:
        """T = Σ (P_k · Δ_k) / Δ"""
        numerator = sp.Integer(0)
        for path, dk in zip(paths, delta_k_list):
            numerator += path["gain"] * dk

        if delta == 0:
            raise ZeroDivisionError("Graph determinant Δ = 0; system is degenerate.")

        return numerator / delta