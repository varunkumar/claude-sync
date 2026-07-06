import subprocess
from pathlib import Path

INSTALL_SH = Path(__file__).resolve().parent.parent / "install.sh"


def test_install_script_is_valid_posix_shell():
    result = subprocess.run(["sh", "-n", str(INSTALL_SH)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def _crontab_stub(fake_bin):
    # install.sh shells out to the real `crontab` binary, which is keyed by OS
    # user account, not $HOME — it is NOT sandboxed by overriding HOME. Put a
    # no-op stub ahead of it on PATH so this test can never touch the real
    # system crontab.
    crontab_stub = fake_bin / "crontab"
    crontab_stub.write_text(
        "#!/bin/sh\n"
        "case \"$1\" in\n"
        "  -l) exit 1 ;;\n"                 # no existing crontab, matches real first-run behavior
        "  -) cat > /dev/null; exit 0 ;;\n"  # accept and discard the write install.sh pipes in
        "  *) exit 0 ;;\n"
        "esac\n"
    )
    crontab_stub.chmod(0o755)


def _run_install(install_copy, code_repo, remote, fake_home, fake_bin):
    env = {
        "HOME": str(fake_home),
        "PATH": f"{fake_bin}:/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }
    return subprocess.run(
        ["sh", str(install_copy), str(remote)],
        cwd=code_repo, check=True, env=env, capture_output=True, text=True,
    )


def _setup_install(tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True, capture_output=True)

    code_repo = tmp_path / "code_repo"
    code_repo.mkdir()
    install_copy = code_repo / "install.sh"
    install_copy.write_text(INSTALL_SH.read_text())
    install_copy.chmod(0o755)
    (code_repo / "memmerge.py").write_text("# stub\n")

    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    fake_bin = tmp_path / "fake_bin"
    fake_bin.mkdir()
    _crontab_stub(fake_bin)

    return install_copy, code_repo, remote, fake_home, fake_bin


def test_install_script_clones_bootstraps_and_configures_merge_driver(tmp_path):
    install_copy, code_repo, remote, fake_home, fake_bin = _setup_install(tmp_path)

    _run_install(install_copy, code_repo, remote, fake_home, fake_bin)

    data_repo_dir = fake_home / ".claudesync" / "repo"
    assert data_repo_dir.is_dir()

    repo_root_config = fake_home / ".claudesync" / "repo_root"
    assert repo_root_config.read_text().strip() == str(data_repo_dir)

    result = subprocess.run(
        ["git", "config", "merge.memmerge.driver"], cwd=data_repo_dir, capture_output=True, text=True,
    )
    assert "memmerge.py" in result.stdout

    assert (data_repo_dir / ".gitattributes").read_text() == "projects/*/memory/MEMORY.md merge=memmerge\n"

    local_log = subprocess.run(
        ["git", "log", "--oneline"], cwd=data_repo_dir, capture_output=True, text=True,
    ).stdout
    assert local_log.strip() != ""

    remote_log = subprocess.run(
        ["git", "log", "--oneline", "main"], cwd=remote, capture_output=True, text=True,
    ).stdout
    assert remote_log.strip() != "", "initial bootstrap commit must be pushed so a plain `git push` in sync.py later succeeds"


def test_install_script_is_idempotent_on_second_run(tmp_path):
    install_copy, code_repo, remote, fake_home, fake_bin = _setup_install(tmp_path)

    _run_install(install_copy, code_repo, remote, fake_home, fake_bin)
    data_repo_dir = fake_home / ".claudesync" / "repo"
    first_log = subprocess.run(
        ["git", "log", "--oneline"], cwd=data_repo_dir, capture_output=True, text=True,
    ).stdout

    _run_install(install_copy, code_repo, remote, fake_home, fake_bin)
    second_log = subprocess.run(
        ["git", "log", "--oneline"], cwd=data_repo_dir, capture_output=True, text=True,
    ).stdout

    assert first_log == second_log, "second run must not re-clone or add a duplicate bootstrap commit"
