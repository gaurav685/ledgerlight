"""Load parsed bhavcopy rows into price_bars, upserting on
(source_id, trade_date, symbol, series) — see ledgerlight.db.models.PriceBar
for why a corrected re-issue of the same trading day updates rather than
duplicates. Quarantined rows are never silently dropped: every one is
returned to the caller with its row number and reason."""

from __future__ import annotations

import zipfile
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ledgerlight.db.models import DocumentVersion, PriceBar
from ledgerlight.processing.bhavcopy import BhavcopyParseResult, QuarantinedRow, parse_bhavcopy_csv


@dataclass
class PriceLoadResult:
    rows_parsed: int = 0
    rows_upserted: int = 0
    rows_unchanged: int = 0
    quarantined: list[QuarantinedRow] = field(default_factory=list)


def extract_csv_text_from_zip_bytes(zip_bytes: bytes) -> str:
    import io

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        if len(names) != 1:
            raise ValueError(f"expected exactly one file in bhavcopy zip, got {names}")
        return zf.read(names[0]).decode("utf-8")


def load_price_bars(
    session: Session, source_id: str, version: DocumentVersion, csv_text: str
) -> PriceLoadResult:
    parsed: BhavcopyParseResult = parse_bhavcopy_csv(csv_text)
    result = PriceLoadResult(rows_parsed=len(parsed.rows), quarantined=parsed.quarantined)

    for row in parsed.rows:
        existing = session.scalar(
            select(PriceBar).where(
                PriceBar.source_id == source_id,
                PriceBar.trade_date == row.trade_date,
                PriceBar.symbol == row.symbol,
                PriceBar.series == row.series,
            )
        )
        if existing is not None:
            if existing.version_id == version.id:
                result.rows_unchanged += 1
                continue
            existing.version_id = version.id
            existing.row_number = row.row_number
            existing.isin = row.isin
            existing.open = row.open
            existing.high = row.high
            existing.low = row.low
            existing.close = row.close
            existing.last = row.last
            existing.prev_close = row.prev_close
            existing.volume = row.volume
            existing.turnover = row.turnover
            existing.trades = row.trades
            existing.raw_row = row.raw_row
            result.rows_upserted += 1
            continue

        session.add(
            PriceBar(
                source_id=source_id,
                version_id=version.id,
                row_number=row.row_number,
                trade_date=row.trade_date,
                symbol=row.symbol,
                series=row.series,
                isin=row.isin,
                open=row.open,
                high=row.high,
                low=row.low,
                close=row.close,
                last=row.last,
                prev_close=row.prev_close,
                volume=row.volume,
                turnover=row.turnover,
                trades=row.trades,
                raw_row=row.raw_row,
            )
        )
        result.rows_upserted += 1

    session.commit()
    return result
