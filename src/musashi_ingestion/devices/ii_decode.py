"""Manual-derived DA01–DA09 payload decoding.

DA01 follows the retained reader's parsing. Other layouts follow the scanned
manufacturer manual, printed pages 89–92; site firmware remains unverified.
"""

from __future__ import annotations

import re

from .ii import IIProtocolError


_PATTERNS = {
    "D01": re.compile(r"DA01P([0-9 ]{4})T([0-9 ]{5})V([0-9 ]{4})M([0-3])N(.{10})", re.DOTALL),
    "D02": re.compile(r"DA02S([0-6])A([1-4])"),
    "D03": re.compile(r"DA03A([+-][0-9]{3})D([0-9]{3})V([+-][0-9]{4})"),
    "D04": re.compile(r"DA04L([0-9]{3})C([0-9]{3})"),
    "D05": re.compile(r"DA05R([0-9]{3})"),
    "D06": re.compile(r"DA06CH([0-9]{3})"),
    "D07": re.compile(r"DA07CT([0-9]{8})"),
    "D08": re.compile(r"DA08VR([0-9]{4})SP([25])"),
    "D09": re.compile(r"DA09SY([01]{7})"),
}


def _number(value: str) -> int | None:
    stripped = value.strip()
    return int(stripped) if stripped else None


def parse_upload(code: str, payload: str) -> dict:
    """Parse an allowed upload without inventing a value for blank fields."""
    pattern = _PATTERNS.get(code)
    if pattern is None:
        raise ValueError("unsupported upload code")
    match = pattern.fullmatch(payload)
    if match is None:
        raise IIProtocolError(f"invalid {code} payload shape")
    values = match.groups()
    if code == "D01":
        pressure, duration, vacuum, mode, name = values
        return {"pressure_kpa": None if _number(pressure) is None else _number(pressure) / 10,
                "dispense_time_ms": _number(duration),
                "vacuum_kpa_magnitude": None if _number(vacuum) is None else _number(vacuum) / 100,
                "mode_code": int(mode), "product_name": name.rstrip()}
    if code == "D02":
        syringe, tube = (int(value) for value in values)
        return {"syringe_size_code": syringe, "syringe_size_cc": {0: 3, 1: 5, 2: 10, 3: 20,
                4: 30, 5: 50, 6: 70}[syringe], "adapter_tube_code": tube,
                "adapter_tube_m": {1: 0.5, 2: 1.0, 3: 1.5, 4: 2.0}[tube]}
    if code == "D03":
        alpha, delta, vacuum = values
        return {"alpha_correction": int(alpha), "delta_correction_percent": int(delta),
                "vacuum_correction_kpa": int(vacuum) / 100}
    if code == "D04":
        return {"remaining_detection_percent": int(values[0]), "remaining_detection_count": int(values[1])}
    if code == "D05":
        return {"remaining_volume_percent": int(values[0])}
    if code == "D06":
        channel = int(values[0])
        if not 1 <= channel <= 100:
            raise IIProtocolError("displayed channel outside supported range")
        return {"displayed_channel": channel}
    if code == "D07":
        return {"dispense_count": int(values[0])}
    if code == "D08":
        return {"software_version_raw": values[0], "model_specification": "V" + values[1]}
    sizes = (3, 5, 10, 20, 30, 50, 70)
    return {"sampled_syringe_sizes_cc": [size for size, flag in zip(sizes, values[0]) if flag == "1"]}
