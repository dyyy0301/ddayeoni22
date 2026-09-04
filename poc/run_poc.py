#!/usr/bin/env python3
"""디렉터-이론 논쟁 루프 PoC 실행 스크립트.

사용법:
  ANTHROPIC_API_KEY=... python3 run_poc.py examples/new_domain_exploration.json
  python3 run_poc.py examples/new_domain_exploration.json --mock   # API 키 없이 구조만 확인
  python3 run_poc.py examples/new_domain_exploration.json --mock --max-rounds 3
"""

import argparse
import json
import sys

from llm import LLM, DEFAULT_MODEL
from orchestrator import run_pipeline, to_markdown, DEFAULT_MAX_ROUNDS


def main():
    parser = argparse.ArgumentParser(description="디렉터(1번 에이전트) 핵심 PoC 파이프라인 실행")
    parser.add_argument("input", help="탐색 문제 정의 JSON 파일 경로")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--mock", action="store_true", help="API 호출 없이 더미 응답으로 구조 검증")
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=None,
        help=f"이론<->디렉터 논쟁 라운드 상한 (입력 파일의 max_rounds보다 우선, 기본 {DEFAULT_MAX_ROUNDS})",
    )
    parser.add_argument("-o", "--out", default=None, help="마크다운 결과 저장 경로 (생략 시 stdout)")
    args = parser.parse_args()

    with open(args.input, encoding="utf-8") as f:
        problem = json.load(f)

    max_rounds = args.max_rounds or problem.get("max_rounds") or DEFAULT_MAX_ROUNDS

    llm = LLM(model=args.model, mock=args.mock)
    if llm.mock:
        print("[info] mock 모드로 실행합니다 (ANTHROPIC_API_KEY 미설정 또는 --mock).", file=sys.stderr)

    result = run_pipeline(problem, llm, max_rounds=max_rounds)
    report = to_markdown(problem, result, max_rounds)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"[info] 저장 완료: {args.out}", file=sys.stderr)
    else:
        print(report)


if __name__ == "__main__":
    main()
