from pathlib import Path

import pytest
import yaml

from labelme.config import get_user_config_file
from labelme.config import load_config


def test_get_user_config_file_creates_sparse(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    config_file = get_user_config_file()
    content = Path(config_file).read_text()
    assert content.startswith("# Labelme config file")
    parsed = yaml.safe_load(content)
    assert parsed is None


def test_get_user_config_file_does_not_overwrite(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    config_path = tmp_path / ".labelmerc"
    config_path.write_text("auto_save: true\n")
    config_file = get_user_config_file()
    content = Path(config_file).read_text()
    assert content == "auto_save: true\n"


def test_get_user_config_file_skip_creation(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    config_file = get_user_config_file(create_if_missing=False)
    assert not Path(config_file).exists()


@pytest.mark.parametrize("old_value", [True, False])
def test_migrate_store_data_to_with_image_data(tmp_path, old_value):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(f"store_data: {str(old_value).lower()}\n")
    config = load_config(config_file=config_file, config_overrides={})
    assert config["with_image_data"] is old_value
    assert "store_data" not in config
