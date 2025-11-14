import os
from typing import List, Dict, Any
import asyncio
from .tools import tool_defs, ToolsDispatcher
from .llm import is_available as llm_available
# from mem0 import MemoryClient

class QASystem:
    def __init__(self) -> None:
        # self.agent = MemoryClient(api_key=os.getenv('MEM0_API_KEY'))
        self.tools = ToolsDispatcher()

    async def answer(self, question: str) -> str:
        question = (question or "").strip()
        if not question:
            return "Please provide a non-empty question."
        if not llm_available():
            return "OpenAI key missing. Set OPENAI_API_KEY."

        try:
            from openai import OpenAI
        except Exception:
            return "OpenAI client not available."

        client = OpenAI()

        system = (
            "You are a life concierge assistant. Your job is to answer questions about a single member using tools and answer based on the information provided."
            "Always figure out the user first from the ask and then call search_user_memory function to retieve relevent imformation."
            "Since evidence may be implicitly, use any piece information including the timestamp in metadata. Analyze the information and make your deductions based on the information provided and answer the question accordingly."
            "If you don't know the answer, say so. Don't make up information."
            "Always answer in a concise and factual manner and don't include the internal reasoning process."
        )
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": question},
        ]

        # Iterative tool-calling loop (search)
        tools_spec = tool_defs()
        for _ in range(3):
            first = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-5"),
                messages=messages,
                tools=tools_spec,
                tool_choice="auto",
                temperature=0.1,
                max_tokens=512,
            )

            msg = first.choices[0].message
            finish_reason = first.choices[0].finish_reason
            tool_calls = getattr(msg, "tool_calls", None)
            
            # Check if response was truncated
            if finish_reason == "length":
                print(f"WARNING: Response was truncated due to max_tokens limit. Finish reason: {finish_reason}")
            
            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [tc.model_dump() for tc in (tool_calls or [])],
            })
            
            if not tool_calls:
                answer = (msg.content or "No tool called").strip()
                print(f"Final answer length: {len(answer)} characters")
                print(f"Finish reason: {finish_reason}")
                return answer

            for tc in tool_calls:
                name = tc.function.name
                args = tc.function.arguments
                result_json = await self.tools.call(name, args, original_question=question)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": name,
                        "content": result_json,
                    }
                )

        # If loop exhausted without a final answer, return unknown
        return "I don't know"


