# PLC-36 automated tests

Pytest hardware tests for a Shelly PLC-36 (DUT) against a Sequent MegaIND HAT.

The engineering plan is in [`.cursor/plans/PLC36_pytest_automation_plan.plan.md`](.cursor/plans/PLC36_pytest_automation_plan.plan.md).

## Setup

Run on the Raspberry Pi that has the MegaIND card (I2C). The DUT must be reachable on Ethernet.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run tests from the terminal

```bash
source .venv/bin/activate
pytest tests/0V_10V_outputs/test_variable_outputs.py \
  --dut-ip 192.168.10.247 \
  --log-to-stdout \
  -k "volts==5"
```

Without a HAT or DUT, hardware tests skip. `tests/4mA_20mA_inputs/` and `tests/rs485/` are skipped placeholders.

## Test dashboard

The responsive dashboard runs on the Raspberry Pi and provides:

- bench and device connectivity status;
- Run all, test-category, and individual-test controls;
- live progress, results, and safe cancellation;
- historical pass-rate and duration statistics;
- structured voltage, accuracy, and DS18B20 metrics;
- an in-app log viewer and one JSONL log download per run.

Start it from the repository root:

```bash
source .venv/bin/activate
plc36-dashboard --host 0.0.0.0 --port 8080
```

Open `http://<raspberry-pi-ip>:8080` from a browser on the same network.
The default PLC IP and MegaIND stack are loaded from `config/bench.yaml`.

Only one hardware run can execute at a time. The lock also protects the bench
when pytest is started separately from a terminal. The dashboard stops tests
with `SIGINT` so fixture cleanup can return outputs to their safe states.

Dashboard history is stored in `output/dashboard.sqlite3`. Each run has a
separate directory under `output/runs/`, so later runs do not overwrite its
measurements or logs.
