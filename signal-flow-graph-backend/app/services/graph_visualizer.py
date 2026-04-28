"""
graph_visualizer.py
--------------------
Computes (x, y) layout coordinates for every node so the Angular front-end
can render the Signal Flow Graph on a canvas / SVG without needing an
external graph-layout library on the client side.

Strategy  (left-to-right layered layout)
-----------------------------------------
1. BFS from the source node assigns each node a *column* (layer).
2. Within each column, nodes are distributed evenly on the y-axis.
3. A simple loop-back arc is added for self-loops or back-edges.

The returned payload is intentionally plain JSON (no sympy objects).

Output schema
-------------
{
    "nodes": [
        {"id": <node>, "x": float, "y": float, "label": str},
        ...
    ],
    "edges": [
        {
            "from": <node>, "to": <node>,
            "gain": str,
            "is_self_loop": bool,
            "is_back_edge": bool,
            "control_x": float | None,   # for quadratic bezier curves
            "control_y": float | None,
        },
        ...
    ],
}
"""

from __future__ import annotations
from collections import defaultdict, deque
from typing import Any
import sympy as sp

from .graph_builder import GraphBuilder


# ── tuneable layout constants ─────────────────────────────────────────────────
CANVAS_WIDTH  = 900     # px
CANVAS_HEIGHT = 500     # px
H_MARGIN      = 80      # px  – left / right padding
V_MARGIN      = 80      # px  – top / bottom padding


class GraphVisualizer:
    """
    Computes display coordinates and edge metadata for the SFG.

    Parameters
    ----------
    builder : GraphBuilder
    """

    def __init__(self, builder: GraphBuilder) -> None:
        self.builder = builder

    # ── public API ────────────────────────────────────────────────────────────

    def layout(self) -> dict:
        """Return the full layout dict ready for JSON serialisation."""
        adj    = self.builder.get_adjacency()
        nodes  = self.builder.get_nodes()
        source = self.builder.get_source()

        # 1. Assign layers via BFS
        layer: dict[Any, int] = self._bfs_layers(source, adj, nodes)

        # 2. Group nodes by layer
        layers_map: dict[int, list[Any]] = defaultdict(list)
        for n, l in layer.items():
            layers_map[l].append(n)

        # Sort nodes within each layer for deterministic output
        for l in layers_map:
            layers_map[l].sort(key=str)

        num_layers = max(layers_map.keys()) + 1

        # 3. Compute pixel positions
        x_step = (CANVAS_WIDTH  - 2 * H_MARGIN) / max(num_layers - 1, 1)
        pos: dict[Any, tuple[float, float]] = {}

        for l, layer_nodes in layers_map.items():
            x = H_MARGIN + l * x_step
            count = len(layer_nodes)
            y_step = (CANVAS_HEIGHT - 2 * V_MARGIN) / max(count, 1)
            for i, n in enumerate(layer_nodes):
                y = V_MARGIN + i * y_step + y_step / 2
                pos[n] = (round(x, 2), round(y, 2))

        # 4. Build node list
        node_list = [
            {
                "id"    : n,
                "x"     : pos[n][0],
                "y"     : pos[n][1],
                "label" : str(n),
            }
            for n in nodes
        ]

        # 5. Build edge list
        edge_list = []
        for u, neighbors in adj.items():
            for v, gain in neighbors.items():
                is_self = u == v
                u_layer = layer.get(u, 0)
                v_layer = layer.get(v, 0)
                is_back = (not is_self) and (v_layer <= u_layer)

                cx, cy = self._control_point(pos, u, v, is_self, is_back)

                edge_list.append(
                    {
                        "from"        : u,
                        "to"          : v,
                        "gain"        : str(sp.simplify(gain)),
                        "is_self_loop": is_self,
                        "is_back_edge": is_back,
                        "control_x"   : cx,
                        "control_y"   : cy,
                    }
                )

        return {"nodes": node_list, "edges": edge_list}

    # ── private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _bfs_layers(
        source: Any,
        adj: dict[Any, dict[Any, Any]],
        all_nodes: list[Any],
    ) -> dict[Any, int]:
        """
        Assign a *column index* (0-based) to each node via BFS from source.
        Nodes unreachable from source are placed in the last column.
        """
        layer: dict[Any, int] = {source: 0}
        queue = deque([source])

        while queue:
            node = queue.popleft()
            for neighbor in adj.get(node, {}):
                if neighbor not in layer:
                    layer[neighbor] = layer[node] + 1
                    queue.append(neighbor)

        # Assign unreachable nodes to last layer
        max_layer = max(layer.values(), default=0)
        for n in all_nodes:
            if n not in layer:
                max_layer += 1
                layer[n] = max_layer

        return layer

    @staticmethod
    def _control_point(
        pos: dict[Any, tuple[float, float]],
        u: Any,
        v: Any,
        is_self: bool,
        is_back: bool,
    ) -> tuple[float | None, float | None]:
        """
        Compute a quadratic bezier control point for curved edges.
        Straight forward edges don't need one (returns None, None).
        """
        if not (is_self or is_back):
            return None, None   # straight arrow

        ux, uy = pos.get(u, (0, 0))
        vx, vy = pos.get(v, (0, 0))

        if is_self:
            # Loop above the node
            return round(ux, 2), round(uy - 80, 2)

        # Back edge → arc curving above the straight line
        mid_x = (ux + vx) / 2
        mid_y = (uy + vy) / 2 - 80   # lift the arc upward

        return round(mid_x, 2), round(mid_y, 2)