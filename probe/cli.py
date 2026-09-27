"""Command line entry point.

    python -m probe.cli health
    python -m probe.cli score --path C:\\Claude\\SongYUE2\\runs\\<id>
    python -m probe.cli score --map stages.json --control control.json --save
    python -m probe.cli serve
"""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .audioio import AudioToolError
from .config import REPORTS_DIR
from .detectors import describe as describe_detectors
from .report import analyze, save, to_json, with_chain_flags
from .stages import StageError, load as load_stage_set

VERDICT_LABEL = {
    "chain-dominant": "체인 부작용",
    "chain-dominant-inverse": "체인 부작용(역방향)",
    "content-specific": "콘텐츠 고유",
    "mixed": "혼합",
}

FLAG_ICON = {"error": "[X]", "warn": "[!]", "info": "[i]"}


def _print_health(_args: argparse.Namespace | None = None) -> int:
    import shutil as _shutil

    print(f"ai-music-probe {__version__}")
    missing_tools = [tool for tool in ("ffmpeg", "ffprobe") if _shutil.which(tool) is None]
    print(f"  ffmpeg : {'ok' if 'ffmpeg' not in missing_tools else 'MISSING'}")
    print(f"  ffprobe: {'ok' if 'ffprobe' not in missing_tools else 'MISSING'}")
    print("  탐지기:")
    for detector in describe_detectors():
        mark = "ok " if detector["available"] else "-- "
        print(f"    [{mark}] {detector['label']}  ({detector['license']})")
        if not detector["available"]:
            print(f"           {detector['reason']}")
    if missing_tools:
        # Unavailable detectors are a valid configuration, so they are reported
        # but do not fail the check; a missing decoder breaks every analysis.
        print(f"\n필수 도구 없음: {', '.join(missing_tools)}", file=sys.stderr)
        return 1
    return 0


def _print_report(report: dict) -> None:
    target = report["target"]
    stages = target["stages"]
    print(f"\n[{target['name']}]  {len(stages)}개 stage")
    print(f"{'stage':<18}{'rate':>8}{'codec':>12}{'dur':>8}{'tilt':>9}{'null':>9}{'peaks':>7}")
    for item in stages:
        profile = item["profile"]
        meta = profile["meta"]
        spectral = profile["spectral"]
        null_hz = spectral["digitalNullHz"]
        print(
            f"{item['stage']:<18}{meta['sampleRate']:>8}{meta['codec']:>12}"
            f"{meta['durationS']:>8.1f}{spectral['tiltDbPerOctave']:>9.2f}"
            f"{(null_hz if null_hz else 0):>9.0f}{len(profile['artifactFingerprint']):>7}"
        )

    peaks = target.get("peakDiff") or {}
    if peaks.get("added") or peaks.get("removed"):
        print(f"\nartifact peak 위치 변화 (±{peaks.get('toleranceHz')}Hz)")
        if peaks.get("added"):
            print(f"  추가됨: {peaks['added']}")
        if peaks.get("removed"):
            print(f"  사라짐: {peaks['removed']}")

    decomposition = report.get("chainDecomposition") or {}
    ranked = sorted(
        (kv for kv in decomposition.items() if not kv[0].startswith("_")),
        key=lambda kv: abs(kv[1]["targetChange"]),
        reverse=True,
    )
    if ranked:
        print(f"\n변화가 큰 지표 상위 12개")
        print(f"{'지표':<40}{'대상':>10}{'대조군':>10}{'비율':>8}  판정")
        for path, entry in ranked[:12]:
            print(
                f"{path:<40}{entry['targetChange']:>10.2f}{entry['controlChange']:>10.2f}"
                f"{entry['chainFloorRatio']:>8.2f}  {VERDICT_LABEL.get(entry['verdict'], entry['verdict'])}"
            )
        print("\n비율 = |대조군 변화| / |대상 변화|. 1.0에 가까우면 체인 부작용으로 설명됩니다.")
    else:
        print("\n[주의] 대조군이 없어 변화의 원인을 구분할 수 없습니다. --control 을 쓰세요.")

    flags = report.get("flags") or []
    if flags:
        print("\n플래그")
        for flag in flags:
            print(f"  {FLAG_ICON.get(flag['level'], '[?]')} {flag['message']}")
    print()


def _cmd_score(args: argparse.Namespace) -> int:
    try:
        target = load_stage_set(args.map if args.map else args.path)
        control = load_stage_set(args.control) if args.control else None
    except StageError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2
    if args.name:
        target = type(target)(name=args.name, stages=target.stages)
    if args.control_name and control is not None:
        control = type(control)(name=args.control_name, stages=control.stages)

    try:
        report = with_chain_flags(analyze(target, control))
    except AudioToolError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2

    _print_report(report)
    if args.json:
        print(to_json(report))
    if args.save:
        stamp = report["generatedAt"].replace(":", "").replace("-", "")
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in target.name)[:60] or "report"
        out = REPORTS_DIR / f"{stamp}-{safe}.json"
        print(f"저장됨: {save(report, out)}")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .app import app

    print(f"ai-music-probe {__version__}  ->  http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="probe", description="단계별 오디오 DSP 핑거프린트 분석")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("health", help="외부 도구와 탐지기 가용성 확인").set_defaults(func=_print_health)

    score = sub.add_parser("score", help="stage 집합 분석")
    source = score.add_mutually_exclusive_group(required=True)
    source.add_argument("--path", help="run 디렉터리 또는 오디오가 든 폴더")
    source.add_argument("--map", help="stage 맵 JSON 파일")
    score.add_argument("--control", help="대조군 stage 맵 JSON 또는 폴더")
    score.add_argument("--name", help="대상 이름")
    score.add_argument("--control-name", help="대조군 이름")
    score.add_argument("--json", action="store_true", help="JSON 전체 출력")
    score.add_argument("--save", action="store_true", help="reports/ 에 저장")
    score.set_defaults(func=_cmd_score)

    serve = sub.add_parser("serve", help="API + UI 서버 실행")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8792)
    serve.add_argument("--log-level", default="info")
    serve.set_defaults(func=_cmd_serve)
    return parser


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to a legacy codepage, which mangles the Korean
    # labels this CLI prints.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
