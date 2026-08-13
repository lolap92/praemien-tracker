"""Tests for configuration translations."""

from __future__ import annotations

from pathlib import Path
import yaml


def test_translations_are_valid():
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    for lang in ["de", "en"]:
        translation_path = repo_root / "praemien_tracker" / "translations" / f"{lang}.yaml"
        assert translation_path.exists()

        content = yaml.safe_load(translation_path.read_text(encoding="utf-8"))
        assert "configuration" in content
        config = content["configuration"]

        all_keys = [
            "demo_modus",
            "anthropic_api_key",
            "anthropic_model",
            "mindestpraemie",
            "mydealz_gruppe",
            "spartanien_url",
            "dealdoktor_feed_url",
            "benachrichtigungsgeraete",
            "benachrichtigungen_aktiv",
            "taeglicher_lauf_aktiv",
            "kuendigung_hinweise_batch_aktiv"
        ]

        # Check existing and new keys are present and correctly formatted
        for key in all_keys:
            assert key in config, f"Key {key} not found in {lang}.yaml"
            assert "name" in config[key]
            assert "description" in config[key]
            assert config[key]["name"].strip() != ""
            assert config[key]["description"].strip() != ""
