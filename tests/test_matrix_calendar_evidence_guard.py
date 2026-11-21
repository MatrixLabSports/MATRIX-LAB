import unittest
from tools.matrix_calendar_evidence_guard import validate_sofascore_tennis_calendar_link, normalize_calendar_links

URL = "https://www.sofascore.com/es/tennis/match/a-b/abc#id:17447688"

class CalendarGuardTests(unittest.TestCase):
    def test_valid_discovery_never_signal(self):
        row = validate_sofascore_tennis_calendar_link({"name":"31/10/26 4:10 Player A Player B","url":URL})
        self.assertEqual(row["status"], "DISCOVERY_ONLY")
        self.assertFalse(row["eligible_for_signal"])
        self.assertIsNone(row["bookmaker_quote"])
        self.assertIsNone(row["timezone"])
        self.assertIsNone(row["surface"])

    def test_cancelled_blocked(self):
        row = validate_sofascore_tennis_calendar_link({"name":"31/10/26 Cancelado A B","url":URL})
        self.assertEqual(row["status"], "BLOCKED")

    def test_wrong_date(self):
        self.assertIsNone(validate_sofascore_tennis_calendar_link({"name":"30/10/26 4:10 A B","url":URL}))

    def test_fake_domain(self):
        self.assertIsNone(validate_sofascore_tennis_calendar_link({"name":"31/10/26 4:10 A B","url":URL.replace("www.sofascore.com","www.sofascore.com.evil.test")}))

    def test_missing_id(self):
        self.assertIsNone(validate_sofascore_tennis_calendar_link({"name":"31/10/26 4:10 A B","url":URL.split("#")[0]}))

    def test_deduplication(self):
        result = normalize_calendar_links([{"name":"31/10/26 4:10 A B","url":URL}]*2)
        self.assertEqual(result["accepted"],1)
        self.assertEqual(result["signals_authorized"],0)

    def test_reject_raw_text(self):
        self.assertIsNone(validate_sofascore_tennis_calendar_link({"name":"31/10/26 4:10 A B 1 1.80","url":""}))

if __name__ == "__main__":
    unittest.main()
