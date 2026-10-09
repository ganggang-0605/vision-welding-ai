"""문자 인식 평가를 Claude Managed Agents(Anthropic 서버의 컨테이너)에서 실행 — 이 컴퓨터는 코드를 올리고 결과만 받음

비용은 .env 의 ANTHROPIC_API_KEY 계정에서 나감 (Claude 토큰 + 컨테이너 실행 시간). 세션마다 예산 상한을 걸어 그 이상 쓰지 않음.

사용:
  backend/.venv/bin/python vision/tools/remote_eval.py                # 10장 시험, 예산 $5
  backend/.venv/bin/python vision/tools/remote_eval.py --limit 0 --budget 10   # 110장 전체
결과: vision/reports/runs/remote/<session_id>/ (eval JSON, 설치·실행 로그)
"""
import argparse
import io
import json
import os
import sys
import tarfile
import time
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "vision" / "reports" / "runs" / "remote"
STATE = OUT_DIR / "state.json"  # 다시 쓰는 환경·에이전트 ID
ENV_NAME = "vision-welding-ocr-eval"
AGENT_NAME = "vision-welding-ocr-eval-runner"
MODEL = "claude-opus-5-5"

# 컨테이너로 보낼 코드 (데이터·비밀·생성물 제외)
CODE_DIRS = ["shared", "vision"]
EXCLUDE = {"__pycache__", ".pytest_cache", "reports", ".venv", "node_modules"}

SYSTEM = """You run evaluation jobs for the vision-welding-ai repository inside this sandbox.
Follow the user's steps exactly and do not modify the repository code.
Keep tool output short: redirect long output (pip, downloads, evaluation stderr) to log files under /tmp and print only the last lines.
If a step fails, make at most one reasonable fix attempt, then stop and report the error instead of retrying in a loop."""

TASK = """Run these steps in order with bash.

1. Environment report: `python3 --version; nproc; (free -h || head -3 /proc/meminfo); df -h /workspace | tail -1`
2. Extract the code: `mkdir -p /workspace/repo && tar -xzf /mnt/session/uploads/code.tar.gz -C /workspace/repo`
3. PaddlePaddle needs Python 3.12. If python3 is 3.12, run `python3 -m venv /workspace/venv`. Otherwise run `pip install -q uv && uv venv -p 3.12 /workspace/venv` (then install packages with `uv pip install --python /workspace/venv/bin/python ...`). Use PY=/workspace/venv/bin/python from here on.
4. Install, logging to /tmp/pip.log: `$PY -m pip install -e /workspace/repo/shared -e /workspace/repo/vision paddlepaddle==3.3.1 paddleocr==3.7.0 huggingface_hub > /tmp/pip.log 2>&1; tail -3 /tmp/pip.log`. Do NOT install torch. If importing paddleocr later fails on libGL/libglib, run `apt-get update -qq && apt-get install -y -qq libgl1 libglib2.0-0 > /tmp/apt.log 2>&1`.
5. Download the dataset, logging to /tmp/hf.log: `$PY -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='Hoshino121/steel-ocr-dataset', repo_type='dataset', local_dir='/workspace/repo/data/raw/external/steel-ocr')" > /tmp/hf.log 2>&1; tail -2 /tmp/hf.log`
6. Evaluate and time it: `cd /workspace/repo && date +%s > /tmp/start && PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True $PY vision/tools/eval_ocr.py {eval_args} --out /mnt/session/outputs/{result_name} 2>/tmp/eval.log | tail -20; echo "seconds: $(( $(date +%s) - $(cat /tmp/start) ))"`
7. `mkdir -p /mnt/session/outputs/logs && cp /tmp/uv.log /tmp/pip.log /tmp/apt.log /tmp/hf.log /tmp/eval*.log /mnt/session/outputs/logs/ 2>/dev/null; ls /mnt/session/outputs/logs`
8. Reply with a short summary: Python version, CPU count, RAM, evaluation wall time in seconds, and the "summary" numbers from step 6 (or the error if a step failed)."""


def load_key() -> None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    if not os.getenv("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY가 없습니다 (저장소 루트 .env)")


def pack_code() -> bytes:
    def skip(info: tarfile.TarInfo):
        parts = Path(info.name).parts
        if any(p in EXCLUDE or p.endswith(".egg-info") for p in parts):
            return None
        return info

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for d in CODE_DIRS:
            tar.add(ROOT / d, arcname=d, filter=skip)
    return buf.getvalue()


def ensure_env_and_agent(client: anthropic.Anthropic) -> tuple[str, str, int]:
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    if "environment_id" not in state:
        env = client.beta.environments.create(
            name=ENV_NAME,
            # PyPI · Hugging Face · PaddleOCR 모델 서버에 접속해야 해서 전체 허용 (컨테이너 안에는 비밀 정보 없음)
            config={"type": "cloud", "networking": {"type": "unrestricted"}},
        )
        state["environment_id"] = env.id
    if "agent_id" not in state:
        agent = client.beta.agents.create(
            name=AGENT_NAME,
            model=MODEL,
            system=SYSTEM,
            tools=[{
                "type": "agent_toolset_20260401",
                # 우리 코드만 있는 컨테이너에서 정해진 명령을 돌리는 일이라 승인 없이 실행
                "default_config": {"enabled": True, "permission_policy": {"type": "always_allow"}},
                "configs": [{"name": "web_fetch", "enabled": False}, {"name": "web_search", "enabled": False}],
            }],
        )
        state["agent_id"], state["agent_version"] = agent.id, agent.version
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2))
    return state["environment_id"], state["agent_id"], state["agent_version"]


def stream_until_idle(client: anthropic.Anthropic, session_id: str, task: str) -> str:
    """작업을 보내고 끝날 때까지 진행 상황 출력. 멈춘 이유를 돌려줌"""
    with client.beta.sessions.events.stream(session_id=session_id) as stream:
        client.beta.sessions.events.send(
            session_id=session_id,
            events=[{"type": "user.message", "content": [{"type": "text", "text": task}]}],
        )
        for event in stream:
            if event.type == "agent.message":
                for block in event.content:
                    if block.type == "text":
                        print(block.text, flush=True)
            elif event.type == "agent.tool_use":
                command = (event.input or {}).get("command") or json.dumps(event.input, ensure_ascii=False)
                print(f"  $ {command[:160]}", flush=True)
                if getattr(event, "evaluated_permission", None) == "ask":  # 지켜보는 사람이 없으니 거절
                    client.beta.sessions.events.send(
                        session_id=session_id,
                        events=[{"type": "user.tool_confirmation", "tool_use_id": event.id, "result": "deny"}],
                    )
            elif event.type == "session.status_idle":
                if event.stop_reason.type != "requires_action":
                    return event.stop_reason.type
            elif event.type == "session.status_terminated":
                return "terminated"
    return "stream_closed"


def download_outputs(client: anthropic.Anthropic, session_id: str) -> Path:
    dest = OUT_DIR / session_id
    dest.mkdir(parents=True, exist_ok=True)
    for _ in range(5):  # 출력 파일이 목록에 잡히기까지 몇 초 걸림
        files = list(client.beta.files.list(scope_id=session_id, betas=["managed-agents-2026-04-01"]))
        if files:
            break
        time.sleep(3)
    for f in files:
        if not getattr(f, "downloadable", True):  # 올린 코드 압축 파일 등 — 세션 결과물이 아님
            continue
        client.beta.files.download(f.id).write_to_file(dest / Path(f.filename).name)
        print(f"  받음: {dest.relative_to(ROOT) / Path(f.filename).name} ({f.size_bytes} bytes)")
    return dest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, default=10, help="평가할 사진 수 (0이면 110장 전체)")
    parser.add_argument("--budget", type=float, default=5.0, help="이 세션의 지출 상한 (달러)")
    parser.add_argument("--eval-args", default="", help="eval_ocr.py에 더 넘길 인자 (예: --charset steel-ocr)")
    args = parser.parse_args()

    load_key()
    client = anthropic.Anthropic()
    env_id, agent_id, agent_version = ensure_env_and_agent(client)

    code = pack_code()
    uploaded = client.beta.files.upload(file=("code.tar.gz", code, "application/gzip"))
    print(f"코드 올림: {len(code) / 1024:.0f} KB")

    session = client.beta.sessions.create(
        agent={"type": "agent", "id": agent_id, "version": agent_version},
        environment_id=env_id,
        title=f"OCR eval limit={args.limit or 'all'}",
        resources=[{"type": "file", "file_id": uploaded.id, "mount_path": "/code.tar.gz"}],
        budget={"type": "limit", "max_list_cost": {"amount": str(round(args.budget * 100)), "currency": "USD"}},
    )
    print(f"세션: {session.id}  (콘솔에서 보기: https://platform.claude.com/workspaces/default/sessions/{session.id})")

    eval_args = " ".join(filter(None, [f"--limit {args.limit}" if args.limit else "", args.eval_args]))
    result_name = f"steel-ocr_det_remote_{args.limit or 'all'}.json"
    started = time.monotonic()
    stop = stream_until_idle(client, session.id, TASK.format(eval_args=eval_args, result_name=result_name))
    print(f"\n멈춘 이유: {stop}  ·  걸린 시간 {time.monotonic() - started:.0f}초")

    dest = download_outputs(client, session.id)
    usage = client.beta.sessions.retrieve(session_id=session.id).usage
    cost = usage.list_cost
    summary = {
        "session_id": session.id,
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
