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

        # Check existing and new keys are present and correctly formatted
        for key in ["benachrichtigungsgeraete", "benachrichtigungen_aktiv", "taeglicher_lauf_aktiv", "kuendigung_hinweise_batch_aktiv"]:
            assert key in config, f"Key {key} not found in {lang}.yaml"
            assert "name" in config[key]
            assert "description" in config[key]
            assert config[key]["name"].strip() != ""
            assert config[key]["description"].strip() != ""
