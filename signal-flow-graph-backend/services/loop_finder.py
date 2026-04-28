"""
loop_finder.py
--------------
Finds:
  1. All individual loops (simple cycles) in the SFG.
  2. All combinations of 2, 3, … non-touching loops (loops that share no node).

A *loop* is a closed path that returns to its starting node, visiting each
intermediate node at most once, and has a non-trivial gain (length ≥ 1 branch).

Result for each loop:
    {
        "nodes"    : [n1, n2, …, n1],   # first == last
        "gain"     : sympy expression,
        "gain_str" : str,
    }

Non-touching groups:
    {
        "loops"    : [loop_index, …],   # 0-based indices into loop list
        "gain"     : sympy product of their gains,
        "gain_str" : str,
    }
"""

from __future__ import annotations
from itertools import combinations
from typing import Any
import sympy as sp

from .graph_builder import GraphBuilder


class LoopFinder:
    """
    Enumerates every simple cycle and groups of mutually non-touching loops.

    Parameters
    ----------
    builder : GraphBuilder
    """

    def __init__(self, builder: GraphBuilder) -> None:
        self.builder = builder
        self._loops: list[dict] | None = None
        self._non_touching: dict[int, list[dict]] | None = None   # key = group size

    # ── public API ────────────────────────────────────────────────────────────

    def find_loops(self) -> list[dict]:
        """
        Return every individual loop (simple cycle) in the graph.
        Loops are deduplicated (rotations of the same cycle count once).
        """
        if self._loops is not None:
            return self._loops

        adj   = self.builder.get_adjacency()
        nodes = self.builder.get_nodes()

        found_signatures: set[frozenset] = set()
        loops: list[dict] = []

        for start in nodes:
            self._dfs_cycles(start, start, [start], sp.Integer(1), adj, found_signatures, loops)

        self._loops = loops
        return loops

    def find_non_touching_groups(self) -> dict[int, list[dict]]:
        """
        Return all groups of mutually non-touching loops, keyed by group size.

        Two loops are *non-touching* when they share NO node.
        Groups of size 1 are the individual loops themselves (always returned).
        """
        if self._non_touching is not None:
            return self._non_touching

        loops = self.find_loops()
        n     = len(loops)
        result: dict[int, list[dict]] = {}

        # size-1 groups
        result[1] = [
            {
                "loops"    : [i],
                "gain"     : loops[i]["gain"],
                "gain_str" : loops[i]["gain_str"],
            }
            for i in range(n)
        ]

        # sizes 2 … n
        for size in range(2, n + 1):
            groups: list[dict] = []
            for combo in combinations(range(n), size):
                if self._are_non_touching(combo, loops):
                    combined_gain = sp.Integer(1)
                    for idx in combo:
                        combined_gain *= loops[idx]["gain"]
                    groups.append(
                        {
                            "loops"    : list(combo),
                            "gain"     : combined_gain,
                            "gain_str" : str(sp.simplify(combined_gain)),
                        }
                    )
            if groups:
                result[size] = groups

        self._non_touching = result
        return result

    def loops_not_touching_path(self, path_nodes: set[Any]) -> list[dict]:
        """
        Return all individual loops that share NO node with *path_nodes*.
        Used by MasonSolver to compute each Δ_k (cofactor).
        """
        loops = self.find_loops()
        return [
            lp for lp in loops
            if not (set(lp["nodes"]) & path_nodes)
        ]

    def summary_loops(self) -> list[dict]:
        return [
            {
                "index"    : i + 1,
                "nodes"    : lp["nodes"],
                "gain"     : lp["gain_str"],
            }
            for i, lp in enumerate(self.find_loops())
        ]

    def summary_non_touching(self) -> list[dict]:
        groups = self.find_non_touching_groups()
        out: list[dict] = []
        for size in sorted(groups.keys()):
            if size < 2:
                continue
            for g in groups[size]:
                out.append(
                    {
                        "size"     : size,
                        "loop_indices": [i + 1 for i in g["loops"]],   # 1-based
                        "gain"     : g["gain_str"],
                    }
                )
        return out

    # ── private helpers ───────────────────────────────────────────────────────

    def _dfs_cycles(
        self,
        start: Any,
        current: Any,
        path: list[Any],
        gain: sp.Expr,
        adj: dict,
        found: set[frozenset],
        loops: list[dict],
    ) -> None:
        """Recursive DFS that collects all simple cycles starting from *start*."""
        for neighbor, branch_gain in adj.get(current, {}).items():
            if neighbor == start and len(path) > 1:
                # Closed cycle found
                cycle_nodes = path[:]          # excludes repeated start
                sig = frozenset(cycle_nodes)   # rotation-invariant signature

                if sig not in found:
                    found.add(sig)
                    cycle_gain = gain * branch_gain
                    loops.append(
                        {
                            "nodes"    : cycle_nodes + [start],  # close the loop
                            "gain"     : cycle_gain,
                            "gain_str" : str(sp.simplify(cycle_gain)),
                        }
                    )

            elif neighbor not in path:
                # Continue DFS only if we haven't visited this node yet
                self._dfs_cycles(
                    start,
                    neighbor,
                    path + [neighbor],
                    gain * branch_gain,
                    adj,
                    found,
                    loops,
                )

    @staticmethod
    def _are_non_touching(combo: tuple[int, ...], loops: list[dict]) -> bool:
        """Return True iff all loops in *combo* share no node with each other."""
        # Build union of node sets one by one; any intersection → touching
        seen: set[Any] = set()
        for idx in combo:
            loop_nodes = set(loops[idx]["nodes"])
            if loop_nodes & seen:
                return False
            seen |= loop_nodes
        return True