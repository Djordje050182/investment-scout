"""Tests for engine/allocators.py — pure 13F/Form-4 parsing and scoring."""
import pytest

from engine.allocators import (
    MANAGERS, INSIDER_WATCH,
    parse_info_table, aggregate_holdings, portfolio_weights, diff_holdings,
    consensus_scores, build_basket, parse_form4, activity_summary,
    MIN_INSIDER_USD,
)


def _info_row(name, cusip, value, shares, put_call=""):
    pc = "<putCall>%s</putCall>" % put_call if put_call else ""
    return """<infoTable>
      <nameOfIssuer>%s</nameOfIssuer><titleOfClass>COM</titleOfClass>
      <cusip>%s</cusip><value>%d</value>
      <shrsOrPrnAmt><sshPrnamt>%d</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
      %s<investmentDiscretion>SOLE</investmentDiscretion>
    </infoTable>""" % (name, cusip, value, shares, pc)


def _table(*rows):
    return "<informationTable>%s</informationTable>" % "".join(rows)


class TestParse13F:
    def test_basic_rows(self):
        xml = _table(_info_row("APPLE INC", "037833100", 1000, 10),
                     _info_row("COCA COLA CO", "191216100", 500, 20))
        rows = parse_info_table(xml)
        assert len(rows) == 2
        assert rows[0]["name"] == "APPLE INC"
        assert rows[0]["value"] == 1000
        assert rows[1]["shares"] == 20

    def test_entities_unescaped(self):
        xml = _table(_info_row("S&amp;P GLOBAL INC", "78409V104", 100, 1))
        assert parse_info_table(xml)[0]["name"] == "S&P GLOBAL INC"

    def test_namespaced_tags(self):
        xml = ('<ns1:informationTable><ns1:infoTable>'
               "<ns1:nameOfIssuer>X</ns1:nameOfIssuer><ns1:cusip>C1</ns1:cusip>"
               "<ns1:value>7</ns1:value>"
               "<ns1:shrsOrPrnAmt><ns1:sshPrnamt>3</ns1:sshPrnamt></ns1:shrsOrPrnAmt>"
               "</ns1:infoTable></ns1:informationTable>")
        rows = parse_info_table(xml)
        assert rows == [{"name": "X", "cusip": "C1", "value": 7,
                         "shares": 3, "put_call": ""}]

    def test_aggregate_merges_same_cusip(self):
        # Berkshire files one row per sub-manager; they must merge
        rows = parse_info_table(_table(
            _info_row("ALLY", "02005N100", 100, 5),
            _info_row("ALLY", "02005N100", 50, 3)))
        agg = aggregate_holdings(rows)
        assert len(agg) == 1
        assert agg["02005N100"]["value"] == 150
        assert agg["02005N100"]["shares"] == 8

    def test_puts_kept_separate(self):
        rows = parse_info_table(_table(
            _info_row("NVDA", "67066G104", 100, 5),
            _info_row("NVDA", "67066G104", 40, 2, put_call="Put")))
        agg = aggregate_holdings(rows)
        assert len(agg) == 2
        assert agg["67066G104|PUT"]["put_call"] == "PUT"


class TestWeights:
    def test_pct(self):
        agg = aggregate_holdings(parse_info_table(_table(
            _info_row("A", "C1", 75_000_000, 1),
            _info_row("B", "C2", 25_000_000, 1))))
        total, holdings = portfolio_weights(agg)
        assert total == 100_000_000
        assert holdings[0]["pct"] == 75.0
        assert holdings[0]["name"] == "A"

    def test_thousands_heuristic(self):
        # some filers still report thousands; a 13F filer can't run < $50m
        agg = aggregate_holdings(parse_info_table(_table(
            _info_row("A", "C1", 3_000_000, 1))))   # $3m reported => thousands
        total, holdings = portfolio_weights(agg)
        assert total == 3_000_000_000
        assert holdings[0]["value"] == 3_000_000_000


def _hold(cusip, value, shares):
    return {"name": cusip, "cusip": cusip, "value": value,
            "shares": shares, "put_call": ""}


class TestDiff:
    def test_new_exit_add_trim(self):
        prev = {"C1": _hold("C1", 50, 100), "C2": _hold("C2", 30, 100),
                "C3": _hold("C3", 20, 100)}
        cur = {"C1": _hold("C1", 90, 140),   # +40% shares -> added
               "C3": _hold("C3", 8, 60),     # -40% shares -> trimmed
               "C4": _hold("C4", 40, 50)}    # new
        changes = diff_holdings(cur, prev, 138, 100)
        kinds = {c["cusip"]: c["type"] for c in changes}
        assert kinds == {"C4": "new", "C2": "exit", "C1": "added", "C3": "trimmed"}

    def test_small_positions_ignored(self):
        prev = {}
        cur = {"C1": _hold("C1", 1, 10), "C2": _hold("C2", 999, 10)}
        changes = diff_holdings(cur, prev, 1000, 0)
        assert [c["cusip"] for c in changes] == ["C2"]   # 0.1% new buy is noise


def _mgr(key, person, holdings, exclude=None):
    return {"key": key, "person": person, "exclude": exclude or [],
            "holdings": holdings}


def _h(ticker, pct, name=None, put_call=""):
    return {"name": name or ticker, "cusip": ticker, "ticker": ticker,
            "pct": pct, "value": 0, "shares": 0, "put_call": put_call}


class TestConsensus:
    def test_conviction_weighting(self):
        data = [_mgr("a", "A", [_h("AAPL", 22.0)]),
                _mgr("b", "B", [_h("AAPL", 3.0), _h("XOM", 1.0)])]
        scores = consensus_scores(data)
        assert scores[0]["ticker"] == "AAPL"
        assert scores[0]["points"] == 25.0
        assert len(scores[0]["held_by"]) == 2

    def test_weight_capped_at_25(self):
        data = [_mgr("a", "A", [_h("CVI", 40.0)])]
        assert consensus_scores(data)[0]["points"] == 25.0

    def test_share_classes_merge(self):
        data = [_mgr("a", "A", [_h("GOOG", 10.0, "ALPHABET INC"),
                                _h("GOOGL", 12.0, "ALPHABET INC")])]
        scores = consensus_scores(data)
        assert len(scores) == 1
        assert scores[0]["ticker"] == "GOOGL"
        assert scores[0]["held_by"][0]["pct"] == 22.0

    def test_skips_options_own_vehicle_unmapped(self):
        data = [_mgr("a", "A",
                     [_h("SPY", 10.0, put_call="PUT"),
                      _h("IEP", 30.0),
                      dict(_h("MYST", 5.0), ticker=None)],
                     exclude=["IEP"])]
        assert consensus_scores(data) == []

    def test_basket_qualification_and_cap(self):
        data = [_mgr("a", "A", [_h("AAPL", 30.0), _h("TINY", 1.0)]),
                _mgr("b", "B", [_h("AAPL", 30.0), _h("TINY", 1.5)])]
        basket = build_basket(consensus_scores(data))
        # AAPL qualifies (2 holders); TINY qualifies (2 holders) but is small
        tickers = [b["ticker"] for b in basket]
        assert "AAPL" in tickers and "TINY" in tickers
        weights = [b["weight"] for b in basket]
        assert abs(sum(weights) - 1.0) < 1e-6
        # single-name cap: AAPL points dominate but weight renormalises
        aapl = [b for b in basket if b["ticker"] == "AAPL"][0]
        assert aapl["weight"] <= 0.999

    def test_single_big_bet_qualifies(self):
        data = [_mgr("a", "A", [_h("CVI", 28.0)])]
        basket = build_basket(consensus_scores(data))
        assert basket and basket[0]["ticker"] == "CVI"


FORM4_BUY = """<ownershipDocument>
  <reportingOwner><reportingOwnerId>
    <rptOwnerName>LE PHONG</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship><isOfficer>1</isOfficer>
    <officerTitle>President &amp; CEO</officerTitle></reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable><nonDerivativeTransaction>
    <transactionDate><value>2026-06-22</value></transactionDate>
    <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
    <transactionAmounts>
      <transactionShares><value>11000</value></transactionShares>
      <transactionPricePerShare><value>90.80</value></transactionPricePerShare>
      <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
    </transactionAmounts>
  </nonDerivativeTransaction></nonDerivativeTable>
</ownershipDocument>"""


class TestForm4:
    def test_open_market_buy(self):
        buys = parse_form4(FORM4_BUY)
        assert len(buys) == 1
        b = buys[0]
        assert b["owner"] == "Le Phong"
        assert b["title"] == "President & CEO"
        assert b["value"] == 998800
        assert b["date"] == "2026-06-22"

    def test_sales_and_grants_ignored(self):
        for code in ("S", "A", "M", "F"):
            xml = FORM4_BUY.replace(
                "<transactionCode>P</transactionCode>",
                "<transactionCode>%s</transactionCode>" % code)
            assert parse_form4(xml) == []

    def test_small_buys_ignored(self):
        xml = FORM4_BUY.replace("<value>11000</value>", "<value>100</value>")
        assert parse_form4(xml) == []
        assert 100 * 90.80 < MIN_INSIDER_USD


class TestSummary:
    def _changes(self, buys, sells):
        return ([{"type": "new"}] * buys) + ([{"type": "exit"}] * sells)

    def test_adding(self):
        s = activity_summary(self._changes(9, 3), "flat")
        assert s["net_activity"] == "adding"

    def test_pulling_back(self):
        s = activity_summary(self._changes(3, 9), "building")
        assert s["net_activity"] == "pulling_back"
        assert s["brk_cash_dir"] == "building"

    def test_mixed(self):
        assert activity_summary(self._changes(5, 5), "flat")["net_activity"] == "mixed"


class TestRoster:
    def test_ciks_unique_and_plausible(self):
        ciks = [m["cik"] for m in MANAGERS]
        assert len(set(ciks)) == len(ciks)
        assert all(isinstance(c, int) and c > 0 for c in ciks)

    def test_insider_watch_shape(self):
        for t, meta in INSIDER_WATCH.items():
            assert meta["cik"] > 0 and meta["name"]
