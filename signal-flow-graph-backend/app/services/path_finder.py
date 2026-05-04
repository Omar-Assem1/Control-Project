

from __future__ import annotations
from typing import Any
import sympy as sp

from .graph_builder import GraphBuilder


class PathFinder:


    def __init__(self, builder: GraphBuilder) -> None:
        self.builder = builder
        self._paths: list[dict] | None = None   # cached after first call

    # ── public API ────────────────────────────────────────────────────────────

    def find_forward_paths(self) -> list[dict]:
        """
        Return a list of all forward paths from source → sink.
        Result is cached; repeated calls are free.
        """
        if self._paths is not None:
            return self._paths

        source = self.builder.get_source()
        sink   = self.builder.get_sink()
        adj    = self.builder.get_adjacency()

        results: list[dict] = []

        # Iterative DFS stack: each frame = (current_node, path_so_far, gain_so_far)
        stack: list[tuple[Any, list[Any], sp.Expr]] = [
            (source, [source], sp.Integer(1))
        ]

        while stack:
            node, path, gain = stack.pop()

            if node == sink:
                results.append(
                    {
                        "nodes"    : list(path),
                        "gain"     : gain,
                        "gain_str" : str(sp.simplify(gain)),
                    }
                )
                continue

            for neighbor, branch_gain in adj.get(node, {}).items():
                if neighbor not in path:          # no revisiting → acyclic path
                    stack.append(
                        (
                            neighbor,
                            path + [neighbor],
                            gain * branch_gain,
                        )
                    )

        self._paths = results
        return results

    def get_path_nodes_set(self, path_index: int) -> set[Any]:
        """Return the set of nodes visited by path number *path_index*."""
        paths = self.find_forward_paths()
        return set(paths[path_index]["nodes"])

    def path_count(self) -> int:
        return len(self.find_forward_paths())

    def summary(self) -> list[dict]:
        """Serialisable summary (gains as strings)."""
        return [
            {
                "index"   : i + 1,
                "nodes"   : p["nodes"],
                "gain"    : p["gain_str"],
            }
            for i, p in enumerate(self.find_forward_paths())
        ]