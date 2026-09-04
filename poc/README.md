# Agent 1 (탕아) PoC

1번 에이전트("탕아" - 문제 제기)를 핵심으로, 2번(전문가)·3번(모르긴 몰라도)을
외부 자문 에이전트로 붙인 4-agent 연구 아이디어 발제 파이프라인의 최소 동작 PoC.

## 왜 이렇게 구성했는가

- **Agent 2 (전문가)**: 도메인이 고정된다. 연구자 본인의 전공 도메인 그대로
  두고, 낮은 temperature로 교과서적/정식 반박만 하게 한다. "내부자" 역할.
- **Agent 3 (모르긴 몰라도)**: 도메인을 미리 고정하지 않는다. 회의에서
  Agent 3의 참고 도메인을 정하지 못했던 문제는, 도메인을 정하는 대신
  "도메인을 스스로 고르는 절차"를 프롬프트 안에 넣어 해결했다.
  1) 탈도메인화(추상 키워드 추출) → 2) 후보 도메인 자체 생성 → 3) 이식 제안,
  순서로 강제하고 높은 temperature로 의도적 환각을 창의성 재료로 쓴다.
  단, 모든 제안 끝에 `[검증 필요]`를 강제로 붙여 사실성 문제를 노출시킨다.
- **라우팅**: Agent 1이 던지는 질문에는 5가지 type
  (`why_definition`, `why_method`, `variable_doubt`, `inversion`, `other_field`)
  을 스스로 태깅하게 하고, 앞의 셋은 Agent 2로, 뒤의 둘은 Agent 3으로 보낸다.
- **Agent 4 (INTP)**: 아이디어의 학술적 가치는 평가하지 않고, 사용자가 준
  config 스키마(data/benchmark/implementation_time/evaluation_metric/
  domain_dependency/risk)에만 근거해 기계적으로 채점한다.

## 실행

```bash
pip install -r requirements.txt

# 실제 Claude 호출 (API 키 필요)
export ANTHROPIC_API_KEY=sk-...
python3 run_poc.py examples/pnt_signal_recovery.json -o report.md

# API 키 없이 파이프라인 구조만 검증 (mock 응답)
python3 run_poc.py examples/pnt_signal_recovery.json --mock
```

## 파일 구성

- `prompts.py` - 4개 에이전트의 system prompt
- `llm.py` - Anthropic API 호출 wrapper (mock 모드 포함)
- `orchestrator.py` - 질문 생성 → 라우팅 → 종합 → 평가 파이프라인
- `run_poc.py` - CLI 진입점
- `examples/pnt_signal_recovery.json` - 팀 회의에서 나온 GNSS 신호 누락 예시를
  그대로 입력값으로 옮긴 데모 케이스

## 다음 단계 (미해결)

- Agent 3의 "후보 도메인 생성"이 순수 LLM 내부 지식에 의존한다. 실제 타 분야
  문헌을 붙이려면 검색/RAG 단계를 추가해야 신뢰도가 올라간다.
- Agent 2를 텍스트북 프롬프트가 아니라 실제 사용자의 전공 자료(PDF/노트)에
  RAG로 연결하면 "아는 척"이 아니라 실제 근거 기반 반박이 된다.
- Agent 1 질문 생성의 type 분류 정확도는 실제 API로 붙여서 검증 필요
  (mock에서는 하드코딩된 예시로만 라우팅을 확인함).
