import os
import sys
import tempfile

# Make `app` importable when pytest runs from the service root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Point the DB at a throwaway file BEFORE anything imports app.config,
# which reads DATABASE_URL once at class-definition time and builds the
# engine from it. Without this, the API tests write rows into whatever DB
# the developer's .env names — the real dev database, on a laptop.
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(prefix="bmv-consultant-tests-"), "test.db")

import pytest


@pytest.fixture(autouse=True)
def _signed_in(monkeypatch):
    """Every API test runs as a signed-in account unless it overrides this
    — the auth gate's own tests monkeypatch resolve_user back to None."""
    from app import auth_client

    monkeypatch.setattr(
        auth_client, "resolve_user",
        lambda authorization: {"email": "test@example.com", "name": "Test"},
    )

from app.ui_spec import ChartSpec, Kpi, Panel, UIDemoSpec


@pytest.fixture
def dental_spec() -> UIDemoSpec:
    return UIDemoSpec.model_validate(
        {
            "business": {
                "name": "SmileBright Dental",
                "industry": "Dental Clinic",
                "primary_color": "#0e9594",
            },
            "product": {
                "name": "SmileBright Operations",
                "purpose": "appointment management and clinic analytics",
                "screen_type": "dashboard",
            },
            "user": {"name": "Dr. Carter", "role": "Practice Owner"},
            "navigation": ["Dashboard", "Patients", "Schedule", "Billing", "Analytics", "Settings"],
            "greeting": "Good morning, Dr. Carter",
            "subheading": "Today at SmileBright",
            "kpis": [
                Kpi(label="Appointments Today", value="18", delta="+12% vs yesterday", trend="up"),
                Kpi(label="New Patients", value="7", delta="+16%", trend="up"),
                Kpi(label="No-show Rate", value="6.2%", delta="-1.1pp", trend="down"),
                Kpi(label="Recovered Revenue", value="$4,850", delta="+23%", trend="up"),
            ],
            "primary_panel": Panel(
                title="Today's Schedule",
                rows=[
                    {"time": "8:30 AM", "patient": "Sarah Mitchell", "treatment": "Dental Cleaning", "status": "Confirmed"},
                    {"time": "9:15 AM", "patient": "James Lopez", "treatment": "Crown Consultation", "status": "Confirmed"},
                ],
            ),
            "secondary_panel": Panel(
                title="Treatment Pipeline",
                rows=[{"patient": "Daniel Wilson", "treatment": "Implant Consultation", "value": "$3,200"}],
            ),
            "chart": ChartSpec(
                title="Appointments This Week",
                labels=["Mon", "Tue", "Wed", "Thu", "Fri"],
                values=[22, 28, 25, 30, 27],
                metric_label="appointments per day",
            ),
            "activity": [
                {"name": "Sarah Mitchell", "action": "Appointment confirmed", "time": "9:02 AM"},
                {"name": "James Lopez", "action": "Follow-up sent"},
            ],
            "style": {"archetype": "operations-dashboard", "density": "normal", "palette_description": "light interface, teal accents"},
        }
    )
