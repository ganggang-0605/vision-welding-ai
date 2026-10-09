"""아무 명령이나 Claude Managed Agents(크레딧 계정 컨테이너)에서 차례로 실행 — remote_eval.py 의 일반판

비용은 .env 의 ANTHROPIC_API_KEY 계정에서 나가고, 세션마다 예산 상한을 검. 컨테이너는 CPU 4개·GPU 없음.

사용:
  backend/.venv/bin/python vision/tools/remote_run.py --paddle --torch --data data/raw/pac/handwriting \\
      --step "python vision/tools/synth_handwriting.py --out data/synth/hw_eval --n 500 --styles eval" \\
      --step "python vision/tools/eval_handwriting.py --data data/synth/hw_eval --model paddle --pac --out \\$OUT/hw.json"
  --step     /workspace/repo 에서 차례로 실행 (python = 컨테이너의 Python 3.12 venv, $OUT = 결과 폴더). 실패하면 거기서 멈춤
  --paddle   paddlepaddle·paddleocr 설치      --torch  CPU용 torch·transformers 설치
  --pip      추가 pip 패키지 (여러 번)        --apt    추가 apt 패키지 (여러 번, 예: 글꼴)
  --data     함께 올릴 파일·폴더 (저장소 기준 경로, 여러 번). data/annotations 는 항상 올림.
             저장소 밖 절대 경로는 컨테이너의 /workspace/repo/extra/<이름> 으로 올라감 (일회용 실험 스크립트 등)
  --session  sesn_… : 이미 준비된 세션에 단계만 이어서 보냄 (설치·데이터 받기 생략). 코드(shared·vision)와
             --data 는 새로 올려 덮어씀 — 컨테이너에서 만든 파일(data/synth 등)은 그대로
결과: vision/reports/runs/remote/<session_id>/ (결과 파일, 단계별 로그)
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

SETUP = """Run these steps in order with bash.

1. Environment report: `python3 --version; nproc; (free -h || head -3 /proc/meminfo); df -h /workspace | tail -1`
2. Extract the code and data: `mkdir -p /workspace/repo && tar -xzf /mnt/session/uploads/code.tar.gz -C /workspace/repo && tar -xzf /mnt/session/uploads/data.tar.gz -C /workspace/repo && ls /workspace/repo`
3. Create the Python 3.12 venv: if python3 is 3.12 run `python3 -m venv /workspace/venv`, otherwise `pip install -q uv && uv venv -p 3.12 /workspace/venv`. Install packages with `uv pip install --python /workspace/venv/bin/python ...` (install uv first if needed).
4. Install, logging everything to /tmp/pip.log and printing only the last 3 lines of each command:
{installs}
"""

RUN = """{n}. Write /tmp/run_all.sh with exactly this content (do not change it):
```
#!/bin/bash
cd /workspace/repo
export PATH=/workspace/venv/bin:$PATH OUT=/mnt/session/outputs PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
mkdir -p $OUT/logs
{steps}
touch /tmp/run_all.done
```
{n1}. Run it in the background: `rm -f /tmp/run_all.done; nohup bash /tmp/run_all.sh > /tmp/run_all.log 2>&1 &`
{n2}. Poll with `sleep 60; ls /tmp/run_all.done 2>/dev/null; tail -n 3 /tmp/run_all.log` until /tmp/run_all.done exists. Do not run anything else while waiting.
{n3}. `tail -n 40 /tmp/run_all.log` and reply with each step's exit code, wall time and the last result lines. If a step failed, include the last 30 lines of its log ($OUT/logs/step<N>.log)."""

STEP = """echo "== step {i}: {label}"; s=$(date +%s)
( {cmd} ) > $OUT/logs/step{i}.log 2>&1; rc=$?
echo "== step {i} exit=$rc seconds=$(( $(date +%s) - s ))"; tail -n 15 $OUT/logs/step{i}.log
if [ $rc -ne 0 ]; then touch /tmp/run_all.done; exit $rc; fi"""


def installs(args) -> str:
    uv = "uv pip install --python /workspace/venv/bin/python"
    lines = []
    if args.apt:
        lines.append(f"apt-get update -qq && apt-get install -y -qq {' '.join(args.apt)} >> /tmp/pip.log 2>&1 || "
                     f"for p in {' '.join(args.apt)}; do apt-get install -y -qq $p >> /tmp/pip.log 2>&1; done")
    if args.torch:  # CPU 전용 빌드 먼저 (기본 빌드는 CUDA 라이브러리까지 받아 수 GB)
        lines.append(f"{uv} --index-url https://download.pytorch.org/whl/cpu torch==2.14.1 torchvision==0.29.1 >> /tmp/pip.log 2>&1")
    pkgs = ["-e /workspace/repo/shared", "-e /workspace/repo/vision", "huggingface_hub"]
    if args.paddle:
        pkgs += ["paddlepaddle==3.3.1", "paddleocr==3.7.0"]
    if args.torch:
        pkgs += ["transformers==5.19.0", "sentencepiece"]
    pkgs += args.pip
    lines.append(f"{uv} {' '.join(pkgs)} >> /tmp/pip.log 2>&1")
    lines.append("/workspace/venv/bin/python -c \"import vision; print('vision ok')\"")
    # libGL 없으면 cv2(·paddle) import가 실패함
    lines.append("/workspace/venv/bin/python -c 'import cv2' 2>/dev/null || (apt-get update -qq && "
                 "apt-get install -y -qq libgl1 libglib2.0-0 >> /tmp/pip.log 2>&1)")
    return "\n".join(f"   - `{l}`" for l in lines)


def build_task(args, setup: bool, uploads: tuple[str, str] = ("code.tar.gz", "data.tar.gz")) -> str:
    steps = "\n".join(STEP.format(i=i, label=cmd[:60].replace('"', "'").replace("$", ""), cmd=cmd)
                      for i, cmd in enumerate(args.step, 1))
    if setup:
        return SETUP.format(installs=installs(args)) + RUN.format(n=5, n1=6, n2=7, n3=8, steps=steps)
    code, data = uploads
    return ("Run these steps in order with bash. The environment from earlier in this session is already set up "
            "(/workspace/repo, /workspace/venv).\n\n"
            "1. Stop anything still running from earlier runs, then refresh the code and data: "
            f"`pkill -f run_all.sh; pkill -f 'vision/tools/'; sleep 2; tar -xzf /mnt/session/uploads/{code} -C /workspace/repo && "
            f"tar -xzf /mnt/session/uploads/{data} -C /workspace/repo && ls /workspace/repo`\n"
            + RUN.format(n=2, n1=3, n2=4, n3=5, steps=steps))


def pack_data(paths: list[str]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for p in ["data/annotations", *paths]:
            src = Path(p) if Path(p).is_absolute() else ROOT / p
            if not src.exists():
                sys.exit(f"없는 경로: {p}")
            tar.add(src, arcname=f"extra/{src.name}" if Path(p).is_absolute() else p)
    return buf.getvalue()


def run_task(client: anthropic.Anthropic, session_id: str, task: str) -> str:
    """작업을 보내고 끝날 때까지 기다림. 긴 스트림이 끊기면 상태를 직접 확인"""
    try:
        return stream_until_idle(client, session_id, task)
    except Exception as e:
        print(f"스트림 끊김({e!r}) — 끝날 때까지 상태 확인으로 기다림", flush=True)
        while client.beta.sessions.retrieve(session_id=session_id).status == "running":
            time.sleep(30)
        return "idle(stream lost)"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--step", action="append", required=True)
    parser.add_argument("--paddle", action="store_true")
    parser.add_argument("--torch", action="store_true")
    parser.add_argument("--pip", action="append", default=[])
    parser.add_argument("--apt", action="append", default=[])
    parser.add_argument("--data", action="append", default=[])
    parser.add_argument("--session")
    parser.add_argument("--budget", type=float, default=3.0, help="새 세션의 지출 상한 (달러)")
    parser.add_argument("--title", default="remote run")
    args = parser.parse_args()

    load_key()
    client = anthropic.Anthropic()
    if args.session:
        session_id = args.session
        stamp = time.strftime("%H%M%S")
        uploads = (f"code_{stamp}.tar.gz", f"data_{stamp}.tar.gz")
        for name, blob in zip(uploads, (pack_code(), pack_data(args.data))):
            f = client.beta.files.upload(file=(name, blob, "application/gzip"))
            client.beta.sessions.resources.add(session_id, type="file", file_id=f.id, mount_path=f"/{name}")
    else:
        uploads = ("code.tar.gz", "data.tar.gz")
        env_id, agent_id, agent_version = ensure_env_and_agent(client)
        code = client.beta.files.upload(file=("code.tar.gz", pack_code(), "application/gzip"))
        data = client.beta.files.upload(file=("data.tar.gz", pack_data(args.data), "application/gzip"))
        session = client.beta.sessions.create(
            agent={"type": "agent", "id": agent_id, "version": agent_version},
            environment_id=env_id,
            title=args.title,
            resources=[{"type": "file", "file_id": code.id, "mount_path": "/code.tar.gz"},
                       {"type": "file", "file_id": data.id, "mount_path": "/data.tar.gz"}],
            budget={"type": "limit", "max_list_cost": {"amount": str(round(args.budget * 100)), "currency": "USD"}},
        )
        session_id = session.id
    print(f"세션: {session_id}  (콘솔에서 보기: https://platform.claude.com/workspaces/default/sessions/{session_id})", flush=True)

    started = time.monotonic()
    stop = run_task(client, session_id, build_task(args, setup=not args.session, uploads=uploads))
    print(f"\n멈춘 이유: {stop}  ·  걸린 시간 {time.monotonic() - started:.0f}초")
    dest = download_outputs(client, session_id)
    usage = client.beta.sessions.retrieve(session_id=session_id).usage
    cost = int(usage.list_cost.amount) / 100 if usage.list_cost else None
    (dest / "session_usage.json").write_text(json.dumps(
        {"session_id": session_id, "stop_reason": stop, "list_cost_usd": cost, "active_seconds": usage.active_seconds,
         "usage": usage.model_dump(mode="json")}, ensure_ascii=False, indent=2))
    print(f"비용(정가 기준, 세션 누적): ${cost}  ·  컨테이너 실행 {usage.active_seconds}초")
    return 0 if stop in ("end_turn", "idle(stream lost)") else 1


if __name__ == "__main__":
    sys.exit(main())
