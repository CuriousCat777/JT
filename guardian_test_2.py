"""
GUARDIAN ONE — Diagnostic Test
Run this FIRST. It will tell you exactly what's wrong.
Usage: python guardian_test.py
   or: py guardian_test.py
   or: python3 guardian_test.py
"""
import sys
print("=" * 60)
print("GUARDIAN ONE DIAGNOSTIC")
print("=" * 60)
print()

# Test 1: Python version
v = sys.version_info
print(f"[1] Python version: {v.major}.{v.minor}.{v.micro}")
if v < (3, 8):
    print("    FAIL: Need Python 3.8+")
    print("    FIX:  Download from https://www.python.org/downloads/")
    print("          Check 'Add Python to PATH' during install")
    sys.exit(1)
else:
    print("    PASS")

# Test 2: Platform
import platform
print(f"[2] Platform: {platform.system()} {platform.release()} {platform.machine()}")
print("    PASS")

# Test 3: Required modules
print("[3] Standard library imports...")
try:
    import json
    import hashlib
    import os
    from datetime import datetime, timezone
    from pathlib import Path
    print("    PASS")
except ImportError as e:
    print(f"    FAIL: {e}")
    print("    FIX:  Your Python install is broken. Reinstall Python.")
    sys.exit(1)

# Test 4: __file__ resolution
print("[4] Script path resolution...")
try:
    script_dir = Path(__file__).resolve().parent
    print(f"    Script dir: {script_dir}")
    print("    PASS")
except Exception as e:
    print(f"    FAIL: {e}")
    print("    FIX:  Don't run via stdin or exec(). Run as:")
    print("          python guardian_test.py")
    sys.exit(1)

# Test 5: Write permission
print("[5] Write permission...")
try:
    test_file = script_dir / ".guardian_test_write"
    with open(str(test_file), "w", encoding="utf-8") as f:
        f.write("test")
    os.remove(str(test_file))
    print("    PASS")
except PermissionError:
    print("    FAIL: Cannot write to this directory")
    print(f"    FIX:  Move the script to Desktop or Documents")
    print(f"          Current dir: {script_dir}")
    sys.exit(1)
except Exception as e:
    print(f"    FAIL: {e}")
    sys.exit(1)

# Test 6: JSON write/read
print("[6] JSON read/write cycle...")
try:
    test_json = script_dir / ".guardian_test.json"
    data = {"test": True, "entries": [{"id": 1, "text": "hello"}]}
    with open(str(test_json), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    with open(str(test_json), "r", encoding="utf-8") as f:
        loaded = json.load(f)
    assert loaded["entries"][0]["id"] == 1
    os.remove(str(test_json))
    print("    PASS")
except Exception as e:
    print(f"    FAIL: {e}")
    sys.exit(1)

# Test 7: os.replace (atomic file swap)
print("[7] Atomic file replace...")
try:
    tmp_path = str(script_dir / ".guardian_tmp")
    final_path = str(script_dir / ".guardian_final")
    with open(tmp_path, "w") as f:
        f.write("temp")
    # On Windows, target must not exist for os.replace in some cases
    if os.path.exists(final_path):
        os.remove(final_path)
    os.replace(tmp_path, final_path)
    os.remove(final_path)
    print("    PASS")
except Exception as e:
    print(f"    WARN: os.replace failed ({e})")
    print("    Will use fallback write method")

# Test 8: Hash computation
print("[8] SHA-256 hash...")
try:
    h = hashlib.sha256(b"guardian one").hexdigest()
    assert len(h) == 64
    print(f"    Result: {h[:16]}...")
    print("    PASS")
except Exception as e:
    print(f"    FAIL: {e}")
    sys.exit(1)

# Test 9: Terminal color support
print("[9] Terminal colors...")
if platform.system() == "Windows":
    try:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.GetStdHandle(-11)
        m = ctypes.c_ulong()
        k.GetConsoleMode(h, ctypes.byref(m))
        k.SetConsoleMode(h, m.value | 0x0004)
        print("    \033[92mGREEN\033[0m \033[91mRED\033[0m \033[93mYELLOW\033[0m \033[94mBLUE\033[0m \033[96mCYAN\033[0m")
        print("    PASS (if you see colors above)")
        print("    If you see garbled text, use: python guardian_system.py list --no-color")
    except Exception:
        print("    WARN: Colors not available (use --no-color flag)")
else:
    print("    \033[92mGREEN\033[0m \033[91mRED\033[0m \033[93mYELLOW\033[0m \033[94mBLUE\033[0m \033[96mCYAN\033[0m")
    print("    PASS")

# Test 10: Encoding
print(f"[10] Default encoding: {sys.getdefaultencoding()}")
print(f"     Filesystem encoding: {sys.getfilesystemencoding()}")
print(f"     stdout encoding: {sys.stdout.encoding}")
print("     PASS")

# Test 11: Try importing the main script
print("[11] Import guardian_system.py...")
guardian_path = script_dir / "guardian_system.py"
if guardian_path.exists():
    try:
        # Don't actually run main(), just check it parses
        import importlib.util
        spec = importlib.util.spec_from_file_location("guardian_system", str(guardian_path))
        mod = importlib.util.module_from_spec(spec)
        # This will execute module-level code but not main()
        spec.loader.exec_module(mod)
        print(f"    Version: {mod.VERSION}")
        print("    PASS")
    except SyntaxError as e:
        print(f"    FAIL: Syntax error at line {e.lineno}: {e.msg}")
        print("    FIX:  Re-download guardian_system.py")
    except Exception as e:
        print(f"    FAIL: {type(e).__name__}: {e}")
else:
    print("    SKIP: guardian_system.py not found in same directory")
    print(f"    PUT IT HERE: {script_dir}")

print()
print("=" * 60)
print("DIAGNOSTIC COMPLETE")
print("=" * 60)
print()
print("If all tests pass but guardian_system.py still fails,")
print("run it with full error output:")
print()
print(f"  cd {script_dir}")
print("  python guardian_system.py list 2>&1")
print()
print("Then copy/paste the FULL error output back to Claude.")
