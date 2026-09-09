from __future__ import annotations

import json
import sys
from typing import Any, TextIO

from .agent import KnowledgeAgent
from .config import Settings
from .llm import AnswerGenerator, LLMConfig
from .store import KnowledgeStore

PROTOCOL_VERSION = "2025-06-18"


def tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "knowledge_search",
            "title": "지식 문서 검색",
            "description": "등록된 문서에서 질문과 관련된 근거 청크를 검색합니다.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "검색 질문"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
                },
                "required": ["query"],
            },
        },
        {
            "name": "knowledge_ask",
            "title": "지식 에이전트 질의",
            "description": "문서를 검색한 뒤 출처와 함께 답변을 생성합니다.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "top_k": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
                },
                "required": ["question"],
            },
        },
        {
            "name": "knowledge_list_documents",
            "title": "지식 문서 목록",
            "description": "현재 등록된 지식 문서 목록을 반환합니다.",
            "inputSchema": {"type": "object", "properties": {}},
        },
    ]


def handle_message(message: dict[str, Any], agent: KnowledgeAgent) -> dict[str, Any] | None:
    request_id = message.get("id")
    method = message.get("method")
    if request_id is None:
        return None
    try:
        if method == "initialize":
            requested = message.get("params", {}).get("protocolVersion", PROTOCOL_VERSION)
            version = requested if requested in {"2024-11-05", "2025-03-26", PROTOCOL_VERSION} else PROTOCOL_VERSION
            result = {
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "knowledge-agent", "title": "Knowledge Agent", "version": "0.1.0"},
                "instructions": "Search and answer only from documents registered in the knowledge base.",
            }
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": tool_definitions()}
        elif method == "tools/call":
            params = message.get("params", {})
            name = params.get("name")
            arguments = params.get("arguments", {})
            if name == "knowledge_search":
                data = [item.to_dict() for item in agent.store.search(arguments.get("query", ""), int(arguments.get("limit", 5)))]
            elif name == "knowledge_ask":
                data = agent.ask(arguments.get("question", ""), int(arguments.get("top_k", 5)))
            elif name == "knowledge_list_documents":
                data = agent.store.list_documents()
            else:
                raise LookupError(f"unknown tool: {name}")
            serialized = json.dumps(data, ensure_ascii=False)
            result = {"content": [{"type": "text", "text": serialized}], "structuredContent": {"result": data}, "isError": False}
        else:
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except (ValueError, TypeError) as error:
        return {"jsonrpc": "2.0", "id": request_id, "result": {"content": [{"type": "text", "text": str(error)}], "isError": True}}
    except LookupError as error:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": str(error)}}


def serve(input_stream: TextIO, output_stream: TextIO, agent: KnowledgeAgent) -> None:
    for line in input_stream:
        try:
            message = json.loads(line)
            response = handle_message(message, agent)
            if response is not None:
                output_stream.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
                output_stream.flush()
        except json.JSONDecodeError as error:
            output_stream.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(error)}}) + "\n")
            output_stream.flush()


def build_agent(settings: Settings) -> KnowledgeAgent:
    store = KnowledgeStore(settings.data_dir / "knowledge.db")
    generator = AnswerGenerator(LLMConfig(settings.llm_base_url, settings.llm_api_key, settings.llm_model, settings.llm_timeout_seconds))
    return KnowledgeAgent(store, generator, settings.top_k)


def main() -> None:
    serve(sys.stdin, sys.stdout, build_agent(Settings.from_env()))


if __name__ == "__main__":
    main()
