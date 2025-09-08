import pathlib
import re
import subprocess

languages = ["zh_CN"]


def main():
    labelme_path = pathlib.Path(__file__).parent.parent / "labelme"
    labelme_translate_path = labelme_path / "translate"
    assert labelme_translate_path.is_dir(), "translate path not found"

    labelme_files = [*labelme_path.rglob("*.py")]
    for lang in languages:
        ts_path = labelme_translate_path / f"{lang}.ts"
        qm_path = labelme_translate_path / f"{lang}.qm"
        subprocess.check_call(
            [
                "pylupdate5",
                *labelme_files,
                "-ts",
                str(ts_path),
            ]
        )
        assert ts_path.exists()
        # Zero out line numbers to reduce unnecessary diffs in .ts file
        ts_content = ts_path.read_text()
        new_ts_content = re.sub(r'line="\d+"', 'line="0"', ts_content)
        assert ts_content.strip() != new_ts_content.strip()
        ts_path.write_text(new_ts_content)
        subprocess.check_call(["lrelease", str(ts_path), "-qm", str(qm_path)])
        assert qm_path.exists()


if __name__ == "__main__":
    main()
