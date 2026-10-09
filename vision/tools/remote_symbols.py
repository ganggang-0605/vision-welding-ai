"""기호 검출 평가(eval_symbols.py)를 Claude Managed Agents에서 실행 — remote_eval.py와 같은 환경·에이전트를 씀

GroundingDINO 실험 기록 재현용 (결과: vision/reports/phase3_groundingdino.md, 세션 sesn_01MWxQ…)

코드와 함께 정답(data/annotations)과 거기에 적힌 사진(data/raw, 저장소에 없음)을 올림.
비용은 .env 의 ANTHROPIC_API_KEY 계정에서 나가고, 세션마다 예산 상한을 검.

사용:
  backend/.venv/bin/python vision/tools/remote_symbols.py      # tiny·base × simple·descriptive 4가지, 예산 $5
  backend/.venv/bin/python vision/tools/remote_symbols.py --eval "--prompts simple" --eval "--prompts descriptive --text-threshold 0.15"
  --eval 은 eval_symbols.py 인자 묶음 (--out·--draw는 자동으로 붙임)
결과: vision/reports/runs/remote/<session_id>/ (평가 JSON, 상자를 그린 사진, 설치·실행 로그)
"""
import argparse
import io
import json
import sys
import tarfile
import time
from pathlib import Path

import anthropic

from remote_eval import ROOT, download_outputs, ensure_env_and_agent, load_key, pack_code, stream_until_idle

ANNOTATIONS = ROOT / "data" / "annotations"
TINY, BASE = "IDEA-Research/grounding-dino-tiny", "IDEA-Research/grounding-dino-base"
DEFAULT_EVALS = [
    f"--model {TINY} --prompts simple",
    f"--model {TINY} --prompts descriptive",
    f"--model {BASE} --prompts simple",
    f"--model {BASE} --prompts descriptive",
]

TASK = """Run these steps in order with bash.

1. Environment report: `python3 --version; nproc; (free -h || head -3 /proc/meminfo); df -h /workspace | tail -1`
2. Extract the code and data: `mkdir -p /workspace/repo && tar -xzf /mnt/session/uploads/code.tar.gz -C /workspace/repo && tar -xzf /mnt/session/uploads/data.tar.gz -C /workspace/repo && ls /workspace/repo/data/annotations | wc -l`
3. If python3 is 3.12 or newer, run `python3 -m venv /workspace/venv`. Otherwise run `pip install -q uv && uv venv -p 3.12 /workspace/venv` (then install packages with `uv pip install --python /workspace/venv/bin/python ...`). Use PY=/workspace/venv/bin/python from here on.
4. Install the CPU-only torch build first, then the rest, logging to /tmp/pip.log: `$PY -m pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu > /tmp/pip.log 2>&1; $PY -m pip install -e /workspace/repo/shared -e /workspace/repo/vision transformers==5.19.0 pillow >> /tmp/pip.log 2>&1; tail -3 /tmp/pip.log`. Do NOT install paddlepaddle or paddleocr. If importing cv2 later fails on libGL/libglib, run `apt-get update -qq && apt-get install -y -qq libgl1 libglib2.0-0 > /tmp/apt.log 2>&1`.
5. Run each evaluation below in order, from /workspace/repo. The first run of each model downloads it from Hugging Face. Time each one. If a command could exceed your tool time limit, start it with nohup in the background and poll every 60 seconds until its output JSON exists. Print only the "by_label" → "any" and the "sec_per_image_mean" parts of each result.
{evals}
6. `mkdir -p /mnt/session/outputs/logs && cp /tmp/pip.log /tmp/apt.log /tmp/eval*.log /mnt/session/outputs/logs/ 2>/dev/null; ls /mnt/session/outputs | head -50`
7. Reply with a short summary: Python version, CPU count, RAM, and for each evaluation its wall time in seconds, sec_per_image_mean, and for each label its "gt" count, "ap@0.5" and "ap@0.3" (or the error if a step failed)."""


def build_task(evals: list[str]) -> str:
    lines = []
    for i, e in enumerate(evals, 1):
        lines.append(f"   {i}. `$PY vision/tools/eval_symbols.py {e} --draw --out /mnt/session/outputs/sym{i}.json 2>/tmp/eval{i}.log`")
    return TASK.format(evals="\n".join(lines))


def pack_data() -> tuple[bytes, int]:
    """정답 JSON과 거기에 적힌 사진만 (data/raw 의 다른 데이터셋은 올리지 않음)"""
    buf, n = io.BytesIO(), 0
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for path in sorted(ANNOTATIONS.glob("*.json")):
            image = ROOT / "data" / "raw" / json.loads(path.read_text(encoding="utf-8"))["image"]
            if not image.exists():
                sys.exit(f"사진이 없습니다: {image.relative_to(ROOT)} ({path.name})")
            tar.add(path, arcname=str(path.relative_to(ROOT)))
            tar.add(image, arcname=str(image.relative_to(ROOT)))
            n += 1
    return buf.getvalue(), n


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--eval", action="append", help="eval_symbols.py 인자 묶음, 여러 번 가능 (기본: tiny·base × simple·descriptive)")
    parser.add_argument("--budget", type=float, default=5.0, help="이 세션의 지출 상한 (달러)")
    args = parser.parse_args()

    evals = args.eval or DEFAULT_EVALS
    load_key()
    client = anthropic.Anthropic()
    env_id, agent_id, agent_version = ensure_env_and_agent(client)

    code = pack_code()
    data, n_images = pack_data()
    code_file = client.beta.files.upload(file=("code.tar.gz", code, "application/gzip"))
    data_file = client.beta.files.upload(file=("data.tar.gz", data, "application/gzip"))
    print(f"올림: 코드 {len(code) / 1024:.0f} KB · 정답과 사진 {n_images}장 {len(data) / 1024:.0f} KB")

    session = client.beta.sessions.create(
        agent={"type": "agent", "id": agent_id, "version": agent_version},
        environment_id=env_id,
        title="Symbol eval: " + " | ".join(evals),
        resources=[
            {"type": "file", "file_id": code_file.id, "mount_path": "/code.tar.gz"},
            {"type": "file", "file_id": data_file.id, "mount_path": "/data.tar.gz"},
        ],
        budget={"type": "limit", "max_list_cost": {"amount": str(round(args.budget * 100)), "currency": "USD"}},
    )
    print(f"세션: {session.id}  (콘솔에서 보기: https://platform.claude.com/workspaces/default/sessions/{session.id})")

    started = time.monotonic()
    stop = stream_until_idle(client, session.id, build_task(evals))
    print(f"\n멈춘 이유: {stop}  ·  걸린 시간 {time.monotonic() - started:.0f}초")

    dest = download_outputs(client, session.id)
    usage = client.beta.sessions.retrieve(session_id=session.id).usage
    cost = usage.list_cost
    summary = {
        "session_id": session.id,
        "evals": evals,
        "stop_reason": stop,
        "list_cost_usd": int(cost.amount) / 100 if cost else None,
        "active_seconds": usage.active_seconds,
        "usage": usage.model_dump(mode="json"),
    }
    (dest / "session_usage.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"비용(정가 기준): ${summary['list_cost_usd']}  ·  컨테이너 실행 {usage.active_seconds}초")
    return 0 if stop == "end_turn" else 1


if __name__ == "__main__":
    sys.exit(main())
