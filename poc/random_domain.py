"""진짜 무(無)에서 시작하는 콜드 스타트용 무작위 도메인 추첨.

target_domain을 사람이 정해주지 않으면 이 모듈이 도메인 선택의 유일한
경로다. LLM에게 "창의적으로 무작위 도메인 하나 골라봐"라고 시키면
실제로는 학습 데이터에서 자주 본 클리셰(양자역학/카오스이론 같은)로
수렴하는 걸 실측으로 확인했다 — 그래서 그런 방식에 기대지 않고, 진짜
외부 무작위 소스에서 도메인을 뽑는다.

OECD Revised Field of Science and Technology (FOS) Classification (2007)의
6대 분야 42개 세부분야를 그대로 사용한다 — 임의로 지어낸 목록이 아니라
국제적으로 통용되는 학문분류 표준이다.
"""

import random

# OECD FOS 2007 classification, 6 broad fields -> 42 subfields
OECD_FIELDS_OF_SCIENCE = {
    "Natural sciences": [
        "Mathematics",
        "Computer and information sciences",
        "Physical sciences",
        "Chemical sciences",
        "Earth and related environmental sciences",
        "Biological sciences",
        "Other natural sciences",
    ],
    "Engineering and technology": [
        "Civil engineering",
        "Electrical, electronic and information engineering",
        "Mechanical engineering",
        "Chemical engineering",
        "Materials engineering",
        "Medical engineering",
        "Environmental engineering",
        "Environmental biotechnology",
        "Industrial biotechnology",
        "Nanotechnology",
        "Other engineering and technologies",
    ],
    "Medical and health sciences": [
        "Basic medicine",
        "Clinical medicine",
        "Health sciences",
        "Health biotechnology",
        "Other medical sciences",
    ],
    "Agricultural sciences": [
        "Agriculture, forestry, and fisheries",
        "Animal and dairy science",
        "Veterinary science",
        "Agricultural biotechnology",
        "Other agricultural sciences",
    ],
    "Social sciences": [
        "Psychology",
        "Economics and business",
        "Educational sciences",
        "Sociology",
        "Law",
        "Political science",
        "Social and economic geography",
        "Media and communications",
        "Other social sciences",
    ],
    "Humanities": [
        "History and archaeology",
        "Languages and literature",
        "Philosophy, ethics and religion",
        "Arts (arts, history of arts, performing arts, music)",
        "Other humanities",
    ],
}

_ALL_SUBFIELDS = [
    (broad, sub) for broad, subs in OECD_FIELDS_OF_SCIENCE.items() for sub in subs
]


def draw_random_field(exclude_broad: set | None = None) -> dict:
    """OECD FOS 42개 세부분야 중 하나를 진짜 무작위(random.choice)로 뽑는다.
    exclude_broad에 넘긴 상위 계열은 후보에서 제외한다 (예: 연구자 본인
    분야의 상위 계열을 제외해서 최소한의 거리를 보장하고 싶을 때)."""
    candidates = _ALL_SUBFIELDS
    if exclude_broad:
        candidates = [(b, s) for b, s in _ALL_SUBFIELDS if b not in exclude_broad]
    broad, sub = random.choice(candidates)
    return {"broad_field": broad, "subfield": sub}
