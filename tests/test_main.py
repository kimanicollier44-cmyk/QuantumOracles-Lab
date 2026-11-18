"""Tests for QuantumOracles-Lab: simulator, DJ, BV, Grover, Simon, gates."""
import math

import pytest

import main as m


# ---- simulator
def test_bell_state():
    probs = m.probabilities(m.bell_state())
    assert abs(probs[0] - 0.5) < 1e-12 and abs(probs[3] - 0.5) < 1e-12
    assert abs(probs[1]) < 1e-12 and abs(probs[2]) < 1e-12


def test_norm_preserved():
    st = m.zero_state(3)
    m.apply_h(st, 0)
    m.apply_x(st, 1)
    m.apply_cnot(st, 0, 2)
    m.apply_z(st, 2)
    assert abs(m.state_norm(st) - 1.0) < 1e-12


def test_hadamard_twice_identity():
    st = m.zero_state(1)
    m.apply_x(st, 0)
    m.apply_h(st, 0)
    m.apply_h(st, 0)
    assert abs(m.probabilities(st)[1] - 1.0) < 1e-12


def test_cnot_truth_table():
    for control in (0, 1):
        for target in (0, 1):
            st = m.zero_state(2)
            if control:
                m.apply_x(st, 0)
            if target:
                m.apply_x(st, 1)
            m.apply_cnot(st, 0, 1)
            assert m.probabilities(st)[control + 2 * (target ^ control)] > 1 - 1e-12


def test_parity():
    assert m.parity(0b1011) == 1
    assert m.parity(0b1010) == 0
    assert m.parity(0) == 0


# ---- Deutsch-Jozsa
@pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 6])
def test_dj_one_query(n):
    for f in m.dj_functions(n).values():
        counter = m.QueryCounter()
        result = m.dj_quantum(n, f, counter)
        assert result["quantum_queries"] == 1


@pytest.mark.parametrize("n", [1, 3, 5])
def test_dj_verdicts(n):
    for name, f in m.dj_functions(n).items():
        counter = m.QueryCounter()
        result = m.dj_quantum(n, f, counter)
        want = "constant" if name.startswith("constant") else "balanced"
        assert result["kind"] == want
        assert result["p_all_zero"] == (1.0 if want == "constant" else 0.0)


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5])
def test_dj_classical_worst_case(n):
    for name in ("constant_0", "constant_1", "balanced_adversarial"):
        counter = m.QueryCounter()
        result = m.dj_classical(n, m.dj_functions(n)[name], counter)
        assert result["classical_queries"] == (1 << (n - 1)) + 1


def test_dj_classical_parity_fast():
    counter = m.QueryCounter()
    result = m.dj_classical(4, m.dj_functions(4)["balanced_parity"], counter)
    assert result["classical_queries"] == 2 and result["kind"] == "balanced"


def test_dj_report_agrees():
    assert all(row["agree"] for row in m.dj_report(4).values())


# ---- Bernstein-Vazirani
@pytest.mark.parametrize("n,s", [(1, 1), (3, 0b101), (4, 0b1011),
                                 (5, 0b10110), (6, 0b101101), (6, 0b111111)])
def test_bv_recovers_in_one_query(n, s):
    qc, cc = m.QueryCounter(), m.QueryCounter()
    q = m.bv_quantum(n, s, qc)
    c = m.bv_classical(n, s, cc)
    assert q["recovered_s"] == s and q["quantum_queries"] == 1
    assert q["p_recovered"] == 1.0
    assert c["recovered_s"] == s and c["classical_queries"] == n


def test_bv_report_match():
    assert m.bv_report(6, 0b101101)["match"]


# ---- Grover
def test_grover_matches_theory():
    for n_items in (8, 16, 32):
        run = m.grover_probabilities(n_items, 3, m.grover_optimal_k(n_items) + 2)
        for k, measured in run["table"].items():
            assert abs(measured - m.grover_theory(n_items, k)) < 2e-6


@pytest.mark.parametrize("n_items", [8, 16, 32, 64])
def test_grover_peak_at_formula_k(n_items):
    rep = m.grover_report(n_items, n_items // 2 + 1)
    assert rep["measured_peak_k"] == rep["optimal_k_formula"]
    assert rep["optimal_k_formula"] == round(math.pi / 4 * math.sqrt(n_items))


def test_grover_demo_headline():
    rep = m.grover_report(16, 9)
    assert rep["optimal_k_formula"] == 3
    assert abs(rep["peak_success_probability"] - 0.961319) < 1e-5
    assert rep["probability_table"][5] < rep["peak_success_probability"]


def test_grover_classical_expected():
    assert m.grover_classical_expected(16) == 8.5
    assert m.grover_classical_expected(8) == 4.5


def test_grover_queries_counted():
    assert m.grover_probabilities(16, 9, 5)["quantum_queries"] == 5


# ---- Simon + GF(2)
def test_simon_function_two_to_one():
    f = m.simon_f(0b1011)
    assert all(f(x) == f(x ^ 0b1011) for x in range(16))
    assert len({f(x) for x in range(16)}) == 8


def test_gf2_null_space():
    assert m.gf2_null_space([0b0011, 0b0100, 0b1001], 4) == [0b1011]
    assert m.gf2_rank([0b0011, 0b0100], 4) == 2


def test_simon_recovers_n4():
    rep = m.simon_report(4, 0b1011)
    assert rep["match"] and rep["recovered_s"] == 0b1011
    assert rep["quantum_queries"] == 5 and rep["classical_queries"] == 9
    assert all(m.parity(y & 0b1011) == 0 for y in rep["equations"])


def test_simon_recovers_n3():
    rep = m.simon_report(3, 0b101)
    assert rep["match"]
    assert rep["quantum_queries"] == 3 and rep["classical_queries"] == 5


# ---- ledger + classifier
def test_ledger_shape():
    ledger = m.query_ledger()
    assert [e["algorithm"] for e in ledger] == [
        "deutsch-jozsa", "bernstein-vazirani", "grover", "simon"]
    for entry in ledger:
        assert entry["quantum_queries"] > 0 and entry["classical_queries"] > 0
        assert abs(entry["ratio_classical_over_quantum"]
                   - round(entry["classical_queries"]
                           / entry["quantum_queries"], 4)) < 1e-9
        assert "oracle model" in entry["fine_print"]


def test_ledger_headline_counts():
    ledger = m.query_ledger()
    assert (ledger[0]["quantum_queries"], ledger[0]["classical_queries"]) == (1, 17)
    assert (ledger[1]["quantum_queries"], ledger[1]["classical_queries"]) == (1, 6)
    assert (ledger[2]["quantum_queries"], ledger[2]["classical_queries"]) == (3, 8.5)
    assert (ledger[3]["quantum_queries"], ledger[3]["classical_queries"]) == (5, 9)


def test_classifier_report():
    rep = m.classifier_report()
    assert rep["dj_n4_constant"]["family"] == "deutsch-jozsa"
    assert rep["bv_n5_hidden_string"]["family"] == "bernstein-vazirani"
    assert rep["grover_N16_marked9"]["family"] == "grover"
    assert rep["simon_n4_period1011"]["family"] == "simon"


def test_classifier_grid_self_consistent():
    assert all(m.classify_run(row) == row["family"] for row in m.TRAINING_GRID)


# ---- gates + seats
def test_hold_gates_count_and_style():
    assert len(m.HOLD_GATES) == 14
    assert all(v.startswith("HOLD") for v in m.HOLD_GATES.values())


@pytest.mark.parametrize("action", [
    "crypto_breaking_claim", "password_or_hash_cracking",
    "real_world_speedup_claim", "quantum_hardware_claim",
    "production_use_claim",
])
def test_gated_actions_hold(action):
    assert m.gate(action) == "HOLD"


def test_sandbox_proceeds():
    assert m.gate("run_simulation") == "PROCEED"


def test_argon4_seat():
    decider = m.brains_report()["decider"]
    assert decider["seat"] == "Gemini Argon 4 Extended Thinking"
    assert decider["model_id"] == "gemini-argon-4"
    assert decider["can_override_hold"] is False
    assert decider["live_calls"] == 0


def test_claude_and_flow_seats():
    brains = m.brains_report()
    assert brains["advisor"]["can_override_hold"] is False
    assert brains["flow"]["rendered"] is False
    assert brains["flow"]["live"] == 0


def test_hold_demo_exit_code(capsys):
    assert m.main(["hold-demo"]) == 2
    assert "crypto_breaking_claim" in capsys.readouterr().out


def test_checks_all_pass():
    checks = m.run_checks()
    assert all(ok for _, ok in checks)
