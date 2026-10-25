"""Small SYNTHETIC bhavcopy fixtures (clearly not real downloaded NSE
files -- hand-written below, a handful of rows each) covering both real
observed column formats (legacy and UDiFF) plus malformed-row quarantine.
"""

from __future__ import annotations

from decimal import Decimal

from ledgerlight.processing.bhavcopy import parse_bhavcopy_csv

_LEGACY_CSV = (
    "SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,TOTTRDQTY,TOTTRDVAL,TIMESTAMP,"
    "TOTALTRADES,ISIN,\n"
    "INFY,EQ,1500.00,1520.50,1495.00,1510.25,1510.00,1498.00,1000000,1510000000.00,"
    "05-JAN-2017,5000,INE009A01021,\n"
    "TCS,EQ,2500.00,2550.00,2480.00,2530.00,2530.00,2490.00,500000,1265000000.00,"
    "05-JAN-2017,3000,INE467B01029,\n"
)

_UDIFF_CSV = (
    "TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,XpryDt,FininstrmActlXpryDt,"
    "StrkPric,OptnTp,FinInstrmNm,OpnPric,HghPric,LwPric,ClsPric,LastPric,PrvsClsgPric,UndrlygPric,"
    "SttlmPric,OpnIntrst,ChngInOpnIntrst,TtlTradgVol,TtlTrfVal,TtlNbOfTxsExctd,SsnId,NewBrdLotQty,"
    "Rmks,Rsvd1,Rsvd2,Rsvd3,Rsvd4\n"
    "2024-07-08,2024-07-08,CM,NSE,STK,12345,INE009A01021,INFY,EQ,,,,,,1600.00,1620.00,1590.00,"
    "1610.00,1610.00,1595.00,,,,,200000,322000000.00,2500,F1,1,,,,,\n"
)

_MALFORMED_LEGACY_CSV = (
    "SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,TOTTRDQTY,TOTTRDVAL,TIMESTAMP,"
    "TOTALTRADES,ISIN,\n"
    "INFY,EQ,1500.00,1520.50,1495.00,1510.25,1510.00,1498.00,1000000,1510000000.00,"
    "05-JAN-2017,5000,INE009A01021,\n"
    ",EQ,100.00,110.00,95.00,105.00,105.00,100.00,1000,100000.00,05-JAN-2017,10,INE000000000,\n"
    "BADROW,EQ,notanumber,110.00,95.00,105.00,105.00,100.00,1000,100000.00,"
    "NOT-A-DATE,10,INE000000000,\n"
)


def test_legacy_format_parses_cleanly() -> None:
    result = parse_bhavcopy_csv(_LEGACY_CSV)
    assert result.format_detected == "legacy"
    assert len(result.rows) == 2
    assert not result.quarantined

    infy = result.rows[0]
    assert infy.symbol == "INFY"
    assert infy.series == "EQ"
    assert infy.open == Decimal("1500.00")
    assert infy.close == Decimal("1510.25")
    assert infy.isin == "INE009A01021"


def test_udiff_format_parses_cleanly() -> None:
    result = parse_bhavcopy_csv(_UDIFF_CSV)
    assert result.format_detected == "udiff"
    assert len(result.rows) == 1
    assert not result.quarantined

    row = result.rows[0]
    assert row.symbol == "INFY"
    assert row.series == "EQ"
    assert row.open == Decimal("1600.00")


def test_malformed_rows_are_quarantined_not_dropped_silently() -> None:
    result = parse_bhavcopy_csv(_MALFORMED_LEGACY_CSV)
    assert len(result.rows) == 1  # only the first, well-formed row
    assert len(result.quarantined) == 2  # empty symbol + bad numeric/date -- never dropped

    reasons = [q.reason for q in result.quarantined]
    assert any("symbol" in r.lower() or "empty" in r.lower() for r in reasons)
    # every quarantined row keeps its original raw text for inspection
    assert all(q.raw_row for q in result.quarantined)


def test_unrecognised_header_raises() -> None:
    import pytest

    with pytest.raises(ValueError, match="Unrecognised bhavcopy header"):
        parse_bhavcopy_csv("NOT,A,REAL,HEADER\n1,2,3,4\n")


def test_empty_file_raises() -> None:
    import pytest

    with pytest.raises(ValueError, match="empty bhavcopy file"):
        parse_bhavcopy_csv("")
