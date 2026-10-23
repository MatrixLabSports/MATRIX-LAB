from tools.telegram_green_signal_alerts import sharp_reference_gate_state


def test_pinnacle_single_fresh_reference_passes_primary_sharp_gate():
    state, detail = sharp_reference_gate_state({
        "sharp_consensus": {
            "status": "SINGLE_SHARP_REFERENCE_ONLY",
            "sharp_rows": [
                {"source": "pinnacle", "quote_age_seconds": 45}
            ],
        }
    })
    assert state == "PASS_SHARP_REFERENCE_GATE"
    assert detail["pinnacle_present"] is True
    assert detail["fanduel_counts_as_sharp"] is False
    assert detail["p_matrix_mutated_by_odds"] is False


def test_fanduel_context_never_satisfies_sharp_gate():
    state, detail = sharp_reference_gate_state({
        "sharp_consensus": {
            "status": "INSUFFICIENT_SHARP_COVERAGE",
            "sharp_rows": [],
            "market_context_rows": [
                {"source": "fanduel", "quote_age_seconds": 20}
            ],
        }
    })
    assert state == "BLOCKED_NO_FRESH_PINNACLE_REFERENCE"
    assert detail["pinnacle_present"] is False


def test_circa_without_pinnacle_does_not_replace_primary_sharp():
    state, detail = sharp_reference_gate_state({
        "sharp_consensus": {
            "status": "SINGLE_SHARP_REFERENCE_ONLY",
            "sharp_rows": [
                {"source": "circa", "quote_age_seconds": 30}
            ],
        }
    })
    assert state == "BLOCKED_NO_FRESH_PINNACLE_REFERENCE"
    assert detail["circa_present"] is True
    assert detail["pinnacle_present"] is False


def test_pinnacle_plus_circa_contradiction_blocks_signal():
    state, detail = sharp_reference_gate_state({
        "sharp_consensus": {
            "status": "CONTRADICTION_REVIEW",
            "sharp_rows": [
                {"source": "pinnacle", "quote_age_seconds": 25},
                {"source": "circa", "quote_age_seconds": 35},
            ],
        }
    })
    assert state == "BLOCKED_SHARP_CONTRADICTION"
    assert detail["pinnacle_present"] is True
    assert detail["circa_present"] is True


def test_pinnacle_plus_betfair_aligned_passes():
    state, detail = sharp_reference_gate_state({
        "sharp_consensus": {
            "status": "PASS_ALIGNED",
            "sharp_rows": [
                {"source": "pinnacle", "quote_age_seconds": 15},
                {"source": "betfair", "quote_age_seconds": 10},
            ],
        }
    })
    assert state == "PASS_SHARP_REFERENCE_GATE"
    assert detail["betfair_present"] is True
