from pathlib import Path

import yaml

from labelme.config import get_user_config_file


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
