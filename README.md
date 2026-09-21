# PLC-36 automated hardware tests

Python and pytest hardware-in-the-loop tests for a Shelly PLC-36 connected to a
Sequent Microsystems MegaIND HAT on a Raspberry Pi. The repository can be used
from the terminal or through the included web dashboard.

## Start the project

The commands below are intended to be run on the Raspberry Pi connected to the
MegaIND HAT. The PLC-36 must be powered, operational, and reachable from the Pi
over Ethernet.

### 1. Clone and install

```bash
git clone https://github.com/KatiaGH/plc.git
cd plc
./scripts/setup_venv.sh
source .venv/bin/activate
```

The setup script creates `.venv`, upgrades pip, and installs the project and its
development dependencies in editable mode. For later sessions, only activate
the existing environment:

```bash
cd ~/plc
source .venv/bin/activate
```

Manual installation is also supported:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Python 3.10 or newer is required.

### 2. Configure the bench

Edit [`config/bench.yaml`](config/bench.yaml) before starting tests:

```yaml
dut:
  ip: 192.168.10.247
  rpc_timeout_s: 10

hat:
  stack: 0
  host_ip: 192.168.10.69

tolerances:
  voltage_v: 0.6
  mpi_high_v: 3.0
  settle_s: 1

onewire:
  min_celsius: -20
  max_celsius: 80
  plausible_room_celsius: [5, 45]
```

Replace the example addresses with the current PLC and Raspberry Pi addresses.
The dashboard and terminal tests load this file automatically.

### 3. Run the tests

Run the default terminal suite:

```bash
pytest
```

Run one hardware area:

```bash
pytest tests/0V_10V_outputs/test_variable_outputs.py
pytest tests/direct_digital_analog_inputs/
pytest tests/isolated_outputs/
pytest tests/opto_isolated_inputs/
```

Run one exact test case:

```bash
pytest "tests/0V_10V_outputs/test_variable_outputs.py::test_variable_output_matches_hat_uin[50-O3]"
```

Hardware tests are skipped when the required PLC or HAT connection is not
available. Only one hardware test process can use the bench at a time.

## Start the dashboard

From the repository root, with the virtual environment active:

```bash
plc36-dashboard --host 0.0.0.0 --port 8080
```

The equivalent module command is:

```bash
python -m plc36_dashboard --host 0.0.0.0 --port 8080
```

Open the dashboard from another computer on the same network:

```text
http://<raspberry-pi-ip>:8080
```

For example, if the Pi address is `192.168.10.69`, open
`http://192.168.10.69:8080`. On the Pi itself, use
`http://127.0.0.1:8080`.

Stop the dashboard with `Ctrl+C`.

The dashboard provides three main areas:

- **Test Health** — daily passed, failed, and skipped totals, recent completed
  runs, and the latest failures that need attention.
- **Tests** — built-in and custom presets, grouped individual-test selection,
  live progress, and safe test cancellation.
- **History & Logs** — previous runs, test results, pytest logs, and PLC RPC
  logs.

The PLC, HAT, and Raspberry Pi status row indicates whether the bench is ready.
The dashboard permits only one active hardware run, but the next selection can
be prepared while a run is in progress.

## What the project tests

| Area | Purpose | Current status |
| --- | --- | --- |
| 0–10 V outputs | Set O1–O4 and compare the expected voltage with MegaIND UIN1–UIN4 | Available |
| MPI inputs and internal relays | Validate NC and NO paths for R1–R4 using HAT voltage outputs | Available |
| Isolated outputs | Verify OA and supported OB output paths through HAT opto inputs | Available |
| Isolated inputs | Exercise PLC II1–II8 through the configured HAT output path | Available |
| Output accuracy | Collect detailed calibration, error, and noise measurements | Implemented, temporarily excluded |
| 1-Wire sensors | Validate two DS18B20 sensors through the O4 transport path | Implemented, temporarily excluded |
| 4–20 mA inputs | Reserved for the finalized current-loop bench | Placeholder, skipped |
| RS485 | Reserved for the finalized RS485 implementation | Placeholder, skipped |

“Available” means that the group is included in the dashboard catalog. The
default `pytest` paths are controlled separately by `pyproject.toml`.

## Hardware and channel mapping

The central mapping is defined in
[`src/plc36_testkit/mapping.py`](src/plc36_testkit/mapping.py).

| PLC-36 path | RPC mapping | Bench connection |
| --- | --- | --- |
| Internal relays R1–R4 | Boolean IDs 100–103 | Route HAT UOUT1–UOUT4 to the paired NC/NO MPI inputs |
| Variable outputs O1–O4 | Number IDs 100–103 | Read back through HAT UIN1–UIN4 |
| MPI inputs DI1–DI8 | Number IDs 104–111 | Driven through the HAT voltage outputs and relay paths |
| 4–20 mA inputs LP1–LP4 | Number IDs 112–115 | Reserved for the current-loop bench |
| Isolated outputs OA1–OB4 | Boolean IDs 104–111 | Read through the mapped HAT opto inputs |
| Isolated inputs II1–II8 | Boolean IDs 120–127 | Driven through the configured HAT OD path |

If wiring changes, update the mapping and the relevant directory fixture
together. Do not compensate for a wiring change by changing assertions alone.

## Configuration reference

| Key | Description |
| --- | --- |
| `dut.ip` | PLC-36 IPv4 or IPv6 address used by RPC requests |
| `dut.rpc_timeout_s` | Timeout for PLC RPC communication |
| `hat.stack` | MegaIND stack address passed to the HAT library |
| `hat.host_ip` | Raspberry Pi/bench host address retained in the configuration |
| `tolerances.voltage_v` | Allowed absolute error for 0–10 V comparisons; also displayed in dashboard failure details |
| `tolerances.mpi_high_v` | Threshold separating LOW and HIGH MPI measurements |
| `tolerances.settle_s` | Delay after changing a relay, output, or HAT signal |
| `onewire.min_celsius` | Minimum accepted decoded temperature |
| `onewire.max_celsius` | Maximum accepted decoded temperature |
| `onewire.plausible_room_celsius` | Expected room-temperature range used by the 1-Wire checks |

Terminal options can override selected configuration values for one run:

```bash
pytest tests/0V_10V_outputs/test_variable_outputs.py \
  --dut-ip 192.168.10.146 \
  --hat-stack 0 \
  --config config/bench.yaml \
  --log-to-stdout
```

Useful pytest options provided by this project:

| Option | Purpose |
| --- | --- |
| `--dut-ip ADDRESS` | Override `dut.ip` for the current run |
| `--hat-stack NUMBER` | Override `hat.stack` for the current run |
| `--config PATH` | Load a different bench YAML file |
| `--log-to-stdout` | Show framework logs in the terminal |
| `--framework-log-level LEVEL` | Set the framework log level, such as `DEBUG` or `INFO` |
| `--capture-dut-logs` | Capture PLC debug logs as additional diagnostics |

## Common test commands

List collected tests without running hardware actions:

```bash
pytest --collect-only -q -o addopts=
```

Run by marker:

```bash
pytest -m analog
pytest -m digital
pytest -m hardware
```

Run the dashboard's unit and integration tests. These do not operate the
hardware bench:

```bash
pytest tests/dashboard -q
```

Run a test repeatedly from the shell:

```bash
for run in 1 2 3 4 5; do
  pytest tests/direct_digital_analog_inputs/test_mpi_and_internal_relays.py || break
done
```

## Project structure

```text
plc/
├── config/
│   └── bench.yaml                  Bench addresses, timing, and tolerances
├── scripts/
│   └── setup_venv.sh               Virtual-environment setup helper
├── src/
│   ├── plc36_testkit/               Shared hardware-test framework
│   │   ├── bench_lock.py            Cross-process exclusive bench lock
│   │   ├── config.py                YAML configuration loader
│   │   ├── conversions.py           Percentage and voltage conversions
│   │   ├── dashboard_events.py      Structured progress and metric events
│   │   ├── dut_log.py               Optional DUT diagnostic capture
│   │   ├── hat.py                   MegaIND wrapper
│   │   ├── logging.py               JSONL failure and RPC logging
│   │   ├── mapping.py               PLC RPC and physical channel mapping
│   │   ├── rpc.py                   PLC-36 RPC client
│   │   └── wait.py                  Bench settling helpers
│   └── plc36_dashboard/             FastAPI dashboard application
│       ├── app.py                   HTTP API, status probes, SSE, CLI entry point
│       ├── catalog.py               Test discovery, categories, friendly names
│       ├── database.py              SQLite run history and analytics
│       ├── runner.py                Managed pytest subprocess and cancellation
│       ├── templates/index.html     Dashboard markup
│       └── static/                  Dashboard CSS and JavaScript
├── tests/
│   ├── 0V_10V_outputs/              Variable-output and accuracy tests
│   ├── 1_wire_interface/            DS18B20 tests
│   ├── 4mA_20mA_inputs/             Current-loop placeholder
│   ├── dashboard/                   Dashboard tests
│   ├── direct_digital_analog_inputs/ MPI and relay-path tests
│   ├── isolated_outputs/            OA/OB output tests
│   ├── opto_isolated_inputs/        II1–II8 input tests
│   ├── rs485/                       RS485 placeholder
│   └── conftest.py                  Shared fixtures and pytest options
├── output/                           Generated results; ignored by Git
├── pyproject.toml                    Package, pytest, and Ruff configuration
└── README.md
```

### Main components

- `plc36_testkit` contains reusable bench configuration, communication,
  mappings, locking, logging, and metric-recording code.
- Test-directory `conftest.py` files restore only the outputs and HAT paths
  used by that hardware area.
- `plc36_dashboard` discovers available tests and starts pytest as a managed
  subprocess. Progress reaches the browser through structured JSONL events and
  server-sent events.
- `DashboardDatabase` stores completed runs, individual results, measurements,
  custom presets, and daily statistics in SQLite.

## Generated results and logs

Dashboard data is written under `output/` and is not committed to Git:

```text
output/
├── dashboard.sqlite3
└── runs/
    └── <run-id>/
        ├── command.json
        ├── events.jsonl
        ├── junit.xml
        ├── run-log.jsonl
        └── rpc_responses.jsonl      Present when PLC RPC records were captured
```

- `dashboard.sqlite3` contains run history, results, measurements, and custom
  presets.
- `run-log.jsonl` contains the pytest process output.
- `rpc_responses.jsonl` contains PLC request and response records.
- `events.jsonl` is the live structured event stream consumed by the dashboard
  runner.
- `junit.xml` is used to reconcile results if a live event was missed.

Each dashboard run receives a separate directory, so a later run does not
overwrite earlier measurements or logs.

## Safety and concurrency

Hardware tests use an exclusive file lock at
`/tmp/plc36-test-bench.lock`. The same lock is used by dashboard runs and
terminal pytest runs, preventing simultaneous access to the PLC and HAT.

Fixtures and `finally` blocks return the affected outputs, relays, and HAT
channels to their safe states. Dashboard cancellation sends `SIGINT` to pytest
and allows this cleanup to execute while pytest exits.

Do not start another hardware-control process outside this project while a run
is active.

## Troubleshooting

### The dashboard starts, but another computer cannot open it

Confirm that the dashboard is listening and works locally:

```bash
curl http://127.0.0.1:8080
ss -ltnp | grep ':8080'
hostname -I
```

Use the Raspberry Pi address returned by `hostname -I`, ensure both computers
are on the same network, and confirm that port `8080` is not blocked.

### Tests are skipped

The shared fixtures skip hardware tests when the PLC RPC endpoint is
unreachable, the PLC is not operational, the MegaIND library is unavailable,
or the HAT firmware cannot be read. Check the status row in the dashboard and
verify `config/bench.yaml`.

### The bench is reported as busy

Another dashboard or terminal run currently owns the hardware lock. Wait for
that process to finish or stop it normally. Do not remove the lock file while a
test process is still controlling hardware.

### Configuration fails to load

All fields shown in the configuration example are required. YAML indentation
must use spaces, and `onewire.plausible_room_celsius` must contain two numeric
values.

### View more diagnostic output

```bash
pytest <test-path> --log-to-stdout --framework-log-level DEBUG
```

For a dashboard run, open **History & Logs** and view or download the pytest and
PLC RPC JSONL logs.

## Development checks

Run the dashboard regression tests and the linter before committing framework
or UI changes:

```bash
pytest tests/dashboard -q
ruff check src tests
```

The longer engineering plan is available in
[`PLC36_pytest_automation_plan.md`](PLC36_pytest_automation_plan.md).
