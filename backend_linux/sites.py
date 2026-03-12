"""Site definitions — each site the agent can connect to."""

SITES: dict[str, dict] = {
    "tower-a": {
        "name": "Tower A",
        "app": "nomachine",
        "host": "192.168.1.10",
        "username": "gateadmin",
        "password": "TowerA_2024!",
        "description": "Tower A main parking gate",
    },
    "building-b": {
        "name": "Building B",
        "app": "teamviewer",
        "remote_id": "1 234 567 890",
        "password": "bldgB9x#2",
        "description": "Building B visitor entrance",
    },
    "parking-hq": {
        "name": "Parking HQ",
        "app": "nomachine",
        "host": "10.0.0.50",
        "username": "hq_operator",
        "password": "HQpark!99",
        "description": "Central operations hub",
    },
    "mall-west": {
        "name": "Mall West",
        "app": "teamviewer",
        "remote_id": "9 876 543 210",
        "password": "mallW3st#",
        "description": "Mall West underground parking",
    },
    "google-test": {
        "name": "Google Test",
        "app": "google-chrome",
        "url": "https://www.google.com",
        "description": "Google search — for testing agent navigation only",
    },
}


def get_site(site_id: str) -> dict:
    """Look up a site by ID. Raises KeyError if not found."""
    if site_id not in SITES:
        available = ", ".join(SITES.keys())
        raise KeyError(f"Unknown site '{site_id}'. Available: {available}")
    return SITES[site_id]


def list_sites() -> list[dict]:
    """Return all sites as a list with their IDs included."""
    return [{"id": sid, **site} for sid, site in SITES.items()]
