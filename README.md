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

## Run

```bash
source .venv/bin/activate
pytest tests/0V_10V_outputs/test_variable_outputs.py \
  --dut-ip 192.168.10.247 \
  --log-to-stdout \
  -k "volts==5"
```

Optional DUT console scrape:

```bash
pytest --capture-dut-logs --log-to-stdout tests/test_dut_log_capture.py
```

Without a HAT or DUT, hardware tests skip. `tests/4mA_20mA_inputs/` and `tests/rs485/` are skipped placeholders.
