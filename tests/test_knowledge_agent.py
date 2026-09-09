from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.request
from io import StringIO
from pathlib import Path

from knowledge_agent.agent import KnowledgeAgent
from knowledge_agent.config import Settings
from knowledge_agent.llm import AnswerGenerator, LLMConfig
from knowledge_agent.mcp_server import handle_message, serve
from knowledge_agent.store import KnowledgeStore
from knowledge_agent.web import KnowledgeServer


class KnowledgeAgentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.path = Path(self.temp_dir.name)
        self.store = KnowledgeStore(self.path / "knowledge.db")
        self.store.add_document(
            title="서비스 운영 가이드",
            source="runbook.md",
            content=(
                "장애가 발생하면 먼저 애플리케이션 로그와 메트릭을 확인합니다. "
                "배포 상태는 Argo CD에서 확인하며 롤백 전 변경 이력을 검토합니다."
            ),
            chunk_size=120,
            chunk_overlap=20,
        )
        self.agent = KnowledgeAgent(self.store, AnswerGenerator(LLMConfig()), top_k=3)

    def test_hybrid_search_handles_korean_suffixes(self) -> None:
        results = self.store.search("장애 발생 시 무엇을 확인하나요?")
        self.assertTrue(results)
        self.assertEqual(results[0].title, "서비스 운영 가이드")
        self.assertIn("로그", results[0].content)

    def test_document_upsert_replaces_old_chunks(self) -> None:
        original = self.store.list_documents()[0]
        self.store.add_document(
            title="서비스 운영 가이드",
            source="runbook.md",
            content="새 지침은 알림 채널을 먼저 확인합니다.",
        )
        updated = self.store.list_documents()[0]
        self.assertEqual(original["id"], updated["id"])
        self.assertEqual(self.store.stats()["chunks"], 1)
        self.assertFalse(self.store.search("Argo CD"))

    def test_agent_returns_citations_and_trace(self) -> None:
        result = self.agent.ask("배포 상태는 어디서 확인하나요?")
        self.assertEqual(result["mode"], "extractive")
        self.assertTrue(result["citations"])
        self.assertEqual(result["trace"][0]["tool"], "knowledge_search")

    def test_agent_routes_document_list(self) -> None:
        result = self.agent.ask("등록된 문서 목록을 알려줘")
        self.assertEqual(result["mode"], "tool")
        self.assertIn("서비스 운영 가이드", result["answer"])

    def test_mcp_lifecycle_and_tool_call(self) -> None:
        initialized = handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18"},
            },
            self.agent,
        )
        self.assertEqual(initialized["result"]["protocolVersion"], "2025-06-18")
        called = handle_message(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "knowledge_search", "arguments": {"query": "Argo CD"}},
            },
            self.agent,
        )
        self.assertFalse(called["result"]["isError"])
        self.assertTrue(called["result"]["structuredContent"]["result"])

    def test_mcp_stdio_uses_one_json_message_per_line(self) -> None:
        request = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}) + "\n"
        output = StringIO()
        serve(StringIO(request), output, self.agent)
        message = json.loads(output.getvalue())
        self.assertEqual(len(message["result"]["tools"]), 3)

    def test_http_health_and_chat(self) -> None:
        settings = Settings(
            data_dir=self.path,
            host="127.0.0.1",
            port=0,
            llm_base_url="",
            llm_api_key="",
            llm_model="test",
            llm_timeout_seconds=1,
            chunk_size=900,
            chunk_overlap=120,
            top_k=5,
        )
        server = KnowledgeServer(("127.0.0.1", 0), settings)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        port = server.server_address[1]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health") as response:
            payload = json.loads(response.read())
        self.assertEqual(payload["status"], "ok")


if __name__ == "__main__":
    unittest.main()
