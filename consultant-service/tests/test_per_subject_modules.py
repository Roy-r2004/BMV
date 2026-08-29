"""One capability deployed per system is a plan, not a duplicate.

Production request 15 ("Masar & MultiAI") proposed a 'Masar Local Inference
Gateway' and a 'MultiAI Local Inference Gateway'. The overlap rule read them as
one capability split in two and refused the engagement three times, so the
client got nothing. An estate whose own name spans two systems legitimately
gets one instance of a shared capability per system.
"""
from app.pipeline.structural import engagement_subjects, module_overlap_findings

GATEWAYS = [
    {"id": "a", "name": "Masar Local Inference Gateway",
     "purpose": "Serve local models to the Masar chat surfaces with queueing and batching"},
    {"id": "b", "name": "MultiAI Local Inference Gateway",
     "purpose": "Serve local models to the MultiAI council with queueing and batching"},
]


def test_subjects_come_from_the_clients_own_name_for_the_estate():
    assert engagement_subjects("Masar & MultiAI") == {"masar", "multiai"}
    assert engagement_subjects("Alpha and Beta") == {"alpha", "beta"}
    assert engagement_subjects("Alpha, Beta, Gamma") == {"alpha", "beta", "gamma"}
    # one subject is not an estate
    assert engagement_subjects("iCARRY Lebanon") == set()
    # and the separator never splits inside a word
    assert engagement_subjects("Brand Standards") == set()
    assert engagement_subjects("Sandbox & Playground") == {"sandbox", "playground"}


def test_one_capability_per_subject_is_not_a_duplicate():
    subjects = engagement_subjects("Masar & MultiAI")
    assert module_overlap_findings(GATEWAYS, subjects) == []
    # without the subjects the rule still fires — the exemption is what the
    # client's own name buys, not a blanket weakening
    assert len(module_overlap_findings(GATEWAYS)) == 1


def test_a_genuine_duplicate_is_still_caught():
    """Two modules for one job, distinguished by nothing the engagement names."""
    subjects = engagement_subjects("Masar & MultiAI")
    dup = [
        {"id": "a", "name": "Customer Booking Assistant Flow",
         "purpose": "Take bookings and confirm them by message for walk-in guests"},
        {"id": "b", "name": "Client Booking Assistant Flow",
         "purpose": "Take bookings and confirm them by message for walk-in guests"},
    ]
    assert len(module_overlap_findings(dup, subjects)) == 1


def test_both_sides_must_name_a_subject():
    """A pair where only ONE side carries a subject is still a duplicate —
    otherwise any estate name would excuse a split capability."""
    subjects = engagement_subjects("Masar & MultiAI")
    half = [
        dict(GATEWAYS[0]),
        {"id": "b", "name": "Shared Local Inference Gateway",
         "purpose": "Serve local models to the Masar chat surfaces with queueing and batching"},
    ]
    assert len(module_overlap_findings(half, subjects)) == 1
