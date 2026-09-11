#!/usr/bin/env python3
"""
Shuriken Config Loader

Central config loader for the Shuriken monorepo. Reads config/projects.yaml
and provides typed access to project configuration.

Two-tier hierarchy:  domain → project
    shuriken/projects/automation/maestro
    shuriken/projects/menu/analyzer
    shuriken/projects/menu/mapper

Project keys are addressed as:
    "maestro"                 ← shorthand (unique name lookup)
    "automation/maestro"      ← fully qualified domain/project

All CI scripts should use this instead of hardcoding values:

    from shuriken_config import get_project, get_all_projects, get_bitrise_apps, get_bs_custom_ids

    project = get_project("maestro")          # shorthand
    project = get_project("menu/analyzer")    # fully qualified

    bitrise_apps = get_bitrise_apps("maestro")
    bs_ids = get_bs_custom_ids("maestro")

    for key, project in get_all_projects().items():
        print(f"{key}: {project['name']}")
"""

import os
import sys

# Fix Windows console encoding
if sys.stdout.encoding and sys.stdout.encoding.lower().startswith('cp'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

try:
    import yaml
except ImportError:
    print("ERROR: 'pyyaml' package required. Run: pip install pyyaml")
    sys.exit(1)


# ── Locate config file ───────────────────────────────────────────
def _find_config_path() -> str:
    """Walk up from this script's directory to find config/projects.yaml."""
    candidates = [
        # From scripts/ci/ → ../../config/
        os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'projects.yaml'),
        # From repo root
        os.path.join(os.getcwd(), 'config', 'projects.yaml'),
    ]
    for path in candidates:
        resolved = os.path.abspath(path)
        if os.path.isfile(resolved):
            return resolved
    raise FileNotFoundError(
        "config/projects.yaml not found. "
        "Run from the Shuriken repo root or ensure the config file exists."
    )


# ── Load & cache ─────────────────────────────────────────────────
_config_cache = None

def _load_config() -> dict:
    global _config_cache
    if _config_cache is None:
        config_path = _find_config_path()
        with open(config_path, 'r', encoding='utf-8') as f:
            _config_cache = yaml.safe_load(f)
    return _config_cache


def reload_config() -> dict:
    """Force reload config from disk (useful after edits)."""
    global _config_cache
    _config_cache = None
    return _load_config()


# ── Public API ────────────────────────────────────────────────────

def get_defaults() -> dict:
    """Get global defaults from config."""
    return _load_config().get('defaults', {})


def _flatten_projects() -> dict:
    """Flatten the two-tier domains→projects hierarchy into a flat dict.

    Returns {project_key: config_dict} where config_dict has an extra
    '_domain' key with the parent domain name, and '_qualified_key'
    with 'domain/project'.

    Supports both old flat `projects:` format and new `domains:` format.
    """
    config = _load_config()

    # ── New format: domains → projects ──
    domains = config.get('domains', {})
    if domains:
        flat = {}
        for domain_key, domain_cfg in domains.items():
            domain_projects = domain_cfg.get('projects', {})
            for proj_key, proj_cfg in domain_projects.items():
                qualified = f"{domain_key}/{proj_key}"
                proj_cfg['_domain'] = domain_key
                proj_cfg['_domain_name'] = domain_cfg.get('name', domain_key)
                proj_cfg['_qualified_key'] = qualified
                flat[proj_key] = proj_cfg        # shorthand: "maestro"
                flat[qualified] = proj_cfg       # qualified: "automation/maestro"
        return flat

    # ── Legacy flat format: projects → {key: config} ──
    legacy = config.get('projects', {})
    for key, cfg in legacy.items():
        cfg['_domain'] = 'default'
        cfg['_domain_name'] = 'Default'
        cfg['_qualified_key'] = key
    return legacy


def get_all_projects() -> dict:
    """Get all project configurations (deduplicated — shorthand keys only).

    Returns {project_key: config_dict} with only the short names,
    not the qualified 'domain/project' duplicates.
    """
    flat = _flatten_projects()
    # Filter out qualified keys (contain '/') to avoid duplicates
    return {k: v for k, v in flat.items() if '/' not in k}


def get_all_domains() -> dict:
    """Get all domain configurations.

    Returns {domain_key: {name, description, owner, projects: {key: config}}}
    """
    config = _load_config()
    return config.get('domains', {})


def get_project(project_key: str) -> dict:
    """Get a specific project's configuration by key.

    Supports both shorthand ("maestro") and qualified ("automation/maestro").

    Args:
        project_key: Project key (e.g., 'maestro', 'menu/analyzer')

    Returns:
        Project configuration dict

    Raises:
        KeyError: If project not found
    """
    flat = _flatten_projects()
    if project_key not in flat:
        # Show only shorthand keys in error message
        available = ', '.join(k for k in flat.keys() if '/' not in k)
        raise KeyError(f"Project '{project_key}' not found. Available: {available}")
    return flat[project_key]


def get_project_names() -> list:
    """Get list of all project keys."""
    return list(get_all_projects().keys())


def get_bitrise_apps(project_key: str) -> dict:
    """Get Bitrise app configuration for a project.

    Returns dict of {brand: {title, slug, abbreviation}}
    """
    project = get_project(project_key)
    return project.get('bitrise', {})


def get_bs_custom_ids(project_key: str) -> dict:
    """Get BrowserStack custom IDs for a project.

    Returns dict of {brand: {android: id, ios: id}} or empty dict if no BS config.
    """
    project = get_project(project_key)
    bs = project.get('browserstack')
    if not bs:
        return {}
    return bs.get('custom_ids', {})


def get_pipeline_config(project_key: str) -> dict:
    """Get pipeline configuration for a project."""
    project = get_project(project_key)
    return project.get('pipeline', {})


def get_bitrise_workflow(project_key: str = None, env: str = None) -> str:
    """Resolve the Bitrise workflow name.

    Uses project-specific override if set, otherwise falls back to
    global default (which is just the env name, e.g., 'uat').
    """
    defaults = get_defaults()
    default_workflow = defaults.get('bitrise_workflow', env or 'uat')

    if project_key:
        project = get_project(project_key)
        return project.get('bitrise_workflow', default_workflow)

    return default_workflow


def list_projects_summary():
    """Print a formatted summary of all projects grouped by domain."""
    domains = get_all_domains()
    total = sum(len(d.get('projects', {})) for d in domains.values())

    print(f"\n{'=' * 65}")
    print(f"  Shuriken Projects ({total} projects across {len(domains)} domains)")
    print(f"{'=' * 65}")

    for domain_key, domain_cfg in domains.items():
        domain_name = domain_cfg.get('name', domain_key)
        domain_owner = domain_cfg.get('owner', '?')
        projects = domain_cfg.get('projects', {})

        print(f"\n  [{domain_key}] {domain_name}")
        print(f"  Owner: {domain_owner}")
        print(f"  {'-' * 55}")

        for proj_key, cfg in projects.items():
            ptype = cfg.get('type', '?')
            # Brands can come from 'bitrise' (Maestro) or 'brands' (menu projects)
            bitrise = cfg.get('bitrise') or {}
            brand_cfg = cfg.get('brands') or {}
            brands = list(bitrise.keys()) or list(brand_cfg.keys())
            has_bs = 'yes' if cfg.get('browserstack') else 'no'
            suites = cfg.get('pipeline', {}).get('suites', [])

            print(f"\n    {domain_key}/{proj_key}")
            print(f"      Name:         {cfg.get('name', proj_key)}")
            print(f"      Type:         {ptype}")
            print(f"      Brands:       {', '.join(brands) if brands else 'none'}")
            print(f"      BrowserStack: {has_bs}")
            print(f"      Path:         {cfg.get('path', '?')}")
            if suites:
                print(f"      Suites:       {', '.join(suites)}")

    print(f"\n{'=' * 65}\n")


# ── CLI: run directly to inspect config ──────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Shuriken Config Inspector")
    parser.add_argument('--project', '-p', help="Show specific project config")
    parser.add_argument('--list', '-l', action='store_true', help="List all projects")
    parser.add_argument('--json', '-j', action='store_true', help="Output as JSON")
    args = parser.parse_args()

    import json

    if args.project:
        try:
            cfg = get_project(args.project)
            if args.json:
                print(json.dumps(cfg, indent=2))
            else:
                print(f"\nProject: {args.project}")
                print(json.dumps(cfg, indent=2))
        except KeyError as e:
            print(f"Error: {e}")
            sys.exit(1)
    elif args.list or not args.project:
        if args.json:
            print(json.dumps(get_all_projects(), indent=2))
        else:
            list_projects_summary()
