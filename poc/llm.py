"""LLM 호출 wrapper. ANTHROPIC_API_KEY가 있으면 실제 Claude를 호출하고,
없거나 --mock이 지정되면 결정적인 더미 응답을 돌려줘서 파이프라인 구조를
API 키 없이도 확인할 수 있게 한다."""

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

    def _mock_response(self, system: str, user: str) -> str:
        """실제 API 키 없이 파이프라인 흐름을 검증하기 위한 더미 응답.
        system prompt의 역할별 시그니처 문자열로 분기한다."""
        if '"stage"' in system or "why_definition" in system:
            return json.dumps(
                [
                    {
                        "stage": "현재_접근",
                        "type": "why_method",
                        "question": "[MOCK] 왜 신호 누락 구간을 '복원'의 문제로 정의했는가? "
                        "복원이 아니라 다른 관측치로부터 위치를 재계산하는 방식은 고려했는가?",
                    },
                    {
                        "stage": "비슷한_문제",
                        "type": "other_field",
                        "question": "[MOCK] 다른 분야에서는 '부분 관측 상태에서의 상태 추정' 문제를 "
                        "어떻게 다루는가?",
                    },
                ],
                ensure_ascii=False,
            )
        if "탕아" in system and "origin_question" in system:
            return json.dumps(
                [
                    {
                        "title": "[MOCK] 신호 복원 대신 보조 센서 퓨전으로 위치 직접 재계산",
                        "origin_question": "왜 신호 누락 구간을 '복원'의 문제로 정의했는가?",
                        "source": "both",
                        "direction": "GNSS 음영 구간에서 신호를 복원하려 하지 말고, IMU/기압계 등 "
                        "보조 센서를 결합한 관측 벡터 확장으로 위치를 직접 추정한다. "
                        "전문가가 지적한 observation geometry 제약은 여전히 유효하므로, "
                        "관측 가능성 조건을 만족하는 최소 센서 조합을 먼저 규명하는 것을 "
                        "선행 과제로 삼는다.",
                    }
                ],
                ensure_ascii=False,
            )
        if "탈도메인화" in system:
            return (
                "[탈도메인화] (MOCK) 부분 관측 상태에서의 결측치 보간 및 상태 추정\n"
                "[후보 도메인] (MOCK) 1) 로보틱스의 센서 퓨전(칼만 필터 계열) "
                "2) 생태학의 개체수 결측 구간 추정 3) 심리학 FACS의 부분 표정 정보로부터 "
                "전체 정서 상태 추론\n"
                "[이식 제안] (MOCK) 신호 자체를 복원하지 말고, 다른 관측 채널(가속도계, "
                "기압계 등)을 이용한 센서 퓨전으로 위치를 직접 재계산하는 방식을 제안.\n"
                "[검증 필요] (MOCK) 해당 센서 퓨전 기법이 실제 GNSS 음영 구간 데이터에서도 "
                "관측 가능성을 만족하는지 확인 필요."
            )
        if "observation geometry" in system or "전문가" in system:
            return (
                "[MOCK] 현재 PNT 구조에서는 observation geometry 제약 때문에 위성 신호 수가 "
                "부족한 구간에서는 위치 계산 방식을 바꿔도 근본적인 관측 가능성(observability) "
                "문제는 해결되지 않는다. 다만 보조 센서를 결합해 관측 벡터를 확장하는 조건부 "
                "완화는 가능하다."
            )
        if '"verdict"' in system:
            return json.dumps(
                {
                    "data": "partial",
                    "benchmark": "available",
                    "implementation_time": "8h",
                    "evaluation_metric": "available",
                    "domain_dependency": "high",
                    "risk": "medium",
                    "verdict": "conditional",
                    "reasoning": "[MOCK] 센서 퓨전 이식 자체는 표준 기법이라 구현 부담은 낮지만, "
                    "실측 데이터 확보 여부에 따라 조건부.",
                },
                ensure_ascii=False,
            )
        return "[MOCK] response"
