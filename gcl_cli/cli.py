import argparse
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from typing import Optional

import yaml

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT / "frontend"
FUNCS_DIR = ROOT / "functions" / "firebase"
DEFAULT_PROJECT = "diatonic-ai-gcp"
DEFAULT_REGION = "us-central1"
CONFIG_PATH = ROOT / "dev.config.yaml"
EMULATOR_ONLY = "auth,firestore,storage,functions,pubsub,database,hosting,ui,logging"


def run(cmd: list[str], cwd: Optional[Path] = None, check: bool = True) -> subprocess.Popen:
    return subprocess.Popen(cmd, cwd=cwd)


def ensure_cmd(name: str):
    if shutil.which(name) is None:
        sys.exit(f"Missing required command: {name}")


def firebase_bin() -> list[str]:
    if shutil.which("firebase"):
        return ["firebase"]
    return ["npx", "firebase-tools"]


def load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def copy_env_templates():
    root_env = ROOT / ".env"
    root_example = ROOT / ".env.example"
    fe_env = FRONTEND_DIR / ".env.local"
    fe_example = FRONTEND_DIR / ".env.example"

    if root_example.exists() and not root_env.exists():
        shutil.copy(root_example, root_env)
        print("📝 Created .env from .env.example")
    if fe_example.exists() and not fe_env.exists():
        fe_env.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(fe_example, fe_env)
        print("📝 Created frontend/.env.local from .env.example")


def install_node():
    ensure_cmd("npm")
    if FRONTEND_DIR.exists():
        lock = FRONTEND_DIR / "package-lock.json"
        cmd = ["npm", "ci"] if lock.exists() else ["npm", "install"]
        subprocess.check_call(cmd, cwd=FRONTEND_DIR)


def install_python():
    ensure_cmd("python3")
    if (ROOT / "requirements.txt").exists():
        subprocess.check_call(
            ["python3", "-m", "pip", "install", "--user", "-r", str(ROOT / "requirements.txt")]
        )
    if (FUNCS_DIR / "requirements.txt").exists():
        subprocess.check_call(
            ["python3", "-m", "pip", "install", "--user", "-r", str(FUNCS_DIR / "requirements.txt")]
        )


def cmd_setup(_args):
    copy_env_templates()
    install_node()
    install_python()
    subprocess.check_call(firebase_bin() + ["--version"])
    print("✅ Setup complete.")


def start_emulators(config):
    env = os.environ.copy()
    env.setdefault("PROJECT_ID", config.get("project_id", DEFAULT_PROJECT))
    env.setdefault("REGION", config.get("region", DEFAULT_REGION))
    env["GOOGLE_CLOUD_PROJECT"] = env["PROJECT_ID"]

    storage_dir = ROOT / ".firebase" / "local"
    storage_dir.mkdir(parents=True, exist_ok=True)

    cmd = firebase_bin() + [
        "emulators:start",
        "--only",
        EMULATOR_ONLY,
        "--project",
        env["PROJECT_ID"],
        "--import",
        str(storage_dir),
        "--export-on-exit",
        str(storage_dir),
    ]
    print(f"🚀 Starting Firebase emulators for {env['PROJECT_ID']}...")
    return run(cmd, cwd=ROOT), env


def start_frontend(config):
    if not FRONTEND_DIR.exists():
        return None
    port = str(config.get("frontend", {}).get("dev_port", 5173))
    cmd = ["npm", "run", "dev", "--", "--host", "--port", port]
    print(f"🌐 Starting frontend dev server on http://localhost:{port} ...")
    return run(cmd, cwd=FRONTEND_DIR)


def wait_with_shutdown(procs: list[subprocess.Popen]):
    def handler(signum, frame):
        print("⏹️  Shutting down...")
        for p in procs:
            if p and p.poll() is None:
                p.terminate()
        for p in procs:
            if p:
                p.wait()

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)
    for p in procs:
        if p:
            p.wait()


def cmd_dev(_args):
    config = load_config()
    copy_env_templates()
    ensure_cmd("npm")
    ensure_cmd("python3")
    emu_proc, _env = start_emulators(config)
    fe_proc = start_frontend(config)
    wait_with_shutdown([emu_proc, fe_proc])


def cmd_emu(_args):
    config = load_config()
    proc, _env = start_emulators(config)
    wait_with_shutdown([proc])


def cmd_build(_args):
    ensure_cmd("npm")
    if FRONTEND_DIR.exists():
        subprocess.check_call(["npm", "run", "build"], cwd=FRONTEND_DIR)
        print("✅ Build complete. Hosting emulator will serve frontend/dist.")
    else:
        print("No frontend directory found; nothing to build.")


def build_parser():
    parser = argparse.ArgumentParser(prog="gcl", description="Wix-like dev CLI for Firebase emulators")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("setup", help="Install deps and prepare env files")
    sub.add_parser("dev", help="Start emulators + frontend dev server")
    sub.add_parser("emu", help="Start Firebase emulators only")
    sub.add_parser("build", help="Build frontend assets")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "setup":
        cmd_setup(args)
    elif args.command == "dev":
        cmd_dev(args)
    elif args.command == "emu":
        cmd_emu(args)
    elif args.command == "build":
        cmd_build(args)
    else:
        parser.print_help()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
