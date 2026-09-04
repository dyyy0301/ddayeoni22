# 연구 주제 탐색 에이전트 PoC (디렉터-이론 논쟁 루프)

## 원래 의도

기존 연구 기획은 "문제 정의" 단계에서부터 연구자 개인의 편향(몇 년간
쌓아온 전공/방법론/논문에 대한 익숙함)에 갇히기 쉽다. 이 PoC는 연구자의
배경과 무관한 완전히 낯선 도메인에서, 그 도메인의 교과서적 근거 자료를
분석하며 새로운 연구 주제(완전 엉뚱한 아이디어)를 뽑아낼 수 있는지를
검증하기 위한 최소 동작 버전이다.

지금 이 시점에서 확인하려는 것은 **"이 구조로 신박한 아이디어를 실제로
찾아낼 수 있는가"** 이며, 특정 도메인(PNT 등)에 대한 검증이 목적이 아니다.
`examples/`의 입력은 그 구조를 시험해보기 위한 하나의 예시일 뿐이다.

## 파이프라인

```
-1) target_domain/grounding_text를 입력에 안 넣었으면, 도메인 스카우트가
    researcher_background를 구조 추출 → 실제 검색(Cross-domain Structural
    Search)해서 스스로 낯선 도메인을 찾음 (사람이 미리 정해줄 필요 없음)
        │
0) 디렉터: grounding_text(낯선 도메인의 교과서적 근거자료)를 분석하며
   researcher_background와 무관한 단정적 주장(seed idea) 여러 개를 던짐
        │
1) 각 주장마다 이론 <-> 디렉터 논쟁 루프
     이론(편향 최대, 기존 이론으로만 반박) <---> 디렉터(웬만하면 안 물러남)
        │
        ├─ 이론이 물러남           -> passed
        ├─ 디렉터가 물러남         -> discarded  (여기서 폐기, 더 진행 안 됨)
        └─ max_rounds(기본 20) 도달 -> deadlocked
        │
2) passed / deadlocked만 외부자문 + 실무·보조 에이전트로 전파
   (discarded는 애초에 전파되지 않음)
   외부자문은 Problem Abstraction → Cross-domain Structural Search(실제
   검색) → Knowledge Transfer(그 분야 전공자로 페르소나 전환 후 실제
   검색으로 방법론 조사) 3단계를 거친다 — 내부 지식 추측 금지
        │
3) 실무·보조가 no-go 준 것도 여기서 최종 제외
        │
4) 최종적으로 살아남은 것만 문서화
```

## 왜 이렇게 구성했는가

- **이론 에이전트**: 도메인이 고정된다. 편향이 최대치로 걸려 있고,
  기존 이론/정설로만 반박하며, 웬만하면 물러나지 않는다 (낮은 temperature).
  "말이 안 통하는" 상대가 있어야 논쟁이 아이디어를 실제로 단련시킨다.
- **디렉터**: 역시 웬만하면 안 물러난다. 반박당하면 원래 주장을 그대로
  반복하지 않고 반드시 한 단계 더 구체화/조건화해서 되받아친다 (높은
  temperature). 정말 결정타를 맞았을 때만 concede하도록 명시해서, 실험
  자체가 "무조건 버티기"로 무의미해지는 것을 막았다.
- **20회 임계값**: 합의도 항복도 안 나는 논쟁은 그 자체로 "쉽게 결론 나지
  않을 만큼 흥미로운 지점"이라는 신호로 보고, 폐기하지 않고 외부자문 +
  실무·보조에게 넘긴다.
- **외부 자문**: 도메인을 미리 고정하지 않는다. Problem Abstraction(구조
  추출) → Cross-domain Structural Search(그 구조 그대로 실제 검색) →
  Knowledge Transfer(선택한 전공자로 페르소나를 갈아입고 그 분야 문헌을
  다시 검색) 순서로 강제한다. "이미 있는 사례인지" 판단을 LLM 내부 지식
  추측에 맡기지 않고 `web_search_20250305` 도구로 실제 검색하게 했다 —
  실측 결과, 추상화 표현이 원 도메인과 너무 가까우면 검색이 근처 분야에서만
  맴돌고, 기하학/도메인 용어를 완전히 벗겨야 실제로 먼 분야로 튄다는 걸
  확인했다. 그래서 "첫 검색이 근처 결과만 주면 표현을 바꿔 최소 2번 더
  검색하라"를 프롬프트에 강제로 넣었다. 모든 판단 끝에 `[검증 필요]`를
  남기고, 검색 도구가 없는 환경(mock 등)에서는 `[미검증 - 검색 불가 환경]`을
  명시하게 했다.
- **도메인 스카우트**: 디렉터가 딴지 걸 target_domain/grounding_text를
  사람이 미리 안 정해줘도 되게 만드는 Phase -1. 외부 자문과 완전히 같은
  Problem Abstraction → Cross-domain Structural Search 로직을 재사용해서,
  researcher_background만 보고 실제 검색으로 낯선 도메인을 스스로 찾는다.
  입력 JSON에 `target_domain`/`grounding_text`를 아예 안 넣으면 자동으로
  이 단계가 실행된다 (`examples/domain_unset.json` 참고).
- **실무·보조**: 아이디어의 학술적 가치는 보지 않는다. 오직 feasibility
  config 스키마(data/benchmark/implementation_time/evaluation_metric/
  domain_dependency/risk/verdict)로만 기계적으로 채점한다. 이 게이트를
  통과 못하면(no-go) 아무리 논쟁을 통과했어도 최종 문서에서 빠진다.
- **선별적 문서화**: discarded, no-go로 걸러진 항목은 "내부 트레이스"에만
  남기고 공식 산출물에는 포함하지 않는다 — 전부 기록하면 노이즈만
  늘어난다는 원래 설계 의도를 그대로 반영.

## 실행

```bash
pip install -r requirements.txt

# 실제 Claude 호출 (API 키 필요)
export ANTHROPIC_API_KEY=sk-...
python3 run_poc.py examples/new_domain_exploration.json -o report.md

# API 키 없이 파이프라인 구조만 검증 (mock 응답, 라운드 상한을 줄여서 빠르게 확인 가능)
python3 run_poc.py examples/new_domain_exploration.json --mock --max-rounds 4
```

mock 모드는 세 갈래 경로를 전부 재현하도록 결정적으로 짜여 있다
(`llm.py` 주석 참고): 1개는 1라운드에 이론이 concede(passed→문서화됨),
1개는 1라운드에 디렉터가 concede(discarded→폐기), 1개는 끝까지 합의가
안 나서 deadlock 처리된 뒤 실무 단계 no-go로 최종 제외된다.

## 파일 구성

- `prompts.py` - 디렉터/이론/외부자문/실무·보조 4개 system prompt
- `llm.py` - Anthropic API 호출 wrapper (mock 모드 포함, mock 분기 설명 주석 있음)
- `orchestrator.py` - 시드 생성 → 논쟁 루프 → 에스컬레이션 → 선별적 문서화
- `run_poc.py` - CLI 진입점 (`--max-rounds`로 20회 상한 조정 가능)
- `examples/new_domain_exploration.json` - PNT 배경 연구자가 곤충 사회성
  군집 이론을 grounding으로 삼아 낯선 아이디어를 탐색하는 데모 입력
- `examples/percolation_forest_fire.json` - 같은 배경 연구자를 산불 확산의
  침투 이론(percolation theory)에 붙여본 두 번째 데모 입력
- `examples/domain_unset.json` - target_domain/grounding_text를 아예 안
  주고 도메인 스카우트가 스스로 찾게 하는 데모 입력

## 다음 단계 (미해결)

- 도메인 스카우트/외부 자문 모두 `web_search_20250305`를 붙여뒀지만 실제
  API 키로 돌려본 적은 아직 없다. mock은 검색을 절대 안 하므로
  (`[미검증 - 검색 불가 환경]`로 항상 표시) 실제 검색 품질은 검증 전이다.
- 디렉터의 시드 생성 자체에는 아직 검색을 안 붙였다 — grounding_text가
  이미 스카우트 단계에서 검색으로 확보되니 필요성은 낮지만, 디렉터가
  주장을 만들 때 추가로 검색해서 더 날카로운 반례를 찾게 할 수도 있다.
- 실제 API로 20라운드 논쟁 + 검색 2회(스카우트, 외부자문)를 여러 개
  돌리면 비용/시간이 꽤 든다. 라운드당 토큰 사용량과 검색 호출 비용을
  먼저 계산해서 실험 예산을 잡아볼 필요가 있다.
- "신박함"을 사람이 최종 판단해야 하는지, 아니면 외부 자문의 참신성
  판단을 정량 점수화할지는 아직 미정.
