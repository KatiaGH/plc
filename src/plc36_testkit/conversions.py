MAX_OUTPUT_VOLTS = 10.0
MAX_PERCENT = 100.0


def percentage_to_volts(percentage: float) -> float:
    if not 0.0 <= percentage <= MAX_PERCENT:
        raise ValueError("Percentage must be between 0 and 100")

    return percentage / MAX_PERCENT * MAX_OUTPUT_VOLTS


def volts_to_percentage(volts: float) -> float:
    if not 0.0 <= volts <= MAX_OUTPUT_VOLTS:
        raise ValueError("Voltage must be between 0 and 10 V")

    return volts / MAX_OUTPUT_VOLTS * MAX_PERCENT