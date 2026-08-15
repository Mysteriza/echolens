import subprocess
import sys
import os
import time

def start_backend():
    print("Starting backend...")
    # Use the python executable from the virtual environment
    if os.name == 'nt':
        python_exec = os.path.join('backend', 'venv', 'Scripts', 'python.exe')
    else:
        python_exec = os.path.join('backend', 'venv', 'bin', 'python')

    return subprocess.Popen(
        [python_exec, "-m", "uvicorn", "main:app", "--reload", "--port", "8000", "--no-access-log"],
        cwd="backend"
    )

def start_frontend():
    print("Starting frontend...")
    npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
    return subprocess.Popen(
        [npm_cmd, "run", "dev"],
        cwd="frontend"
    )

def main():
    if not os.path.exists(os.path.join("backend", "venv")):
        print("Error: Backend virtual environment not found. Please follow setup instructions in README.md first.")
        sys.exit(1)
        
    if not os.path.exists(os.path.join("frontend", "node_modules")):
        print("Error: Frontend node_modules not found. Please run 'npm install' in the frontend folder first.")
        sys.exit(1)

    backend_process = start_backend()
    frontend_process = start_frontend()

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
