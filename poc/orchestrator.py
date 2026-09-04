"""1번 탕아 에이전트를 핵심으로 하는 파이프라인.

흐름:
  1) Agent1: path_dependency를 보고 도발적 질문들을 생성 (JSON, type 태깅됨)
  2) 라우팅: type에 따라 질문을 Agent2(전문가) 또는 Agent3(모르긴 몰라도)로 전달
     - why_definition / why_method / variable_doubt -> Agent2 (정식 이론 반박)
     - inversion / other_field                       -> Agent3 (타 분야 유추)
  3) Agent1: 반박/유추 결과를 종합해 살아남은 연구 방향 후보를 정리
  4) Agent4: 각 후보를 feasibility config로 평가
"""

import json
from dataclasses import dataclass, field

from llm import LLM
from prompts import (
    AGENT1_SYSTEM,
    AGENT1_SYNTHESIZE_SYSTEM,
    AGENT2_SYSTEM,
    AGENT3_SYSTEM,
    AGENT4_SYSTEM,
)

ROUTE_TO_AGENT2 = {"why_definition", "why_method", "variable_doubt"}
ROUTE_TO_AGENT3 = {"inversion", "other_field"}


def _parse_json_array(text: str):
    text = text.strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        raise ValueError(f"JSON 배열을 찾지 못함: {text[:200]}")
    return json.loads(text[start : end + 1])


def _parse_json_object(text: str):
    text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"JSON 객체를 찾지 못함: {text[:200]}")
    return json.loads(text[start : end + 1])


@dataclass
class RunResult:
    challenges: list = field(default_factory=list)
    advisor_responses: list = field(default_factory=list)
    directions: list = field(default_factory=list)
    evaluations: list = field(default_factory=list)


def run_pipeline(problem: dict, llm: LLM) -> RunResult:
    result = RunResult()

    # 1) Agent1 - 질문 생성
    user_input = json.dumps(problem, ensure_ascii=False, indent=2)
    raw_challenges = llm.complete(AGENT1_SYSTEM, user_input, temperature=0.7)
    challenges = _parse_json_array(raw_challenges)
    result.challenges = challenges

    # 2) 라우팅 -> Agent2 / Agent3
    for ch in challenges:
        qtype = ch.get("type")
        question_ctx = json.dumps(
            {"problem": problem, "question": ch}, ensure_ascii=False, indent=2
        )
        if qtype in ROUTE_TO_AGENT2:
            answer = llm.complete(AGENT2_SYSTEM, question_ctx, temperature=0.25)
            advisor = "agent2_expert"
        elif qtype in ROUTE_TO_AGENT3:
            answer = llm.complete(AGENT3_SYSTEM, question_ctx, temperature=0.9)
            advisor = "agent3_cross_domain"
        else:
            # 알 수 없는 type은 둘 다에게 물어 안전하게 처리
            answer = llm.complete(AGENT2_SYSTEM, question_ctx, temperature=0.25)
            advisor = "agent2_expert"
        result.advisor_responses.append(
            {"question": ch, "advisor": advisor, "answer": answer}
        )

    # 3) Agent1 - 종합
    synth_input = json.dumps(
        {"problem": problem, "advisor_responses": result.advisor_responses},
        ensure_ascii=False,
        indent=2,
    )
    raw_directions = llm.complete(AGENT1_SYNTHESIZE_SYSTEM, synth_input, temperature=0.6)
    result.directions = _parse_json_array(raw_directions)

    # 4) Agent4 - feasibility 평가
    for d in result.directions:
        eval_input = json.dumps({"problem": problem, "direction": d}, ensure_ascii=False, indent=2)
        raw_eval = llm.complete(AGENT4_SYSTEM, eval_input, temperature=0.2)
        evaluation = _parse_json_object(raw_eval)
        result.evaluations.append({"direction": d, "evaluation": evaluation})

    return result


def to_markdown(problem: dict, result: RunResult) -> str:
    lines = []
    lines.append(f"# PoC 실행 결과: {problem.get('problem_domain', '')}\n")
    lines.append(f"**현재 접근**: {problem.get('current_approach', '')}\n")

    lines.append("## 1. 탕아(Agent1)가 던진 질문\n")
    for ch in result.challenges:
        lines.append(f"- `[{ch.get('stage')}/{ch.get('type')}]` {ch.get('question')}")
    lines.append("")

    lines.append("## 2. 외부 자문 응답\n")
    for r in result.advisor_responses:
        q = r["question"]
        lines.append(f"### Q. {q.get('question')}")
        lines.append(f"*(라우팅: {r['advisor']})*\n")
        lines.append(r["answer"])
        lines.append("")

    lines.append("## 3. 종합된 후보 연구 방향 (Agent1)\n")
    for d in result.directions:
        lines.append(f"### {d.get('title')}")
        lines.append(f"- 근거 질문: {d.get('origin_question')}")
        lines.append(f"- 출처: {d.get('source')}")
        lines.append(f"- 방향: {d.get('direction')}")
        lines.append("")

    lines.append("## 4. 실현 가능성 평가 (Agent4)\n")
    for e in result.evaluations:
        title = e["direction"].get("title")
        ev = e["evaluation"]
        lines.append(f"### {title}")
        lines.append("```json")
        lines.append(json.dumps(ev, ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")

    return "\n".join(lines)
