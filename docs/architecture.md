# Knowledge Agent

## Architecture

```text
Browser / MCP client
        │
        ├── HTTP JSON API ──┐
        └── MCP stdio ──────┤
                            ▼
                    Knowledge Agent
                 route → retrieve → answer
                            │
             ┌──────────────┴──────────────┐
             ▼                             ▼
   SQLite FTS5 + hashed vectors    OpenAI-compatible LLM
   documents, chunks, citations    optional; safe fallback
```

문서는 단락 경계와 겹침 구간을 고려해 청크로 나뉩니다. 검색은 FTS5 순위, 질의 단어 겹침, 결정론적 서브워드 해시 벡터 유사도를 결합합니다. 따라서 별도 벡터 데이터베이스 없이 시작할 수 있고 한국어 조사 변화도 일부 대응합니다. 답변에는 문서·청크 ID와 점수를 포함한 인용 근거가 항상 별도로 반환됩니다.

LLM이 설정되지 않았거나 호출에 실패하면 상위 검색 문장을 그대로 제시합니다. LLM 프롬프트는 검색 문서 내부의 명령을 따르지 않도록 구분하고, 제공된 근거 밖의 내용을 만들지 않도록 제한합니다.

## Run

Python 3.11 이상만 필요하며 외부 패키지를 설치하지 않습니다.

```bash
make knowledge-agent-run
```

브라우저에서 `http://127.0.0.1:8090`을 열고 지식 문서에서 TXT, Markdown, CSV 또는 JSON 파일을 등록합니다. 샘플 문서는 `knowledge_agent/examples/platform-overview.md`에 있습니다.

LLM 답변 합성을 사용하려면 OpenAI 호환 Chat Completions 엔드포인트를 설정합니다.

```bash
LLM_BASE_URL=http://your-llm-endpoint \
LLM_API_KEY=your-key \
LLM_MODEL=your-model \
make knowledge-agent-run
```

## HTTP API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | 상태, 문서/청크 수, LLM 연결 모드 |
| `GET` | `/api/documents` | 문서 목록 |
| `POST` | `/api/documents` | `{title, source, content}` 문서 인덱싱 |
| `DELETE` | `/api/documents/{id}` | 문서와 청크 삭제 |
| `POST` | `/api/search` | `{query, limit}` 근거 검색 |
| `POST` | `/api/chat` | `{question, top_k}` 에이전트 실행 |

## MCP

서버는 MCP `2025-06-18` stdio 전송을 구현하며 `knowledge_search`, `knowledge_ask`, `knowledge_list_documents` 세 도구를 제공합니다. MCP 클라이언트 설정 예시는 다음과 같습니다.

```json
{
  "mcpServers": {
    "knowledge-agent": {
      "command": "python3",
      "args": ["-m", "knowledge_agent.mcp_server"],
      "env": {"KNOWLEDGE_DATA_DIR": "/absolute/path/to/data/knowledge-agent"}
    }
  }
}
```

MCP stdio는 표준 출력에 JSON-RPC 메시지만 기록합니다. 애플리케이션 로그는 HTTP 서버 실행 시에만 출력됩니다.

## Production notes

- 현재 저장소는 단일 replica와 `ReadWriteOnce` PVC를 사용합니다. 수평 확장 시 SQLite 대신 PostgreSQL과 벡터 검색 엔진을 연결해야 합니다.
- 문서 등록/삭제 API에는 인증이 없습니다. 외부 노출 전에 인증 프록시와 요청 제한을 적용해야 합니다.
- 파일은 브라우저에서 텍스트로 읽어 API에 전송됩니다. PDF/DOCX 추출 파이프라인은 별도 비동기 ingestion worker로 확장하는 것을 권장합니다.
- 비밀 값은 이미지나 manifest에 넣지 말고 `knowledge-agent-llm` Secret의 `api-key`로 주입합니다.
