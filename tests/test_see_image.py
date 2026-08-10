import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("see_image", ROOT / "scripts" / "see_image.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class SeeImageTests(unittest.TestCase):
    def test_chat_endpoint(self):
        self.assertEqual(
            MODULE.chat_endpoint("https://example.test/v1"),
            "https://example.test/v1/chat/completions",
        )
        self.assertEqual(
            MODULE.chat_endpoint("https://example.test/v1/chat/completions"),
            "https://example.test/v1/chat/completions",
        )

    def test_parse_args_modes(self):
        image, prompt, dry_run, tier, provider = MODULE.parse_args(
            ["shot.png", "--mode", "describe", "--tier", "high", "--provider", "2"]
        )
        self.assertEqual(image, "shot.png")
        self.assertIn("结构化描述", prompt)
        self.assertFalse(dry_run)
        self.assertEqual(tier, "high")
        self.assertEqual(provider, 2)

    def test_build_payload_contains_image(self):
        payload = MODULE.build_payload(
            {"model": "vision", "max_tokens": 100}, "read it", "data:image/png;base64,AA=="
        )
        self.assertEqual(payload["model"], "vision")
        content = payload["messages"][0]["content"]
        self.assertEqual(content[0]["text"], "read it")
        self.assertEqual(content[1]["image_url"]["url"], "data:image/png;base64,AA==")

    def test_local_file_missing(self):
        with self.assertRaises(ValueError):
            MODULE.to_image_url("/path/that/does/not/exist.png", False)

    def test_parse_env_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.env"
            path.write_text('# comment\nA=one\nB="two"\n', encoding="utf-8")
            self.assertEqual(MODULE.parse_env_file(str(path)), {"A": "one", "B": "two"})


if __name__ == "__main__":
    unittest.main()
