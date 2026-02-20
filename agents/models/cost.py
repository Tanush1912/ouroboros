"""Cost tracking models.

Every workflow run produces a CostSummary. Emitted to Logfire after completion.
"""

from pydantic import BaseModel, Field


class CostSummary(BaseModel):
    tokens_in: int = Field(description="Input tokens consumed")
    tokens_out: int = Field(description="Output tokens generated")
    cost_usd: float = Field(description="Estimated cost in USD based on Vertex AI pricing")
    model: str = Field(description="Model name used")
    task: str = Field(description="Task description (truncated to 200 chars)")
    workflow: str = Field(description="Workflow name (e.g. ralph_loop, entropy_gc)")
    duration_seconds: float = Field(description="Total wall-clock time for the workflow")
    iterations: int = Field(description="Number of implement/validate cycles")
    tool_calls: int = Field(description="Total tool calls across all nodes")


class RunMetrics(BaseModel):
    cost: CostSummary
    per_node_costs: dict[str, CostSummary] = Field(
        description="Cost breakdown by LangGraph node name"
    )
    highest_cost_node: str = Field(description="Node name with highest token spend")

    def total_cost_usd(self) -> float:
        return self.cost.cost_usd

    def summary_line(self) -> str:
        return (
            f"[{self.cost.workflow}] {self.cost.task[:60]} | "
            f"${self.cost.cost_usd:.4f} | "
            f"{self.cost.tokens_in}in/{self.cost.tokens_out}out | "
            f"{self.cost.iterations} iterations | "
            f"{self.cost.tool_calls} tool calls | "
            f"{self.cost.duration_seconds:.1f}s"
        )
