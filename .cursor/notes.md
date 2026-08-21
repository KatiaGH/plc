<tldr>
PLC-36 pytest framework is in the repo. 40 tests collect; they skip without DUT/HAT. Plan: [PLC36_pytest_automation_plan.plan.md](/home/ibogoev/Work/STF/plc_36/automated-tests-repo/.cursor/plans/PLC36_pytest_automation_plan.plan.md). README: [README.md](/home/ibogoev/Work/STF/plc_36/automated-tests-repo/README.md).
</tldr>

- Done: Phases 0–7 — skeleton, 0–10 V, II, DI NC/NO, OA/OB, 1-Wire, `--capture-dut-logs`
- Placeholders: `tests/4mA_20mA_inputs/`, `tests/rs485/` stay skipped
- Off-bench: 40 collected, all skipped (no DUT/HAT lib here)
