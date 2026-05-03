"""
app/models/graph.py
--------------------
Pydantic v2 request and response models for the Signal Flow Graph API.

Request  : GraphInput          – nodes, branches, source, sink
Response : GraphAnalysisResult – everything the frontend needs
"""

from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field, model_validator


# ═══════════════════════════════════════════════════════════════════════════════
# REQUEST MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class BranchInput(BaseModel):
    """A single directed branch in the SFG."""

    from_node: Any = Field(
        ...,
        alias="from",
        description="Source node identifier (int or string).",
        examples=[1, "x1"],
    )
    to_node: Any = Field(
        ...,
        alias="to",
        description="Destination node identifier.",
        examples=[2, "x2"],
    )
    gain: Any = Field(
        ...,
        description=(
            "Branch gain. Accepts a number (int/float) or a symbolic string "
            "such as '2', '-0.5', 's', '1/s', '2*s+3'."
        ),
        examples=[2, -1, "1/s", "2*s+3"],
    )

    model_config = {"populate_by_name": True}


class GraphInput(BaseModel):
    """Full SFG definition sent by the client."""

    nodes: list[Any] = Field(
        ...,
        description="Ordered list of node identifiers.",
        examples=[[1, 2, 3, 4, 5, 6]],
        min_length=2,
    )
    branches: list[BranchInput] = Field(
        ...,
        description="List of directed branches with gains.",
        min_length=1,
    )
    source: Any = Field(
        ...,
        description="Input (source) node identifier.",
        examples=[1],
    )
    sink: Any = Field(
        ...,
        description="Output (sink) node identifier.",
        examples=[6],
    )

    @model_validator(mode="after")
    def validate_source_sink_in_nodes(self) -> "GraphInput":
        if self.source not in self.nodes:
            raise ValueError(f"source={self.source!r} is not in nodes list.")
        if self.sink not in self.nodes:
            raise ValueError(f"sink={self.sink!r} is not in nodes list.")
        if self.source == self.sink:
            raise ValueError("source and sink must be different nodes.")
        return self


# ═══════════════════════════════════════════════════════════════════════════════
# RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class BranchOutput(BaseModel):
    """A branch as returned in the graph layout / summary."""

    from_node: Any = Field(..., alias="from")
    to_node:   Any = Field(..., alias="to")
    gain:      str = Field(..., description="Gain as a simplified string.")

    model_config = {"populate_by_name": True}


class ForwardPath(BaseModel):
    """One forward path from source to sink."""

    index:    int       = Field(..., description="1-based path index.")
    nodes:    list[Any] = Field(..., description="Ordered list of nodes on the path.")
    gain:     str       = Field(..., description="Product of branch gains (string).")


class Loop(BaseModel):
    """One individual loop (simple cycle)."""

    index: int       = Field(..., description="1-based loop index.")
    nodes: list[Any] = Field(..., description="Nodes in the loop (first == last).")
    gain:  str       = Field(..., description="Product of branch gains (string).")


class NonTouchingGroup(BaseModel):
    """A set of mutually non-touching loops."""

    size:         int       = Field(..., description="Number of loops in this group.")
    loop_indices: list[int] = Field(..., description="1-based loop indices.")
    gain:         str       = Field(..., description="Product of all loop gains.")


class DeltaK(BaseModel):
    """Cofactor Δₖ for a single forward path."""

    path_index: int = Field(..., description="1-based forward-path index.")
    value:      str = Field(..., description="Δₖ value as a string.")
    latex:      str = Field(..., description="Δₖ value in LaTeX.")


# ── Layout models ──────────────────────────────────────────────────────────────

class NodeLayout(BaseModel):
    """Pixel position of a node for canvas rendering."""

    id:    Any   = Field(..., description="Node identifier.")
    x:     float = Field(..., description="Horizontal pixel position.")
    y:     float = Field(..., description="Vertical pixel position.")
    label: str   = Field(..., description="Display label.")


class EdgeLayout(BaseModel):
    """Edge rendering metadata."""

    from_node:    Any           = Field(..., alias="from")
    to_node:      Any           = Field(..., alias="to")
    gain:         str           = Field(..., description="Gain label for display.")
    is_self_loop: bool          = Field(False)
    is_back_edge: bool          = Field(False)
    control_x:    float | None  = Field(None, description="Bezier control point X.")
    control_y:    float | None  = Field(None, description="Bezier control point Y.")

    model_config = {"populate_by_name": True}


class GraphLayout(BaseModel):
    """Full canvas layout returned to the frontend."""

    nodes: list[NodeLayout]
    edges: list[EdgeLayout]


# ── Top-level response ─────────────────────────────────────────────────────────

class GraphAnalysisResult(BaseModel):
    """
    Complete analysis result returned by POST /api/graph/analyze.
    """

    # ── graph summary ──────────────────────────────────────────────────────
    graph_summary: dict = Field(
        ...,
        description="Raw node/branch summary from GraphBuilder.",
    )

    # ── Mason components ───────────────────────────────────────────────────
    forward_paths: list[ForwardPath] = Field(
        ...,
        description="All forward paths from source to sink.",
    )
    loops: list[Loop] = Field(
        ...,
        description="All individual loops (simple cycles).",
    )
    non_touching_groups: list[NonTouchingGroup] = Field(
        default_factory=list,
        description="All groups of mutually non-touching loops (size ≥ 2).",
    )

    # ── determinants ──────────────────────────────────────────────────────
    delta:       str       = Field(..., description="Graph determinant Δ.")
    delta_latex: str       = Field(..., description="Δ in LaTeX.")
    delta_k:     list[DeltaK] = Field(..., description="Cofactors Δₖ per path.")

    # ── result ────────────────────────────────────────────────────────────
    transfer_function:       str = Field(..., description="T(s) simplified.")
    transfer_function_latex: str = Field(..., description="T(s) in LaTeX.")

    # ── layout ────────────────────────────────────────────────────────────
    #layout: GraphLayout = Field(
    #    ...,
    #   description="Node coordinates and edge metadata for canvas rendering.",
    #)


# ═══════════════════════════════════════════════════════════════════════════════
# ERROR MODEL
# ═══════════════════════════════════════════════════════════════════════════════

class ErrorResponse(BaseModel):
    """Standard error envelope."""

    detail: str = Field(..., description="Human-readable error message.")
    code:   str = Field("ANALYSIS_ERROR", description="Machine-readable error code.")