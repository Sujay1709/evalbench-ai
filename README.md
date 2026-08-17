# EvalBench

**A reproducible LLM evaluation and regression platform for testing answer quality before model changes reach production.**

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.x-000000?logo=flask&logoColor=white)
![Phase](https://img.shields.io/badge/status-Phase%201%20verified-2E8B57)
![Operation](https://img.shields.io/badge/tests-offline%20%26%20deterministic-F59E0B)

EvalBench turns datasets, prompt versions, provider settings, and scoring rules into traceable evaluation runs. It stores per-example evidence, reuses identical responses through content-addressed caching, and makes regressions inspectable from a Flask dashboard.

The current automotive QA vertical slice is deliberately offline and deterministic. It proves that the evaluation infrastructure works without API keys or paid model calls. Live provider adapters, Hugging Face dataset importers, retrieval-augmented generation (RAG), and statistical model comparisons are the next milestones—not features claimed as complete.

## Why this project exists

LLM demos often show a handful of successful answers but cannot answer the engineering questions that matter in production:

- Did a prompt or model change improve quality across a fixed test set?
- Can every score be traced to the exact dataset, prompt, provider, and configuration?
- Are repeated runs reproducible, cacheable, and inexpensive?
- Which examples regressed, and why did a scorer fail them?
- Can the same evaluation run in CI before a release?

EvalBench is designed around those questions. It emphasizes measurable behavior, immutable run history, explicit failure evidence, and honest separation between deterministic checks and model-based judgment.

## Verified capabilities

| Capability | Evidence in the current repository |
|---|---|
| Versioned evaluation data | Validated automotive JSONL examples with a dataset content hash |
| Versioned prompts | YAML prompt registry with variable validation and a prompt content hash |
| Provider abstraction | Framework-independent provider protocol and deterministic offline provider |
| Deterministic scoring | Exact-match and JSON Schema scorers with readable evidence |
| Reproducibility | Dataset, prompt, provider, and settings hashes are stored with each run |
| Response caching | Identical requests are served from a content-addressed SQLite cache |
| Audit trail | Append-only run summaries and per-example results |
| Web observability | Run dashboard, run-detail view, liveness, and database readiness routes |
| Local quality gate | Eight automated tests and Ruff static analysis pass locally |

## Architecture pipeline

```mermaid
flowchart LR
    D["Versioned JSONL dataset"] --> V["Pydantic validation"]
    P["Versioned YAML prompt"] --> V
    V --> H["Content hashing"]
    H --> R["Evaluation runner"]
    R --> C{"Response cache hit?"}
    C -- Yes --> O["Cached model output"]
    C -- No --> S["Provider protocol"]
    S --> M["Offline mock provider"]
    S -. "Phase 2" .-> L["Live LLM provider"]
    M --> W["Cache response"]
    L --> W
    W --> O
    O --> E["Deterministic scorers"]
    E --> DB[("SQLite / SQLAlchemy")]
    DB --> UI["Flask dashboard and run evidence"]
    DB -. "Future" .-> CI["Regression gate in CI"]
```

The Flask routes only handle HTTP concerns. Dataset loading, prompt rendering, providers, scoring, caching, and run orchestration live in framework-independent modules so they can also be used by the CLI, background jobs, and future CI workflows.

## Evaluation workflow

1. **Load and validate** a pinned dataset and prompt definition.
2. **Hash the inputs** so a run can be reproduced and compared later.
3. **Render one prompt per example** using only declared template variables.
4. **Check the response cache** using the provider, prompt, example, and settings identity.
5. **Generate or retrieve a response** through the provider protocol.
6. **Apply compatible scorers** and capture human-readable evidence.
7. **Persist an append-only run** with per-example outputs, scores, latency, and cache status.
8. **Inspect failures** in the dashboard or compare the stored results programmatically.

```mermaid
sequenceDiagram
    participant User as CLI / future job
    participant Runner as Evaluation runner
    participant Cache as Response cache
    participant Provider as System under test
    participant Scorer as Scorers
    participant Store as Run store

    User->>Runner: Start(dataset, prompt, provider)
    loop Each validated example
        Runner->>Cache: Lookup content key
        alt Cached
            Cache-->>Runner: Stored response
        else Not cached
            Runner->>Provider: Generate rendered prompt
            Provider-->>Runner: Response + latency
            Runner->>Cache: Store response
        end
        Runner->>Scorer: Score response against hidden expectation
        Scorer-->>Runner: Score + evidence
        Runner->>Store: Append example result
    end
    Runner->>Store: Finalize aggregate metrics
    Store-->>User: Run ID and summary
```

## Repository layout

```text
evalbench/
├── datasets/automotive_qa/   # Versioned JSONL evaluation examples
├── prompts/                  # Versioned YAML prompt definitions
├── evalbench/
│   ├── datasets/             # Validation, loading, and hashing
│   ├── prompts/              # Prompt registry and rendering
│   ├── providers/            # Provider protocol and offline provider
│   ├── scorers/              # Exact-match and JSON Schema scoring
│   ├── services/             # Evaluation orchestration
│   ├── templates/            # Dashboard and run-detail pages
│   ├── models.py             # Runs, results, and response cache
│   └── cli.py                # Reproducible command-line runner
├── migrations/               # Alembic database migrations
├── tests/                    # Unit and integration tests
├── Dockerfile                # Production container definition
├── plan.md                   # Phased implementation plan
└── Deploy.md                 # Deployment and inactivity strategy
```

## Quick start

Python 3.12 is the supported project runtime.

```bash
git clone https://github.com/Sujay1709/evalbench-ai.git
cd evalbench-ai
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
flask --app evalbench:create_app db upgrade
pytest
python -m evalbench.cli run
flask --app evalbench:create_app run --debug
```

Open [http://localhost:5000](http://localhost:5000) to inspect the run dashboard.

### Health checks

```bash
curl --fail http://localhost:5000/health
curl --fail http://localhost:5000/health/ready
```

- `/health` confirms that the web process is alive.
- `/health/ready` also verifies that the database is reachable.

### Reproducibility and cache check

```bash
python -m evalbench.cli run
python -m evalbench.cli run
```

The first run generates deterministic offline responses. The second run should mark every response as coming from the cache while producing the same scores and content hashes.

## What has actually been tested

The following checks were run locally on August 17, 2026:

| Check | Result |
|---|---|
| `pytest` | 8 tests passed |
| `ruff check .` | Passed |
| Database migration | Upgrade completed and all three application tables were created |
| First CLI evaluation | 5 of 5 deterministic fixtures passed; all responses generated |
| Repeated CLI evaluation | 5 of 5 passed with identical metrics; all responses served from cache |
| Flask dashboard | Homepage and run-detail evidence rendered successfully |
| Health routes | Liveness and database readiness returned successful responses |

The 100% fixture result validates the mechanics of the runner and scorers. It is **not** presented as evidence that a real LLM has perfect automotive knowledge.

## Evaluation data contract

Each JSONL record is one independent test case. This example follows the implemented Pydantic schema:

```json
{
  "id": "auto-001",
  "input": {
    "question": "What does ICE stand for in an automotive powertrain?",
    "response_format": "Return only the expanded term."
  },
  "mock_response": "internal combustion engine",
  "scorers": [
    {
      "type": "exact_match",
      "expected": "Internal Combustion Engine"
    }
  ],
  "tags": ["powertrain", "terminology"],
  "difficulty": "easy",
  "split": "development"
}
```

Dataset and prompt hashes change when their content changes. That means two runs should only be compared as the same benchmark when the recorded identities match—or when the difference is intentional and documented.

## Real-world evaluation strategy

Yes, EvalBench can be tested with Hugging Face datasets and live reference data. That expansion should happen through explicit dataset adapters rather than passing an arbitrary dataset directly to the LLM.

### Recommended benchmark ladder

| Source | What it tests | Proposed EvalBench use |
|---|---|---|
| [SQuAD v2](https://huggingface.co/datasets/rajpurkar/squad_v2) | Grounded extractive QA plus questions with no answer in the supplied context | Measure exact match, token F1, and correct abstention on a pinned validation sample |
| [HotpotQA](https://huggingface.co/datasets/hotpotqa/hotpot_qa) | Multi-hop reasoning across multiple context passages with supporting facts | Measure answer quality, supporting-evidence recall, and distractor resistance |
| [NHTSA vPIC](https://vpic.nhtsa.dot.gov/api/Home/Index) | Live automotive manufacturer, model, VIN, and vehicle specification data | Create timestamped domain regression cases and test freshness, normalization, and API-failure handling |
| Curated automotive holdout | Portfolio-specific questions reviewed against authoritative sources | Measure domain accuracy and regression behavior without benchmark contamination |

Hugging Face supports streamed dataset loading, so an adapter can sample examples without downloading an entire corpus. For reproducibility, EvalBench should pin the dataset name, configuration, split, revision, sampling seed, and selected example IDs; the normalized JSONL artifact should then be content-hashed and stored with the run metadata.

### Benchmark answers are not reference context

This distinction prevents evaluation leakage:

| Data element | May the model see it? | Purpose |
|---|---:|---|
| User question | Yes | Input to the system under test |
| Approved context or retrieved documents | Yes | Evidence the model is allowed to use |
| Gold answer / expected JSON | **No** | Hidden answer key used only by scorers |
| Scorer thresholds and private labels | Normally no | Evaluation policy, not generation context |
| Public system instructions | Yes | Defines the task and response contract |

Putting the expected answer into the prompt would test copying, not reasoning or retrieval. For RAG evaluation, EvalBench should index a separate reference corpus, retrieve top-k passages, pass those passages to the model, and keep the gold answer isolated in the evaluator. The run should record retrieved document IDs so groundedness and citation quality can be audited.

### Proposed live-test pipeline

```mermaid
flowchart LR
    HF["Pinned Hugging Face split"] --> A["Dataset adapter"]
    API["Timestamped NHTSA snapshot"] --> A
    A --> N["Normalized EvalBench JSONL"]
    N --> Q["Seeded development sample"]
    N --> T["Hidden holdout sample"]
    Q --> SUT["Live provider or RAG system"]
    T --> SUT
    RC["Reference corpus"] --> IDX["LlamaIndex retrieval - planned"]
    IDX --> SUT
    SUT --> SC["Exact match / F1 / schema / groundedness"]
    SC --> CMP["Baseline comparison + confidence interval"]
    CMP --> G{"Regression threshold met?"}
    G -- Yes --> PASS["Release candidate"]
    G -- No --> FAIL["Inspect failed examples"]
```

### Five stages before calling it production evidence

1. **Adapter validation:** map a small pinned SQuAD v2 sample into EvalBench and manually inspect the normalized examples.
2. **Scorer validation:** add token F1 and answerability scoring, then unit-test edge cases such as punctuation, aliases, and empty answers.
3. **Live provider comparison:** evaluate a fixed holdout against at least two provider/model configurations with caching, retry limits, latency, and cost capture.
4. **RAG evaluation:** use LlamaIndex only as the retrieval layer, log retrieved evidence, and score both final answers and retrieval quality.
5. **Statistical regression gate:** compare against a stored baseline using paired examples and uncertainty estimates; fail CI only when a documented threshold is crossed.

This staged approach keeps the current offline suite fast and free while adding a separate opt-in integration suite for network-dependent and paid tests.

## Scoring philosophy

EvalBench uses deterministic scoring whenever a property can be checked directly:

- **Exact match:** suitable for normalized labels and short canonical facts.
- **JSON Schema:** verifies parseability, required fields, types, and structural contracts.
- **Token F1 — planned:** gives partial credit for overlapping answer spans.
- **Answerability — planned:** measures whether a model correctly abstains when context lacks an answer.
- **Retrieval metrics — planned:** evaluates whether the right supporting passages were retrieved.
- **LLM judge — later phase:** reserved for subjective qualities and calibrated against human labels before being trusted.

Model-based judges are useful but not ground truth. Their prompt, model version, and variance must be tracked like any other system under test.

## Deployment status

| Target | Status | Notes |
|---|---|---|
| Local CLI | **Verified** | Migrations, evaluation, persistence, and cache replay pass locally |
| Local Flask dashboard | **Verified** | Run summaries, per-example evidence, and health routes render locally |
| Docker | **Prepared, not yet verified** | Container definition exists; image build and runtime smoke test remain |
| Render | **Not deployed** | Deployment procedure and inactivity mitigation are documented in `Deploy.md` |
| External uptime monitor | **Not configured** | `/health` is ready for a permitted monitoring service |
| Inngest background jobs | **Planned** | Deferred until evaluation execution is moved out of the request cycle |
| Public portfolio demo | **Planned** | Must use a read-only seeded demo or authenticated, rate-limited live runs |

The deploy status is intentionally explicit: a Dockerfile or deployment document is not the same as a verified public deployment.

## Reliability, cost, and security controls

- Secrets belong in environment variables and `.env` is excluded from Git.
- Offline tests require no provider credentials and incur no model cost.
- Content-addressed caching prevents identical live requests from being billed twice.
- Historical evaluation runs are append-only for auditability.
- A public demo must never expose an unauthenticated paid generation endpoint.
- Live adapters should implement timeouts, bounded retries, rate limits, and failure classification.
- External dataset terms, licenses, revisions, and provenance should be recorded before redistribution.

## Roadmap

- [x] **Phase 0:** Flask foundation, typed settings, persistence, migrations, health checks, and tests
- [x] **Phase 1:** versioned automotive data, prompt registry, provider protocol, deterministic scoring, persisted runs, and response caching
- [ ] **Phase 2:** Hugging Face adapters, token F1/answerability metrics, and opt-in live provider integration
- [ ] **Phase 3:** Inngest background execution, retries, and operational failure visibility
- [ ] **Phase 4:** baseline comparison dashboard, latency/cost analysis, and retrieval metrics
- [ ] **Phase 5:** calibrated LLM judge and human-reviewed evaluation subset
- [ ] **Phase 6:** CI regression policy with statistically justified thresholds
- [ ] **Phase 7:** verified Docker/Render deployment and safe public demo mode

See [`plan.md`](plan.md) for completion criteria and [`Deploy.md`](Deploy.md) for the deployment design.

## Known limitations

- The current provider is deterministic and offline; it does not measure real-model intelligence.
- The seeded dataset contains five automotive fixtures, which is appropriate for infrastructure verification but too small for model selection.
- Only exact-match and JSON Schema scoring are implemented today.
- Docker and Render execution have not yet been smoke-tested.
- No statistical significance, cost comparison, or human calibration is claimed yet.

These are roadmap boundaries, not hidden caveats. Each one maps to a testable milestone above.

## Engineering story

EvalBench demonstrates more than API integration: it shows dataset design, experiment reproducibility, provider abstraction, deterministic testing, persistence, caching, observability, and production-aware deployment planning. The strongest interview discussion is the decision to validate the evaluation harness offline first, then add live model complexity behind stable interfaces and measurable regression criteria.
