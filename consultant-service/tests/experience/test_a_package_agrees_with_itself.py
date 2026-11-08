"""The faults real runs were stamped DRAFT for, fixed where they start."""
from app.pipeline import canon, integrity, pilot_gate, registry


GATE = {"id": "PG-01", "primary_metric": "Cleaner retention rate", "target_value": 15, "target_unit": "percentage_point",
        "duration_value": 6, "duration_unit": "week", "direction": "rise"}
MODULES = [{"id": "cleaner-matching-engine", "client_facing_name": "Cleaner Matching Engine", "phase_number": 2, "workstream": "delivery"},
           {"id": "cleaner-earnings-dashboard", "client_facing_name": "Cleaner Earnings Dashboard", "phase_number": 3, "workstream": "delivery"},
           {"id": "customer-booking-portal", "client_facing_name": "Customer Booking Portal", "phase_number": None, "workstream": "parallel"}]


def test_the_gate_sentence_is_still_the_gate_sentence_when_a_role_is_capitalised():
    sentence = pilot_gate.canonical_sentence(GATE)
    assert "cleaner" in sentence and pilot_gate.restatement_findings(sentence.replace("cleaner", "Cleaner"), GATE) == []


def test_a_gate_restated_with_another_number_is_still_a_paraphrase():
    assert pilot_gate.restatement_findings("Success means the cleaner retention rate has a target of a 20% rise.", GATE)


def test_a_module_id_reads_as_its_name():
    assert registry.name_the_ids("Open the cleaner-matching-engine today.", MODULES) == "Open the Cleaner Matching Engine today."


def test_an_id_on_a_build_team_line_stays_for_the_engineers():
    line = "For your build team: deploy cleaner-matching-engine behind the gateway."
    assert registry.name_the_ids(line, MODULES) == line


def test_a_longer_word_containing_an_id_is_left_alone():
    text = "the old-cleaner-matching-engine-v2 path"
    assert registry.name_the_ids(text, MODULES) == text


def test_the_settled_sequence_is_what_the_writers_are_told():
    assert registry.phase_lines(MODULES).split("\n") == [
        "Phase 2: Cleaner Matching Engine", "Phase 3: Cleaner Earnings Dashboard",
        "In parallel, outside the numbered phases: Customer Booking Portal"]


def test_a_person_and_the_system_named_after_them_are_a_sentence_not_a_broken_name():
    assert canon.repeated_run("Cleaner accesses the Cleaner Earnings Dashboard", {"Cleaner"}) is None


def test_a_name_built_twice_is_still_caught():
    assert canon.repeated_run("Client Client Portal", {"Client"})
    assert canon.repeated_run("Client Portal Client Portal", {"Client"})


class _Module:
    def __init__(self, name, phase):
        self.canonical, self.data = name, {"phase": phase}


class _Canon:
    def of_kind(self, kind):
        return [_Module("Cleaner Matching Engine", "FUTURE")] if kind == "module" else []

    def channel_mapping(self, name):
        return None


def test_a_checklist_that_needs_an_unbuilt_part_says_so():
    checks = {"checklists": [{"name": "Open", "items": ["Check the Cleaner Matching Engine"]}, {"name": "Close", "items": ["Lock up"]}]}
    integrity.retype({"procedures": {"procedures": []}, "checklists": checks, "modules": []}, _Canon())
    assert checks["checklists"][0]["phase"] == "future" and "phase" not in checks["checklists"][1]
