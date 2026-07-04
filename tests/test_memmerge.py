import memmerge


def test_union_merge_combines_disjoint_entries():
    local = "- entry X\n"
    remote = "- entry Y\n"

    result = memmerge.union_merge(local, remote)

    assert "- entry X" in result
    assert "- entry Y" in result


def test_union_merge_dedups_identical_lines():
    local = "# Memory Index\n- entry X\n"
    remote = "# Memory Index\n- entry X\n- entry Y\n"

    result = memmerge.union_merge(local, remote)

    assert result.count("- entry X") == 1
    assert result.count("# Memory Index") == 1
    assert "- entry Y" in result


def test_union_merge_preserves_local_order_then_appends_remote_only_lines():
    local = "- A\n- B\n"
    remote = "- B\n- C\n"

    result = memmerge.union_merge(local, remote)

    lines = [line for line in result.splitlines() if line]
    assert lines == ["- A", "- B", "- C"]


def test_main_writes_merged_content_into_local_file(tmp_path):
    base = tmp_path / "base.md"
    local = tmp_path / "local.md"
    remote = tmp_path / "remote.md"
    base.write_text("- A\n")
    local.write_text("- A\n- B\n")
    remote.write_text("- A\n- C\n")

    exit_code = memmerge.main(
        ["memmerge.py", str(base), str(local), str(remote), "MEMORY.md"]
    )

    assert exit_code == 0
    merged = local.read_text()
    assert "- B" in merged
    assert "- C" in merged


def test_main_returns_error_code_with_wrong_arg_count():
    assert memmerge.main(["memmerge.py", "only-one-arg"]) == 2
