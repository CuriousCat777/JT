"""
================================================================================
GUARDIAN ONE — LAUNCHER
================================================================================
Double-click this file. It does the rest.

What it does:
    1. Finds all your Guardian files wherever they are
    2. Checks if Python is working
    3. Tells you what's ready and what's missing
    4. Gives you a simple menu to run things
    5. Asks YES/NO questions so you always know what's happening

NO TERMINAL KNOWLEDGE NEEDED. Just double-click.
================================================================================
"""

import os
import subprocess
import sys
import glob
import shutil
import json
import time
from pathlib import Path

# =============================================================================
# HELPERS
# =============================================================================

def clear():
    subprocess.run(["cls" if os.name == "nt" else "clear"], shell=False, check=False)

def pause():
    input("\n  Press ENTER to continue...")

def ask_yes_no(question):
    """Ask a yes/no question. Returns True for yes, False for no."""
    while True:
        answer = input(f"\n  {question} (y/n): ").strip().lower()
        if answer in ("y", "yes"):
            return True
        elif answer in ("n", "no"):
            return False
        else:
            print("  Type 'y' for yes or 'n' for no.")

def ask_choice(prompt, options):
    """Show numbered choices. Returns the number chosen."""
    print(f"\n  {prompt}\n")
    for i, opt in enumerate(options, 1):
        print(f"    {i}. {opt}")
    print(f"    0. Go back")
    while True:
        try:
            choice = int(input(f"\n  Enter number (0-{len(options)}): ").strip())
            if 0 <= choice <= len(options):
                return choice
        except ValueError:
            pass
        print(f"  Please enter a number between 0 and {len(options)}.")

def show_banner():
    clear()
    print()
    print("  ╔══════════════════════════════════════════════════╗")
    print("  ║         GUARDIAN ONE — CONTROL CENTER            ║")
    print("  ║         Your AI Agent Launcher                   ║")
    print("  ╚══════════════════════════════════════════════════╝")
    print()

# =============================================================================
# FILE FINDER — Searches everywhere for Guardian files
# =============================================================================

GUARDIAN_FILES = {
    "guardian_system.py":       "CLI Log Engine (Lesson 1) — Create and manage log entries",
    "guardian_lesson_2.py":     "Lesson 2 — Date queries, CSV export, backup",
    "guardian_lesson_3.py":     "Lesson 3 — Classes, objects, API calls",
    "guardian_lesson_4.py":     "Lesson 4 — Web server and dashboard",
    "guardian_learning.py":     "Learning Intelligence — Track skills, errors, gaps",
    "guardian_agent_setup.py":  "Agent Setup — Install local AI (Ollama)",
    "guardian_agent.py":        "Agent — Sovereign AI that monitors your work",
    "guardian_one_log.json":    "Your log data (entries you've created)",
    "guardian_skills.json":     "Your skill tracking data",
    "guardian_errors.json":     "Your error tracking data",
    "guardian_workflow.json":   "Your workflow tracking data",
    "guardian_agent.db":        "Agent database (SQLite)",
    "guardian_agent_config.json": "Agent configuration",
}

def get_search_directories():
    """Get all directories to search for Guardian files."""
    home = Path.home()
    dirs = [
        home / "Downloads",
        home / "Documents",
        home / "Desktop",
        home,
        Path.cwd(),
    ]
    # Also check if there's a guardian folder
    for base in [home / "Downloads", home / "Documents", home / "Desktop", home]:
        for name in ["guardian", "Guardian", "guardian_one", "GuardianOne"]:
            candidate = base / name
            if candidate.is_dir():
                dirs.append(candidate)

    return [d for d in dirs if d.is_dir()]

def find_all_files():
    """Search for all Guardian files. Returns dict of {filename: full_path}."""
    found = {}
    searched = []

    for directory in get_search_directories():
        searched.append(str(directory))
        try:
            for item in directory.iterdir():
                if item.name in GUARDIAN_FILES and item.name not in found:
                    found[item.name] = str(item)
        except PermissionError:
            continue

    return found, searched

# =============================================================================
# WORKSPACE SETUP — Collect all files into one folder
# =============================================================================

def get_workspace():
    """Get or create the Guardian workspace folder."""
    home = Path.home()
    workspace = home / "Documents" / "GuardianOne"
    return workspace

def setup_workspace(found_files):
    """Copy all found files into one organized folder."""
    workspace = get_workspace()

    print(f"\n  This will organize all your Guardian files into ONE folder:")
    print(f"  {workspace}")
    print()

    if not ask_yes_no("Create this folder and copy files there?"):
        return None

    workspace.mkdir(parents=True, exist_ok=True)

    copied = 0
    skipped = 0

    for filename, source_path in found_files.items():
        dest = workspace / filename
        if dest.exists():
            # Check if source is newer
            source_time = os.path.getmtime(source_path)
            dest_time = os.path.getmtime(str(dest))
            if source_time <= dest_time and str(dest) != source_path:
                skipped += 1
                continue

        if str(dest) != source_path:
            try:
                shutil.copy2(source_path, str(dest))
                copied += 1
                print(f"    Copied: {filename}")
            except Exception as e:
                print(f"    Failed: {filename} ({e})")
        else:
            skipped += 1

    print(f"\n  Done. Copied {copied} files, skipped {skipped} (already there).")
    print(f"  Workspace: {workspace}")

    return workspace

# =============================================================================
# STATUS CHECK
# =============================================================================

def check_python_version():
    v = sys.version_info
    return f"{v.major}.{v.minor}.{v.micro}", v >= (3, 10)

def check_ollama():
    """Check if Ollama is installed and running."""
    import subprocess

    # Check installed
    installed = False
    try:
        result = subprocess.run(
            ["ollama", "version"],
            capture_output=True, text=True, timeout=5
        )
        installed = result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Check running
    running = False
    if installed:
        try:
            import urllib.request
            req = urllib.request.Request("http://127.0.0.1:11434/api/tags")
            with urllib.request.urlopen(req, timeout=3) as resp:
                running = resp.status == 200
        except Exception:
            pass

    return installed, running

def show_status(found_files):
    """Show comprehensive status of everything."""
    show_banner()

    # Python
    py_version, py_ok = check_python_version()
    icon = "+" if py_ok else "X"
    print(f"  [{icon}] Python {py_version} {'(OK)' if py_ok else '(Need 3.10+)'}")

    # Ollama
    ollama_installed, ollama_running = check_ollama()
    if ollama_running:
        print(f"  [+] Ollama installed and running")
    elif ollama_installed:
        print(f"  [~] Ollama installed but NOT running")
        print(f"      Fix: Open new PowerShell → type: ollama serve")
    else:
        print(f"  [ ] Ollama not installed (needed for AI agent)")
        print(f"      Install: https://ollama.com/download")

    # Workspace
    workspace = get_workspace()
    if workspace.is_dir():
        print(f"  [+] Workspace: {workspace}")
    else:
        print(f"  [ ] Workspace not created yet")

    print()
    print(f"  FILES FOUND:")
    print()

    # Group files
    programs = {k: v for k, v in GUARDIAN_FILES.items() if k.endswith(".py")}
    data_files = {k: v for k, v in GUARDIAN_FILES.items() if not k.endswith(".py")}

    print(f"  Programs:")
    for filename, description in programs.items():
        if filename in found_files:
            location = Path(found_files[filename]).parent.name
            print(f"    [+] {filename:<30} ({location})")
        else:
            print(f"    [ ] {filename:<30} NOT FOUND")

    print()
    print(f"  Data:")
    for filename, description in data_files.items():
        if filename in found_files:
            location = Path(found_files[filename]).parent.name
            print(f"    [+] {filename:<30} ({location})")
        else:
            print(f"    [ ] {filename:<30} Not yet created")

    print()

# =============================================================================
# RUN PROGRAMS — With confirmation at every step
# =============================================================================

def find_best_path(filename, found_files):
    """Find the best version of a file to run."""
    workspace = get_workspace()
    workspace_path = workspace / filename

    # Prefer workspace copy
    if workspace_path.exists():
        return str(workspace_path)
    # Fall back to found location
    if filename in found_files:
        return found_files[filename]
    return None

def run_program(filepath, args=None):
    """Run a Python program with clear feedback."""
    import subprocess

    if not os.path.exists(filepath):
        print(f"  File not found: {filepath}")
        return False

    cmd = [sys.executable, filepath]
    if args:
        cmd.extend(args)

    print(f"\n  Running: {os.path.basename(filepath)} {' '.join(args or [])}")
    print(f"  Location: {filepath}")
    print(f"  {'-' * 50}")
    print()

    try:
        result = subprocess.run(cmd, cwd=os.path.dirname(filepath))
        print()
        if result.returncode == 0:
            print(f"  Finished successfully.")
        else:
            print(f"  Finished with exit code: {result.returncode}")
        return result.returncode == 0
    except KeyboardInterrupt:
        print(f"\n  Stopped by you (Ctrl+C).")
        return True
    except Exception as e:
        print(f"\n  Error running program: {e}")
        return False

# =============================================================================
# INTERACTIVE MENU
# =============================================================================

def menu_learn(found_files):
    """Learning track menu."""
    while True:
        show_banner()
        print("  LEARNING TRACK — Python Lessons")
        print()

        lessons = [
            ("guardian_system.py",   "Lesson 1: Log Engine Basics",     ["--help"]),
            ("guardian_lesson_2.py", "Lesson 2: Date Queries & Export", []),
            ("guardian_lesson_3.py", "Lesson 3: Classes & API Calls",   []),
            ("guardian_lesson_4.py", "Lesson 4: Web Server Dashboard",  []),
        ]

        options = []
        for filename, title, _ in lessons:
            available = filename in found_files or (get_workspace() / filename).exists()
            status = "READY" if available else "NOT FOUND"
            options.append(f"{title} [{status}]")

        choice = ask_choice("Which lesson?", options)
        if choice == 0:
            return

        filename, title, default_args = lessons[choice - 1]
        filepath = find_best_path(filename, found_files)

        if not filepath:
            print(f"\n  {filename} not found. Download it from Claude first.")
            pause()
            continue

        print(f"\n  {title}")
        print(f"  File: {filepath}")

        if ask_yes_no("Run this lesson?"):
            run_program(filepath, default_args)
        pause()

def menu_skills(found_files):
    """Skills and error tracking menu."""
    while True:
        show_banner()
        print("  SKILL TRACKER — Know Your Gaps")
        print()

        filepath = find_best_path("guardian_learning.py", found_files)
        if not filepath:
            print("  guardian_learning.py not found. Download it first.")
            pause()
            return

        options = [
            "Set up initial data (first time only)",
            "View all my skills",
            "See my knowledge gaps",
            "See my learning roadmap (what to study next)",
            "View my logged errors",
            "Find error patterns",
            "Full dashboard",
            "Generate prompt for Claude (paste to get advice)",
        ]

        commands = [
            ["seed"],
            ["skills"],
            ["gaps"],
            ["roadmap"],
            ["errors"],
            ["patterns"],
            ["dashboard"],
            ["suggest"],
        ]

        choice = ask_choice("What do you want to see?", options)
        if choice == 0:
            return

        run_program(filepath, commands[choice - 1])
        pause()

def menu_agent(found_files):
    """AI Agent menu."""
    while True:
        show_banner()
        print("  AI AGENT — Sovereign Intelligence")
        print()

        # Check prerequisites
        ollama_installed, ollama_running = check_ollama()

        if not ollama_installed:
            print("  Ollama is NOT installed. The AI Agent needs it.")
            print()
            print("  Ollama runs AI models on YOUR computer. No cloud. No API keys.")
            print("  Your data never leaves your machine.")
            print()
            print("  Install: https://ollama.com/download")
            print("  Or in PowerShell: winget install Ollama.Ollama")
            print()
            print("  After installing, come back and try again.")
            pause()
            return

        if not ollama_running:
            print("  Ollama is installed but NOT running.")
            print()
            if ask_yes_no("Try to start Ollama now?"):
                import subprocess
                try:
                    # Start ollama serve in background
                    subprocess.Popen(
                        ["ollama", "serve"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    )
                    print("  Starting Ollama... waiting 5 seconds...")
                    time.sleep(5)
                    _, running = check_ollama()
                    if running:
                        print("  Ollama is now running!")
                    else:
                        print("  Still not running. Open PowerShell and type: ollama serve")
                        pause()
                        continue
                except Exception as e:
                    print(f"  Could not start: {e}")
                    print("  Open a new PowerShell window and type: ollama serve")
                    pause()
                    continue
            else:
                return

        options = [
            "Run first-time setup (downloads AI model ~4GB)",
            "Check agent status",
            "Start the agent (monitors your work + web dashboard)",
            "Ask the AI a question",
            "Get a personalized lesson from the AI",
            "View detected patterns",
        ]

        choice = ask_choice("What do you want to do?", options)
        if choice == 0:
            return

        if choice == 1:
            filepath = find_best_path("guardian_agent_setup.py", found_files)
            if not filepath:
                print("  guardian_agent_setup.py not found.")
                pause()
                continue
            if ask_yes_no("This downloads a ~4GB AI model. Takes 5-15 min. Continue?"):
                run_program(filepath)
            pause()

        elif choice == 2:
            filepath = find_best_path("guardian_agent.py", found_files)
            if filepath:
                run_program(filepath, ["status"])
            pause()

        elif choice == 3:
            filepath = find_best_path("guardian_agent.py", found_files)
            if filepath:
                print("\n  The agent will start monitoring your files and")
                print("  open a dashboard at http://localhost:8080")
                print("  Press Ctrl+C at any time to stop it.")
                if ask_yes_no("Start the agent?"):
                    run_program(filepath, ["start"])
            pause()

        elif choice == 4:
            question = input("\n  Ask the AI anything: ").strip()
            if question:
                filepath = find_best_path("guardian_agent.py", found_files)
                if filepath:
                    run_program(filepath, ["ask", question])
            pause()

        elif choice == 5:
            filepath = find_best_path("guardian_agent.py", found_files)
            if filepath:
                run_program(filepath, ["teach"])
            pause()

        elif choice == 6:
            filepath = find_best_path("guardian_agent.py", found_files)
            if filepath:
                run_program(filepath, ["patterns"])
            pause()

def menu_organize(found_files):
    """File management menu."""
    show_banner()
    print("  ORGANIZE — Collect all files into one folder")
    print()

    workspace = get_workspace()
    print(f"  Current files found: {len(found_files)}")
    print(f"  Target folder: {workspace}")
    print()

    for filename, path in sorted(found_files.items()):
        location = Path(path).parent.name
        print(f"    {filename:<35} in {location}")

    print()

    if found_files:
        workspace = setup_workspace(found_files)
        if workspace:
            print(f"\n  All files are now in: {workspace}")
            print(f"  You can run everything from there.")
    else:
        print("  No Guardian files found. Download them from Claude first.")

    pause()

# =============================================================================
# MAIN MENU
# =============================================================================

def main():
    # First scan for files
    found_files, searched = find_all_files()

    while True:
        show_status(found_files)

        options = [
            "LEARN — Run Python lessons (Lessons 1-4)",
            "SKILLS — Track what I know and my gaps",
            "AGENT — Start the sovereign AI agent",
            "ORGANIZE — Collect all files into one folder",
            "REFRESH — Scan for files again",
            "QUIT",
        ]

        choice = ask_choice("What do you want to do?", options)

        if choice == 0 or choice == 6:
            print("\n  Goodbye.\n")
            break
        elif choice == 1:
            menu_learn(found_files)
        elif choice == 2:
            menu_skills(found_files)
        elif choice == 3:
            menu_agent(found_files)
        elif choice == 4:
            menu_organize(found_files)
        elif choice == 5:
            found_files, searched = find_all_files()
            print(f"\n  Scanned {len(searched)} locations. Found {len(found_files)} files.")
            pause()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Stopped.\n")
    except Exception as e:
        print(f"\n  Something went wrong: {e}")
        print(f"  Take a screenshot and send it to Claude.\n")
        input("  Press ENTER to close...")
