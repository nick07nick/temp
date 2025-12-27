# dev_runner.py
import subprocess
import sys
import time
import os
import signal
import platform


# Определяем цвета для логов, чтобы отличать Backend от Frontend
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def log(tag, message, color=Colors.BLUE):
    print(f"{color}[{tag}] {message}{Colors.ENDC}")


def main():
    log("RUNNER", "Starting BikeFit Development Environment...", Colors.HEADER)

    # Определяем пути
    root_dir = os.path.dirname(os.path.abspath(__file__))
    frontend_dir = os.path.join(root_dir, "frontend")

    processes = []

    try:
        # 1. Запуск React Frontend
        # npm start на Mac/Linux, npm.cmd на Windows
        npm_cmd = "npm.cmd" if platform.system() == "Windows" else "npm"

        log("FRONTEND", "Launching React...", Colors.GREEN)
        frontend_proc = subprocess.Popen(
            [npm_cmd, "start"],
            cwd=frontend_dir,
            shell=False,
            # stdout=subprocess.DEVNULL, # Раскомментируй, если логи React мешают
            # stderr=subprocess.DEVNULL
        )
        processes.append(("Frontend", frontend_proc))

        # Даем фору фронтенду (необязательно, но приятно)
        time.sleep(2)

        # 2. Запуск Python Core
        # Используем тот же интерпретатор, которым запущен этот скрипт
        python_executable = sys.executable
        main_script = os.path.join(root_dir, "src", "main.py")

        log("BACKEND", f"Launching Python Core ({main_script})...", Colors.BLUE)
        backend_proc = subprocess.Popen(
            [python_executable, main_script],
            cwd=root_dir,
            env=os.environ.copy()  # Передаем переменные окружения
        )
        processes.append(("Backend", backend_proc))

        # 3. Мониторинг процессов
        while True:
            time.sleep(1)
            # Проверяем, не упал ли кто-то
            if backend_proc.poll() is not None:
                log("ERROR", "Backend process died unexpectedly!", Colors.FAIL)
                break
            if frontend_proc.poll() is not None:
                log("ERROR", "Frontend process died unexpectedly!", Colors.FAIL)
                break

    except KeyboardInterrupt:
        log("RUNNER", "\nStopping development environment...", Colors.WARNING)
    finally:
        # Graceful Shutdown для всех
        for name, proc in processes:
            if proc.poll() is None:
                log("RUNNER", f"Killing {name}...", Colors.WARNING)
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()

        log("RUNNER", "Environment stopped.", Colors.HEADER)


if __name__ == "__main__":
    main()