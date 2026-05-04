
from __future__ import annotations
from typing import Any
import sympy as sp


# ── public types ──────────────────────────────────────────────────────────────

# A branch is a 3-tuple  (from_node, to_node, gain)
Branch = tuple[Any, Any, Any]


# ── helpers ───────────────────────────────────────────────────────────────────

def _to_sympy(value: Any) -> sp.Expr:
    """
    Accept int / float / str (e.g. 's', '1/s', '2*s+3') and return a
    sympy expression.  Plain numbers become sympy.Float / sympy.Integer.
    """
    if isinstance(value, (int, float)):
        return sp.sympify(value)
    if isinstance(value, str):
        return sp.sympify(value)
    if isinstance(value, sp.Basic):
        return value
    raise TypeError(f"Unsupported gain type: {type(value)!r}  value={value!r}")


# ── main class ────────────────────────────────────────────────────────────────

class GraphBuilder:


    def __init__(
        self,
        nodes: list[Any],
        branches: list[Branch],
        source: Any,
        sink: Any,
    ) -> None:
        self.nodes: list[Any] = list(nodes)
        self.raw_branches: list[Branch] = list(branches)
        self.source = source
        self.sink = sink

        # adjacency dict:  adj[u][v] = sympy gain
        self.adj: dict[Any, dict[Any, sp.Expr]] = {n: {} for n in nodes}

        self._build()

    # ── private ───────────────────────────────────────────────────────────────

    def _build(self) -> None:
        """Populate self.adj from raw_branches, converting gains to sympy."""
        for from_node, to_node, gain in self.raw_branches:
            if from_node not in self.adj:
                raise ValueError(
                    f"Branch references unknown from_node: {from_node!r}"
                )
            if to_node not in self.adj:
                raise ValueError(
                    f"Branch references unknown to_node: {to_node!r}"
                )

            sym_gain = _to_sympy(gain)

            # Multiple branches between the same pair of nodes → sum their gains
            if to_node in self.adj[from_node]:
                self.adj[from_node][to_node] += sym_gain
            else:
                self.adj[from_node][to_node] = sym_gain

    # ── public API ────────────────────────────────────────────────────────────

    def get_adjacency(self) -> dict[Any, dict[Any, sp.Expr]]:
        """Return the adjacency dict (read-only view is fine for callers)."""
        return self.adj

    def get_nodes(self) -> list[Any]:
        return self.nodes

    def get_source(self) -> Any:
        return self.source

    def get_sink(self) -> Any:
        return self.sink

    def branch_gain(self, from_node: Any, to_node: Any) -> sp.Expr:
        """Return the gain of edge (from_node → to_node), or 0 if absent."""
        return self.adj.get(from_node, {}).get(to_node, sp.Integer(0))

    def neighbors(self, node: Any) -> list[Any]:
        """Return all nodes reachable from *node* in one step."""
        return list(self.adj.get(node, {}).keys())

    def summary(self) -> dict:
        """Human-readable summary (useful for debugging / API responses)."""
        return {
            "nodes": self.nodes,
            "source": self.source,
            "sink": self.sink,
            "branches": [
                {
                    "from": u,
                    "to": v,
                    "gain": str(gain),
                }
                for u, neighbors in self.adj.items()
                for v, gain in neighbors.items()
            ],
        }