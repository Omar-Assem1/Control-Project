"""
app/api/graph_router.py
-----------------------
FastAPI router for the Signal Flow Graph analysis endpoint.

POST /api/graph/analyze
  - Accepts GraphInput (nodes, branches, source, sink)
  - Runs GraphBuilder → MasonSolver → GraphVisualizer
  - Returns GraphAnalysisResult
"""

from fastapi import APIRouter, HTTPException, status

from app.models import GraphInput, GraphAnalysisResult, ErrorResponse
from app.services import GraphBuilder, MasonSolver, GraphVisualizer

router = APIRouter(prefix="/api/graph", tags=["Signal Flow Graph"])


@router.post(
    "/analyze",
    response_model=GraphAnalysisResult,
    responses={
        422: {"model": ErrorResponse, "description": "Validation error"},
        400: {"model": ErrorResponse, "description": "Analysis error"},
    },
    summary="Analyze a Signal Flow Graph",
    description=(
        "Accepts a directed SFG definition and applies Mason's Gain Formula "
        "to return forward paths, loops, non-touching groups, the graph "
        "determinant Δ, cofactors Δₖ, and the simplified transfer function T(s)."
    ),
)
def analyze_graph(payload: GraphInput) -> GraphAnalysisResult:
    """
    Full pipeline:
      1. Build the adjacency graph (GraphBuilder)
      2. Apply Mason's formula  (MasonSolver)
      3. Compute canvas layout  (GraphVisualizer)
      4. Assemble and return    (GraphAnalysisResult)
    """
    try:
        # ── 1. Build graph ────────────────────────────────────────────────
        branches = [
            (b.from_node, b.to_node, b.gain)
            for b in payload.branches
        ]
        builder = GraphBuilder(
            nodes=payload.nodes,
            branches=branches,
            source=payload.source,
            sink=payload.sink,
        )

        # ── 2. Mason's formula ────────────────────────────────────────────
        solver = MasonSolver(builder)
        mason  = solver.solve()

        # ── 3. Layout ─────────────────────────────────────────────────────
        viz    = GraphVisualizer(builder)
        layout = viz.layout()

        # ── 4. Assemble response ──────────────────────────────────────────
        return GraphAnalysisResult(
            graph_summary=builder.summary(),
            forward_paths=mason["forward_paths"],
            loops=mason["loops"],
            non_touching_groups=mason["non_touching_groups"],
            delta=mason["delta"],
            delta_latex=mason["delta_latex"],
            delta_k=mason["delta_k"],
            transfer_function=mason["transfer_function"],
            transfer_function_latex=mason["transfer_function_latex"],
            layout=layout,
        )

    except (ValueError, ZeroDivisionError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error: {exc}",
        ) from exc
