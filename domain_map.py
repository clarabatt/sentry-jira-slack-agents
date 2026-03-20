import yaml
from pathlib import Path
from functools import lru_cache

DATA_DIR = Path(__file__).parent / "data"


@lru_cache
def load_domain_map() -> dict:
    return yaml.safe_load((DATA_DIR / "domain_map.yaml").read_text())


def lookup_team(url_path: str) -> dict:
    dm = load_domain_map()
    for team in dm["teams"]:
        for pattern in team["patterns"]:
            if pattern in url_path:
                return team
    return {
        "name": "Unknown",
        "slack_handle": "@devops",
        "leads": ["@john.lennon"],
        "patterns": [],
    }


def get_triage_owner() -> str:
    dm = load_domain_map()
    return dm["triage_rotation"]["current_owner"]
