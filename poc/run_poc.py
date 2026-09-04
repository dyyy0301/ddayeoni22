#!/usr/bin/env python3
"""1번(탕아) 에이전트 PoC 실행 스크립트.

사용법:
  ANTHROPIC_API_KEY=... python3 run_poc.py examples/pnt_signal_recovery.json
  python3 run_poc.py examples/pnt_signal_recovery.json --mock   # API 키 없이 구조만 확인
"""

import argparse
import json
import sys

from llm import LLM, DEFAULT_MODEL
from orchestrator import run_pipeline, to_markdown


def main():
    parser = argparse.ArgumentParser(description="Agent1(탕아) 핵심 PoC 파이프라인 실행")
    parser.add_argument("input", help="문제 정의 JSON 파일 경로")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--mock", action="store_true", help="API 호출 없이 더미 응답으로 구조 검증")
    parser.add_argument("-o", "--out", default=None, help="마크다운 결과 저장 경로 (생략 시 stdout)")
    args = parser.parse_args()

    with open(args.input, encoding="utf-8") as f:
        problem = json.load(f)

    llm = LLM(model=args.model, mock=args.mock)
    if llm.mock:
        print("[info] mock 모드로 실행합니다 (ANTHROPIC_API_KEY 미설정 또는 --mock).", file=sys.stderr)

    result = run_pipeline(problem, llm)
    report = to_markdown(problem, result)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"[info] 저장 완료: {args.out}", file=sys.stderr)
    else:
        print(report)


if __name__ == "__main__":
    main()
