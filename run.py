import subprocess
import sys
import os
import time
import shutil

def check_env_file(env_path):
    print("Verifying .env configuration...")
    if not os.path.exists(env_path):
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
    elif 'postgresql+asyncpg://' not in content:
        errors.append("- DATABASE_URL must start with 'postgresql+asyncpg://' to work with Echolens backend.")

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

def setup_backend():
    backend_dir = "backend"
    venv_dir = os.path.join(backend_dir, "venv")
    
    if os.name == 'nt':
        python_exec = os.path.join(venv_dir, 'Scripts', 'python.exe')
        alembic_exec = os.path.join(venv_dir, 'Scripts', 'alembic.exe')
    else:
        python_exec = os.path.join(venv_dir, 'bin', 'python')
        alembic_exec = os.path.join(venv_dir, 'bin', 'alembic')

    # 1. Check & Create VENV
    if not os.path.exists(venv_dir):
        print("Backend virtual environment not found. Creating one...")
        subprocess.run([sys.executable, "-m", "venv", "venv"], cwd=backend_dir, check=True)
        
    # 2. Check .env
    env_path = os.path.join(backend_dir, ".env")
    env_example = os.path.join(backend_dir, ".env.example")
    if not os.path.exists(env_path) and os.path.exists(env_example):
        print("Creating .env file from .env.example...")
        shutil.copy(env_example, env_path)
    
    # 3. Validate .env contents
    check_env_file(env_path)

    # 4. Install Requirements
    print("Installing/Updating Backend Dependencies...")
    subprocess.run([python_exec, "-m", "pip", "install", "-r", "requirements.txt"], cwd=backend_dir, check=True)

    # 4. Run Migrations
    print("Applying Database Migrations...")
    try:
        subprocess.run([alembic_exec, "upgrade", "head"], cwd=backend_dir, check=True)
    except Exception as e:
        print(f"Warning: Database migration failed. Is your database running? Error: {e}")
        
    return python_exec

def setup_frontend():
    frontend_dir = "frontend"
    node_modules = os.path.join(frontend_dir, "node_modules")
    npm_cmd = "npm.cmd" if os.name == "nt" else "npm"

    if not os.path.exists(node_modules):
        print("Frontend node_modules not found. Installing dependencies...")
        subprocess.run([npm_cmd, "install"], cwd=frontend_dir, check=True)
    
    return npm_cmd

def start_backend(python_exec):
    print("Starting backend...")
    return subprocess.Popen(
        [python_exec, "-m", "uvicorn", "main:app", "--reload", "--port", "8000", "--no-access-log"],
        cwd="backend"
    )

def start_frontend(npm_cmd):
    print("Starting frontend...")
    return subprocess.Popen(
        [npm_cmd, "run", "dev"],
        cwd="frontend"
    )

def main():
    print("=== Echolens Automated Setup & Runner ===")
    
    try:
        python_exec = setup_backend()
        npm_cmd = setup_frontend()
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
        backend_process.terminate()
        frontend_process.terminate()
        backend_process.wait()
        frontend_process.wait()
        print("All servers stopped gracefully.")

if __name__ == "__main__":
    main()
