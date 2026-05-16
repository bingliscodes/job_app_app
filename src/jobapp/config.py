from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class UserConfig:
    name: str
    email: str
    phone: str = ""
    resume_path: str = "./my_resume.pdf"
    github_url: str = ""
    linkedin_url: str = ""


@dataclass
class PreferencesConfig:
    roles: list[str] = field(default_factory=lambda: ["software engineer"])
    locations: list[str] = field(default_factory=lambda: ["Remote", "United States"])
    max_results_per_source: int = 25
    days_posted: int = 7
    min_years: int = 0
    max_years: int = 4
    country: str = "us"  # ISO 3166-1 alpha-2; used for Adzuna country endpoint
    # Additional companies to treat as login-walled (extend the built-in list
    # in sourcing/account_required.py:DEFAULT_ACCOUNT_REQUIRED).
    extra_account_required_companies: list[str] = field(default_factory=list)


@dataclass
class ApiKeysConfig:
    anthropic: str = ""
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""


@dataclass
class AiConfig:
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 4096


@dataclass
class OutputConfig:
    directory: str = "./output"


@dataclass
class Config:
    user: UserConfig
    preferences: PreferencesConfig
    api_keys: ApiKeysConfig
    ai: AiConfig
    output: OutputConfig


def load_config(path: str = "config.toml") -> Config:
    config_path = Path(path)
    if not config_path.exists():
        print(f"Error: Config file not found at {config_path.resolve()}", file=sys.stderr)
        print("Copy config.example.toml to config.toml and fill in your details.", file=sys.stderr)
        sys.exit(1)

    with open(config_path, "rb") as f:
        raw = tomllib.load(f)

    user = UserConfig(**raw.get("user", {}))
    preferences = PreferencesConfig(**raw.get("preferences", {}))
    api_keys = ApiKeysConfig(**raw.get("api_keys", {}))
    ai = AiConfig(**raw.get("ai", {}))
    output = OutputConfig(**raw.get("output", {}))

    # Environment variables override config file values
    if key := os.environ.get("ANTHROPIC_API_KEY"):
        api_keys.anthropic = key
    if key := os.environ.get("ADZUNA_APP_ID"):
        api_keys.adzuna_app_id = key
    if key := os.environ.get("ADZUNA_APP_KEY"):
        api_keys.adzuna_app_key = key

    return Config(
        user=user,
        preferences=preferences,
        api_keys=api_keys,
        ai=ai,
        output=output,
    )
