import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from translate.factory import TranslationManager  # noqa: E402

class TestTranslationChain(unittest.TestCase):
    def setUp(self):
        # Force limited provider order for deterministic test
        os.environ["TRANSLATE_ENABLED"] = "true"
        os.environ["TRANSLATE_PROVIDER_ORDER"] = "glossary,dictionary"
        # Ensure glossary exists
        glossary_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'glossary.json'))
        if not os.path.exists(glossary_path):
            with open(glossary_path, 'w', encoding='utf-8') as f:
                f.write('{"egér": "muis"}')
        self.manager = TranslationManager(cache_path="python-sync/data/cache/test_translations.json")

    def test_glossary_exact_match(self):
        result = self.manager.translate("egér")
        self.assertEqual(result, "muis")

    def test_dictionary_fallback(self):
        result = self.manager.translate("billentyűzet")
        self.assertEqual(result, "toetsenbord")

    def test_no_change_returns_original(self):
        text = "unmapped term"
        result = self.manager.translate(text)
        self.assertEqual(result, text)

if __name__ == "__main__":
    unittest.main()
