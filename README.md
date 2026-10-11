# Orbit Knowledge

문서를 등록하고 근거와 함께 답변하는 경량 RAG/MCP 지식 에이전트입니다.

[GitHub Pages에서 실행하기](https://choijinwon.github.io/agent-wiki/)

## Netlify

저장소를 연결하면 `netlify.toml`의 설정에 따라 `knowledge_agent/static` 폴더를 게시합니다. 별도의 빌드 명령이나 패키지 설치는 필요하지 않습니다. 저장소 루트에는 `index.html`이 없으므로 루트 폴더를 게시하면 404가 발생합니다.

`*.netlify.app`에서는 GitHub Pages와 동일한 브라우저 데모 모드로 문서 등록·검색·출처 표시를 사용할 수 있습니다. 문서는 현재 브라우저의 `localStorage`에 저장되며 다른 기기와 공유되지 않습니다. Python API, MCP 서버, LLM 답변 합성은 별도 서버 실행이 필요합니다.

## Features

- SQLite FTS5와 한국어 서브워드 해시 벡터를 결합한 하이브리드 검색
- 출처와 에이전트 실행 추적을 포함하는 근거 기반 질의응답
- OpenAI 호환 Chat Completions LLM 연결 및 안전한 로컬 fallback
- `knowledge_search`, `knowledge_ask`, `knowledge_list_documents` MCP 도구
- 반응형 웹 UI, Docker 이미지, Kubernetes 배포 manifest
- GitHub Pages용 브라우저 로컬 지식 베이스

## Run locally

외부 Python 패키지가 필요하지 않습니다.

```bash
make test
make run
```

`http://127.0.0.1:8090`에서 웹 UI를 사용할 수 있습니다.

```bash
LLM_BASE_URL=http://your-llm-endpoint \
LLM_API_KEY=your-key \
LLM_MODEL=your-model \
make run
```

GitHub Pages에서는 브라우저의 `localStorage`에 문서를 저장하고 검색합니다. 서버 API와 LLM 합성이 필요한 운영 환경에서는 Python 애플리케이션을 실행하세요.

구조와 API, MCP 설정은 [architecture 문서](docs/architecture.md)를 참고하세요.
