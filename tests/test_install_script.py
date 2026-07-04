import subprocess
from pathlib import Path

INSTALL_SH = Path(__file__).resolve().parent.parent / "install.sh"


def test_install_script_is_valid_posix_shell():
    result = subprocess.run(["sh", "-n", str(INSTALL_SH)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_install_script_configures_merge_driver(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    install_copy = repo / "install.sh"
    install_copy.write_text(INSTALL_SH.read_text())
    install_copy.chmod(0o755)
    memmerge_stub = repo / "memmerge.py"
    memmerge_stub.write_text("# stub\n")

    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    env = {"HOME": str(fake_home), "PATH": "/usr/bin:/bin"}

    subprocess.run(["sh", str(install_copy)], cwd=repo, check=True, env=env, capture_output=True, text=True)

    result = subprocess.run(
        ["git", "config", "merge.memmerge.driver"], cwd=repo, capture_output=True, text=True
    )
    assert "memmerge.py" in result.stdout
