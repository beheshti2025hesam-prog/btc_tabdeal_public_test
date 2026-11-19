from __future__ import annotations

import json
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from web.dashboard import Handler


class DocumentationRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_four_locales_return_same_complete_page_set_and_read_only_contract(self):
        expected_ids = None
        for language in ("fa", "en", "de", "fr"):
            with urlopen(f"{self.base}/api/documentation?lang={language}") as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers.get_content_type(), "application/json")
                self.assertEqual(response.headers.get("Cache-Control"), "no-store")
                payload = json.loads(response.read())
            self.assertEqual(payload["schema"], "hes.documentation_response.v1")
            self.assertEqual(payload["language"], language)
            self.assertEqual(payload["safety"], {
                "read_only": True,
                "execution_enabled": False,
                "orders_placed": False,
                "policy_mutation": False,
            })
            ids = [page["id"] for page in payload["pages"]]
            self.assertEqual(len(ids), 13)
            self.assertIn("troubleshooting", ids)
            self.assertIn("changelog", ids)
            self.assertEqual(len(set(ids)), len(ids))
            expected_ids = ids if expected_ids is None else expected_ids
            self.assertEqual(ids, expected_ids)
            structure = [(page["id"], len(page["sections"]), tuple(len(section["bullets"]) for section in page["sections"])) for page in payload["pages"]]
            if language == "fa":
                self._expected_structure = structure
            else:
                self.assertEqual(structure, self._expected_structure)
            self.assertTrue(all(page["title"] and page["summary"] and page["sections"] for page in payload["pages"]))
            self.assertTrue(all(section["heading"] and section["body"] and section["bullets"] for page in payload["pages"] for section in page["sections"]))
            self.assertTrue(all(page["title"] != page["id"] for page in payload["pages"]))
            self.assertFalse(any("TODO" in page["summary"] or "TBD" in page["summary"] for page in payload["pages"]))

    def test_unsupported_locale_is_rejected(self):
        with self.assertRaises(HTTPError) as raised:
            urlopen(f"{self.base}/api/documentation?lang=es")
        self.assertEqual(raised.exception.code, 400)

    def test_dashboard_exposes_documentation_navigation_and_assets(self):
        with urlopen(self.base + "/") as response:
            html = response.read().decode("utf-8")
            self.assertIn('href="#documentationPanel"', html)
            self.assertIn('id="documentationPanel"', html)
            self.assertIn('src="/static/documentation.js"', html)
            self.assertIn('href="/static/documentation.css"', html)
        with urlopen(self.base + "/static/documentation.js") as response:
            self.assertEqual(response.headers.get_content_type(), "text/javascript")
            script = response.read().decode("utf-8")
            self.assertIn("/api/documentation?lang=", script)
            self.assertIn("textContent", script)
            self.assertNotIn("innerHTML", script)
        with urlopen(self.base + "/static/documentation.css") as response:
            self.assertEqual(response.headers.get_content_type(), "text/css")
            self.assertIn("[dir=rtl]", response.read().decode("utf-8"))

    def test_editorial_metadata_and_source_register_are_complete(self):
        with urlopen(f"{self.base}/api/documentation?lang=fa") as response:
            payload = json.loads(response.read())
        review = payload["editorial_review"]
        self.assertEqual(set(review["languages"]), {"fa", "en", "de", "fr"})
        self.assertEqual(review["native_speaker_review"], "pending")
        self.assertIn("not primary exchange evidence", payload["source_register"][-1])
        self.assertTrue(payload["ui"]["editorial_note"])
        for language in ("en", "de", "fr"):
            with urlopen(f"{self.base}/api/documentation?lang={language}") as response:
                localized = json.loads(response.read())
            self.assertTrue(localized["ui"]["editorial_note"])

    def test_documentation_api_is_get_only_and_source_register_resolves(self):
        request = Request(self.base + "/api/documentation?lang=en", data=b"{}", method="POST")
        with self.assertRaises(HTTPError) as raised:
            urlopen(request)
        self.assertEqual(raised.exception.code, 405)

        root = Path(__file__).resolve().parents[1]
        catalog = json.loads((root / "docs/documentation/catalog.v1.json").read_text(encoding="utf-8"))
        for source in catalog["source_register"]:
            relative_path = source.split(" (", 1)[0]
            self.assertTrue((root / relative_path).is_file(), relative_path)

    def test_user_facing_titles_are_localized(self):
        payloads = {}
        for language in ("en", "fa", "de", "fr"):
            with urlopen(f"{self.base}/api/documentation?lang={language}") as response:
                payloads[language] = json.loads(response.read())
        english = {page["id"]: page["title"] for page in payloads["en"]["pages"]}
        for language in ("fa", "de", "fr"):
            localized = {page["id"]: page["title"] for page in payloads[language]["pages"]}
            self.assertTrue(all(localized[key] != english[key] for key in english), language)

    def test_all_locale_copy_is_complete_and_not_left_in_english(self):
        payloads = {}
        for language in ("en", "fa", "de", "fr"):
            with urlopen(f"{self.base}/api/documentation?lang={language}") as response:
                payloads[language] = json.loads(response.read())

        english = {page["id"]: page for page in payloads["en"]["pages"]}
        ui_keys = set(payloads["en"]["ui"])
        for language in ("fa", "de", "fr"):
            localized = {page["id"]: page for page in payloads[language]["pages"]}
            self.assertEqual(set(localized), set(english))
            self.assertEqual(len(localized["dna"]["sections"]), 4)
            self.assertEqual(len(localized["roadmap"]["sections"]), 3)
            self.assertEqual(len(localized["strategy"]["sections"]), 4)
            expected_heading = {"fa": "ارزیابی کیفیت تصمیم NO_TRADE", "de": "Bewertung der NO_TRADE-Entscheidungsqualität", "fr": "Évaluation de la qualité des décisions NO_TRADE"}[language]
            self.assertEqual(localized["strategy"]["sections"][-1]["heading"], expected_heading)
            self.assertEqual(set(payloads[language]["ui"]), ui_keys)
            self.assertTrue(all(value.strip() for value in payloads[language]["ui"].values()))
            for page_id, page in localized.items():
                reference = english[page_id]
                self.assertNotEqual(page["title"], reference["title"], (language, page_id, "title"))
                self.assertNotEqual(page["summary"], reference["summary"], (language, page_id, "summary"))
                self.assertNotEqual(page["category"], reference["category"], (language, page_id, "category"))
                self.assertEqual(len(page["sections"]), len(reference["sections"]))
                for index, section in enumerate(page["sections"]):
                    source = reference["sections"][index]
                    for field in ("heading", "body"):
                        self.assertTrue(section[field].strip(), (language, page_id, index, field))
                        self.assertNotEqual(section[field], source[field], (language, page_id, index, field))
                    self.assertEqual(len(section["bullets"]), len(source["bullets"]))
                    for bullet_index, bullet in enumerate(section["bullets"]):
                        self.assertTrue(bullet.strip(), (language, page_id, index, bullet_index))
                        self.assertNotEqual(bullet, source["bullets"][bullet_index], (language, page_id, index, bullet_index))
                        self.assertEqual(bullet, bullet.strip())
                        self.assertNotIn("  ", bullet)

if __name__ == "__main__":
    unittest.main()
