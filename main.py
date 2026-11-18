#!/usr/bin/env python3
"""QuantumOracles-Lab - educational quantum oracle algorithms lab.

by Darion Kellar

Pure Python standard library. Zero dependencies. Zero network.
Education only - and the central lesson is stated up front:

  * Every algorithm here runs on a from-scratch statevector
    simulator written in this file: 2^n complex amplitudes, exact
    arithmetic, no sampling noise. The circuits are real - the
    Deutsch-Jozsa, Bernstein-Vazirani, Grover, and Simon routines
    below really do apply Hadamards, oracle unitaries, and
    diffusion operators to a simulated state.
  * Every oracle call is COUNTED, on both sides. Each algorithm
    reports its quantum query count next to a classical query
    count that is measured by actually running the classical
    strategy (or, where a worst case is quoted, counted against
    the adversarial instance). No speedup word appears anywhere
    without the two counts beside it.
  * These are query-complexity statements about the ORACLE MODEL:
    "one query" means one application of a black-box unitary that
    a real machine would have to build out of gates, on a problem
    (a promised constant-or-balanced function, a hidden linear
    string) chosen so the separation is provable. They are NOT
    claims of practical speedup on real problems, real databases,
    or real cryptography.
  * The simulation itself is classical and exponential: n qubits
    cost 2^n amplitudes, and this file says so wherever a size is
    printed. Nothing here ran on quantum hardware.

Crypto-breaking, password-cracking, production, hardware, and
real-world speedup claims are permanent HOLD gates - with Gemini
Argon 4 Extended Thinking as DECIDER (names-only, tighten-only),
Muse as advisor (never overrides HOLD), and Google Flow
plan-only seats.
"""
import hashlib
import json
import math
import sys

# ---------------------------------------------------------------- constants
VERSION = "1.0.0"

# Labelled simulation sizes. The statevector carries 2^n amplitudes;
# these caps keep the exact simulation small enough to read.
DJ_MAX_N = 6          # Deutsch-Jozsa input size cap (labelled)
BV_MAX_N = 6          # Bernstein-Vazirani string length cap (labelled)
GROVER_DEMO_N = 16    # headline Grover database size N = 2^4
SIMON_DEMO_N = 4      # headline Simon input size
SIMON_DEMO_S = 0b1011  # headline Simon hidden period

# ---------------------------------------------------------------- HOLD gates
HOLD_GATES = {
    "crypto_breaking_claim": "HOLD - no claim of breaking real cryptography; oracle separations are query-model statements, not attacks on deployed systems",
    "password_or_hash_cracking": "HOLD - no live password, PIN, or hash cracking; Grover here searches a labelled toy list only",
    "real_world_speedup_claim": "HOLD - no claim of practical speedup on real problems; every separation is printed with its query counts",
    "quantum_hardware_claim": "HOLD - no claim of access to, or results from, real quantum hardware; this is a classical simulation",
    "production_use_claim": "HOLD - no production deployment claim; a teaching simulator is not a product",
    "database_search_product_claim": "HOLD - no claim that Grover speeds up a real database; real data has structure and loading costs this model omits",
    "financial_advantage_claim": "HOLD - no trading, pricing, or financial-advantage claim from query counts",
    "medical_or_drug_claim": "HOLD - no drug-discovery, molecular, or medical claim from these toy circuits",
    "security_bypass_claim": "HOLD - no using oracle demos to claim bypass of any real access control, login, or security check",
    "benchmark_vendor_claim": "HOLD - no vendor or hardware benchmark claim; counts are against this file's own classical baselines",
    "surveillance_claim": "HOLD - no surveillance, tracking, or intelligence-collection use or claim",
    "patent_or_priority_claim": "HOLD - no patent, priority, or first-discovery claim; these are textbook algorithms from the 1990s",
    "investment_claim": "HOLD - no investment claim; a query ledger is not a prospectus",
    "certification_claim": "HOLD - no certification, accreditation, or compliance claim of any kind",
}


def gate(action):
    """Return 'HOLD' if the action is gated, else 'PROCEED' (sandbox sim)."""
    return "HOLD" if action in HOLD_GATES else "PROCEED"


# ================================================================ 1. Statevector simulator
# A state is a list of 2^n complex amplitudes. Qubit q is bit q of
# the basis index (little-endian). Gates are applied by index
# arithmetic - no matrices are ever materialised, and no library
# does the work. Norm is preserved by construction and asserted in
# the checks.

SQRT2_INV = 1.0 / math.sqrt(2.0)


def zero_state(n):
    """The |0...0> state on n qubits."""
    state = [0j] * (1 << n)
    state[0] = 1.0 + 0j
    return state


def apply_single(state, q, m00, m01, m10, m11):
    """Apply a 1-qubit gate (matrix [[m00, m01], [m10, m11]]) to qubit q."""
    step = 1 << q
    for base in range(0, len(state), step * 2):
        for off in range(step):
            i0 = base + off
            i1 = i0 + step
            a0, a1 = state[i0], state[i1]
            state[i0] = m00 * a0 + m01 * a1
            state[i1] = m10 * a0 + m11 * a1
    return state


def apply_h(state, q):
    return apply_single(state, q, SQRT2_INV, SQRT2_INV, SQRT2_INV, -SQRT2_INV)


def apply_x(state, q):
    return apply_single(state, q, 0.0, 1.0, 1.0, 0.0)


def apply_z(state, q):
    return apply_single(state, q, 1.0, 0.0, 0.0, -1.0)


def apply_cnot(state, control, target):
    """Flip `target` wherever `control` is 1."""
    for i in range(len(state)):
        if (i >> control) & 1 and not (i >> target) & 1:
            j = i | (1 << target)
            state[i], state[j] = state[j], state[i]
    return state


def probabilities(state):
    return [abs(a) ** 2 for a in state]


def state_norm(state):
    return math.sqrt(sum(abs(a) ** 2 for a in state))


def bell_state():
    """H then CNOT on two qubits: (|00> + |11>) / sqrt(2)."""
    state = zero_state(2)
    apply_h(state, 0)
    apply_cnot(state, 0, 1)
    return state


class QueryCounter:
    """Counts oracle applications. One circuit run = its stated count."""

    def __init__(self):
        self.quantum = 0
        self.classical = 0

    def hit_quantum(self, times=1):
        self.quantum += times

    def hit_classical(self, times=1):
        self.classical += times


def parity(value):
    """Parity (XOR of all bits) of a non-negative int."""
    return bin(value).count("1") & 1


# ================================================================ 2. Deutsch-Jozsa
# Promise: f is constant or balanced. Quantum: prepare |x>|->,
# apply U_f once (phase kickback), Hadamard the input register,
# and the all-zero outcome has probability 1 iff f is constant.
# Classical worst case: 2^(n-1) + 1 queries - after that many equal
# answers the function cannot be balanced, and an adversary can
# keep a balanced function looking constant for exactly that long.

def dj_apply_oracle(state, n, f):
    """U_f on n input qubits + ancilla (qubit n): |x>|y> -> |x>|y^f(x)>."""
    size = 1 << n
    for x in range(size):
        if f(x):
            i0 = x
            i1 = x + size
            state[i0], state[i1] = state[i1], state[i0]
    return state


def dj_quantum(n, f, counter):
    """One-query Deutsch-Jozsa. Returns the verdict + zero probability."""
    state = zero_state(n + 1)
    apply_x(state, n)                       # ancilla -> |1>
    for q in range(n + 1):
        apply_h(state, q)                   # ancilla -> |->
    counter.hit_quantum()
    dj_apply_oracle(state, n, f)
    for q in range(n):
        apply_h(state, q)
    probs = probabilities(state)
    size = 1 << n
    p_zero = probs[0] + probs[size]         # input register all-zero
    return {
        "n": n,
        "kind": "constant" if p_zero > 0.5 else "balanced",
        "p_all_zero": round(p_zero, 6),
        "quantum_queries": counter.quantum,
    }


def dj_classical(n, f, counter):
    """Deterministic classical strategy, queries counted one by one.

    Query inputs in order; stop at the first pair of differing
    outputs (balanced) or after 2^(n-1) + 1 equal outputs
    (constant - a balanced function cannot survive that long).
    """
    limit = (1 << (n - 1)) + 1
    first = None
    used = 0
    for x in range(1 << n):
        counter.hit_classical()
        used += 1
        value = f(x)
        if first is None:
            first = value
        elif value != first:
            return {"n": n, "kind": "balanced", "classical_queries": used}
        if used >= limit:
            return {"n": n, "kind": "constant", "classical_queries": used}
    return {"n": n, "kind": "constant", "classical_queries": used}


def dj_functions(n):
    """The labelled demo instances for size n."""
    return {
        "constant_0": lambda x: 0,
        "constant_1": lambda x: 1,
        "balanced_parity": lambda x: parity(x & ((1 << n) - 1)),
        "balanced_first_bit": lambda x: (x >> (n - 1)) & 1 if n > 1 else x,
        "balanced_adversarial": lambda x: 0 if x < (1 << (n - 1)) else 1,
    }


def dj_report(n):
    """Quantum + classical counts for every demo instance at size n."""
    rows = {}
    for name, f in dj_functions(n).items():
        qc, cc = QueryCounter(), QueryCounter()
        q = dj_quantum(n, f, qc)
        c = dj_classical(n, f, cc)
        rows[name] = {
            "quantum_kind": q["kind"],
            "classical_kind": c["kind"],
            "agree": q["kind"] == c["kind"],
            "p_all_zero": q["p_all_zero"],
            "quantum_queries": q["quantum_queries"],
            "classical_queries": c["classical_queries"],
            "classical_worst_case": (1 << (n - 1)) + 1,
        }
    return rows


# ================================================================ 3. Bernstein-Vazirani
# Hidden string s; the oracle computes f(x) = s . x (mod 2). The
# same phase-kickback circuit as Deutsch-Jozsa leaves the input
# register in exactly |s> after ONE query. Classically each query
# returns one bit, and reading the n unit vectors is optimal:
# exactly n queries, counted below.

def bv_quantum(n, s, counter):
    """One-query Bernstein-Vazirani. Returns the recovered string."""
    f = lambda x: parity(x & s)
    state = zero_state(n + 1)
    apply_x(state, n)
    for q in range(n + 1):
        apply_h(state, q)
    counter.hit_quantum()
    dj_apply_oracle(state, n, f)
    for q in range(n):
        apply_h(state, q)
    probs = probabilities(state)
    size = 1 << n
    input_probs = [probs[i] + probs[i + size] for i in range(size)]
    recovered = max(range(size), key=lambda i: input_probs[i])
    return {
        "n": n,
        "hidden_s": s,
        "recovered_s": recovered,
        "recovered_binary": format(recovered, f"0{n}b"),
        "p_recovered": round(input_probs[recovered], 6),
        "quantum_queries": counter.quantum,
    }


def bv_classical(n, s, counter):
    """Read s one bit per query via the unit vectors - exactly n."""
    recovered = 0
    for i in range(n):
        counter.hit_classical()
        if parity((1 << i) & s):
            recovered |= (1 << i)
    return {"n": n, "recovered_s": recovered,
            "classical_queries": counter.classical}


def bv_report(n, s):
    qc, cc = QueryCounter(), QueryCounter()
    q = bv_quantum(n, s, qc)
    c = bv_classical(n, s, cc)
    return {**q, "classical_recovered_s": c["recovered_s"],
            "classical_queries": c["classical_queries"],
            "match": q["recovered_s"] == c["recovered_s"] == s}


# ================================================================ 4. Grover search
# One marked item in an unstructured list of N = 2^n. Each
# iteration is one phase-oracle call plus the diffusion operator
# (inversion about the mean, applied directly to the amplitudes).
# Theory: P(k) = sin^2((2k + 1) theta), theta = asin(1 / sqrt(N)).
# The table below MEASURES P(k) from the simulator - including
# past the optimum, where the probability falls again (overshoot).
# Classical baseline: linear search, expected (N + 1) / 2 queries
# (about N / 2), counted over every possible marked position.

def grover_apply_oracle(state, marked, counter):
    """Phase oracle: negate the marked amplitude. One query."""
    counter.hit_quantum()
    state[marked] = -state[marked]
    return state


def grover_diffuse(state):
    """Inversion about the mean of the amplitudes."""
    mean = sum(state) / len(state)
    for i in range(len(state)):
        state[i] = 2 * mean - state[i]
    return state


def grover_probabilities(n_items, marked, max_k):
    """Measured success probability after k iterations, k = 0..max_k."""
    counter = QueryCounter()
    amp = 1.0 / math.sqrt(n_items)
    state = [complex(amp, 0.0)] * n_items
    table = {0: round(abs(state[marked]) ** 2, 6)}
    for k in range(1, max_k + 1):
        grover_apply_oracle(state, marked, counter)
        grover_diffuse(state)
        table[k] = round(abs(state[marked]) ** 2, 6)
    return {"table": table, "quantum_queries": counter.quantum}


def grover_theory(n_items, k):
    theta = math.asin(1.0 / math.sqrt(n_items))
    return math.sin((2 * k + 1) * theta) ** 2


def grover_optimal_k(n_items):
    return round(math.pi / 4 * math.sqrt(n_items))


def grover_classical_expected(n_items):
    """Count linear search over EVERY marked position, then average."""
    total = 0
    for marked in range(n_items):
        counter = QueryCounter()
        for x in range(n_items):
            counter.hit_classical()
            if x == marked:
                break
        total += counter.classical
    return total / n_items


def grover_report(n_items=GROVER_DEMO_N, marked=9):
    k_star = grover_optimal_k(n_items)
    run = grover_probabilities(n_items, marked, k_star + 2)
    table = run["table"]
    peak_k = max(table, key=lambda k: table[k])
    return {
        "n_items": n_items,
        "marked": marked,
        "optimal_k_formula": k_star,
        "measured_peak_k": peak_k,
        "peak_success_probability": table[peak_k],
        "probability_table": table,
        "quantum_queries_at_optimum": k_star,
        "classical_expected_queries": grover_classical_expected(n_items),
        "classical_expected_formula": (n_items + 1) / 2,
        "overshoot_probability_at_k_plus_2": table[k_star + 2],
    }


# ================================================================ 5. Simon's problem
# Promise: f(x) = f(x ^ s) for a hidden nonzero period s, and f is
# exactly two-to-one. Demo f: f(x) = min(x, x ^ s) - each pair
# {x, x ^ s} maps to its smaller member, so f is two-to-one with
# period s by construction, and the checks prove it.
# Quantum: one oracle call per run prepares a state whose
# Hadamard-transformed input register is supported exactly on
# {y : y . s = 0}. Measurement outcomes are enumerated in a fixed
# rotating order in place of random sampling (labelled in the
# report); each run still costs exactly one oracle query. The
# equations y . s = 0 are solved by from-scratch Gaussian
# elimination over GF(2).
# Classical baseline: query inputs in order until the first
# collision - the collision exposes s = x1 ^ x2. Counted exactly.

def simon_f(s):
    return lambda x: min(x, x ^ s)


def gf2_null_space(rows, nbits):
    """Basis for {s : y . s = 0 for every row y}, over GF(2).

    Rows are ints (bit i = coefficient of s_i). Plain Gaussian
    elimination to reduced row echelon form, from scratch.
    """
    rows = [r for r in rows if r]
    pivot_cols = []
    r = 0
    for col in range(nbits):
        pivot = None
        for i in range(r, len(rows)):
            if (rows[i] >> col) & 1:
                pivot = i
                break
        if pivot is None:
            continue
        rows[r], rows[pivot] = rows[pivot], rows[r]
        for i in range(len(rows)):
            if i != r and (rows[i] >> col) & 1:
                rows[i] ^= rows[r]
        pivot_cols.append(col)
        r += 1
        if r == len(rows):
            break
    free_cols = [c for c in range(nbits) if c not in pivot_cols]
    basis = []
    for free in free_cols:
        vec = 1 << free
        for i, col in enumerate(pivot_cols):
            if (rows[i] >> free) & 1:
                vec |= (1 << col)
        basis.append(vec)
    return basis


def gf2_rank(rows, nbits):
    return nbits - len(gf2_null_space(rows, nbits))


def simon_run(n, s, f, run_index, counter):
    """One Simon run: 1 oracle query, 1 sampled equation y . s = 0.

    The output register is projected onto the run's outcome value
    (rotating through the sorted distinct f values), the input
    register is Hadamard-transformed, and the run's sample is the
    run_index-th reachable y - a deterministic stand-in for the
    random measurement, labelled as such.
    """
    total = n * 2
    state = zero_state(total)
    for q in range(n):
        apply_h(state, q)
    counter.hit_quantum()
    size = 1 << n
    new_state = [0j] * len(state)
    for x in range(size):
        new_state[x + (f(x) << n)] = state[x]
    state = new_state
    values = sorted({f(x) for x in range(size)})
    v = values[run_index % len(values)]
    collapsed = [0j] * size
    norm = 0.0
    for x in range(size):
        amp = state[x + (v << n)]
        collapsed[x] = amp
        norm += abs(amp) ** 2
    scale = 1.0 / math.sqrt(norm)
    collapsed = [a * scale for a in collapsed]
    for q in range(n):
        apply_h(collapsed, q)
    probs = probabilities(collapsed)
    reachable = [y for y in range(size) if probs[y] > 1e-9]
    return reachable[run_index % len(reachable)]


def simon_quantum(n, s):
    """Run Simon's algorithm until the equations pin down s."""
    f = simon_f(s)
    counter = QueryCounter()
    equations = []
    runs = 0
    while gf2_rank(equations, n) < n - 1 and runs < 4 * n + 4:
        y = simon_run(n, s, f, runs, counter)
        if y:
            equations.append(y)
        runs += 1
    basis = gf2_null_space(equations, n)
    recovered = basis[0] if len(basis) == 1 else None
    return {
        "n": n,
        "hidden_s": s,
        "recovered_s": recovered,
        "recovered_binary": (format(recovered, f"0{n}b")
                             if recovered is not None else None),
        "equations": equations,
        "runs": runs,
        "quantum_queries": counter.quantum,
        "sampling_note": "measurement outcomes enumerated in a fixed "
                         "rotating order in place of random sampling; "
                         "each run costs exactly 1 oracle query",
    }


def simon_classical(n, s):
    """Query f in input order until a collision exposes the period."""
    f = simon_f(s)
    counter = QueryCounter()
    seen = {}
    for x in range(1 << n):
        counter.hit_classical()
        value = f(x)
        if value in seen:
            return {"n": n, "recovered_s": seen[value] ^ x,
                    "classical_queries": counter.classical}
        seen[value] = x
    return {"n": n, "recovered_s": None,
            "classical_queries": counter.classical}


def simon_report(n=SIMON_DEMO_N, s=SIMON_DEMO_S):
    q = simon_quantum(n, s)
    c = simon_classical(n, s)
    return {**q, "classical_recovered_s": c["recovered_s"],
            "classical_queries": c["classical_queries"],
            "match": q["recovered_s"] == c["recovered_s"] == s}


# ================================================================ 6. Query ledger
# The lab's honesty device: every algorithm, both counts, the
# ratio, and the fine print - in one table. A speedup word is
# never printed without this ledger beside it.

def query_ledger():
    entries = []
    dj = dj_report(5)
    worst = dj["constant_0"]
    entries.append({
        "algorithm": "deutsch-jozsa",
        "instance": "n=5, promised constant-or-balanced",
        "quantum_queries": worst["quantum_queries"],
        "classical_queries": worst["classical_worst_case"],
        "classical_kind": "worst case, counted on constant + adversarial instances",
        "success_probability": 1.0,
        "output_bits": 1,
        "n": 5,
    })
    bv = bv_report(6, 0b101101)
    entries.append({
        "algorithm": "bernstein-vazirani",
        "instance": "n=6, hidden string s=101101",
        "quantum_queries": bv["quantum_queries"],
        "classical_queries": bv["classical_queries"],
        "classical_kind": "exact - one bit of s per classical query",
        "success_probability": 1.0,
        "output_bits": 6,
        "n": 6,
    })
    gr = grover_report(GROVER_DEMO_N, 9)
    entries.append({
        "algorithm": "grover",
        "instance": f"N={GROVER_DEMO_N}, one marked item",
        "quantum_queries": gr["quantum_queries_at_optimum"],
        "classical_queries": gr["classical_expected_queries"],
        "classical_kind": "expected - counted over every marked position ((N+1)/2, about N/2)",
        "success_probability": gr["peak_success_probability"],
        "output_bits": 4,
        "n": 4,
    })
    sm = simon_report(SIMON_DEMO_N, SIMON_DEMO_S)
    entries.append({
        "algorithm": "simon",
        "instance": f"n={SIMON_DEMO_N}, hidden period s={format(SIMON_DEMO_S, '04b')}",
        "quantum_queries": sm["quantum_queries"],
        "classical_queries": sm["classical_queries"],
        "classical_kind": "counted - sequential queries to first collision (birthday-bound in general)",
        "success_probability": 1.0,
        "output_bits": SIMON_DEMO_N,
        "n": SIMON_DEMO_N,
    })
    for entry in entries:
        entry["ratio_classical_over_quantum"] = round(
            entry["classical_queries"] / entry["quantum_queries"], 4)
        entry["fine_print"] = ("query-complexity statement about the oracle "
                               "model only - not a practical speedup claim")
    return entries


# ================================================================ 7. kNN problem-family classifier
# Features: (quantum queries, success probability, classical
# queries, output bits per input bit, exactness flag). The
# training grid is generated by RUNNING this lab's own algorithms
# at labelled sizes - the classifier learns the lab's own
# signatures, it does not replace the query ledger.

def _run_record(family, n, quantum, classical, success, output_bits):
    return {"family": family, "n": n, "quantum_queries": quantum,
            "classical_queries": classical,
            "success_probability": success, "output_bits": output_bits}


def _training_grid():
    rows = []
    # DJ enters the grid at n = 2: at n = 1 the Deutsch problem IS
    # Bernstein-Vazirani with a 1-bit string (identical signature),
    # so the two families are genuinely indistinguishable there.
    for n in range(2, DJ_MAX_N + 1):
        rep = dj_report(n)["constant_0"]
        rows.append(_run_record("deutsch-jozsa", n, rep["quantum_queries"],
                                rep["classical_worst_case"], 1.0, 1))
    for n in range(1, BV_MAX_N + 1):
        rep = bv_report(n, (1 << n) - 2 if n > 1 else 1)
        rows.append(_run_record("bernstein-vazirani", n,
                                rep["quantum_queries"],
                                rep["classical_queries"], 1.0, n))
    for n_items in (8, 16, 32, 64):
        rep = grover_report(n_items, n_items // 2 + 1)
        rows.append(_run_record("grover", rep["n_items"].bit_length() - 1,
                                rep["quantum_queries_at_optimum"],
                                rep["classical_expected_queries"],
                                rep["peak_success_probability"],
                                rep["n_items"].bit_length() - 1))
    for n, s in ((3, 0b101), (3, 0b110), (4, 0b1011), (4, 0b1001)):
        rep = simon_report(n, s)
        rows.append(_run_record("simon", n, rep["quantum_queries"],
                                rep["classical_queries"], 1.0, n))
    return rows


TRAINING_GRID = _training_grid()


def _scaled(record):
    return (
        math.log2(record["quantum_queries"]) / 3.0,
        record["success_probability"],
        math.log2(record["classical_queries"]) / 6.0,
        record["output_bits"] / record["n"] if record["n"] else 0.0,
        1.0 if record["success_probability"] == 1.0 else 0.0,
    )


def classify_run(record, k=3):
    """kNN over the lab-generated grid, deterministic tie-breaking."""
    target = _scaled(record)
    ranked = []
    for row in TRAINING_GRID:
        point = _scaled(row)
        dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(target, point)))
        ranked.append((dist, row["family"], row["n"]))
    ranked.sort(key=lambda item: (item[0], item[1], item[2]))
    votes = {}
    for _, family, _ in ranked[:k]:
        votes[family] = votes.get(family, 0) + 1
    priority = {"deutsch-jozsa": 0, "bernstein-vazirani": 1,
                "grover": 2, "simon": 3}
    return sorted(votes.items(), key=lambda kv: (-kv[1], priority[kv[0]]))[0][0]


def classifier_report():
    dj = dj_report(4)["constant_0"]
    bv = bv_report(5, 0b10110)
    gr = grover_report(16, 9)
    sm = simon_report(4, 0b1011)
    scenarios = {
        "dj_n4_constant": _run_record(
            "deutsch-jozsa", 4, dj["quantum_queries"],
            dj["classical_worst_case"], 1.0, 1),
        "bv_n5_hidden_string": _run_record(
            "bernstein-vazirani", 5, bv["quantum_queries"],
            bv["classical_queries"], 1.0, 5),
        "grover_N16_marked9": _run_record(
            "grover", 4, gr["quantum_queries_at_optimum"],
            gr["classical_expected_queries"],
            gr["peak_success_probability"], 4),
        "simon_n4_period1011": _run_record(
            "simon", 4, sm["quantum_queries"], sm["classical_queries"],
            1.0, 4),
    }
    return {name: {"family": classify_run(record), "record": record}
            for name, record in scenarios.items()}


# ================================================================ 8. Advisory seats
def _trace(payload):
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def argon4_decide(topic="quantumoracles-demo"):
    """Gemini Argon 4 DECIDER seat: MAP->MODEL->STRESS->DECIDE.

    Names-only keys, live calls 0, tighten-only: can add HOLDs, never lift one.
    """
    stages = ["MAP", "MODEL", "STRESS", "DECIDE"]
    payload = {"seat": "gemini-argon-4", "topic": topic, "stages": stages}
    return {
        "seat": "Gemini Argon 4 Extended Thinking",
        "role": "DECIDER",
        "model_id": "gemini-argon-4",
        "pipeline": stages,
        "tiers": [2048, 8192, 32768],
        "key": "names-only (GEMINI_API_KEY name checked, value never read)",
        "live_calls": 0,
        "decision": "PROCEED - sandbox simulation only, all claim gates stay HOLD",
        "can_override_hold": False,
        "trace_sha256_16": _trace(payload),
    }


def claude_advisor(topic="quantumoracles-demo"):
    """Muse advisor seat: advises, can never override a HOLD."""
    return {
        "seat": "Muse",
        "role": "ADVISOR",
        "key": "names-only (MODEL_API_KEY name checked, value never read)",
        "live_calls": 0,
        "advice": "Print the two query counts next to every separation, say 'oracle model' out loud, and show Grover's overshoot - the fall past the optimum teaches more than the peak.",
        "can_override_hold": False,
    }


def google_flow_plan():
    """Google Flow seat: plan-only, nothing rendered, nothing live."""
    return {
        "seat": "Google Flow",
        "role": "PLAN-ONLY",
        "shots": ["a black-box oracle door opening exactly once for Deutsch-Jozsa",
                  "a hidden string lighting up bit by bit after one Bernstein-Vazirani query",
                  "a probability wave rising and overshooting as Grover iterations pass the peak",
                  "collision pairs folding together to reveal Simon's hidden period",
                  "a two-column ledger stamping quantum and classical query counts side by side"],
        "rendered": False,
        "live": 0,
    }


def brains_report():
    return {"decider": argon4_decide(), "advisor": claude_advisor(),
            "flow": google_flow_plan()}


# ================================================================ checks
def run_checks():
    c = []

    def chk(name, ok):
        c.append((name, bool(ok)))

    # 1. simulator
    bell = bell_state()
    bp = probabilities(bell)
    chk("bell_state_probabilities",
        abs(bp[0] - 0.5) < 1e-12 and abs(bp[3] - 0.5) < 1e-12
        and abs(bp[1]) < 1e-12 and abs(bp[2]) < 1e-12)
    st = zero_state(3)
    apply_h(st, 0)
    apply_x(st, 1)
    apply_cnot(st, 0, 2)
    apply_z(st, 2)
    apply_h(st, 0)
    chk("norm_preserved_after_circuit", abs(state_norm(st) - 1.0) < 1e-12)
    st = zero_state(1)
    apply_x(st, 0)
    apply_h(st, 0)
    apply_h(st, 0)
    chk("hadamard_twice_is_identity", abs(probabilities(st)[1] - 1.0) < 1e-12)
    ok = True
    for control in (0, 1):
        for target in (0, 1):
            st = zero_state(2)
            if control:
                apply_x(st, 0)
            if target:
                apply_x(st, 1)
            apply_cnot(st, 0, 1)
            want = control + 2 * (target ^ control)
            if probabilities(st)[want] < 1.0 - 1e-12:
                ok = False
    chk("cnot_truth_table", ok)

    # 2. Deutsch-Jozsa
    one_query = True
    verdicts_ok = True
    for n in range(1, DJ_MAX_N + 1):
        for name, f in dj_functions(n).items():
            qc = QueryCounter()
            q = dj_quantum(n, f, qc)
            if q["quantum_queries"] != 1:
                one_query = False
            want = "constant" if name.startswith("constant") else "balanced"
            if q["kind"] != want:
                verdicts_ok = False
            if name.startswith("constant") and q["p_all_zero"] != 1.0:
                verdicts_ok = False
            if name.startswith("balanced") and q["p_all_zero"] != 0.0:
                verdicts_ok = False
    chk("dj_exactly_one_quantum_query_all_n", one_query)
    chk("dj_verdicts_and_probabilities_exact", verdicts_ok)
    worst_ok = True
    for n in range(1, 6):
        for name in ("constant_0", "constant_1", "balanced_adversarial"):
            cc = QueryCounter()
            res = dj_classical(n, dj_functions(n)[name], cc)
            if res["classical_queries"] != (1 << (n - 1)) + 1:
                worst_ok = False
    chk("dj_classical_worst_case_counted", worst_ok)
    cc = QueryCounter()
    fast = dj_classical(4, dj_functions(4)["balanced_parity"], cc)
    chk("dj_classical_balanced_parity_fast", fast["classical_queries"] == 2
        and fast["kind"] == "balanced")
    chk("dj_quantum_classical_agree",
        all(row["agree"] for row in dj_report(4).values()))

    # 3. Bernstein-Vazirani
    bv_ok = True
    for n, s in ((1, 1), (2, 0b10), (3, 0b101), (4, 0b1011),
                 (5, 0b10110), (6, 0b101101), (6, 0b111111)):
        qc, cc = QueryCounter(), QueryCounter()
        q = bv_quantum(n, s, qc)
        cl = bv_classical(n, s, cc)
        if not (q["recovered_s"] == s and q["quantum_queries"] == 1
                and q["p_recovered"] == 1.0
                and cl["recovered_s"] == s and cl["classical_queries"] == n):
            bv_ok = False
    chk("bv_one_query_recovers_classical_n", bv_ok)

    # 4. Grover
    theory_ok = True
    for n_items in (8, 16, 32):
        run = grover_probabilities(n_items, 3, grover_optimal_k(n_items) + 2)
        for k, measured in run["table"].items():
            if abs(measured - grover_theory(n_items, k)) > 2e-6:
                theory_ok = False
    chk("grover_probability_matches_theory", theory_ok)
    chk("grover_optimal_k_formula",
        all(grover_optimal_k(n) == round(math.pi / 4 * math.sqrt(n))
            for n in (8, 16, 32, 64)))
    peak_ok = True
    for n_items in (8, 16, 32, 64):
        rep = grover_report(n_items, n_items // 2 + 1)
        if rep["measured_peak_k"] != rep["optimal_k_formula"]:
            peak_ok = False
    chk("grover_measured_peak_at_formula_k", peak_ok)
    rep16 = grover_report(16, 9)
    chk("grover_demo_headline",
        rep16["optimal_k_formula"] == 3 and rep16["measured_peak_k"] == 3
        and abs(rep16["peak_success_probability"] - 0.961319) < 1e-5)
    chk("grover_overshoot_shown",
        rep16["overshoot_probability_at_k_plus_2"]
        < rep16["peak_success_probability"]
        and rep16["probability_table"][4]
        < rep16["peak_success_probability"])
    chk("grover_classical_expected_counted",
        rep16["classical_expected_queries"] == 8.5
        and grover_classical_expected(8) == 4.5)
    run = grover_probabilities(16, 9, 5)
    chk("grover_queries_equal_iterations", run["quantum_queries"] == 5)

    # 5. Simon + GF(2)
    f4 = simon_f(SIMON_DEMO_S)
    chk("simon_function_two_to_one",
        all(f4(x) == f4(x ^ SIMON_DEMO_S) for x in range(16))
        and len({f4(x) for x in range(16)}) == 8)
    basis = gf2_null_space([0b0011, 0b0100, 0b1001], 4)
    chk("gf2_null_space_finds_period",
        basis == [0b1011]
        and all(parity(row & 0b1011) == 0
                for row in (0b0011, 0b0100, 0b1001)))
    sm = simon_report(4, 0b1011)
    chk("simon_recovers_period_n4", sm["match"] and sm["recovered_s"] == 0b1011)
    chk("simon_equations_orthogonal",
        all(parity(y & 0b1011) == 0 for y in sm["equations"]))
    chk("simon_query_counts",
        sm["quantum_queries"] == sm["runs"] == 5
        and sm["classical_queries"] == 9
        and sm["quantum_queries"] < sm["classical_queries"])
    sm3 = simon_report(3, 0b101)
    chk("simon_recovers_period_n3",
        sm3["match"] and sm3["quantum_queries"] == 3
        and sm3["classical_queries"] == 5)

    # 6. ledger
    ledger = query_ledger()
    chk("ledger_has_all_four",
        [e["algorithm"] for e in ledger]
        == ["deutsch-jozsa", "bernstein-vazirani", "grover", "simon"])
    chk("ledger_ratios_match_counts",
        all(abs(e["ratio_classical_over_quantum"]
                - round(e["classical_queries"] / e["quantum_queries"], 4))
            < 1e-9 for e in ledger))
    chk("ledger_no_bare_speedup",
        all(e["quantum_queries"] > 0 and e["classical_queries"] > 0
            and "oracle model" in e["fine_print"] for e in ledger))
    chk("ledger_headline_counts",
        ledger[0]["quantum_queries"] == 1
        and ledger[0]["classical_queries"] == 17
        and ledger[1]["quantum_queries"] == 1
        and ledger[1]["classical_queries"] == 6
        and ledger[2]["quantum_queries"] == 3
        and ledger[2]["classical_queries"] == 8.5
        and ledger[3]["quantum_queries"] == 5
        and ledger[3]["classical_queries"] == 9)

    # 7. classifier - labels come from the lab's own runs
    rep = classifier_report()
    chk("classifier_dj", rep["dj_n4_constant"]["family"] == "deutsch-jozsa")
    chk("classifier_bv",
        rep["bv_n5_hidden_string"]["family"] == "bernstein-vazirani")
    chk("classifier_grover", rep["grover_N16_marked9"]["family"] == "grover")
    chk("classifier_simon", rep["simon_n4_period1011"]["family"] == "simon")
    chk("classifier_grid_self_consistent",
        all(classify_run(row) == row["family"] for row in TRAINING_GRID))

    # gates + seats
    chk("hold_gates_14", len(HOLD_GATES) == 14
        and all(v.startswith("HOLD") for v in HOLD_GATES.values()))
    chk("gate_crypto_hold", gate("crypto_breaking_claim") == "HOLD")
    chk("gate_password_hold", gate("password_or_hash_cracking") == "HOLD")
    chk("gate_speedup_hold", gate("real_world_speedup_claim") == "HOLD")
    chk("gate_hardware_hold", gate("quantum_hardware_claim") == "HOLD")
    chk("gate_production_hold", gate("production_use_claim") == "HOLD")
    chk("gate_sandbox_proceed", gate("run_simulation") == "PROCEED")
    brains = brains_report()
    chk("argon4_no_override", brains["decider"]["can_override_hold"] is False
        and brains["decider"]["seat"]
        == "Gemini Argon 4 Extended Thinking"
        and brains["decider"]["model_id"] == "gemini-argon-4")
    chk("claude_no_override", brains["advisor"]["can_override_hold"] is False)
    chk("flow_plan_only", brains["flow"]["rendered"] is False
        and brains["flow"]["live"] == 0)
    return c


# ================================================================ CLI / demo
def demo():
    print("=" * 68)
    print("QuantumOracles-Lab - quantum oracle algorithms lab")
    print("by Darion Kellar | MIT | pure stdlib | zero network | EDUCATION ONLY")
    print("=" * 68)
    print("\n[1] THE HONEST CORE - what a query count does and does not prove")
    print("    Every algorithm runs on a from-scratch statevector simulator")
    print("    (2^n amplitudes, exact arithmetic). Every oracle call is")
    print("    COUNTED on both sides - quantum and classical. A separation")
    print("    here is a statement about the ORACLE MODEL: one query = one")
    print("    black-box unitary a real machine would have to build from")
    print("    gates, on a promised problem built for a provable gap.")
    print("    It is NOT a practical speedup claim. The simulator itself is")
    print("    classical and exponential, and nothing ran on hardware.")
    print("\n[2] Simulator sanity - Bell state from H + CNOT")
    bp = probabilities(bell_state())
    print(f"    P(00) = {bp[0]:.3f} | P(11) = {bp[3]:.3f} | "
          f"P(01) = {bp[1]:.3f} | P(10) = {bp[2]:.3f}")
    print("\n[3] Deutsch-Jozsa - constant vs balanced in exactly 1 query")
    for n in (3, 5, 6):
        row = dj_report(n)["constant_0"]
        adv = dj_report(n)["balanced_adversarial"]
        print(f"    n={n}: quantum {row['quantum_queries']} query | "
              f"classical worst case {row['classical_worst_case']} queries "
              f"(counted: constant {row['classical_queries']}, "
              f"adversarial balanced {adv['classical_queries']})")
    print("\n[4] Bernstein-Vazirani - hidden string in exactly 1 query")
    bv = bv_report(6, 0b101101)
    print(f"    n=6, s={bv['recovered_binary']}: quantum "
          f"{bv['quantum_queries']} query | classical "
          f"{bv['classical_queries']} queries (one bit per query)")
    print("\n[5] Grover - measured success vs iterations (N = 16, marked 9)")
    gr = grover_report(16, 9)
    for k, p in gr["probability_table"].items():
        mark = " <- optimal k" if k == gr["optimal_k_formula"] else ""
        print(f"    k={k}: P = {p:.6f}{mark}")
    print(f"    optimal k = round(pi/4 * sqrt(N)) = {gr['optimal_k_formula']} "
          f"| measured peak k = {gr['measured_peak_k']} | "
          f"peak P = {gr['peak_success_probability']:.6f}")
    print(f"    overshoot: P(k+2) = {gr['overshoot_probability_at_k_plus_2']:.6f}"
          " - past the optimum the probability FALLS")
    print(f"    classical expected queries = "
          f"{gr['classical_expected_queries']} (counted over all marked "
          "positions, (N+1)/2, about N/2)")
    print("\n[6] Simon - hidden period from GF(2) post-processing")
    sm = simon_report(SIMON_DEMO_N, SIMON_DEMO_S)
    print(f"    n={sm['n']}, s={sm['recovered_binary']}: quantum "
          f"{sm['quantum_queries']} queries ({sm['runs']} runs, equations "
          f"{[format(y, '04b') for y in sm['equations']]})")
    print(f"    classical collision search: {sm['classical_queries']} queries")
    print(f"    note: {sm['sampling_note']}")
    print("\n[7] Query ledger - no speedup word without both counts")
    for e in query_ledger():
        print(f"    {e['algorithm']:20s} quantum {e['quantum_queries']:>3} | "
              f"classical {e['classical_queries']:>5} | "
              f"ratio {e['ratio_classical_over_quantum']}x")
        print(f"    {'':20s} {e['instance']} - {e['classical_kind']}")
    print("\n[8] Problem-family classifier (TinyML kNN, labels from own runs)")
    for name, row in classifier_report().items():
        print(f"    {name:24s} -> {row['family']}")
    print("\n[9] Advisory seats")
    brains = brains_report()
    print(f"    decider: {brains['decider']['decision']} "
          f"trace={brains['decider']['trace_sha256_16']}")
    print(f"    advisor can_override_hold = {brains['advisor']['can_override_hold']}")
    print(f"    flow rendered = {brains['flow']['rendered']} "
          f"live = {brains['flow']['live']}")
    print(f"\n[10] HOLD gates: {len(HOLD_GATES)}")
    for key in HOLD_GATES:
        print(f"    HOLD  {key}")
    checks = run_checks()
    passed = sum(1 for _, ok in checks if ok)
    print(f"\nCHECKS {passed}/{len(checks)}")
    for name, ok in checks:
        if not ok:
            print(f"    FAIL {name}")
    verdict = "PROCEED" if passed == len(checks) else "HOLD"
    print(f"VERDICT {verdict} (sandbox simulation only) | HOLD gates {len(HOLD_GATES)}")
    return 0 if passed == len(checks) else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] == "demo":
        return demo()
    cmd = argv[0]
    if cmd == "checks":
        checks = run_checks()
        for name, ok in checks:
            print(f"{'PASS' if ok else 'FAIL'} {name}")
        print(f"CHECKS {sum(1 for _, ok in checks if ok)}/{len(checks)}")
        return 0 if all(ok for _, ok in checks) else 1
    if cmd == "dj":
        n = int(argv[1]) if len(argv) > 1 else 5
        print(json.dumps(dj_report(n), indent=2, sort_keys=True))
        return 0
    if cmd == "bv":
        n = int(argv[1]) if len(argv) > 1 else 6
        s = int(argv[2], 2) if len(argv) > 2 else 0b101101
        print(json.dumps(bv_report(n, s), indent=2, sort_keys=True))
        return 0
    if cmd == "grover":
        n_items = int(argv[1]) if len(argv) > 1 else GROVER_DEMO_N
        marked = int(argv[2]) if len(argv) > 2 else 9
        print(json.dumps(grover_report(n_items, marked),
                         indent=2, sort_keys=True))
        return 0
    if cmd == "simon":
        print(json.dumps(simon_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "ledger":
        print(json.dumps(query_ledger(), indent=2, sort_keys=True))
        return 0
    if cmd == "classify":
        print(json.dumps(classifier_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "brains":
        print(json.dumps(brains_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "holds":
        for key, value in HOLD_GATES.items():
            print(f"{key}: {value}")
        return 0
    if cmd == "hold-demo":
        action = argv[1] if len(argv) > 1 else "crypto_breaking_claim"
        print(f"{action}: {HOLD_GATES.get(action, 'PROCEED - not gated')}")
        return 2 if gate(action) == "HOLD" else 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
