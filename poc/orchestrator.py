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
    ABSTRACTION_SYSTEM,
    EXTERNAL_ADVISOR_SYSTEM,
    PRACTICAL_SYSTEM,
    DOMAIN_SCOUT_SYSTEM,
    COLD_START_GROUNDING_SYSTEM,
)
from random_domain import draw_random_field

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
    mode: str  # devils_advocate | naive_curiosity
    tactic: str
    seed_claim: str
    grounded_in: str
    final_claim: str
    outcome: str  # passed | discarded | deadlocked
    round_count: int
    rounds: list = field(default_factory=list)


@dataclass
class RunResult:
    scouted: dict = None  # 도메인 스카우트 결과 (target_domain/grounding_text가 입력에 없었을 때만 채워짐)
    seeds: list = field(default_factory=list)
    debates: list = field(default_factory=list)  # DebateResult
    escalations: list = field(default_factory=list)  # {"debate", "advisor", "practical"}
    documented: list = field(default_factory=list)  # subset of escalations that passed practical gate


def abstract_problem(text: str, llm: LLM) -> list:
    """도메인 스카우트/외부자문이 공유하는 단일 책임 컴포넌트.
    검색/판단 없이, 서로 다른 두 각도로 구조만 추상화해서 돌려준다.
    나쁜 추상화가 나와도 이 단계만 다시 돌리면 되고, 뒤이은 검색을
    낭비하지 않는다."""
    user_input = json.dumps({"text": text}, ensure_ascii=False, indent=2)
    raw = llm.complete(ABSTRACTION_SYSTEM, user_input, temperature=0.6)
    return _parse_json_array(raw)


def cold_start_domain(llm: LLM) -> dict:
    """researcher_background조차 없는 완전 콜드 스타트. Abstraction은 벗길
    대상이 없어 무의미하므로 건너뛰고, 진짜 외부 무작위 소스(OECD 학문분류)에서
    세부분야를 뽑은 뒤 그 안의 구체 이론을 실제 검색으로 좁혀 grounding_text를
    만든다."""
    field = draw_random_field()
    ctx = json.dumps(field, ensure_ascii=False, indent=2)
    raw = llm.complete(COLD_START_GROUNDING_SYSTEM, ctx, temperature=0.6, search=True)
    result = _parse_json_object(raw)
    result["random_draw"] = field
    result["target_domain"] = f"{result.get('narrowed_topic', field['subfield'])} ({field['broad_field']})"
    return result


def scout_domain(problem: dict, llm: LLM) -> dict:
    """target_domain/grounding_text가 없을 때, researcher_background를 먼저
    abstract_problem으로 추상화한 뒤, 그 추상화로 도메인 스카우트가 실제
    검색(search=True)해서 낯선 도메인을 스스로 찾는다."""
    abstractions = abstract_problem(problem.get("researcher_background", ""), llm)
    ctx = json.dumps({**problem, "abstractions": abstractions}, ensure_ascii=False, indent=2)
    raw = llm.complete(DOMAIN_SCOUT_SYSTEM, ctx, temperature=0.7, search=True)
    result = _parse_json_object(raw)
    result["abstractions"] = abstractions
    return result


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
                mode=idea.get("mode", ""),
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
                mode=idea.get("mode", ""),
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
        mode=idea.get("mode", ""),
        tactic=idea.get("tactic", ""),
        seed_claim=idea["claim"],
        grounded_in=idea.get("grounded_in", ""),
        final_claim=current_claim,
        outcome="deadlocked",
        round_count=max_rounds,
        rounds=history,
    )


def verify_transfer(debate: DebateResult, advisor_text: str, problem: dict, llm: LLM, max_rounds: int) -> DebateResult:
    """외부자문이 제안한 타 분야 이식을 그냥 통과시키지 않는다. 이론 에이전트는
    타 분야(예: 물류공학) 전문가가 아니라 여전히 원 도메인 전문가일 뿐이므로,
    "그 타 분야 이론이 옳은가"가 아니라 "이 이식이 원 도메인이 이미 아는 제약과
    충돌하는가"를 심사하게 만든다. run_debate()를 그대로 재사용한다 — 외부자문의
    이식 제안을 새로운 claim으로 취급해 같은 이론<->디렉터 논쟁 루프에 태우고,
    디렉터가 그 이식을 방어한다."""
    transfer_idea = {
        "idea_id": f"{debate.idea_id}-transfer",
        "mode": "devils_advocate",
        "tactic": "cross_domain_transfer_check",
        "claim": advisor_text,
        "grounded_in": debate.final_claim,
    }
    # 원래 논쟁보다 짧게 — 여긴 심층 토론이 아니라 상식 충돌 여부만 보는 체크다.
    return run_debate(transfer_idea, problem, llm, min(max_rounds, 6))


def escalate(debate: DebateResult, problem: dict, llm: LLM, max_rounds: int) -> dict:
    # 먼저 논쟁에서 살아남은 final_claim을 별도로 추상화한다 (외부자문 프롬프트
    # 안에 섞어서 시키지 않는다 — 나쁜 추상화면 검색 전에 걸러내야 하므로).
    abstractions = abstract_problem(debate.final_claim, llm)
    ctx = json.dumps(
        {
            "problem": problem,
            "idea_id": debate.idea_id,
            "final_claim": debate.final_claim,
            "outcome": debate.outcome,
            "round_count": debate.round_count,
            "abstractions": abstractions,
        },
        ensure_ascii=False,
        indent=2,
    )
    advisor = llm.complete(EXTERNAL_ADVISOR_SYSTEM, ctx, temperature=0.8, search=True)

    transfer_check = verify_transfer(debate, advisor, problem, llm, max_rounds)
    if transfer_check.outcome == "discarded":
        # 디렉터조차 이 이식을 원 도메인 상식 앞에서 방어 못 했다 -> 실무 게이트로
        # 보내지 않는다. no-go로 착수 계획을 짜는 건 시간 낭비다.
        return {
            "debate": debate,
            "abstractions": abstractions,
            "advisor": advisor,
            "transfer_check": transfer_check,
            "practical": None,
        }

    practical = _parse_json_object(llm.complete(PRACTICAL_SYSTEM, ctx, temperature=0.2))
    return {
        "debate": debate,
        "abstractions": abstractions,
        "advisor": advisor,
        "transfer_check": transfer_check,
        "practical": practical,
    }


def run_pipeline(problem: dict, llm: LLM, max_rounds: int = DEFAULT_MAX_ROUNDS) -> RunResult:
    result = RunResult()

    if not problem.get("target_domain") or not problem.get("grounding_text"):
        if problem.get("researcher_background"):
            scouted = scout_domain(problem, llm)
        else:
            # researcher_background조차 없는 완전 콜드 스타트 -> Abstraction
            # 건너뛰고 진짜 무작위 소스(OECD 학문분류)에서 도메인을 뽑는다.
            scouted = cold_start_domain(llm)
        result.scouted = scouted
        # in-place update so the caller's problem dict (used later for the report) sees it too
        problem["target_domain"] = scouted["target_domain"]
        problem["grounding_text"] = scouted["grounding_text"]

    seeds = generate_seed_ideas(problem, llm)
    result.seeds = seeds

    for seed in seeds:
        debate = run_debate(seed, problem, llm, max_rounds)
        result.debates.append(debate)

    for debate in result.debates:
        if debate.outcome in ("passed", "deadlocked"):
            escalation = escalate(debate, problem, llm, max_rounds)
            result.escalations.append(escalation)
            if escalation["practical"] is not None and escalation["practical"]["verdict"] != "no-go":
                result.documented.append(escalation)

    return result


def to_markdown(problem: dict, result: RunResult, max_rounds: int) -> str:
    lines = []
    lines.append(f"# 연구 주제 탐색 PoC: {problem.get('target_domain', '')}\n")
    lines.append(f"**연구자 배경(회피 대상)**: {problem.get('researcher_background', '')}")
    lines.append(f"**최대 논쟁 라운드**: {max_rounds}\n")

    if result.scouted:
        if "random_draw" in result.scouted:
            lines.append("## -1. 완전 콜드 스타트 (researcher_background도 없어서 진짜 무작위 추첨)\n")
            rd = result.scouted["random_draw"]
            lines.append(f"- 무작위 추첨(OECD 학문분류, random.choice): "
                          f"**{rd['subfield']}** ({rd['broad_field']} 계열)")
            lines.append(f"- 그 안에서 검색으로 좁힌 구체 주제: {result.scouted.get('narrowed_topic', '')}")
            lines.append(f"- 시도한 검색어: {result.scouted.get('search_queries_tried', [])}")
            lines.append(f"- 확정된 도메인: **{result.scouted.get('target_domain', '')}**\n")
        else:
            lines.append("## -1. 도메인 스카우트 (target_domain을 사람이 안 정해줘서 스스로 찾음)\n")
            lines.append("- 구조 추출 (다각도, 별도 Abstraction 단계):")
            for a in result.scouted.get("abstractions", []):
                lines.append(f"  - `[{a.get('angle', '')}]` {a.get('abstraction', '')}")
            lines.append(f"- 시도한 검색어: {result.scouted.get('search_queries_tried', [])}")
            lines.append(f"- 후보 도메인: {result.scouted.get('candidate_domains', [])}")
            lines.append(f"- 확정된 도메인: **{result.scouted.get('target_domain', '')}**\n")

    lines.append("## 0. 디렉터가 던진 시드 아이디어\n")
    for s in result.seeds:
        mode_label = "호기심천국" if s.get("mode") == "naive_curiosity" else "딴지"
        lines.append(
            f"- `[{s['idea_id']}/{mode_label}/{s.get('tactic', '')}]` {s['claim']} "
            f"*(물어뜯은/캐물은 지점: {s.get('grounded_in', '')})*"
        )
    lines.append("")

    lines.append("## 1. 논쟁 결과 요약\n")
    lines.append("| idea_id | mode | tactic | outcome | rounds | final_claim |")
    lines.append("|---|---|---|---|---|---|")
    for d in result.debates:
        mode_label = "호기심천국" if d.mode == "naive_curiosity" else "딴지"
        lines.append(f"| {d.idea_id} | {mode_label} | {d.tactic} | {d.outcome} | {d.round_count} | {d.final_claim} |")
    lines.append("")

    lines.append("## 2. 최종 문서화 (통과된 아이디어만)\n")
    if not result.documented:
        lines.append("*이번 실행에서는 최종 문서화 기준을 통과한 아이디어가 없음.*\n")
    for e in result.documented:
        d = e["debate"]
        tc = e.get("transfer_check")
        lines.append(f"### [{d.idea_id}] {d.final_claim}")
        lines.append(f"- 논쟁 결과: {d.outcome} ({d.round_count}라운드)")
        lines.append("- 구조 추출 (다각도, 별도 Abstraction 단계):")
        for a in e.get("abstractions", []):
            lines.append(f"  - `[{a.get('angle', '')}]` {a.get('abstraction', '')}")
        lines.append(f"- 외부 자문:\n\n{e['advisor']}\n")
        if tc:
            lines.append(f"- 이식 검증(원 도메인 상식 충돌 여부, {tc.round_count}라운드): "
                          f"**{tc.outcome}** — {tc.final_claim[:200]}{'...' if len(tc.final_claim) > 200 else ''}")
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
        tc = e.get("transfer_check")
        reason = "이식 검증 실패로 실무 게이트 자체를 안 감" if e["practical"] is None else "실무 단계 no-go로 최종 제외"
        lines.append(f"### [{d.idea_id}] {d.final_claim} *({reason})*")
        lines.append(f"- 논쟁 결과: {d.outcome} ({d.round_count}라운드)")
        lines.append(f"- 외부 자문:\n\n{e['advisor']}\n")
        if tc:
            lines.append(f"- 이식 검증(원 도메인 상식 충돌 여부, {tc.round_count}라운드): "
                          f"**{tc.outcome}** — {tc.final_claim[:200]}{'...' if len(tc.final_claim) > 200 else ''}")
        if e["practical"] is not None:
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
