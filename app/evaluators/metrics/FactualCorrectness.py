import asyncio

import numpy as np
import yaml
from pydantic import BaseModel, Field
from typing import List

from app.evaluators.metrics.Faithfulness import Faithfulness
from app.utils.constants import PROMPT_DIR
from app.utils.logger import get_logger
from app.utils.llm_utils import call_llm

with open(PROMPT_DIR, "r", encoding="utf-8") as f:
    _prompt_config = yaml.safe_load(f)

logger = get_logger(__name__)


class ClaimDecompositionOutput(BaseModel):
    claims: List[str] = Field(..., title="Decomposed Claims")


def fbeta_score(tp, fp, fn, beta=1.0):
    precision = tp / (tp + fp) if (tp + fp) else 0
    recall = tp / (tp + fn) if (tp + fn) else 0
    if precision == 0 and recall == 0:
        return 0.0
    beta_sq = beta ** 2
    return (1 + beta_sq) * (precision * recall) / (beta_sq * precision + recall)


class FactualCorrectness:
    """Factual-correctness metric (precision / recall / F1)."""

    name: str = "factual_correctness"
    required_fields: list[str] = ["reference", "response"]

    def __init__(self, beta: float = 1.0):
        self.beta = beta

    async def decompose_claims(self, user_input: str, split_level: str):
        logger.info("Starting decompose claims for FactualCorrectness")
        metric_prompt = _prompt_config["FactualCorrectness"]
        instruction = metric_prompt["Instruction"].strip("\n")
        messages = [{"role": "system", "content": instruction}]

        examples = metric_prompt.get("Examples", "")
        if examples:
            for key in examples:
                messages.append({"role": "user", "content": examples[key]["Input"].strip("\n")})
                messages.append(
                    {"role": "assistant", "content": examples[key]["Output"][split_level].strip("\n")}
                )

        messages.append({"role": "user", "content": user_input})

        resp = await call_llm(messages, response_format=ClaimDecompositionOutput)
        return resp.choices[0].message.parsed.claims

    async def verify_claims(self, premise: str, hypothesis_list: List[str]):
        """Use Faithfulness to verify claims against the premise."""
        ff = Faithfulness()
        response = await ff.create_verdict(retrieved_contexts=premise, statements=hypothesis_list)
        claim_verifications = np.array([bool(r.verdict) for r in response])
        verdicts_json = [
            {"statement": r.statement, "reason": r.reason, "verdict": r.verdict}
            for r in response
        ]
        return claim_verifications, verdicts_json

    async def decompose_and_verify_claims(self, reference: str, response: str, split_level: str):
        claims = await self.decompose_claims(response, split_level)
        return await self.verify_claims(premise=reference, hypothesis_list=claims)

    async def evaluate(self, reference: str, response: str):
        reference_response, precision_verdicts = await self.decompose_and_verify_claims(
            reference=reference, response=response, split_level="HIGH_ATOMICITY_HIGH_COVERAGE",
        )
        response_reference, recall_verdicts = await self.decompose_and_verify_claims(
            reference=response, response=reference, split_level="HIGH_ATOMICITY_HIGH_COVERAGE",
        )

        tp = int(sum(reference_response))
        fp = int(sum(~reference_response))
        fn = int(sum(~response_reference))

        return {
            "precision": float(np.round(tp / (tp + fp + 1e-8), 2)),
            "recall": float(np.round(tp / (tp + fn + 1e-8), 2)),
            "f1": float(np.round(fbeta_score(tp, fp, fn, self.beta), 2)),
            "precision_verdicts": precision_verdicts,
            "recall_verdicts": recall_verdicts,
        }


if __name__ == "__main__":
    async def _test():
        fc = FactualCorrectness()
        res = await fc.evaluate(
            reference="国产乙肝疫苗与进口乙肝疫苗在安全性和预防效果上完全相同，均可放心使用。",
            response="国产乙肝疫苗与进口疫苗在安全性方面没有区别。",
        )
        print(res)

    asyncio.run(_test())
