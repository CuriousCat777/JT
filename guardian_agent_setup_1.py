"""
================================================================================
GUARDIAN AGENT — SETUP SCRIPT (guardian_agent_setup.py)
================================================================================

Prepares your Ryzen for the sovereign Guardian Agent.

WHAT THIS DOES:
    1. Checks Python version and required modules
    2. Checks for / guides Ollama installation (local LLM runtime)
    3. Pulls the reasoning model (Mistral 7B or Llama 3.1 8B)
    4. Initializes the SQLite knowledge base
    5. Validates the full stack is operational

RUN ONCE:
    python guardian_agent_setup.py

REQUIREMENTS:
    - Windows 11 (your Ryzen)
    - Python 3.10+ (you have 3.14.3)
    - 64GB RAM (you have this)
    - ~8GB disk for the model
    - Internet connection (one-time download only)
================================================================================
"""

import os
import sys
import json
import sqlite3
import subprocess
import urllib.request
import urllib.error
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "guardian_agent.db")
CONFIG_PATH = os.path.join(SCRIPT_DIR, "guardian_agent_config.json")

# Default model — fits in 64GB RAM easily, fast on Ryzen 9
DEFAULT_MODEL = "mistral:7b-instruct-v0.3-q5_K_M"
FALLBACK_MODEL = "mistral:7b"
MINIMAL_MODEL = "phi3:mini"  # 3.8B params, very fast, for testing


def utc_now():
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def check_section(name):
    print(f"\n  {'=' * 60}")
    print(f"  CHECK: {name}")
    print(f"  {'=' * 60}")


def pass_msg(msg):
    print(f"  [PASS] {msg}")


def fail_msg(msg):
    print(f"  [FAIL] {msg}")


def info_msg(msg):
    print(f"  [INFO] {msg}")


# =============================================================================
# CHECK 1: Python Version & Modules
# =============================================================================

def check_python():
    check_section("Python Environment")

    version = sys.version_info
    version_str = f"{version.major}.{version.minor}.{version.micro}"
    info_msg(f"Python {version_str} at {sys.executable}")

    if version >= (3, 10):
        pass_msg(f"Python {version_str} >= 3.10 required")
    else:
        fail_msg(f"Python {version_str} is below minimum 3.10")
        return False

    # Check stdlib modules we need
    required = ["sqlite3", "json", "hashlib", "http.server",
                "urllib.request", "csv", "threading", "subprocess"]
    for mod in required:
        try:
            __import__(mod)
            pass_msg(f"Module: {mod}")
        except ImportError:
            fail_msg(f"Module missing: {mod}")
            return False

    return True


# =============================================================================
# CHECK 2: Ollama (Local LLM Runtime)
# =============================================================================

def check_ollama():
    check_section("Ollama (Local LLM Runtime)")

    # Check if ollama command exists
    try:
        result = subprocess.run(
            ["ollama", "--version"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            pass_msg(f"Ollama installed: {version}")
            return True
        else:
            fail_msg("Ollama found but returned error")
    except FileNotFoundError:
        fail_msg("Ollama not found in PATH")
    except subprocess.TimeoutExpired:
        fail_msg("Ollama command timed out")
    except Exception as e:
        fail_msg(f"Ollama check failed: {e}")

    # Not installed — give instructions
    print()
    print("  Ollama is the local LLM runtime. It runs AI models on YOUR hardware.")
    print("  No cloud. No API keys. No data leaves your machine.")
    print()
    print("  INSTALL OLLAMA:")
    print("  1. Go to: https://ollama.com/download")
    print("  2. Click 'Download for Windows'")
    print("  3. Run the installer")
    print("  4. Restart this script: python guardian_agent_setup.py")
    print()
    print("  Or install via PowerShell:")
    print("    winget install Ollama.Ollama")
    print()

    return False


# =============================================================================
# CHECK 3: Ollama Service Running
# =============================================================================

def check_ollama_service():
    check_section("Ollama Service")

    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = data.get("models", [])
            pass_msg(f"Ollama service running on port 11434")
            info_msg(f"Models installed: {len(models)}")
            for m in models:
                name = m.get("name", "unknown")
                size_gb = m.get("size", 0) / (1024**3)
                info_msg(f"  {name} ({size_gb:.1f} GB)")
            return True, models
    except urllib.error.URLError:
        fail_msg("Ollama service not running")
        print()
        print("  START OLLAMA:")
        print("  1. Open a NEW PowerShell window")
        print("  2. Run: ollama serve")
        print("  3. Leave that window open")
        print("  4. Come back here and re-run this script")
        print()
        print("  Or: Ollama may auto-start. Try restarting your computer.")
        return False, []
    except Exception as e:
        fail_msg(f"Cannot reach Ollama API: {e}")
        return False, []


# =============================================================================
# CHECK 4: Pull Model
# =============================================================================

def pull_model(model_name=None):
    check_section("LLM Model")

    model = model_name or DEFAULT_MODEL
    info_msg(f"Target model: {model}")

    # Check if already installed
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            installed = [m.get("name", "") for m in data.get("models", [])]

            # Check for exact match or base name match
            for inst in installed:
                if model in inst or inst in model or model.split(":")[0] in inst:
                    pass_msg(f"Model already installed: {inst}")
                    return inst
    except Exception:
        pass

    # Pull the model
    info_msg(f"Pulling model: {model}")
    info_msg("This downloads the model weights (~4-5 GB). One-time only.")
    info_msg("This may take 5-15 minutes depending on your connection.")
    print()

    try:
        result = subprocess.run(
            ["ollama", "pull", model],
            timeout=1800  # 30 min timeout
        )
        if result.returncode == 0:
            pass_msg(f"Model pulled successfully: {model}")
            return model
        else:
            fail_msg(f"Model pull failed with code {result.returncode}")

            # Try fallback
            info_msg(f"Trying fallback model: {FALLBACK_MODEL}")
            result2 = subprocess.run(
                ["ollama", "pull", FALLBACK_MODEL],
                timeout=1800
            )
            if result2.returncode == 0:
                pass_msg(f"Fallback model pulled: {FALLBACK_MODEL}")
                return FALLBACK_MODEL

    except subprocess.TimeoutExpired:
        fail_msg("Model pull timed out after 30 minutes")
    except FileNotFoundError:
        fail_msg("Cannot run 'ollama pull' — is Ollama in PATH?")
    except Exception as e:
        fail_msg(f"Model pull error: {e}")

    return None


# =============================================================================
# CHECK 5: Test Model Inference
# =============================================================================

def test_inference(model_name):
    check_section("Model Inference Test")

    info_msg(f"Testing {model_name} with a simple prompt...")

    try:
        payload = json.dumps({
            "model": model_name,
            "prompt": "Respond with exactly: GUARDIAN AGENT OPERATIONAL",
            "stream": False,
            "options": {
                "temperature": 0,
                "num_predict": 20
            }
        }).encode("utf-8")

        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            response_text = data.get("response", "").strip()
            total_duration = data.get("total_duration", 0) / 1e9  # ns to seconds
            eval_count = data.get("eval_count", 0)

            pass_msg(f"Inference successful")
            info_msg(f"Response: {response_text[:80]}")
            info_msg(f"Duration: {total_duration:.1f}s")
            info_msg(f"Tokens generated: {eval_count}")

            if total_duration > 0 and eval_count > 0:
                tps = eval_count / total_duration
                info_msg(f"Speed: {tps:.1f} tokens/sec")

            return True

    except urllib.error.URLError as e:
        fail_msg(f"Cannot reach Ollama: {e}")
    except Exception as e:
        fail_msg(f"Inference test failed: {e}")

    return False


# =============================================================================
# CHECK 6: Initialize SQLite Database
# =============================================================================

def init_database():
    check_section("SQLite Knowledge Base")

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # --- Core tables ---

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS skills (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                domain TEXT,
                level INTEGER DEFAULT 0,
                level_label TEXT DEFAULT 'UNKNOWN',
                description TEXT,
                dependencies TEXT,
                evidence TEXT,
                assessment_count INTEGER DEFAULT 0,
                last_assessed TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS goals (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                required_skills TEXT,
                min_level INTEGER DEFAULT 3,
                target_date TEXT,
                status TEXT DEFAULT 'active',
                created_at TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS errors (
                id TEXT PRIMARY KEY,
                timestamp TEXT,
                type TEXT,
                what TEXT,
                why TEXT,
                fix TEXT,
                context TEXT,
                related_skill TEXT,
                recurrence_count INTEGER DEFAULT 1,
                resolved INTEGER DEFAULT 0,
                last_recurrence TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS commands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                command TEXT,
                result TEXT,
                note TEXT,
                duration_seconds REAL DEFAULT 0,
                session_id TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                source TEXT,
                event_type TEXT,
                description TEXT,
                raw_data TEXT,
                processed INTEGER DEFAULT 0,
                action_taken TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS interventions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                trigger_type TEXT,
                trigger_data TEXT,
                reasoning TEXT,
                action TEXT,
                outcome TEXT,
                accepted INTEGER DEFAULT 0
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                start_time TEXT,
                end_time TEXT,
                commands_run INTEGER DEFAULT 0,
                errors_caught INTEGER DEFAULT 0,
                interventions_made INTEGER DEFAULT 0,
                summary TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_type TEXT,
                description TEXT,
                frequency INTEGER DEFAULT 1,
                first_seen TEXT,
                last_seen TEXT,
                severity TEXT DEFAULT 'info',
                auto_fix TEXT,
                active INTEGER DEFAULT 1
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                memory_type TEXT,
                key TEXT,
                value TEXT,
                confidence REAL DEFAULT 1.0,
                source TEXT,
                expires_at TEXT
            )
        """)

        # --- Indexes for fast queries ---
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_skills_domain ON skills(domain)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_skills_level ON skills(level)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_errors_type ON errors(type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_commands_ts ON commands(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_observations_ts ON observations(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_observations_processed ON observations(processed)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_patterns_type ON patterns(pattern_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_key ON agent_memory(key)")

        conn.commit()

        # Write initial config
        configs = {
            "agent_version": "0.1.0",
            "owner": "Jeremy Tabernero, MD",
            "created": utc_now(),
            "schema_version": "1",
            "monitoring_enabled": "true",
            "intervention_mode": "suggest",  # suggest | auto | silent
            "watch_directories": json.dumps([
                os.path.expanduser("~\\Downloads"),
                os.path.expanduser("~\\Documents"),
                os.path.expanduser("~\\Desktop"),
            ]),
            "watch_extensions": json.dumps([
                ".py", ".json", ".csv", ".txt", ".md", ".html", ".js"
            ]),
        }
        for key, value in configs.items():
            cursor.execute("""
                INSERT OR IGNORE INTO config (key, value, updated_at)
                VALUES (?, ?, ?)
            """, (key, value, utc_now()))

        conn.commit()
        conn.close()

        # Report
        db_size = os.path.getsize(DB_PATH)
        pass_msg(f"Database initialized: {os.path.basename(DB_PATH)}")
        info_msg(f"Size: {db_size:,} bytes")
        info_msg(f"Tables: config, skills, goals, errors, commands,")
        info_msg(f"        observations, interventions, sessions,")
        info_msg(f"        patterns, agent_memory")
        info_msg(f"Path: {DB_PATH}")

        return True

    except Exception as e:
        fail_msg(f"Database initialization failed: {e}")
        return False


# =============================================================================
# CHECK 7: Import existing Guardian data
# =============================================================================

def import_guardian_data():
    check_section("Guardian One Data Import")

    # Check for existing Guardian files
    log_file = os.path.join(SCRIPT_DIR, "guardian_one_log.json")
    skills_file = os.path.join(SCRIPT_DIR, "guardian_skills.json")
    errors_file = os.path.join(SCRIPT_DIR, "guardian_errors.json")
    workflow_file = os.path.join(SCRIPT_DIR, "guardian_workflow.json")

    imported = 0

    if os.path.exists(skills_file):
        try:
            with open(skills_file, "r", encoding="utf-8-sig") as f:
                data = json.load(f)

            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            for skill in data.get("skills", []):
                cursor.execute("""
                    INSERT OR REPLACE INTO skills
                    (id, name, domain, level, level_label, description,
                     dependencies, evidence, assessment_count, last_assessed,
                     created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    skill.get("id", ""),
                    skill.get("name", ""),
                    skill.get("domain", ""),
                    skill.get("level", 0),
                    skill.get("level_label", "UNKNOWN"),
                    skill.get("description", ""),
                    json.dumps(skill.get("dependencies", [])),
                    json.dumps(skill.get("evidence", [])),
                    skill.get("assessment_count", 0),
                    skill.get("last_assessed"),
                    skill.get("created"),
                    utc_now()
                ))
                imported += 1

            for goal in data.get("goals", []):
                cursor.execute("""
                    INSERT OR REPLACE INTO goals
                    (id, name, description, required_skills, min_level,
                     target_date, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    goal.get("id", ""),
                    goal.get("name", ""),
                    goal.get("description", ""),
                    json.dumps(goal.get("required_skills", [])),
                    goal.get("min_level_required", 3),
                    goal.get("target_date"),
                    goal.get("status", "active"),
                    goal.get("created")
                ))

            conn.commit()
            conn.close()
            pass_msg(f"Imported {imported} skills from guardian_skills.json")

        except Exception as e:
            fail_msg(f"Skills import failed: {e}")
    else:
        info_msg("No guardian_skills.json found (run guardian_learning.py seed first)")

    if os.path.exists(errors_file):
        try:
            with open(errors_file, "r", encoding="utf-8-sig") as f:
                data = json.load(f)

            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            err_count = 0

            for error in data.get("errors", []):
                cursor.execute("""
                    INSERT OR IGNORE INTO errors
                    (id, timestamp, type, what, why, fix, context,
                     related_skill, recurrence_count, resolved)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    error.get("id", ""),
                    error.get("timestamp", ""),
                    error.get("type", ""),
                    error.get("what", ""),
                    error.get("why", ""),
                    error.get("fix", ""),
                    error.get("context", ""),
                    error.get("related_skill", ""),
                    error.get("recurrence_count", 1),
                    1 if error.get("resolved") else 0
                ))
                err_count += 1

            conn.commit()
            conn.close()
            pass_msg(f"Imported {err_count} errors from guardian_errors.json")

        except Exception as e:
            fail_msg(f"Errors import failed: {e}")
    else:
        info_msg("No guardian_errors.json found")

    if os.path.exists(log_file):
        pass_msg(f"Guardian log found: {os.path.basename(log_file)}")
    else:
        info_msg("No guardian_one_log.json found")

    return True


# =============================================================================
# WRITE CONFIG FILE
# =============================================================================

def write_config(model_name):
    check_section("Configuration")

    config = {
        "version": "0.1.0",
        "created": utc_now(),
        "llm": {
            "provider": "ollama",
            "model": model_name,
            "endpoint": "http://127.0.0.1:11434",
            "temperature": 0.3,
            "max_tokens": 500,
            "timeout_seconds": 30
        },
        "monitoring": {
            "enabled": True,
            "watch_directories": [
                os.path.expanduser("~\\Downloads"),
                os.path.expanduser("~\\Documents"),
            ],
            "watch_extensions": [".py", ".json", ".csv", ".txt", ".md"],
            "poll_interval_seconds": 5,
            "command_history_source": "powershell"
        },
        "intervention": {
            "mode": "suggest",
            "auto_fix_threshold": 0.9,
            "notification_method": "terminal"
        },
        "database": {
            "path": DB_PATH
        },
        "guardian_one": {
            "log_path": os.path.join(SCRIPT_DIR, "guardian_one_log.json"),
            "skills_path": os.path.join(SCRIPT_DIR, "guardian_skills.json"),
            "errors_path": os.path.join(SCRIPT_DIR, "guardian_errors.json"),
            "workflow_path": os.path.join(SCRIPT_DIR, "guardian_workflow.json")
        }
    }

    try:
        with open(CONFIG_PATH, "w", encoding="utf-8", newline="\n") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        pass_msg(f"Config written: {os.path.basename(CONFIG_PATH)}")
        info_msg(f"Model: {model_name}")
        info_msg(f"Mode: suggest (agent recommends, you decide)")
        return True
    except Exception as e:
        fail_msg(f"Config write failed: {e}")
        return False


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 70)
    print("  GUARDIAN AGENT — SETUP")
    print("  Sovereign AI Agent for Your Ryzen")
    print("=" * 70)

    results = {}

    # Step 1: Python
    results["python"] = check_python()

    # Step 2: Ollama installed
    results["ollama"] = check_ollama()

    if not results["ollama"]:
        print("\n  SETUP PAUSED — Install Ollama first, then re-run this script.")
        print("  Download: https://ollama.com/download")
        return

    # Step 3: Ollama service running
    service_ok, models = check_ollama_service()
    results["service"] = service_ok

    if not results["service"]:
        print("\n  SETUP PAUSED — Start Ollama service first.")
        print("  In a new PowerShell window: ollama serve")
        return

    # Step 4: Pull model
    model_name = pull_model()
    results["model"] = model_name is not None

    if not results["model"]:
        print("\n  SETUP PAUSED — Could not pull model.")
        print(f"  Try manually: ollama pull {FALLBACK_MODEL}")
        return

    # Step 5: Test inference
    results["inference"] = test_inference(model_name)

    # Step 6: Database
    results["database"] = init_database()

    # Step 7: Import existing data
    results["import"] = import_guardian_data()

    # Step 8: Config
    results["config"] = write_config(model_name)

    # --- Final Report ---
    print("\n" + "=" * 70)
    print("  SETUP COMPLETE")
    print("=" * 70)
    print()

    all_pass = all(results.values())
    for step, passed in results.items():
        icon = "+" if passed else "X"
        print(f"  [{icon}] {step}")

    print()
    if all_pass:
        print("  ALL CHECKS PASSED. Guardian Agent is ready.")
        print()
        print("  NEXT STEPS:")
        print("    1. Start the agent:")
        print("       python guardian_agent.py start")
        print()
        print("    2. Open the dashboard:")
        print("       http://localhost:8080")
        print()
        print("    3. The agent will begin monitoring your workflow.")
        print("       It watches file changes, detects patterns,")
        print("       and uses your local LLM to reason about")
        print("       what you're doing and where you might need help.")
        print()
        print("    4. All data stays on your machine. Zero cloud calls.")
    else:
        print("  SOME CHECKS FAILED. Fix the issues above and re-run.")

    print()


if __name__ == "__main__":
    main()
