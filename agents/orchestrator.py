"""Agent Orchestrator: coordinates multi-agent workflows."""

import asyncio
import logging

from agents.matcher import MatcherAgent
from agents.pricer import PricerAgent
from agents.risk import RiskAgent

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """Coordinates multiple AI agents for freight operations."""

    def __init__(self):
        self.matcher = MatcherAgent()
        self.pricer = PricerAgent()
        self.risk = RiskAgent()

    async def process_new_cargo(
        self, cargo_data: dict, available_vehicles: list[dict]
    ) -> dict:
        """Full pipeline when a new cargo is posted:
        1. Estimate fair price (Pricer)
        2. Find matching carriers (Matcher)
        3. Assess risk for top matches (Risk)
        All run concurrently where possible.
        """
        # Step 1 & 2 run in parallel
        price_task = self.pricer.estimate_price(cargo_data)
        match_task = self.matcher.find_matches(cargo_data, available_vehicles)

        price_result, match_result = await asyncio.gather(
            price_task, match_task, return_exceptions=True
        )

        if isinstance(price_result, Exception):
            logger.error("Pricer failed: %s", price_result)
            price_result = {"error": str(price_result)}
        if isinstance(match_result, Exception):
            logger.error("Matcher failed: %s", match_result)
            match_result = {"matches": [], "error": str(match_result)}

        # Step 3: assess risk for top matches (parallel)
        matches = match_result.get("matches", [])
        risk_results = {}
        if matches:
            risk_tasks = []
            for m in matches[:5]:
                carrier_data = {
                    "full_name": m.get("carrier_name", "N/A"),
                    "rating": m.get("owner_rating", 0),
                    "total_deals": m.get("total_deals", 0),
                    "is_verified": m.get("is_verified", False),
                    "created_at": m.get("created_at", "N/A"),
                }
                risk_tasks.append(
                    self.risk.assess_carrier(carrier_data, reviews=[])
                )

            results = await asyncio.gather(*risk_tasks, return_exceptions=True)
            for i, result in enumerate(results):
                vid = matches[i].get("vehicle_id", i)
                if isinstance(result, Exception):
                    risk_results[vid] = {"error": str(result)}
                else:
                    risk_results[vid] = result

        return {
            "pricing": price_result,
            "matches": match_result,
            "risk_assessments": risk_results,
        }

    async def process_carrier_available(
        self, vehicle_data: dict, active_cargos: list[dict]
    ) -> dict:
        """Proactive: carrier declares availability → find matching cargos."""
        return await self.matcher.suggest_proactive(vehicle_data, active_cargos)

    async def assess_deal_risk(
        self, carrier_data: dict, cargo_data: dict, proposed_price: float
    ) -> dict:
        """Assess risk before confirming a deal."""
        return await self.risk.assess_deal(carrier_data, cargo_data, proposed_price)
