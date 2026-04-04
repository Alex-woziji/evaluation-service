import yaml
import asyncio
from typing import List
from pydantic import BaseModel, Field

from app.utils.constants import PROMPT_DIR
from app.utils.logger import get_logger
from app.utils.llm_utils import call_llm

with open(PROMPT_DIR, "r", encoding="utf-8") as f:
    _prompt_config = yaml.safe_load(f)

logger = get_logger(__name__)


def _build_messages(metric_prompt: dict, user_input: str) -> list[dict]:
    instruction = metric_prompt["Instruction"]
    messages = [{"role": "system", "content": instruction}]
    examples = metric_prompt.get("Examples", "")
    if examples:
        for key in examples:
            messages.append({"role": "user", "content": examples[key]["Input"]})
            messages.append({"role": "assistant", "content": examples[key]["Output"]})
    messages.append({"role": "user", "content": user_input})
    return messages


# ---------- Pydantic schemas ----------

class StatementGeneratorOutput(BaseModel):
    statements: List[str] = Field(description="The generated statements")


class StatementFaithfulnessAnswer(BaseModel):
    statement: str = Field(..., description="the original statement, word-by-word")
    reason: str = Field(..., description="the reason of the verdict")
    verdict: int = Field(..., description="the verdict(0/1) of the faithfulness.")


class NLIStatementOutput(BaseModel):
    statements: List[StatementFaithfulnessAnswer]


# ---------- Metric ----------

class Faithfulness:
    """Faithfulness metric — verifies claims against context."""

    async def create_statement(self, response: str, user_input: str | None = None):
        """Break answer into standalone statements."""
        logger.info("Starting statement extraction for faithfulness evaluation")
        metric_prompt = _prompt_config["FAITHFULNESS"]["Statements"]

        concat_data: dict = {"answer": response}
        if user_input:
            concat_data["question"] = user_input
        messages = _build_messages(metric_prompt, str(concat_data))

        resp = await call_llm(messages, response_format=StatementGeneratorOutput)
        return resp.choices[0].message.parsed.statements

    async def create_verdict(self, retrieved_contexts: str, statements):
        """Judge each statement against the context."""
        logger.info("Starting verdict generation for faithfulness evaluation")
        logger.info("Num of statements: %d", len(statements))

        metric_prompt = _prompt_config["FAITHFULNESS"]["Verdicts"]
        context_statement_data = {"context": retrieved_contexts, "statements": statements}
        messages = _build_messages(metric_prompt, str(context_statement_data))

        resp = await call_llm(messages, response_format=NLIStatementOutput)
        return resp.choices[0].message.parsed.statements

    async def calculate_score(self, response: str, retrieved_contexts: str, user_input: str | None = None):
        """Calculate faithfulness score.

        Returns ``{"score": float, "reason": list[dict]}`` where *score* is the
        fraction of statements whose verdict is 1, and *reason* contains the
        full verdict details for every statement.
        """
        statements = await self.create_statement(response, user_input)
        verdicts = await self.create_verdict(retrieved_contexts, statements)

        total = len(verdicts)
        passed = sum(1 for v in verdicts if v.verdict == 1)
        score = round(passed / total, 2) if total else 0.0

        reason = [
            {"statement": v.statement, "reason": v.reason, "verdict": v.verdict}
            for v in verdicts
        ]
        return {"score": score, "reason": reason}


if __name__ == "__main__":
    async def _test():
        ff = Faithfulness()
        context = (
            "John is a student at XYZ University. He is pursuing a degree in "
            "Computer Science. He is enrolled in several courses this semester."
        )
        response = "John is majoring in Biology and he is a dedicated student."

        result = await ff.calculate_score(retrieved_contexts=context, response=response)
        print(f"Score: {result['score']}")
        print(f"Reason: {result['reason']}")

    asyncio.run(_test())
