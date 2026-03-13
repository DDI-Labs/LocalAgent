"""Hardcoded test bookings for the mock verification server.

Each booking maps a license plate to a site, building, bay, and driver name.
The agent's job is to query by plate and read the result on screen.
"""

BOOKINGS = [
    {
        "plate": "ABC-1234",
        "driver": "James Whitfield",
        "building": "Tower A",
        "bay": "B12",
        "site": "tower-a",
        "reason": "Employee",
        "status": "active",
    },
    {
        "plate": "XYZ-5678",
        "driver": "Maria Gonzalez",
        "building": "Tower A",
        "bay": "A03",
        "site": "tower-a",
        "reason": "Contractor",
        "status": "active",
    },
    {
        "plate": "DEF-9012",
        "driver": "Chen Wei",
        "building": "Building B",
        "bay": "V22",
        "site": "building-b",
        "reason": "Visitor",
        "status": "active",
    },
    {
        "plate": "GHI-3456",
        "driver": "Sarah Okonkwo",
        "building": "Parking HQ",
        "bay": "P01",
        "site": "parking-hq",
        "reason": "Staff",
        "status": "active",
    },
    {
        "plate": "JKL-7890",
        "driver": "Tom Hendricks",
        "building": "Mall West",
        "bay": "MW-15",
        "site": "mall-west",
        "reason": "Tenant",
        "status": "active",
    },
    {
        "plate": "MNO-2345",
        "driver": "Aisha Patel",
        "building": "Tower A",
        "bay": "B07",
        "site": "tower-a",
        "reason": "Visitor",
        "status": "expired",
    },
    {
        "plate": "PQR-6789",
        "driver": "Erik Johansson",
        "building": "Building B",
        "bay": "V10",
        "site": "building-b",
        "reason": "Delivery",
        "status": "active",
    },
    {
        "plate": "STU-0123",
        "driver": "Fatima Al-Rashid",
        "building": "Mall West",
        "bay": "MW-03",
        "site": "mall-west",
        "reason": "Employee",
        "status": "suspended",
    },
]

# Quick lookup by plate
_BY_PLATE = {b["plate"]: b for b in BOOKINGS}


def lookup(plate: str) -> dict | None:
    """Look up a booking by license plate (case-insensitive). Returns None if not found."""
    return _BY_PLATE.get(plate.upper().strip())
