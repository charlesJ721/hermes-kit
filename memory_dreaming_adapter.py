#!/usr/bin/env python3
"""Memory Dreaming Adapter — offline memory consolidation engine.

Reads MEMORY.md, USER.md, and fact_store to identify merge/compress/remove
candidates. Produces a structured plan that respects four safety boundaries
discovered through SERI adversarial review (Gemini Review, 2026-07-06):

  BLOCKING gates (do not auto-execute):
  1. Triage rules (MEMORY[8]) — compression must not change behavioral threshold
  2. Active environment limitations (FACT[15], FACT[16]) — keep while upstream unresolved
  3. System authorization (FACT[8]) — migrate to skill/vault, not just cold-store
  4. Credential-like entries (FACT[18]) — require human confirmation before removal

Usage:
    python3 memory_dreaming_adapter.py              # scan only, produce plan
    python3 memory_dreaming_adapter.py --dry-run    # scan only
    python3 memory_dreaming_adapter.py --safe-only  # execute only low/medium risk actions
    python3 memory_dreaming_adapter.py --json       # machine-readable output

Integration: cron nightly at 3am. Runs in read-only mode by default;
execution requires explicit --safe-only or per-action approval.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Discovery rules — learned from Scout (Opus) + Establish (GPT-5.5) + Review (Gemini)
# ---------------------------------------------------------------------------

# Patterns that indicate an entry is stale/obsolete
STALE_PATTERNS: List[Tuple[str, str]] = [
    (r"adhoc.*签名", "TCC adhoc signing — one-shot system authorization"),
    (r"测试密码", "Test credential — must verify before removal"),
    (r"已停用|已废弃|\(deprecated\)|\(obsolete\)", "Explicitly marked as deprecated"),
    (r"workaround.*obsolete|不再需要", "Workaround no longer needed"),
]

# Patterns identifying entries that MUST NOT be auto-modified
RED_LINE_PATTERNS: List[str] = [
    r"雷区",
    r"认知引擎",
    r"基调",
    r"行为准则",
    r"Triage纪律",
    r"设计哲学.*万源归宗",
    r"永远能干预",
    r"能查却反问",
]

# Cross-system duplication: same fact in MEMORY + USER + fact_store
# Key: canonical topic, Value: (memory_keyword, user_keyword, fact_keyword)
DUPLICATE_TOPICS: List[Tuple[str, str, str, str]] = [
    ("VPS/proxy", "BandwagonHost|Xray|VLESS|SOCKS5|代理", "VPS.*CN2|搬瓦工", "VPS.*CN2|代理.*mihomo"),
    ("设计哲学", "万源归宗|架构偏好", "万源归宗|设计哲学", "万源归宗"),
    ("Triage", "Triage纪律|who在how前", "Triage纪律|who在how前", "行为准则|who.*how"),
    ("GitHub/cron", "digital-twin.*cron|GitHub", "digital-twin|GitHub", ""),
    ("网络路由", "Xray|SOCKS5|NO_PROXY|OR走VPS", "", "代理.*mihomo|境外API"),
]


@dataclass
class Entry:
    """A single memory entry from any source."""
    source: str          # "MEMORY", "USER", "FACT"
    index: int           # position in source
    content: str         # full text
    char_count: int      # byte length
    category: str = ""   # fact_store category or MEMORY tier

@dataclass  
class Action:
    """A proposed consolidation action."""
    action_id: int
    action_type: str     # MERGE, COMPRESS, REMOVE, RELOCATE
    targets: List[str]   # entry references like "MEMORY[5]", "FACT[10]"
    description: str
    before_texts: List[str] = field(default_factory=list)
    after_text: str = ""
    char_savings: int = 0
    risk: str = "LOW"    # LOW, MEDIUM, HIGH, BLOCKED
    blocked_by_gemini: bool = False
    gemini_reason: str = ""


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def dream(mem_path: str = "~/.hermes/memories/MEMORY.md",
          user_path: str = "~/.hermes/memories/USER.md",
          dry_run: bool = True) -> Dict[str, Any]:
    """Run the full dreaming cycle: discover → classify → plan.
    
    Returns {status, entries_scanned, actions, total_savings, blocked_actions}.
    """
    mem = Path(mem_path).expanduser()
    user = Path(user_path).expanduser()
    
    # Phase 1: Load all entries
    entries = _load_all_entries(mem, user)
    
    # Phase 2: Discover candidates
    actions = _discover_candidates(entries)
    
    # Phase 3: Apply Review BLOCKING gates
    actions = _apply_review_gates(actions)
    
    safe_actions = [a for a in actions if a.risk != "BLOCKED"]
    blocked = [a for a in actions if a.risk == "BLOCKED"]
    total_savings = sum(a.char_savings for a in safe_actions)
    
    report = {
        "status": "plan_produced" if dry_run else "executed",
        "entries_scanned": len(entries),
        "actions": [{
            "id": a.action_id,
            "type": a.action_type,
            "targets": a.targets,
            "description": a.description,
            "char_savings": a.char_savings,
            "risk": a.risk,
            "blocked": a.blocked_by_gemini,
            "after": a.after_text if a.action_type != "REMOVE" else "[REMOVED]",
            "before_texts": a.before_texts,
        } for a in actions],
        "total_savings": total_savings,
        "blocked_actions": len(blocked),
        "blocked_savings": sum(a.char_savings for a in blocked),
        "dreamed_at": datetime.now().isoformat(),
    }
    
    return report


def execute_safe_actions(actions: List[Action], 
                         mem_path: str = "~/.hermes/memories/MEMORY.md",
                         user_path: str = "~/.hermes/memories/USER.md") -> Dict[str, Any]:
    """Execute only LOW and MEDIUM risk actions. HIGH/BLOCKED actions are skipped.
    
    WARNING: This modifies MEMORY.md and USER.md on disk.
    Always run dream(dry_run=True) first and review the plan.
    """
    safe = [a for a in actions if a.risk in ("LOW", "MEDIUM") and not a.blocked_by_gemini]
    
    if not safe:
        return {"status": "nothing_to_execute", "actions_executed": 0}
    
    mem_path = Path(mem_path).expanduser()
    user_path = Path(user_path).expanduser()
    
    # Backup before modifying
    _backup(mem_path)
    _backup(user_path)
    
    executed = 0
    for action in safe:
        try:
            _execute_action(action, mem_path, user_path)
            executed += 1
        except Exception as e:
            print(f"  FAILED action {action.action_id}: {e}", file=sys.stderr)
    
    return {
        "status": "executed",
        "actions_executed": executed,
        "actions_skipped": len(actions) - executed,
    }


# ---------------------------------------------------------------------------
# Internal: Entry loading
# ---------------------------------------------------------------------------

def _load_all_entries(mem_path: Path, user_path: Path) -> List[Entry]:
    entries = []
    
    # Load MEMORY.md
    if mem_path.exists():
        content = mem_path.read_text()
        parts = [e.strip() for e in content.split('§') if e.strip()]
        for i, part in enumerate(parts):
            entries.append(Entry(source="MEMORY", index=i, content=part, char_count=len(part)))
    
    # Load USER.md
    if user_path.exists():
        content = user_path.read_text()
        parts = [e.strip() for e in content.split('§') if e.strip()]
        for i, part in enumerate(parts):
            entries.append(Entry(source="USER", index=i, content=part, char_count=len(part)))
    
    # Load fact_store from Holographic memory DB
    try:
        db_path = Path.home() / ".hermes" / "memory_store.db"
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            'SELECT fact_id, content, category, tags, trust_score '
            'FROM facts ORDER BY fact_id'
        ).fetchall()
        conn.close()
        for row in rows:
            entries.append(Entry(
                source="FACT", index=row[0],
                content=row[1],
                char_count=len(row[1]),
                category=row[2] or 'general'
            ))
    except Exception:
        pass  # fact_store unavailable — skip, not fatal
    
    return entries


# ---------------------------------------------------------------------------
# Internal: Candidate discovery
# ---------------------------------------------------------------------------

def _discover_candidates(entries: List[Entry]) -> List[Action]:
    actions: List[Action] = []
    aid = 0
    
    # Rule 1: Cross-source duplicates
    for topic, mem_kw, user_kw, fact_kw in DUPLICATE_TOPICS:
        mem_matches = [e for e in entries if e.source == "MEMORY" and re.search(mem_kw, e.content)]
        user_matches = [e for e in entries if e.source == "USER" and re.search(user_kw, e.content)] if user_kw else []
        fact_matches = [e for e in entries if e.source == "FACT" and re.search(fact_kw, e.content)] if fact_kw else []
        
        if len(mem_matches) + len(user_matches) + len(fact_matches) >= 2:
            aid += 1
            targets = [f"{e.source}[{e.index}]" for e in mem_matches + user_matches + fact_matches]
            # Keep MEMORY version (injected every turn), remove others
            keeper = mem_matches[0] if mem_matches else (user_matches[0] if user_matches else fact_matches[0])
            removals = [e for e in user_matches + fact_matches if e != keeper]
            
            risk = "LOW"
            if re.search('|'.join(RED_LINE_PATTERNS), topic):
                risk = "BLOCKED"
            
            actions.append(Action(
                action_id=aid, action_type="MERGE",
                targets=targets,
                description=f"Dedup '{topic}' — keep {keeper.source}[{keeper.index}], remove {len(removals)} copies",
                before_texts=[e.content for e in mem_matches + user_matches + fact_matches],
                after_text=keeper.content,
                char_savings=sum(e.char_count for e in removals),
                risk=risk,
            ))
    
    # Rule 2: Stale entries
    for entry in entries:
        for pattern, reason in STALE_PATTERNS:
            if re.search(pattern, entry.content, re.IGNORECASE):
                risk = "HIGH" if "密码" in entry.content else "MEDIUM"
                aid += 1
                actions.append(Action(
                    action_id=aid, action_type="REMOVE",
                    targets=[f"{entry.source}[{entry.index}]"],
                    description=f"Stale: {reason}",
                    before_texts=[entry.content],
                    after_text="",
                    char_savings=entry.char_count,
                    risk=risk,
                ))
                break
    
    # Rule 3: Compressible entries (>150 chars, verbose patterns)
    verbose_patterns = [
        (r'\(.*?\)', "parenthetical clarifications"),
        (r'例如.*?[。.]', "verbose examples"),
        (r'——.*?[。.]', "em-dash elaborations"),
    ]
    for entry in entries:
        if entry.char_count > 150 and entry.source in ("MEMORY", "USER"):
            for pattern, reason in verbose_patterns:
                matches = re.findall(pattern, entry.content)
                if len(matches) >= 2:
                    aid += 1
                    compressed = re.sub(pattern, '', entry.content)
                    compressed = re.sub(r'\s+', ' ', compressed).strip()
                    savings = entry.char_count - len(compressed)
                    if savings > 20:  # Only propose if meaningful savings
                        risk = "BLOCKED" if re.search('|'.join(RED_LINE_PATTERNS), entry.content) else "LOW"
                        actions.append(Action(
                            action_id=aid, action_type="COMPRESS",
                            targets=[f"{entry.source}[{entry.index}]"],
                            description=f"Compress: remove {reason}",
                            before_texts=[entry.content],
                            after_text=compressed,
                            char_savings=savings,
                            risk=risk,
                        ))
                    break
    
    return actions


# ---------------------------------------------------------------------------
# Internal: Review gates (Gemini BLOCKING findings)
# ---------------------------------------------------------------------------

def _apply_review_gates(actions: List[Action]) -> List[Action]:
    """Apply the 4 BLOCKING gates discovered by Gemini Review phase.
    
    Gate 1: Triage rule compression → must not change behavioral threshold
    Gate 2: Active environment limitations → keep while upstream unresolved  
    Gate 3: System authorization facts → migrate to skill/vault, not just cold-store
    Gate 4: Credential-like entries → require human confirmation
    """
    for action in actions:
        desc = action.description.lower()
        targets_str = ' '.join(action.targets)

        # All action types that mutate MEMORY.md / USER.md on disk.
        # LINK, CREATE, UPDATE are SQLite-only and non-destructive.
        _MUTATING = frozenset({"COMPRESS", "REMOVE", "MERGE", "DEDUP"})

        # Gate 1: Triage rules — any mutation could change behavioral threshold
        if re.search(r'triage|行为准则|who.*how', targets_str + desc):
            if action.action_type in _MUTATING:
                action.blocked_by_gemini = True
                action.gemini_reason = "BLOCKING: Triage rule — mutation must not change behavioral threshold (Constitution Art.1)"
                action.risk = "BLOCKED"

        # Gate 2: Active environment limitations — removal only (compression ok)
        if re.search(r'SSH|frp|frpc|TCC|环境', targets_str):
            if action.action_type == "REMOVE":
                action.blocked_by_gemini = True
                action.gemini_reason = "BLOCKING: Active environment limitation — keep while upstream unresolved (Constitution Art.2)"
                action.risk = "BLOCKED"

        # Gate 3: System authorization — must migrate before removal
        if re.search(r'TCC|adhoc.*签名|授权', targets_str):
            if action.action_type == "REMOVE":
                action.blocked_by_gemini = True
                action.gemini_reason = "BLOCKING: Migrate to skill/vault first, not just cold-store (Constitution Art.3)"
                action.risk = "BLOCKED"
        
        # Gate 4: Credentials
        if re.search(r'密码|password|credential', targets_str):
            action.blocked_by_gemini = True
            action.gemini_reason = "BLOCKING: Requires human confirmation (potential credential)"
            action.risk = "BLOCKED"
    
    return actions


# ---------------------------------------------------------------------------
# Internal: Execution
# ---------------------------------------------------------------------------

def _backup(path: Path) -> None:
    """Create timestamped backup with seconds to avoid same-day collision."""
    if not path.exists():
        return
    ts = datetime.now().strftime("%Y-%m-%dT%H%M%S")
    backup = path.with_suffix(f".md.dreaming-backup-{ts}")
    backup.write_text(path.read_text())


def _execute_action(action: Action, mem_path: Path, user_path: Path) -> None:
    """Execute a single action on disk."""
    if action.action_type == "REMOVE":
        for target in action.targets:
            source, idx_str = target.split('[')
            idx = int(idx_str.rstrip(']'))
            if source == "MEMORY":
                _remove_memory_entry(mem_path, idx)
            elif source == "USER":
                _remove_memory_entry(user_path, idx)
    
    elif action.action_type == "COMPRESS":
        for target in action.targets:
            source, idx_str = target.split('[')
            idx = int(idx_str.rstrip(']'))
            if source == "MEMORY":
                _replace_entry(mem_path, idx, action.before_texts[0], action.after_text)
            elif source == "USER":
                _replace_entry(user_path, idx, action.before_texts[0], action.after_text)
    
    elif action.action_type == "MERGE":
        # Keep first target, remove others in descending order
        removals = []
        for target in action.targets[1:]:
            source, idx_str = target.split('[')
            idx = int(idx_str.rstrip(']'))
            if source == "MEMORY":
                removals.append((mem_path, idx))
            elif source == "USER":
                removals.append((user_path, idx))
        # Group by path, sort by descending index, remove
        for path, indices in _group_by_path(removals):
            _remove_entries_sorted(path, indices)


def _remove_memory_entry(path: Path, idx: int) -> None:
    """Remove entry at index, using same filtered indexing as _load_all_entries.

    _load_all_entries strips empty § segments and assigns sequential indices
    to the remaining non-empty parts.  This function mirrors that: it filters
    empty parts, locates the entry at `idx`, then removes it by substring
    replacement in the original content (avoiding §-split index drift).
    """
    content = path.read_text()
    raw_parts = content.split('§')
    # Build the filtered index → raw_index mapping
    filtered = [(ri, p) for ri, p in enumerate(raw_parts) if p.strip()]
    if idx < len(filtered):
        ri, target = filtered[idx]
        # Remove the target part: replace the exact segment delimited by §
        # Find the substring in original content and remove it
        before = '§'.join(raw_parts[:ri])
        after = '§'.join(raw_parts[ri + 1:])
        path.write_text(before + after if before.endswith('§') or not after else before + '§' + after)
    # else: entry already gone or index invalid — no-op


def _remove_entries_sorted(path: Path, indices: List[int]) -> None:
    """Remove multiple entries in descending index order to avoid shift."""
    for idx in sorted(indices, reverse=True):
        _remove_memory_entry(path, idx)


def _group_by_path(removals: List[Tuple[Path, int]]) -> List[Tuple[Path, List[int]]]:
    """Group (path, index) pairs by path for batch removal."""
    groups: Dict[Path, List[int]] = {}
    for p, idx in removals:
        if p not in groups:
            groups[p] = []
        groups[p].append(idx)
    return list(groups.items())


def _replace_entry(path: Path, idx: int, old_text: str, new_text: str) -> None:
    """Replace entry text. Uses substring match first, falls back to §-indexed."""
    content = path.read_text()
    # Try exact substring replacement first (most reliable)
    if old_text in content:
        content = content.replace(old_text, new_text, 1)
        path.write_text(content)
        return
    # Fall back to §-based indexed replacement
    parts = content.split('§')
    if idx < len(parts):
        if old_text.strip() in parts[idx]:
            parts[idx] = parts[idx].replace(old_text.strip(), new_text)
            path.write_text('§'.join(parts))
            return
    raise ValueError(f"Cannot find entry {idx} in {path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(prog="memory-dreaming", 
                                     description="Memory Dreaming Engine — consolidate memory nightly")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Scan and produce plan only (default)")
    parser.add_argument("--safe-only", action="store_true",
                        help="Execute only LOW/MEDIUM risk actions (skips BLOCKED/HIGH)")
    parser.add_argument("--json", action="store_true",
                        help="Machine-readable JSON output")
    args = parser.parse_args()
    
    report = dream(dry_run=not args.safe_only)
    
    if args.safe_only:
        # Map report dict keys to Action dataclass fields
        # Report: {id, type, targets, description, char_savings, risk, blocked, after}
        # Action:  {action_id, action_type, targets, description, after_text, char_savings, risk, blocked_by_gemini, before_texts}
        field_map = {'id': 'action_id', 'type': 'action_type', 'after': 'after_text', 'blocked': 'blocked_by_gemini'}
        actions = []
        for a in report['actions']:
            mapped = {}
            for k, v in a.items():
                new_k = field_map.get(k, k)
                mapped[new_k] = v
            mapped.setdefault('before_texts', [])
            mapped.setdefault('gemini_reason', '')
            actions.append(Action(**mapped))
        exec_report = execute_safe_actions(actions)
        report.update(exec_report)
    
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"=== Memory Dreaming Report — {report['dreamed_at'][:19]} ===")
        print(f"Entries scanned: {report['entries_scanned']}")
        print(f"Actions: {len(report['actions'])} total")
        safe = [a for a in report['actions'] if a['risk'] != 'BLOCKED']
        blocked = [a for a in report['actions'] if a['risk'] == 'BLOCKED']
        print(f"  Safe: {len(safe)} ({sum(a['char_savings'] for a in safe)} chars)")
        print(f"  Blocked: {len(blocked)} ({sum(a['char_savings'] for a in blocked)} chars)")
        
        if blocked:
            print(f"\n### BLOCKED (Review gates) ###")
            for a in blocked:
                print(f"  [{a.get('id', a.get('action_id', '?'))}] {a['description']}")
        
        if safe:
            print(f"\n### Safe Actions (can execute with --safe-only) ###")
            for a in safe:
                print(f"  [{a.get('id', a.get('action_id', '?'))}] {a.get('type', a.get('action_type', '?'))}: {a['description']} ({a['char_savings']} chars, {a['risk']})")
        
        if not args.safe_only:
            print(f"\nRun with --safe-only to execute the {len(safe)} safe actions.")
