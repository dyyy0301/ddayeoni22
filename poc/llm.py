"""LLM 호출 wrapper. ANTHROPIC_API_KEY가 있으면 실제 Claude를 호출하고,
없거나 --mock이 지정되면 결정적인 더미 응답을 돌려줘서 파이프라인 구조를
API 키 없이도 확인할 수 있게 한다.

mock 모드에서는 3개의 시드 아이디어(i1/i2/i3)가 각각 다른 경로를 타도록
설계해 두었다 (run_poc.py --mock 실행 시 그대로 재현됨):
  i1 -> 이론이 1라운드에 concede            -> passed    -> 최종 문서화 O
  i2 -> 디렉터가 1라운드에 concede           -> discarded -> 외부자문/실무 전파 안 됨
  i3 -> 끝까지 합의 안 됨 (max_rounds 도달)  -> deadlocked -> 실무 verdict no-go로 최종 제외
"""

import json
import os

DEFAULT_MODEL = "claude-sonnet-5"


class LLM:
    def __init__(self, model: str = DEFAULT_MODEL, mock: bool = False):
        self.model = model
        self.mock = mock or not os.environ.get("ANTHROPIC_API_KEY")
        self._client = None
        if not self.mock:
            import anthropic

            self._client = anthropic.Anthropic()

    def complete(self, system: str, user: str, temperature: float = 0.5, max_tokens: int = 1500) -> str:
        if self.mock:
            return self._mock_response(system, user)
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in resp.content if block.type == "text")

    @staticmethod
    def _idea_id(user: str) -> str:
        try:
            data = json.loads(user)
        except (json.JSONDecodeError, TypeError):
            return ""
        return data.get("idea_id") or data.get("idea", {}).get("idea_id", "") or ""

    def _mock_response(self, system: str, user: str) -> str:
        idea_id = self._idea_id(user)

        if "researcher_background" in user and "grounded_in" in system:
            return json.dumps(
                [
                    {
                        "idea_id": "i1",
                        "claim": "[MOCK] 개체가 위치를 '계산'하는 것이 아니라, 주변 개체와의 상대 신호"
                        "농도 교환만으로 집단 전체가 위치 확률장에 수렴하도록 설계해야 한다.",
                        "grounded_in": "페로몬 농도 기반 분산 탐색 원리",
                    },
                    {
                        "idea_id": "i2",
                        "claim": "[MOCK] 개별 노드는 자기 위치를 절대 알 필요가 없고, 집단의 상대 위상"
                        "구조만 유지하면 된다.",
                        "grounded_in": "군집의 상대 위상 유지 메커니즘",
                    },
                    {
                        "idea_id": "i3",
                        "claim": "[MOCK] 신호가 강한 개체가 약한 개체를 대신해 위치를 대리 발신하는 "
                        "'대리 관측' 구조를 표준 측위 알고리즘에 편입해야 한다.",
                        "grounded_in": "역할 분담형 정보 중계 구조",
                    },
                ],
                ensure_ascii=False,
            )

        if '"stance": "reject"' in system:
            if idea_id == "i1":
                return json.dumps(
                    {"stance": "concede", "argument": "[MOCK] 상대 신호 농도만으로 확률장을 수렴시키는 "
                     "방식은 실제로 협력 측위(cooperative positioning)의 분산 추정 이론으로 이미 "
                     "정당화된다. 더 반박할 논리가 없다."},
                    ensure_ascii=False,
                )
            return json.dumps(
                {"stance": "reject", "argument": "[MOCK] observation geometry 제약상 상대 위상만으로는 "
                 "절대 좌표계로의 변환이 불확정(under-determined)해진다. 최소 하나의 절대 기준점 없이는 "
                 "이론적으로 성립하지 않는다."},
                ensure_ascii=False,
            )

        if '"stance": "counter"' in system:
            if idea_id == "i2":
                return json.dumps(
                    {"stance": "concede", "argument": "[MOCK] 절대 기준점 없이는 불확정하다는 지적이 "
                     "맞다. 이 형태로는 더 밀어붙일 논리가 없다."},
                    ensure_ascii=False,
                )
            return json.dumps(
                {
                    "stance": "counter",
                    "claim": "[MOCK] 대리 발신 개체 중 최소 1개만 절대 기준(GNSS 앵커)을 유지하고, "
                    "나머지는 신호 중계만 담당하는 하이브리드 구조로 좁힌다.",
                    "argument": "[MOCK] 불확정성 문제는 전원이 상대 위상만 쓸 때의 얘기고, 앵커 1개를 "
                    "고정하면 나머지 개체는 신호 강도가 약해도 대리 중계로 관측 가능성을 유지할 수 있다.",
                },
                ensure_ascii=False,
            )

        if "[기존 유사 사례 유무]" in system:
            return (
                f"[MOCK idea_id={idea_id}] "
                "[기존 유사 사례 유무] 로보틱스의 협력 측위(cooperative localization)와 구조적으로 "
                "유사하지만, '신호 강한 개체가 약한 개체를 대리 발신'하는 역할 분담 구조는 표준 "
                "협력 측위 문헌에서 명시적으로 다루지 않는다.\n"
                "[참신성 판단] 참신함은 '중계 자체를 관측치로 취급'하는 지점에 있다.\n"
                "[보강 제안] 통신 이론의 relay channel 모델을 결합하면 중계 신호의 신뢰도를 "
                "정량화할 수 있다.\n"
                "[검증 필요] relay 개체의 위치 오차가 대리 관측 정확도에 미치는 영향 분석 필요."
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
                        "reasoning": "[MOCK] 대리 관측 구조를 검증할 실측 데이터/벤치마크가 없고, "
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
                    "reasoning": "[MOCK] 협력 측위 이론과 시뮬레이션 벤치마크가 이미 있어 착수 부담이 "
                    "낮다.",
                },
                ensure_ascii=False,
            )

        return "[MOCK] response"
