import base64
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from analysis.jade_lizard_legacy import aggregate, import_legacy_jade_lizards, write_reports
from project_paths import PAPER_TRADES_CSV


HEADER = "Date,Entry Time,Symbol,Strategy,StrategyId,Short Call,Long Call,Short Put,Long Put,Credit Collected,Buying Power,Status,Exit P/L,Closed at Debit,Notes\n"
GOOD = "2026-06-02,15:00,SPX,JadeLizard_5DTE,JL5-1500,.SPXW260608C06500,.SPXW260608C06505,.SPXW260608P06350,.SPXW260608P06330,4.50,1550,CLOSED,1.25,3.25,target_expiry=2026-06-08;dte=5\n"
REAL_LEDGER = PAPER_TRADES_CSV
REAL_HEADER = "Date,Entry Time,Symbol,Strategy,StrategyId,Short Call,Long Call,Short Put,Long Put,Credit Collected,Buying Power,Profit Target,Stop Loss,Status,Exit Time,Exit P/L,Notes,IV Rank,Short Delta,SPX Spot\n"
REAL_NOTES_ROW = "2026-05-06,15:30:10,SPX,JadeLizard_5DTE,JL5,.SPXW260511C7395,.SPXW260511C7400,.SPXW260511P7255,.SPXW260511P7235,4.60,1540.00,1.15,,CLOSED,20:50:01,1.30,target_expiry=2026-05-11;dte=5;em=71.57 |   cLoSeD   At  DeBiT :  3.30,0.00,,7325.18\n"


class TestLegacyJadeLizardImport(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.addCleanup(self.temp.cleanup)

    def write(self, body: bytes | str, name="ledger.csv") -> Path:
        path = Path(self.temp.name) / name
        path.write_bytes(body if isinstance(body, bytes) else body.encode())
        return path

    def test_preserves_multiline_crlf_hash_and_ordinals(self):
        body = (HEADER + GOOD.replace("target_expiry=2026-06-08;dte=5", '"target_expiry=2026-06-08;dte=5;memo=line one\r\nline two"')).replace("\n", "\r\n")
        path = self.write(body)
        row = import_legacy_jade_lizards(path, "both")[0]
        raw_record = body.encode().split(b"\r\n", 1)[1]
        self.assertEqual((row.csv_record_ordinal_zero_based, row.data_row_ordinal_one_based), (1, 1))
        self.assertEqual(row.raw_record_sha256, hashlib.sha256(raw_record).hexdigest())
        self.assertEqual(row.exact_leg_replay, "verified_credit_minus_debit_equals_exit_pnl")
        self.assertEqual(row.decision_replay, "unavailable_no_frozen_chain_or_quote_snapshot")

    def test_notes_debit_is_canonical_and_column_contradiction_is_rejected(self):
        row = import_legacy_jade_lizards(self.write(REAL_HEADER + REAL_NOTES_ROW), "exact-leg")[0]
        self.assertEqual(row.exact_leg_replay, "verified_credit_minus_debit_equals_exit_pnl")
        self.assertNotIn("closed_at_debit_source_contradiction", row.anomaly_flags)

        contradicted = import_legacy_jade_lizards(self.write(HEADER + GOOD.replace("3.25,target", "2.25,target").replace("target_expiry=2026-06-08;dte=5", "target_expiry=2026-06-08;dte=5 | Closed at Debit: 3.25")), "exact-leg")[0]
        self.assertEqual(contradicted.exact_leg_replay, "rejected_conflicting_closed_at_debit_sources")
        self.assertIn("closed_at_debit_source_contradiction", contradicted.anomaly_flags)

    def test_real_ledger_closed_rows_are_notes_arithmetic_verified(self):
        rows = import_legacy_jade_lizards(REAL_LEDGER, "exact-leg")
        self.assertEqual(sum(row.exact_leg_replay == "verified_credit_minus_debit_equals_exit_pnl" for row in rows), 57)

    def test_open_and_expired_without_debit_are_honestly_unavailable(self):
        open_row = import_legacy_jade_lizards(self.write(HEADER + GOOD.replace("CLOSED,1.25,3.25,", "OPEN,,,")), "exact-leg")[0]
        expired_row = import_legacy_jade_lizards(self.write(HEADER + GOOD.replace("CLOSED,1.25,3.25,", "EXPIRED,0.00,")), "exact-leg")[0]
        self.assertEqual(open_row.exact_leg_replay, "unavailable_open_no_recorded_debit")
        self.assertEqual(expired_row.exact_leg_replay, "unavailable_expired_no_recorded_debit")

    def test_invalid_utf8_jade_evidence_is_losslessly_retained(self):
        path = self.write(HEADER.encode() + b"JadeLizard_5DTE,JL5,\xff\xfe\n")
        row = import_legacy_jade_lizards(path)[0]
        self.assertEqual(row.classification, "invalid")
        self.assertIn("invalid_utf8_record", row.anomaly_flags)
        self.assertEqual(base64.b64decode(row.original_fields["__raw_bytes_base64__"]), b"JadeLizard_5DTE,JL5,\xff\xfe\n")

    def test_malformed_jade_csv_record_is_retained_as_invalid(self):
        raw = b'JadeLizard_5DTE,JL5,"unterminated\n'
        row = import_legacy_jade_lizards(self.write(HEADER.encode() + raw))[0]
        self.assertEqual(row.classification, "invalid")
        self.assertIn("csv_parse_error", row.anomaly_flags)
        self.assertEqual(base64.b64decode(row.original_fields["__raw_bytes_base64__"]), raw)

    def test_osi_symbol_scale_and_point_unit_boundaries(self):
        osi = GOOD.replace(".SPXW260608C06500", "SPXW  260608C06500000").replace(".SPXW260608C06505", "SPXW  260608C06505000").replace(".SPXW260608P06350", "SPXW  260608P06350000").replace(".SPXW260608P06330", "SPXW  260608P06330000")
        row = import_legacy_jade_lizards(self.write(HEADER + osi), "exact-leg")[0]
        self.assertNotIn("unrecognised_leg_symbol", row.anomaly_flags)
        self.assertNotIn("exit_pnl_exceeds_entry_credit", row.anomaly_flags)
        self.assertNotIn("exit_pnl_below_structural_minimum", row.anomaly_flags)
        too_high = import_legacy_jade_lizards(self.write(HEADER + GOOD.replace(",1.25,3.25,", ",4.52,3.25,")), "exact-leg")[0]
        self.assertIn("exit_pnl_exceeds_entry_credit", too_high.anomaly_flags)
        self.assertIn("closed_at_debit_pnl_mismatch", too_high.anomaly_flags)
        too_low = import_legacy_jade_lizards(self.write(HEADER + GOOD.replace(",1.25,3.25,", ",-15.52,3.25,")), "exact-leg")[0]
        self.assertIn("exit_pnl_below_structural_minimum", too_low.anomaly_flags)

    def test_open_invalid_duplicate_and_spx_anomalies_are_retained(self):
        bad = "bad,15:00,NDX,Jade Lizard 7 DTE,JL7-1500,,,P,L,0,0,OPEN,1,,target_expiry=2026-06-01\n"
        rows = import_legacy_jade_lizards(self.write(HEADER + GOOD + GOOD + bad))
        self.assertEqual(len(rows), 3)
        self.assertTrue(all("duplicate_identity" in row.anomaly_flags for row in rows[:2]))
        self.assertEqual(rows[2].classification, "invalid")
        self.assertIn("underlying_symbol_anomaly", rows[2].anomaly_flags)
        self.assertEqual(aggregate(rows)["classification"], {"completed": 2, "invalid": 1})

    def test_strategy_id_is_strict_and_contract_duplicates_are_canonical(self):
        unrelated = GOOD.replace("JadeLizard_5DTE,JL5-1500", "Other Strategy,JL50-1500")
        unrelated += GOOD.replace("JadeLizard_5DTE,JL5-1500", "Other Strategy,JLIST")
        self.assertEqual(import_legacy_jade_lizards(self.write(HEADER + unrelated)), [])

        occ = GOOD.replace("JadeLizard_5DTE,JL5-1500", "jade lizard 5 dte,jl5-1500")
        occ = occ.replace("15:00,", "15:00:00,", 1)
        occ = occ.replace(".SPXW260608C06500", "SPXW  260608C06500000")
        occ = occ.replace(".SPXW260608C06505", "SPXW  260608C06505000")
        occ = occ.replace(".SPXW260608P06350", "SPXW  260608P06350000")
        occ = occ.replace(".SPXW260608P06330", "SPXW  260608P06330000")
        rows = import_legacy_jade_lizards(self.write(HEADER + GOOD + occ))
        self.assertTrue(all("duplicate_identity" in row.anomaly_flags for row in rows))

        distinct = occ.replace("C06505000", "C06510000")
        rows = import_legacy_jade_lizards(self.write(HEADER + GOOD + distinct))
        self.assertTrue(all("duplicate_identity" not in row.anomaly_flags for row in rows))

    def test_report_publication_is_new_atomic_and_symlink_safe(self):
        source = self.write(HEADER + GOOD)
        rows = import_legacy_jade_lizards(source)
        target = Path(self.temp.name) / "new-report"
        reports = write_reports(rows, target, source)
        self.assertTrue(all(item.is_file() for item in reports))
        self.assertEqual(json.loads(reports[0].read_text())["aggregate"]["selected_rows"], 1)
        second = Path(self.temp.name) / "second-report"
        reports_two = write_reports(rows, second, source)
        self.assertEqual(reports[0].read_bytes(), reports_two[0].read_bytes())
        self.assertEqual(reports[1].read_bytes(), reports_two[1].read_bytes())
        self.assertEqual(reports[2].read_bytes(), reports_two[2].read_bytes())
        with self.assertRaises(ValueError): write_reports(rows, target, source)
        with self.assertRaises(ValueError): write_reports(rows, source, source)
        link = Path(self.temp.name) / "link-report"
        try:
            os.symlink(target, link)
        except OSError as exc:
            self.skipTest(f"symlinks unavailable: {exc}")
        with self.assertRaises(ValueError): write_reports(rows, link, source)


if __name__ == "__main__":
    unittest.main()
