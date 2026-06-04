"""CLI profile discovery.

A "profile" is a CLI config-home directory selected through an environment
variable. Codex reads ``CODEX_HOME`` and Claude reads ``CLAUDE_CONFIG_DIR``;
pointing either at an alternate directory switches the logged-in account.

Profiles are discovered by scanning the user's home directory for folders that
match each provider's config-dir naming convention:

- ``~/.codex``            -> profile "codex"        (the default account)
- ``~/.codex-shlomo``     -> profile "codex-shlomo"
- ``~/.claude``           -> profile "claude"       (the default account)
- ``~/.claude-michael``   -> profile "michael"

The default directory (no suffix) is always treated as the default profile and
runs with no environment override.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


@dataclass(frozen=True)
class CLIProfile:
    """One discovered CLI profile.

    ``name`` is the label shown in the UI and stored on the node. ``env`` is the
    environment overlay to merge into the subprocess; it is empty for the
    default profile so the CLI uses its normal config directory.
    """

    name: str
    directory: str
    env: Dict[str, str]
    is_default: bool


# Per-provider scan rules: the dot-folder base name plus the env var the CLI
# honours to relocate its config home. Providers absent from this map (e.g.
# Gemini) do not support profile selection.
_PROVIDER_RULES = {
    "codex": {"base": ".codex", "env_var": "CODEX_HOME"},
    "claude": {"base": ".claude", "env_var": "CLAUDE_CONFIG_DIR"},
}


def provider_supports_profiles(provider_name: str) -> bool:
    return provider_name in _PROVIDER_RULES


def _home_dir() -> Path:
    return Path.home()


def discover_profiles(provider_name: str) -> List[CLIProfile]:
    """Return the profiles available for ``provider_name``.

    The default directory (``~/.codex`` or ``~/.claude``) is listed first when
    it exists, followed by suffixed directories sorted by name. An empty list
    means the provider does not support profiles or none were found.
    """
    rule = _PROVIDER_RULES.get(provider_name)
    if rule is None:
        return []

    base = rule["base"]
    env_var = rule["env_var"]
    home = _home_dir()

    default_profile: Optional[CLIProfile] = None
    suffixed: List[CLIProfile] = []

    try:
        entries = list(home.iterdir())
    except OSError:
        return []

    for entry in entries:
        if not entry.is_dir():
            continue
        folder = entry.name
        if folder == base:
            default_profile = CLIProfile(
                name=base.lstrip("."),
                directory=str(entry),
                env={},
                is_default=True,
            )
        elif folder.startswith(base + "-"):
            suffix = folder[len(base) + 1:]
            if not suffix:
                continue
            suffixed.append(
                CLIProfile(
                    name=suffix,
                    directory=str(entry),
                    env={env_var: str(entry)},
                    is_default=False,
                )
            )

    suffixed.sort(key=lambda p: p.name.lower())

    profiles: List[CLIProfile] = []
    if default_profile is not None:
        profiles.append(default_profile)
    profiles.extend(suffixed)
    return profiles


def resolve_profile_env(provider_name: str, profile_name: Optional[str]) -> Dict[str, str]:
    """Return the environment overlay for a node's saved profile selection.

    An empty dict means "use the CLI default" — the case for no selection, the
    default profile, or an unknown provider/profile. Unknown profile names fall
    back to the default rather than raising so stale saved workflows still run.
    """
    if not profile_name:
        return {}
    for profile in discover_profiles(provider_name):
        if profile.name == profile_name:
            return dict(profile.env)
    return {}
