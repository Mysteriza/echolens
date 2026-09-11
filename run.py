import argparse
import subprocess
import sys
import os
import time
import shutil

ROOT_ENV = os.path.join(os.path.dirname(__file__), ".env")
ROOT_ENV_EXAMPLE = os.path.join(os.path.dirname(__file__), ".env.example")

def check_env_file(env_path):
    print("Verifying .env configuration...")
    if not os.path.exists(env_path):
        print(f"NOTE: {env_path} not found. Backend will use built-in defaults;")
        print("set YOUTUBE_API_KEY to enable fetching.")
        return
        
    with open(env_path, 'r', encoding='utf-8') as f:
        content = f.read()

    errors = []
    
    if 'YOUTUBE_API_KEY=' not in content or 'YOUTUBE_API_KEY=KODE_API' in content or 'YOUTUBE_API_KEY=YOUR_YOUTUBE' in content:
        errors.append("- YOUTUBE_API_KEY is missing or still using the default placeholder.")
        
    if 'GEMINI_API_KEY=' not in content or 'GEMINI_API_KEY=KODE_API' in content or 'GEMINI_API_KEY=YOUR_GEMINI' in content:
        errors.append("- GEMINI_API_KEY is missing or still using the default placeholder.")
        
    if 'DATABASE_URL=' not in content:
        errors.append("- DATABASE_URL is missing.")
    elif 'PASSWORD_SUPABASE_ANDA' in content or 'YOUR_SUPABASE_PASSWORD' in content:
        errors.append("- DATABASE_URL still contains the password placeholder. Please replace it with your actual database password.")
    elif 'postgresql+asyncpg://' not in content and 'postgresql://' not in content and 'postgres://' not in content:
        errors.append("- DATABASE_URL must be a PostgreSQL URL (config auto-converts 'postgresql://' to the asyncpg driver).")

    if errors:
        print("\n" + "="*50)
        print("❌ CONFIGURATION ERROR IN .env FILE ❌")
        print("="*50)
        print("Please fix the following issues in backend/.env before running Echolens:\n")
        for err in errors:
            print(err)
        print("\n" + "="*50)
        sys.exit(1)
    
    print("✅ Configuration is valid!")

def setup_backend(do_install=False):
    backend_dir = "backend"
    venv_dir = os.path.join(backend_dir, "venv")
    
    if os.name == 'nt':
        python_exec = os.path.join(venv_dir, 'Scripts', 'python.exe')
    else:
        python_exec = os.path.join(venv_dir, 'bin', 'python')

    # 1. Check & Create VENV
    if not os.path.exists(venv_dir):
        print("Backend virtual environment not found. Creating one...")
        subprocess.run([sys.executable, "-m", "venv", "venv"], cwd=backend_dir, check=True)
        
    # 2. Check .env (project root is canonical; backend/.env legacy fallback)
    env_path = ROOT_ENV if os.path.exists(ROOT_ENV) else os.path.join(backend_dir, ".env")
    if not os.path.exists(env_path) and os.path.exists(ROOT_ENV_EXAMPLE):
        print("Creating .env file from .env.example...")
        shutil.copy(ROOT_ENV_EXAMPLE, ROOT_ENV)
        env_path = ROOT_ENV
    
    # 3. Validate .env contents
    check_env_file(env_path)

    # 4. Install Requirements (only with --setup; `python run.py` just runs)
    if do_install:
        print("Installing/Updating Backend Dependencies...")
        subprocess.run([python_exec, "-m", "pip", "install", "-r", "requirements.txt"], cwd=backend_dir, check=True)
    else:
        print("Skipping pip install (use `python run.py --setup` to install/update).")

    return python_exec

def setup_frontend(do_install=False):
    frontend_dir = "frontend"
    node_modules = os.path.join(frontend_dir, "node_modules")
    npm_cmd = "npm.cmd" if os.name == "nt" else "npm"

    if not os.path.exists(node_modules) or do_install:
        print("Frontend node_modules not found. Installing dependencies...")
        subprocess.run([npm_cmd, "install"], cwd=frontend_dir, check=True)
    else:
        print("Skipping npm install (use `python run.py --setup` to install/update).")
    
    return npm_cmd

def start_backend(python_exec):
    print("Starting backend...")
    kwargs = {}
    if os.name == 'nt':
        kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(
        [python_exec, "-m", "uvicorn", "main:app", "--reload", "--port", "8000", "--no-access-log"],
        cwd="backend",
        **kwargs
    )

def start_frontend(npm_cmd):
    print("Starting frontend...")
    kwargs = {}
    if os.name == 'nt':
        kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(
        [npm_cmd, "run", "dev"],
        cwd="frontend",
        **kwargs
    )

def main(argv=None):
    parser = argparse.ArgumentParser(description="Echolens setup & runner")
    parser.add_argument("--setup", action="store_true",
                        help="Install/update backend + frontend dependencies before running.")
    parser.add_argument("--skip-checks", action="store_true",
                        help="Skip .env validation (useful for frontend-only work).")
    args = parser.parse_args(argv)
    print("=== Echolens Automated Setup & Runner ===")

    try:
        python_exec = setup_backend(do_install=args.setup)
        npm_cmd = setup_frontend(do_install=args.setup)
        if not args.skip_checks:
            check_env_file(ROOT_ENV if os.path.exists(ROOT_ENV) else os.path.join("backend", ".env"))
    except subprocess.CalledProcessError as e:
        print(f"\n[!] Setup Failed. Command failed: {e.cmd}")
        sys.exit(1)

    backend_process = start_backend(python_exec)
    frontend_process = start_frontend(npm_cmd)

    try:
        print("\n=== Both servers are running! ===")
        print("API is available at: http://localhost:8000")
        print("Web App is available at: http://localhost:5173")
        print("Press Ctrl+C to stop both servers.\n")
        
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down servers...")
        if os.name == 'nt':
            # Kill process tree on Windows to prevent orphaned node/uvicorn background processes
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(backend_process.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(frontend_process.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            backend_process.terminate()
            frontend_process.terminate()
            backend_process.wait()
            frontend_process.wait()
        print("All servers stopped gracefully.")

if __name__ == "__main__":
    main()
