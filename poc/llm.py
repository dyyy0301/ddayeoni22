"""LLM 호출 wrapper. ANTHROPIC_API_KEY가 있으면 실제 Claude를 호출하고,
없거나 --mock이 지정되면 결정적인 더미 응답을 돌려줘서 파이프라인 구조를
API 키 없이도 확인할 수 있게 한다.

mock 모드에서는 3개의 시드 아이디어(i1/i2/i3)가 디렉터의 3가지 도발 전술
(tactic)을 하나씩 대표하고, 각각 다른 경로를 타도록 설계해 두었다
(run_poc.py --mock 실행 시 그대로 재현됨):
  i1 (free_from_evidence)      -> 이론이 1라운드에 concede  -> passed    -> 최종 문서화 O
  i2 (naive_assumption_attack) -> 디렉터가 1라운드에 concede -> discarded -> 외부자문/실무 전파 안 됨
  i3 (extreme_stress_test)     -> 끝까지 합의 안 됨(max_rounds) -> deadlocked -> 실무 verdict no-go로 최종 제외
"""

import json
import os

DEFAULT_MODEL = "claude-sonnet-5"

# Anthropic 서버사이드 웹 검색 도구. 외부자문/도메인스카우트처럼 "이미 있는
# 사례인지"를 내부 지식 추측이 아니라 실제 검색으로 확인해야 하는 호출에만
# 켠다 (search=True). 검색 실행은 API가 서버에서 알아서 처리하므로 우리가
# 별도 tool-use 루프를 짤 필요는 없다.
WEB_SEARCH_TOOL = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 6}]


class LLM:
    def __init__(self, model: str = DEFAULT_MODEL, mock: bool = False):
        self.model = model
        self.mock = mock or not os.environ.get("ANTHROPIC_API_KEY")
        self._client = None
        if not self.mock:
            import anthropic

            self._client = anthropic.Anthropic()

    def complete(
        self,
        system: str,
        user: str,
        temperature: float = 0.5,
        max_tokens: int = 1500,
        search: bool = False,
    ) -> str:
        if self.mock:
            return self._mock_response(system, user, search)
        kwargs = {}
        if search:
            kwargs["tools"] = WEB_SEARCH_TOOL
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
            **kwargs,
        )
        return "".join(block.text for block in resp.content if block.type == "text")

    @staticmethod
    def _idea_id(user: str) -> str:
        try:
            data = json.loads(user)
        except (json.JSONDecodeError, TypeError):
            return ""
        return data.get("idea_id") or data.get("idea", {}).get("idea_id", "") or ""

    def _mock_response(self, system: str, user: str, search: bool = False) -> str:
        idea_id = self._idea_id(user)

        if '"angle"' in system:
            # ABSTRACTION_SYSTEM: 검색/판단 없이 순수 구조 추상화만. scout든
            # advisor든 입력 텍스트와 무관하게 mock에서는 결정론적 2각도를 준다.
            return json.dumps(
                [
                    {
                        "angle": "관측-추정 구조",
                        "abstraction": "[MOCK] 국소적으로 관측한 신호만으로 전역 상태를 추정하는 문제",
                    },
                    {
                        "angle": "정보 전파 구조",
                        "abstraction": "[MOCK] 개별 노드 간 신호 교환을 통해 정보가 집단적으로 전파·"
                        "수렴하는 구조",
                    },
                ],
                ensure_ascii=False,
            )

        if '"narrowed_topic"' in system:
            # COLD_START_GROUNDING_SYSTEM: researcher_background조차 없을 때.
            # 실제로는 random_domain.py가 뽑은 subfield가 user에 들어있지만,
            # mock에서는 검색을 안 하므로 내용은 결정론적 placeholder를 쓴다.
            return json.dumps(
                {
                    "narrowed_topic": "[미검증 - 검색 불가 환경] mock 모드 placeholder 주제",
                    "search_queries_tried": ["[미검증 - 검색 불가 환경] mock 모드에서는 실제 검색을 "
                    "실행하지 않음"],
                    "grounding_text": "[미검증 - 검색 불가 환경] random_domain.py가 뽑은 세부분야 안의 "
                    "구체 이론을 실제 검색으로 채워야 하는 자리 (mock이라 비어 있음).",
                },
                ensure_ascii=False,
            )

        if "search_queries_tried" in system:
            return json.dumps(
                {
                    "search_queries_tried": ["[미검증 - 검색 불가 환경] mock 모드에서는 실제 검색을 "
                    "실행하지 않음"],
                    "candidate_domains": ["[미검증] 생태학", "[미검증] 사회연결망 이론", "[미검증] 통계역학"],
                    "target_domain": "[미검증 - 검색 불가 환경] 곤충 사회성 군집의 분산 탐색(collective "
                    "foraging) 이론",
                    "grounding_text": "[미검증 - 검색 불가 환경] 개미 군집은 개별 개체가 전역 지도 없이도 "
                    "페로몬 농도 구배만으로 먹이원까지 경로를 집단적으로 수렴시킨다.",
                },
                ensure_ascii=False,
            )

        if "grounded_in" in system:
            # DIRECTOR_SEED_SYSTEM. researcher_background가 아예 없는 완전
            # 콜드 스타트 입력도 있으므로 그 필드 존재 여부로 분기하지 않는다.
            return json.dumps(
                [
                    {
                        "idea_id": "i1",
                        "tactic": "free_from_evidence",
                        "claim": "[MOCK] '위치 계산'이라는 개념 자체를 폐기해야 한다. 개체는 절대 좌표를 "
                        "따질 필요 없이, 순전히 이웃과의 국소 신호 강도 비교만으로 목적 상태에 "
                        "수렴하는 시스템이면 충분하다.",
                        "grounded_in": "페로몬 농도 기반 분산 탐색 원리",
                    },
                    {
                        "idea_id": "i2",
                        "tactic": "naive_assumption_attack",
                        "claim": "[MOCK] 이 이론은 '신호를 중계하는 개체가 항상 정직하게 신호를 전달한다'는 "
                        "순진한 가정을 깔고 있다. 신호가 강한 개체가 거짓 신호를 흘려도 걸러낼 방법이 "
                        "전혀 없다는 걸 아무도 지적하지 않는다.",
                        "grounded_in": "역할 분담형 정보 중계 구조",
                    },
                    {
                        "idea_id": "i3",
                        "tactic": "extreme_stress_test",
                        "claim": "[MOCK] 중계 개체 수가 100배로 폭증해서 신호가 완전히 뒤섞이는 극한 "
                        "상황이 오면, 국소 신호 구배 자체가 노이즈에 파묻혀 이 이론은 통째로 무너진다. "
                        "그런데 교과서는 그런 상황을 단 한 줄도 언급하지 않는다.",
                        "grounded_in": "군집의 상대 위상 유지 메커니즘",
                    },
                ],
                ensure_ascii=False,
            )

        if '"stance": "reject"' in system:
            if idea_id == "i1":
                return json.dumps(
                    {"stance": "concede", "argument": "[MOCK] 절대 좌표 없이 국소 신호 비교만으로 "
                     "수렴시키는 방식은 실제로 협력 측위(cooperative positioning)의 분산 추정 이론으로 "
                     "이미 정당화된다. 더 반박할 논리가 없다."},
                    ensure_ascii=False,
                )
            if idea_id == "i2":
                return json.dumps(
                    {"stance": "reject", "argument": "[MOCK] '거를 방법이 전혀 없다'는 전제 자체가 "
                     "틀렸다. 표준 협력 네트워크 이론에는 이미 신뢰도 가중 합의(trust-weighted "
                     "consensus) 메커니즘이 정식화되어 있어 거짓 신호를 통계적으로 감쇠시킨다."},
                    ensure_ascii=False,
                )
            return json.dumps(
                {"stance": "reject", "argument": "[MOCK] 중계 개체 수가 아무리 늘어나도, 신호대잡음비만 "
                 "충분하면 중심극한정리에 의해 노이즈는 평균화되어 국소 구배는 복원 가능하다. "
                 "붕괴한다는 주장은 근거가 없다."},
                ensure_ascii=False,
            )

        if '"stance": "counter"' in system:
            if idea_id == "i2":
                return json.dumps(
                    {"stance": "concede", "argument": "[MOCK] trust-weighted consensus로 이미 다뤄진다는 "
                     "지적이 맞다. 이 형태로는 더 밀어붙일 논리가 없다."},
                    ensure_ascii=False,
                )
            return json.dumps(
                {
                    "stance": "counter",
                    "claim": "[MOCK] 노이즈가 서로 독립적일 때만 평균화가 성립한다. 중계 개체들이 "
                    "서로의 신호에 다시 반응하는 상관 잡음(correlated noise) 상황으로 조건을 좁히면 "
                    "중심극한정리가 성립하지 않는다.",
                    "argument": "[MOCK] '충분한 SNR'이라는 전제 역시 중계 밀도가 커질수록 상관 구조가 "
                    "생긴다는 걸 무시한 편의적 가정이다.",
                },
                ensure_ascii=False,
            )

        if "[기존 유사 사례 유무]" in system:
            # mock은 search 플래그와 무관하게 실제 검색을 절대 하지 않으므로 항상 명시한다.
            disclosed = "[미검증 - 검색 불가 환경] "
            if idea_id == "i1":
                return (
                    "[MOCK idea_id=i1]\n"
                    f"[Cross-domain Structural Search] 사용한 abstraction: '국소적으로 관측한 신호만으로 "
                    f"전역 상태를 추정하는 문제' / {disclosed}시도한 검색어: "
                    "'local interaction consensus without global coordinates' / "
                    "후보 1) 물리학 - 통계역학의 스핀 정렬(이징 모델) "
                    "2) 사회학 - 사회연결망의 여론 수렴(threshold consensus dynamics) "
                    "3) 생물학 - 새떼의 군집 비행(flocking) 규칙.\n"
                    "[선택된 전공 + 페르소나 전환] 사회학(여론 동역학 연구자) - 개체 간 국소 "
                    "상호작용만으로 전역 합의가 나타나는 조건(문턱값, 연결 밀도)이 이미 정량화되어 "
                    "있어, 수렴 조건을 그대로 빌려올 수 있기 때문.\n"
                    f"[기존 유사 사례 유무] {disclosed}로보틱스의 flocking/swarm consensus와 개념적으로 "
                    "유사하지만, 사회연결망의 '문턱값 모델(threshold model)'을 측위 문제에 명시적으로 "
                    "적용한 사례는 드물다.\n"
                    f"[Knowledge Transfer 제안] {disclosed}여론 동역학의 '연결 밀도 임계값' 공식을 "
                    "가져와, 최소 몇 개체가 연결되어야 확률장이 수렴하는지 사전 계산할 수 있다. "
                    "[검증 필요: 실제 통신 반경/밀도 데이터로 임계값 검증]"
                )
            return (
                "[MOCK idea_id=i3]\n"
                f"[Cross-domain Structural Search] 사용한 abstraction: '개별 노드 간 신호 교환을 통해 "
                f"정보가 집단적으로 전파·수렴하는 구조' / {disclosed}시도한 검색어: "
                "'correlated noise breaks relay network capacity at scale' / "
                "후보 1) 통신공학 - 다중경로 페이딩과 중계망 용량 이론 "
                "2) 생태학 - 개체군 밀도 증가에 따른 자원 경쟁/혼잡 효과 "
                "3) 언어학 - 다자간 대화에서 화자 수 증가에 따른 정보 손실(오버랩/노이즈).\n"
                "[선택된 전공 + 페르소나 전환] 통신공학(중계망 용량이론 연구자) - 상관 잡음 하에서의 "
                "용량 한계가 이미 정식화(correlated relay channel capacity)되어 있어 붕괴 조건을 "
                "정량적으로 도출할 수 있기 때문.\n"
                f"[기존 유사 사례 유무] {disclosed}무선 중계망의 상관 페이딩 채널 용량 연구와 구조적으로 "
                "거의 동일하다. 다만 '생물학적 군집'을 이 프레임으로 재해석한 사례는 없다.\n"
                f"[Knowledge Transfer 제안] {disclosed}상관 relay channel의 capacity outage "
                "probability 공식을 가져와, 중계 밀도의 임계 붕괴점을 사전에 계산할 수 있다. "
                "[검증 필요: 시뮬레이션으로 임계 밀도 산출 후 실측 비교]"
            )

        if '"verdict"' in system:
            if idea_id == "i3":
                return json.dumps(
                    {
                        "data": "unavailable",
                        "benchmark": "unavailable",
                        "implementation_time": "3w",
                        "evaluation_metric": "partial",
                        "domain_dependency": "high",
                        "risk": "high",
                        "verdict": "no-go",
                        "reasoning": "[MOCK] 상관 잡음 붕괴 조건을 검증할 실측 데이터/벤치마크가 없고, "
                        "20라운드 넘게 이론과 합의도 안 됐다. 지금 단계에서 착수하기엔 리스크가 크다.",
                    },
                    ensure_ascii=False,
                )
            return json.dumps(
                {
                    "data": "partial",
                    "benchmark": "available",
                    "implementation_time": "8h",
                    "evaluation_metric": "available",
                    "domain_dependency": "medium",
                    "risk": "medium",
                    "verdict": "go",
                    "reasoning": "[MOCK] 협력 측위 이론과 여론 동역학 시뮬레이션 벤치마크가 이미 있어 "
                    "착수 부담이 낮다.",
                },
                ensure_ascii=False,
            )

        return "[MOCK] response"
