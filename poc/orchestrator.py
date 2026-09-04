"""디렉터-이론 논쟁 루프 파이프라인 (v2).

  0) 디렉터가 grounding_text를 보고 완전히 낯선 주장(seed idea) 여러 개를 던짐
  1) 주장마다 이론 <-> 디렉터 논쟁 루프
       - 이론이 물러나면      -> passed
       - 디렉터가 물러나면    -> discarded  (여기서 폐기, 전파 안 됨)
       - max_rounds 도달      -> deadlocked
  2) passed / deadlocked만 외부자문 + 실무·보조 에이전트로 전파
  3) 실무·보조가 no-go 준 것도 최종 문서에서 제외
  4) 최종적으로 살아남은 것만 "문서화" 대상
"""

import json
from dataclasses import dataclass, field

from llm import LLM
from prompts import (
    DIRECTOR_SEED_SYSTEM,
    THEORY_SYSTEM,
    DIRECTOR_DEBATE_SYSTEM,
    EXTERNAL_ADVISOR_SYSTEM,
    PRACTICAL_SYSTEM,
)

DEFAULT_MAX_ROUNDS = 20


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
class DebateResult:
    idea_id: str
    tactic: str
    seed_claim: str
    grounded_in: str
    final_claim: str
    outcome: str  # passed | discarded | deadlocked
    round_count: int
    rounds: list = field(default_factory=list)


@dataclass
class RunResult:
    seeds: list = field(default_factory=list)
    debates: list = field(default_factory=list)  # DebateResult
    escalations: list = field(default_factory=list)  # {"debate", "advisor", "practical"}
    documented: list = field(default_factory=list)  # subset of escalations that passed practical gate


def generate_seed_ideas(problem: dict, llm: LLM) -> list:
    user_input = json.dumps(problem, ensure_ascii=False, indent=2)
    raw = llm.complete(DIRECTOR_SEED_SYSTEM, user_input, temperature=0.9)
    return _parse_json_array(raw)


def run_debate(idea: dict, problem: dict, llm: LLM, max_rounds: int) -> DebateResult:
    history = []
    current_claim = idea["claim"]

    for round_num in range(1, max_rounds + 1):
        theory_ctx = json.dumps(
            {
                "problem": problem,
                "idea_id": idea["idea_id"],
                "current_claim": current_claim,
                "history": history,
            },
            ensure_ascii=False,
            indent=2,
        )
        theory_resp = _parse_json_object(llm.complete(THEORY_SYSTEM, theory_ctx, temperature=0.2))
        history.append({"round": round_num, "role": "theory", **theory_resp})

        if theory_resp["stance"] == "concede":
            return DebateResult(
                idea_id=idea["idea_id"],
                tactic=idea.get("tactic", ""),
                seed_claim=idea["claim"],
                grounded_in=idea.get("grounded_in", ""),
                final_claim=current_claim,
                outcome="passed",
                round_count=round_num,
                rounds=history,
            )

        director_ctx = json.dumps(
            {
                "problem": problem,
                "idea_id": idea["idea_id"],
                "current_claim": current_claim,
                "theory_argument": theory_resp["argument"],
                "history": history,
            },
            ensure_ascii=False,
            indent=2,
        )
        director_resp = _parse_json_object(
            llm.complete(DIRECTOR_DEBATE_SYSTEM, director_ctx, temperature=0.8)
        )
        history.append({"round": round_num, "role": "director", **director_resp})

        if director_resp["stance"] == "concede":
            return DebateResult(
                idea_id=idea["idea_id"],
                tactic=idea.get("tactic", ""),
                seed_claim=idea["claim"],
                grounded_in=idea.get("grounded_in", ""),
                final_claim=current_claim,
                outcome="discarded",
                round_count=round_num,
                rounds=history,
            )

        current_claim = director_resp.get("claim", current_claim)

    return DebateResult(
        idea_id=idea["idea_id"],
        tactic=idea.get("tactic", ""),
        seed_claim=idea["claim"],
        grounded_in=idea.get("grounded_in", ""),
        final_claim=current_claim,
        outcome="deadlocked",
        round_count=max_rounds,
        rounds=history,
    )


def escalate(debate: DebateResult, problem: dict, llm: LLM) -> dict:
    ctx = json.dumps(
        {
            "problem": problem,
            "idea_id": debate.idea_id,
            "final_claim": debate.final_claim,
            "outcome": debate.outcome,
            "round_count": debate.round_count,
        },
        ensure_ascii=False,
        indent=2,
    )
    advisor = llm.complete(EXTERNAL_ADVISOR_SYSTEM, ctx, temperature=0.8)
    practical = _parse_json_object(llm.complete(PRACTICAL_SYSTEM, ctx, temperature=0.2))
    return {"debate": debate, "advisor": advisor, "practical": practical}


def run_pipeline(problem: dict, llm: LLM, max_rounds: int = DEFAULT_MAX_ROUNDS) -> RunResult:
    result = RunResult()

    seeds = generate_seed_ideas(problem, llm)
    result.seeds = seeds

    for seed in seeds:
        debate = run_debate(seed, problem, llm, max_rounds)
        result.debates.append(debate)

    for debate in result.debates:
        if debate.outcome in ("passed", "deadlocked"):
            escalation = escalate(debate, problem, llm)
            result.escalations.append(escalation)
            if escalation["practical"]["verdict"] != "no-go":
                result.documented.append(escalation)

    return result


def to_markdown(problem: dict, result: RunResult, max_rounds: int) -> str:
    lines = []
    lines.append(f"# 연구 주제 탐색 PoC: {problem.get('target_domain', '')}\n")
    lines.append(f"**연구자 배경(회피 대상)**: {problem.get('researcher_background', '')}")
    lines.append(f"**최대 논쟁 라운드**: {max_rounds}\n")

    lines.append("## 0. 디렉터가 던진 시드 아이디어\n")
    for s in result.seeds:
        lines.append(
            f"- `[{s['idea_id']}/{s.get('tactic', '')}]` {s['claim']} "
            f"*(물어뜯은 지점: {s.get('grounded_in', '')})*"
        )
    lines.append("")

    lines.append("## 1. 논쟁 결과 요약\n")
    lines.append("| idea_id | tactic | outcome | rounds | final_claim |")
    lines.append("|---|---|---|---|---|")
    for d in result.debates:
        lines.append(f"| {d.idea_id} | {d.tactic} | {d.outcome} | {d.round_count} | {d.final_claim} |")
    lines.append("")

    lines.append("## 2. 최종 문서화 (통과된 아이디어만)\n")
    if not result.documented:
        lines.append("*이번 실행에서는 최종 문서화 기준을 통과한 아이디어가 없음.*\n")
    for e in result.documented:
        d = e["debate"]
        lines.append(f"### [{d.idea_id}] {d.final_claim}")
        lines.append(f"- 논쟁 결과: {d.outcome} ({d.round_count}라운드)")
        lines.append(f"- 외부 자문:\n\n{e['advisor']}\n")
        lines.append("- 실무·보조 평가:")
        lines.append("```json")
        lines.append(json.dumps(e["practical"], ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")

    lines.append("---\n")
    lines.append("## 내부 트레이스 (비공식, 문서화 대상 아님)\n")
    lines.append("*discarded는 애초에 외부자문으로 전파되지 않아 논쟁 기록만 남는다. "
                  "escalate까지 갔지만 실무 단계에서 no-go로 걸러진 건은 외부자문이 어떤 전공을 "
                  "골랐는지까지 그대로 남긴다 — 디버깅/검토용이며 공식 산출물에는 포함되지 않음.*\n")

    documented_ids = {e["debate"].idea_id for e in result.documented}
    escalated_but_filtered = [e for e in result.escalations if e["debate"].idea_id not in documented_ids]

    for e in escalated_but_filtered:
        d = e["debate"]
        lines.append(f"### [{d.idea_id}] {d.final_claim} *(실무 단계 no-go로 최종 제외)*")
        lines.append(f"- 논쟁 결과: {d.outcome} ({d.round_count}라운드)")
        lines.append(f"- 외부 자문:\n\n{e['advisor']}\n")
        lines.append("- 실무·보조 평가:")
        lines.append("```json")
        lines.append(json.dumps(e["practical"], ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")

    escalated_ids = {e["debate"].idea_id for e in result.escalations}
    for d in result.debates:
        if d.idea_id in escalated_ids:
            continue
        lines.append(f"- `[{d.idea_id}]` discarded (디렉터가 물러남, 외부자문에 전파되지 않음) / "
                      f"최종 주장: {d.final_claim}")
    lines.append("")

    return "\n".join(lines)
