#!/usr/bin/env python3
"""Post-install patch for Windows.

Fixes issues that break Claude Code hooks on Windows:
1. Orphan hook entries left by --update (entries without __module__ duplicated by new ones)
2. Hook command paths in settings.json (forward slashes + quoted .py paths)
3. Hardcoded /tmp in harness lock functions (doesn't exist on Windows)
4. Missing python3 executable (Windows ships only python.exe)
5. Verify codeagent-wrapper availability after install
6. Installed config/docs updates (model IDs, skill text)

Run:  python windows-patch.py [--dry-run]
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

DRY_RUN = "--dry-run" in sys.argv
CLAUDE_DIR = Path.home() / ".claude"

fixed: list[str] = []
skipped: list[str] = []
errors: list[str] = []
verified: list[str] = []
warnings: list[str] = []

PYTHON_HOOK_COMMAND_RE = re.compile(
    r"^(?P<prefix>\s*python3(?:\.exe)?\s+)"
    r'(?P<path>"[^"]+\.py"|[^"]+?\.py)'
    r"(?P<suffix>(?:\s+.*)?)$"
)


def print_step(index: int, total: int, title: str) -> None:
    print(f"[{index}/{total}] {title}")


def patch_file(
    path: Path,
    replacements: list[tuple[str, str]],
    label: str,
    check_stale: bool = False,
) -> bool:
    """Apply text replacements to a file. Returns True if changed."""
    if not path.is_file():
        skipped.append(f"{label}: file not found")
        return False
    text = path.read_text(encoding="utf-8")
    new_text = text
    for old, new in replacements:
        new_text = new_text.replace(old, new)
    if new_text == text:
        if check_stale and any(old in text for old in MODEL_REPLACEMENTS):
            errors.append(
                f"{label}: stale model IDs found but replacements didn't match (format changed?)"
            )
        else:
            skipped.append(f"{label}: already patched")
        return False
    if not DRY_RUN:
        path.write_text(new_text, encoding="utf-8")
    fixed.append(label)
    return True


# -----------------------------------------------------------------------
# 1. Fix settings.json: orphan hook entries left by --update
# -----------------------------------------------------------------------
def fix_orphan_hooks() -> None:
    """Remove orphan hook entries (no __module__) duplicated by __module__ entries.

    After `npx --update` re-installs modules, new entries with __module__ are added
    but old entries without __module__ (from the original install) are not removed.
    This causes each hook to fire 2-3× per event.
    """
    print_step(1, 6, "settings.json — orphan hooks from prior installs")
    settings_path = CLAUDE_DIR / "settings.json"
    if not settings_path.is_file():
        skipped.append("settings.json orphan hooks: not found")
        return

    data = json.loads(settings_path.read_text(encoding="utf-8"))
    hooks = data.get("hooks")
    if not hooks:
        skipped.append("settings.json orphan hooks: no hooks section")
        return

    def normalize_cmd(cmd: str) -> str:
        return cmd.replace("\\", "/").replace('"', "").lower().strip()

    def entry_cmds(entry: dict) -> set:
        return {
            normalize_cmd(h.get("command", ""))
            for h in entry.get("hooks", [])
            if h.get("command")
        }

    total_removed = 0
    for event, entries in hooks.items():
        # Collect normalized commands from authoritative (__module__) entries
        authoritative: set = set()
        for entry in entries:
            if "__module__" in entry:
                authoritative |= entry_cmds(entry)

        if not authoritative:
            continue  # No module-owned entries — keep everything as-is

        before = len(entries)
        hooks[event] = [
            entry
            for entry in entries
            if "__module__" in entry or not entry_cmds(entry).issubset(authoritative)
        ]
        total_removed += before - len(hooks[event])

    if total_removed == 0:
        skipped.append("settings.json orphan hooks: none found")
        return

    if not DRY_RUN:
        data["hooks"] = hooks
        settings_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    fixed.append(f"settings.json: removed {total_removed} orphan hook entries")


# -----------------------------------------------------------------------
# 2. Fix settings.json: hook command paths and quoting
# -----------------------------------------------------------------------
def fix_settings_json() -> None:
    print_step(2, 6, "settings.json — normalize hook commands")
    settings_path = CLAUDE_DIR / "settings.json"
    if not settings_path.is_file():
        skipped.append("settings.json: not found")
        return

    data = json.loads(settings_path.read_text(encoding="utf-8"))
    hooks = data.get("hooks")
    if not hooks:
        skipped.append("settings.json: no hooks section")
        return

    def normalize_hook_command(command: str) -> str:
        normalized = command.replace("\\", "/")
        match = PYTHON_HOOK_COMMAND_RE.match(normalized)
        if not match:
            return normalized

        script_path = match.group("path")
        if script_path.startswith('"') and script_path.endswith('"'):
            script_path = script_path[1:-1]

        return f'{match.group("prefix")}"{script_path}"{match.group("suffix")}'

    def fix_hook_commands(obj):
        if isinstance(obj, dict):
            fixed_obj = {}
            for key, value in obj.items():
                if key == "command" and isinstance(value, str):
                    fixed_obj[key] = normalize_hook_command(value)
                else:
                    fixed_obj[key] = fix_hook_commands(value)
            return fixed_obj
        if isinstance(obj, list):
            return [fix_hook_commands(item) for item in obj]
        return obj

    new_hooks = fix_hook_commands(hooks)
    if new_hooks == hooks:
        skipped.append("settings.json hooks: commands already normalized")
        return

    if not DRY_RUN:
        data["hooks"] = new_hooks
        settings_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    fixed.append("settings.json: normalized hook commands (slashes + quotes)")


# -----------------------------------------------------------------------
# 3. Fix harness hooks: Path("/tmp") → Path(tempfile.gettempdir())
# -----------------------------------------------------------------------
def fix_tmp_paths() -> None:
    print_step(3, 6, "Harness hooks — hardcoded /tmp")
    targets = [
        CLAUDE_DIR / "skills" / "harness" / "hooks" / "_harness_common.py",
        CLAUDE_DIR / "skills" / "harness" / "hooks" / "harness-claim.py",
        CLAUDE_DIR / "skills" / "harness" / "hooks" / "harness-renew.py",
    ]
    for path in targets:
        label = path.name
        if not path.is_file():
            skipped.append(f"{label}: not found")
            continue

        text = path.read_text(encoding="utf-8")
        new_text = text

        # Add import tempfile if missing
        if "import tempfile" not in new_text:
            inserted = False
            for anchor in ("import time\n", "import sys\n"):
                if anchor in new_text:
                    new_text = new_text.replace(anchor, anchor + "import tempfile\n", 1)
                    inserted = True
                    break
            if not inserted:
                errors.append(
                    f"{label}: cannot insert 'import tempfile' — no known anchor found; skipping /tmp replacement"
                )
                continue

        # Replace Path("/tmp") with Path(tempfile.gettempdir())
        new_text = new_text.replace('Path("/tmp")', "Path(tempfile.gettempdir())")

        if new_text == text:
            skipped.append(f"{label}: already patched")
            continue
        if not DRY_RUN:
            path.write_text(new_text, encoding="utf-8")
        fixed.append(f"{label}: /tmp → tempfile.gettempdir()")


# -----------------------------------------------------------------------
# 4. Fix python3 symlink
# -----------------------------------------------------------------------
def fix_python3_symlink() -> None:
    print_step(4, 6, "python3 symlink")
    python_exe = shutil.which("python")
    if not python_exe:
        errors.append("python3 symlink: python.exe not found in PATH")
        return

    python_dir = Path(python_exe).parent
    python3_exe = python_dir / "python3.exe"

    if python3_exe.exists():
        skipped.append("python3.exe: already exists")
        return

    if DRY_RUN:
        fixed.append(f"python3.exe: would create symlink at {python3_exe}")
        return

    try:
        os.symlink(python_exe, str(python3_exe))
        fixed.append(f"python3.exe: symlink created at {python3_exe}")
    except OSError as e:
        # Symlink creation may require admin rights on older Windows
        errors.append(
            f"python3.exe: symlink failed ({e}). "
            "Try running as Administrator, or copy python.exe to python3.exe manually."
        )


# -----------------------------------------------------------------------
# 5. Verify codeagent-wrapper availability
# -----------------------------------------------------------------------
def verify_codeagent_wrapper() -> None:
    print_step(5, 6, "codeagent-wrapper — post-install verification")

    def get_version(binary: Path | str) -> str | None:
        try:
            result = subprocess.run(
                [str(binary), "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None

        if result.returncode != 0:
            return None
        version = (result.stdout or result.stderr).strip()
        return version or None

    wrapper_on_path = shutil.which("codeagent-wrapper")
    if wrapper_on_path:
        version = get_version(wrapper_on_path)
        if version:
            verified.append(f"codeagent-wrapper: available via PATH ({version})")
            return
        errors.append(
            f"codeagent-wrapper: found in PATH at {wrapper_on_path} but '--version' failed"
        )
        return

    fallback = Path.home() / "bin" / "codeagent-wrapper.exe"
    if fallback.is_file():
        version = get_version(fallback)
        if version:
            verified.append(f"codeagent-wrapper: available at {fallback} ({version})")
            warnings.append(
                "codeagent-wrapper: not in current PATH; open a new shell or add %USERPROFILE%\\bin manually if commands fail"
            )
            return
        errors.append(f"codeagent-wrapper: found at {fallback} but '--version' failed")
        return

    errors.append("codeagent-wrapper: not found in PATH or %USERPROFILE%\\bin")


# -----------------------------------------------------------------------
# 6. Fix installed config/docs updates
# -----------------------------------------------------------------------
MODEL_REPLACEMENTS = {
    "claude-opus-4-5-20251101": "claude-opus-4-8",
    "claude-opus-4-6": "claude-opus-4-8",
    "claude-sonnet-4-5-20250929": "claude-sonnet-4-6",
    "gpt-4.1": "gpt-5.5",
    "gpt-5.2": "gpt-5.5",
    "gpt-5.3-codex": "gpt-5.5",
    "gpt-5.4": "gpt-5.5",
    "gemini-3-pro-preview": "gemini-3.1-pro-preview",
}

AGENT_OVERRIDES = {
    "code-architect": {"backend": "claude", "model": "claude-opus-4-8"},
    "code-reviewer": {"backend": "codex", "model": "gpt-5.5", "reasoning": "xhigh"},
    "code-explorer": {"backend": "claude", "model": "claude-sonnet-4-6"},
    "explore": {"backend": "claude", "model": "claude-haiku-4-5-20251001"},
    "librarian": {"backend": "codex", "model": "gpt-5.5", "reasoning": "xhigh"},
}


def fix_models() -> None:
    print_step(6, 6, "Installed config/docs updates")
    codeagent_dir = Path.home() / ".codeagent"

    # --- models.json (JSON-aware) ---
    models_path = codeagent_dir / "models.json"
    if models_path.is_file():
        data = json.loads(models_path.read_text(encoding="utf-8"))
        changed = False

        # default_model
        old_default = data.get("default_model", "")
        if old_default in MODEL_REPLACEMENTS:
            data["default_model"] = MODEL_REPLACEMENTS[old_default]
            changed = True

        agents = data.get("agents", {})
        for name, agent in agents.items():
            old_model = agent.get("model", "")
            # Global model replacement
            if old_model in MODEL_REPLACEMENTS:
                agent["model"] = MODEL_REPLACEMENTS[old_model]
                changed = True
            # Per-agent overrides (only for our modules, not user-defined agents)
            if name in AGENT_OVERRIDES:
                module = agent.get("__module__", "")
                if module in ("do", "omo", ""):
                    for key, val in AGENT_OVERRIDES[name].items():
                        if agent.get(key) != val:
                            agent[key] = val
                            changed = True
            # Ensure xhigh reasoning for all codex/gpt agents
            if agent.get("backend") == "codex" or "gpt" in agent.get("model", ""):
                if agent.get("reasoning") != "xhigh":
                    agent["reasoning"] = "xhigh"
                    changed = True

        if changed:
            if not DRY_RUN:
                models_path.write_text(
                    json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
                )
            fixed.append("models.json: updated model IDs and agent configs")
        else:
            skipped.append("models.json: already up to date")
    else:
        skipped.append("models.json: not found")

    # --- Installed docs/files (text replacement) ---
    text_replacements = list(MODEL_REPLACEMENTS.items())

    do_readme = CLAUDE_DIR / "skills" / "do" / "README.md"
    patch_file(
        do_readme, text_replacements, "skills/do/README.md: model IDs", check_stale=True
    )

    product_requirements = CLAUDE_DIR / "skills" / "product-requirements" / "SKILL.md"
    patch_file(
        product_requirements,
        [
            (
                "Think in English, respond to user in Chinese.",
                "Think in English, respond to user in Russian.",
            ),
        ],
        "skills/product-requirements/SKILL.md: Russian response",
    )

    do_install = CLAUDE_DIR / "skills" / "do" / "install.py"
    patch_file(
        do_install,
        [
            (
                "str(Path(HOOK_PATH).expanduser())",
                "Path(HOOK_PATH).expanduser().as_posix()",
            ),
        ],
        "skills/do/install.py: as_posix() for hook_command",
    )

    # --- do/install.py (template models) ---
    # Each replacement includes agent name as unique context to prevent wrong matches
    do_install_replacements = text_replacements + [
        (
            '"code-architect": {\n            "backend": "claude",\n            "model": "claude-sonnet-4-6"',
            '"code-architect": {\n            "backend": "claude",\n            "model": "claude-opus-4-8"',
        ),
        (
            '"code-reviewer": {\n            "backend": "claude",\n            "model": "claude-sonnet-4-6"',
            '"code-reviewer": {\n            "backend": "codex",\n            "model": "gpt-5.5",\n            "reasoning": "xhigh"',
        ),
    ]
    patch_file(
        do_install,
        do_install_replacements,
        "skills/do/install.py: model template",
        check_stale=True,
    )


# -----------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------
def main() -> int:
    if sys.platform != "win32":
        print("This patch is for Windows only. Exiting.")
        return 0

    mode = "DRY RUN" if DRY_RUN else "APPLY"
    print(f"=== myclaude Windows patch ({mode}) ===")
    print(f"Claude dir:  {CLAUDE_DIR}")
    print("-" * 50)

    fix_orphan_hooks()
    fix_settings_json()
    fix_tmp_paths()
    fix_python3_symlink()
    verify_codeagent_wrapper()
    fix_models()

    print("-" * 50)
    if fixed:
        heading = "Would change" if DRY_RUN else "Fixed"
        print(f"{heading} ({len(fixed)}):")
        for f in fixed:
            print(f"  + {f}")
    if errors:
        if fixed:
            print()
        print(f"Errors ({len(errors)}):")
        for e in errors:
            print(f"  ! {e}")
    if warnings:
        if fixed or errors:
            print()
        print(f"Warnings ({len(warnings)}):")
        for warning in warnings:
            print(f"  * {warning}")
    if verified:
        if fixed or errors or warnings:
            print()
        print(f"Verified ({len(verified)}):")
        for item in verified:
            print(f"  = {item}")

    if not fixed and not errors and not warnings and not verified:
        print("All good — nothing to patch.")
    elif DRY_RUN and fixed:
        print("\nRe-run without --dry-run to apply.")

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
