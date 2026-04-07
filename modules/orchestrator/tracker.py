"""TokenTracker — 에이전트별 토큰 사용량 추적 + 비용 계산."""

from __future__ import annotations

from modules.orchestrator.base import AgentContext, TokenUsage
from modules.orchestrator.config import MODELS, TOKEN_BUDGETS


class TokenTracker:
    """토큰 예산 관리 및 비용 추적."""

    def __init__(self, ctx: AgentContext):
        self._ctx = ctx

    def record(self, agent_name: str, model_id: str,
               input_tokens: int, output_tokens: int,
               cached_tokens: int = 0):
        spec = MODELS.get(model_id)
        cost = 0.0
        provider = "unknown"
        if spec:
            provider = spec.provider
            billable_input = max(input_tokens - cached_tokens, 0)
            cost = (spec.input_price_per_1m * billable_input / 1_000_000
                    + spec.output_price_per_1m * output_tokens / 1_000_000)

        usage = TokenUsage(
            agent=agent_name,
            model=model_id,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            cost_usd=cost,
        )
        self._ctx.record_tokens(usage)

    def agent_tokens_used(self, agent_name: str) -> int:
        return sum(u.input_tokens + u.output_tokens
                   for u in self._ctx.token_log if u.agent == agent_name)

    def total_tokens_used(self) -> int:
        return sum(u.input_tokens + u.output_tokens for u in self._ctx.token_log)

    def is_over_budget(self, agent_name: str) -> bool:
        budget = TOKEN_BUDGETS.get(agent_name, float('inf'))
        return self.agent_tokens_used(agent_name) > budget

    def is_request_over_budget(self) -> bool:
        total_budget = TOKEN_BUDGETS.get("total_request", float('inf'))
        return self.total_tokens_used() > total_budget

    def summary(self) -> dict:
        by_agent = self._ctx.cost_by_agent()
        return {
            "total_tokens": self.total_tokens_used(),
            "total_cost_usd": round(self._ctx.total_cost(), 4),
            "by_agent": {
                name: {
                    "tokens": self.agent_tokens_used(name),
                    "cost_usd": round(cost, 4),
                    "budget": TOKEN_BUDGETS.get(name, "unlimited"),
                }
                for name, cost in by_agent.items()
            },
            "calls": len(self._ctx.token_log),
        }
