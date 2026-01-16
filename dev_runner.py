# dev_runner.py
import subprocess
import sys
import time
import os
import signal
import platform
import psutil


# Цвета для консоли
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


def kill_proc_tree(pid, including_parent=True):
    """
    Надежно убивает процесс и ВСЕХ его потомков через psutil.
    """
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)

        # Сначала убиваем детей
        for child in children:
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                pass

        # Ждем их завершения
        _, alive = psutil.wait_procs(children, timeout=3)
        for p in alive:
            try:
                p.kill()  # Если не поняли по-хорошему - убиваем жестко
            except psutil.NoSuchProcess:
                pass

        # Убиваем родителя
        if including_parent:
            try:
                parent.terminate()
                parent.wait(3)
            except (psutil.NoSuchProcess, psutil.TimeoutExpired):
                try:
                    parent.kill()
                except psutil.NoSuchProcess:
                    pass
    except psutil.NoSuchProcess:
        pass


def cleanup_stale_processes():
    """
    Ищет и убивает старые зависшие процессы main.py перед запуском.
    Это спасет твою оперативку.
    """
    current_pid = os.getpid()
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            # Не убиваем сами себя
            if proc.info['pid'] == current_pid:
                continue

            cmdline = proc.info['cmdline']
            if cmdline:
                # Ищем python процессы, запускающие main.py
                cmd_str = " ".join(cmdline)
                if "python" in proc.info['name'].lower() and "src/main.py" in cmd_str.replace("\\", "/"):
                    log("CLEANUP", f"Killing zombie process: {proc.info['pid']}", Colors.WARNING)
                    kill_proc_tree(proc.info['pid'])
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass


def start_process(command, cwd, name):
    is_windows = platform.system() == "Windows"
    use_shell = is_windows and "npm" in command[0]

    # На Windows shell=True для npm нужен, но он создает сложности с PID.
    # psutil с этим справляется лучше стандартных средств.

    proc = subprocess.Popen(
        command,
        cwd=cwd,
        shell=use_shell,
        env=os.environ.copy()
    )
    return proc


def main():
    log("RUNNER", "=== BikeFit Development Environment ===", Colors.HEADER)

    # 0. Чистим зомби перед стартом
    cleanup_stale_processes()

    root_dir = os.path.dirname(os.path.abspath(__file__))
    frontend_dir = os.path.join(root_dir, "frontend")

    frontend_proc = None
    backend_proc = None

    try:
        # 1. Запуск Python Backend
        # Запускаем его первым, чтобы если порт занят, мы сразу упали, а не ждали React
        log("BACKEND", "Launching Python Core...", Colors.BLUE)
        python_exec = sys.executable
        main_script = os.path.join(root_dir, "src", "main.py")

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        backend_proc = start_process([python_exec, main_script], root_dir, "Backend")

        # 2. Запуск React Frontend
        npm_cmd = "npm.cmd" if platform.system() == "Windows" else "npm"
        log("FRONTEND", "Launching React (npm start)...", Colors.GREEN)

        frontend_proc = start_process([npm_cmd, "start"], frontend_dir, "Frontend")

        log("RUNNER", "All systems GO. Press Ctrl+C to stop.", Colors.BOLD)

        # 3. Мониторинг
        while True:
            time.sleep(1)
            if backend_proc.poll() is not None:
                log("ERROR", "Backend died! Stopping...", Colors.FAIL)
                break
            if frontend_proc.poll() is not None:
                # React (npm) может "завершиться", но оставить node процесс, тут сложнее отловить
                # но для dev runner пойдет
                pass

    except KeyboardInterrupt:
        log("RUNNER", "\nStopping environment...", Colors.WARNING)

    finally:
        # Clean Shutdown
        if backend_proc:
            log("BACKEND", "Stopping process tree...", Colors.WARNING)
            kill_proc_tree(backend_proc.pid)

        if frontend_proc:
            log("FRONTEND", "Stopping process tree...", Colors.WARNING)
            kill_proc_tree(frontend_proc.pid)

        log("RUNNER", "Done.", Colors.HEADER)


if __name__ == "__main__":
    main()