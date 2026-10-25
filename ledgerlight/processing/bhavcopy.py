"""NSE bhavcopy CSV parsing into price_bars rows, with schema validation
(Pydantic) and quarantine for malformed rows — never silently dropped.

Two real formats were observed across the ingested corpus (see
docs/ingestion/architecture.md for the exact column-set evidence):

- **Legacy** (through 2024-07-05): `SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,
  LAST,PREVCLOSE,TOTTRDQTY,TOTTRDVAL,TIMESTAMP,TOTALTRADES,ISIN,`
  (trailing comma -> one trailing empty field). Consistent across every
  2018-2023 sample actually inspected; no further drift detected within
  the ingested window.
- **UDiFF** (from 2024-07-08): a much wider, named-column format
  (`TradDt,BizDt,Sgmt,...,TckrSymb,SctySrs,...`) covering every traded
  instrument type on the exchange that day (equities, SGBs, etc.), not
  only cash-market equities. All rows are parsed into price_bars
  regardless of instrument type — the schema is generic enough to hold
  any of them, and filtering to equities-only was not something Phase 1
  needed to decide.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, ValidationError, field_validator

LEGACY_HEADER_MARKER = "SYMBOL,SERIES,"
UDIFF_HEADER_MARKER = "TradDt,"


class BhavcopyRow(BaseModel):
    row_number: int
    trade_date: dt.date
    symbol: str
    series: str
    isin: str | None = None
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    close: Decimal | None = None
    last: Decimal | None = None
    prev_close: Decimal | None = None
    volume: int | None = None
    turnover: Decimal | None = None
    trades: int | None = None
    raw_row: str

    @field_validator("symbol", "series")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be empty")
        return v.strip()


@dataclass
class QuarantinedRow:
    row_number: int
    reason: str
    raw_row: str


@dataclass
class BhavcopyParseResult:
    format_detected: str  # "legacy" | "udiff"
    rows: list[BhavcopyRow] = field(default_factory=list)
    quarantined: list[QuarantinedRow] = field(default_factory=list)


def _to_decimal(value: str) -> Decimal | None:
    value = value.strip()
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _to_int(value: str) -> int | None:
    value = value.strip()
    if not value:
        return None
    try:
        return int(Decimal(value))
    except InvalidOperation:
        return None


def _parse_legacy_date(value: str) -> dt.date:
    return dt.datetime.strptime(value.strip(), "%d-%b-%Y").date()


def _parse_udiff_date(value: str) -> dt.date:
    return dt.date.fromisoformat(value.strip())


def _detect_format(header_line: str) -> str:
    if header_line.startswith(LEGACY_HEADER_MARKER):
        return "legacy"
    if header_line.startswith(UDIFF_HEADER_MARKER):
        return "udiff"
    raise ValueError(f"Unrecognised bhavcopy header: {header_line[:80]!r}")


def parse_bhavcopy_csv(csv_text: str) -> BhavcopyParseResult:
    lines = csv_text.splitlines()
    if not lines:
        raise ValueError("empty bhavcopy file")
    fmt = _detect_format(lines[0])

    reader = csv.DictReader(io.StringIO(csv_text))
    result = BhavcopyParseResult(format_detected=fmt)

    for row_number, raw in enumerate(reader, start=1):
        raw_line = ",".join(f"{k}={v}" for k, v in raw.items())
        try:
            if fmt == "legacy":
                parsed = BhavcopyRow(
                    row_number=row_number,
                    trade_date=_parse_legacy_date(raw["TIMESTAMP"]),
                    symbol=raw["SYMBOL"],
                    series=raw["SERIES"],
                    isin=raw.get("ISIN") or None,
                    open=_to_decimal(raw["OPEN"]),
                    high=_to_decimal(raw["HIGH"]),
                    low=_to_decimal(raw["LOW"]),
                    close=_to_decimal(raw["CLOSE"]),
                    last=_to_decimal(raw["LAST"]),
                    prev_close=_to_decimal(raw["PREVCLOSE"]),
                    volume=_to_int(raw["TOTTRDQTY"]),
                    turnover=_to_decimal(raw["TOTTRDVAL"]),
                    trades=_to_int(raw.get("TOTALTRADES", "")),
                    raw_row=raw_line,
                )
            else:
                parsed = BhavcopyRow(
                    row_number=row_number,
                    trade_date=_parse_udiff_date(raw["TradDt"]),
                    symbol=raw["TckrSymb"],
                    series=raw["SctySrs"],
                    isin=raw.get("ISIN") or None,
                    open=_to_decimal(raw["OpnPric"]),
                    high=_to_decimal(raw["HghPric"]),
                    low=_to_decimal(raw["LwPric"]),
                    close=_to_decimal(raw["ClsPric"]),
                    last=_to_decimal(raw["LastPric"]),
                    prev_close=_to_decimal(raw["PrvsClsgPric"]),
                    volume=_to_int(raw["TtlTradgVol"]),
                    turnover=_to_decimal(raw["TtlTrfVal"]),
                    trades=_to_int(raw.get("TtlNbOfTxsExctd", "")),
                    raw_row=raw_line,
                )
        except (ValidationError, KeyError, ValueError) as exc:
            result.quarantined.append(
                QuarantinedRow(row_number=row_number, reason=str(exc), raw_row=raw_line)
            )
            continue
        result.rows.append(parsed)

    return result
