import json
import os
import signal
import subprocess
import sys


def run_cli(home, *args, cwd=None):
    return subprocess.run(
        [sys.executable, "-m", "codex_view", "--codex-home", str(home), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_list_filters_and_codex_home_environment(corpus):
    home, project, other, create = corpus
    create("one")
    create("two", cwd=other)
    result = run_cli(home, "--list", "--json", cwd=project)
    assert result.returncode == 0
    assert [item["id"] for item in json.loads(result.stdout)] == ["one"]
    result = run_cli(home, "--list", "--all", "--json", cwd=project)
    assert len(json.loads(result.stdout)) == 2
    result = run_cli(home, "-C", str(other), "--list", "--json", cwd=project)
    assert json.loads(result.stdout)[0]["id"] == "two"
    result = subprocess.run(
        [sys.executable, "-m", "codex_view", "--list", "--json"],
        cwd=project,
        env={**os.environ, "CODEX_HOME": str(home)},
        capture_output=True,
        text=True,
    )
    assert json.loads(result.stdout)[0]["id"] == "one"


def test_noninteractive_picker_errors_instead_of_hanging(corpus):
    home, project, _, create = corpus
    create()
    result = run_cli(home, cwd=project)
    assert result.returncode == 2
    assert "use --last or SESSION_ID" in result.stderr
    assert run_cli(home, "--json", cwd=project).returncode == 2
    assert run_cli(home, "--port", "99999", cwd=project).returncode == 2


def test_specific_id_bypasses_directory_filter_and_prefix_ambiguity(corpus):
    home, project, other, create = corpus
    create("abc-one", cwd=other)
    create("abc-two", cwd=other)
    result = run_cli(home, "abc-one", "--list", "--json", cwd=project)
    assert json.loads(result.stdout)[0]["id"] == "abc-one"
    assert run_cli(home, "abc", "--list", cwd=project).returncode == 2


def test_last_launch_and_clean_shutdown(corpus):
    home, project, _, create = corpus
    create()
    process = subprocess.Popen(
        [
            sys.executable,
            "-u",
            "-m",
            "codex_view",
            "--codex-home",
            str(home),
            "--last",
            "--host",
            "0.0.0.0",
            "--port",
            "0",
        ],
        cwd=project,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        lines = []
        for line in process.stdout:
            lines.append(line)
            if "Ctrl+C" in line:
                break
        assert any("Listening: 0.0.0.0:" in line for line in lines)
        assert any("Available addresses:" in line for line in lines)
        assert any("http://127.0.0.1:" in line for line in lines)
        assert any("Ctrl+C" in line for line in lines)
        process.send_signal(signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=5)
        assert process.returncode == 0, stderr
        assert "Viewer stopped" in stdout
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
