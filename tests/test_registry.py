import json

import pytest

from myquant.registry import GENESIS_HASH, append_trial, read_and_verify, write_anchor


def test_ledger_appends_and_verifies(tmp_path):
    path = tmp_path / "trials.jsonl"
    append_trial(path, trial_id="T1", hypothesis_id="H0001", status="failed",
                 result={"sharpe": -0.2})
    append_trial(path, trial_id="T2", hypothesis_id="H0001", status="failed",
                 result={"reason": "no out-of-sample effect"})
    records = read_and_verify(path)
    assert len(records) == 2
    assert records[1]["previous_hash"] == records[0]["record_hash"]


def test_ledger_detects_tampering(tmp_path):
    path = tmp_path / "trials.jsonl"
    append_trial(path, trial_id="T1", hypothesis_id="H0001", status="failed",
                 result={"sharpe": -0.2})
    record = json.loads(path.read_text().strip())
    record["result"]["sharpe"] = 9.9
    path.write_text(json.dumps(record) + "\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        read_and_verify(path)


def test_ledger_detects_broken_previous_hash(tmp_path):
    path = tmp_path / "trials.jsonl"
    append_trial(path, trial_id="T1", hypothesis_id="H0001", status="failed",
                 result={"sharpe": -0.2})
    append_trial(path, trial_id="T2", hypothesis_id="H0001", status="failed",
                 result={"sharpe": -0.1})
    lines = path.read_text().splitlines()
    second = json.loads(lines[1])
    second["previous_hash"] = "f" * 64
    path.write_text(lines[0] + "\n" + json.dumps(second) + "\n")
    with pytest.raises(ValueError, match="broken hash chain"):
        read_and_verify(path)


def test_ledger_read_of_missing_file_is_empty(tmp_path):
    assert read_and_verify(tmp_path / "does-not-exist.jsonl") == []


def test_ledger_truncation_passes_verification_without_anchor(tmp_path):
    # Documented limitation: a hash chain detects tampering with records
    # that are still present, not deletion of trailing records. Removing
    # the failed trial below leaves a shorter chain that still verifies,
    # which is exactly why anchors exist (see the next test).
    path = tmp_path / "trials.jsonl"
    append_trial(path, trial_id="T1", hypothesis_id="H0001", status="completed",
                 result={"sharpe": 0.5})
    append_trial(path, trial_id="T2", hypothesis_id="H0001", status="failed",
                 result={"reason": "no out-of-sample effect"})
    lines = path.read_text().splitlines()
    path.write_text(lines[0] + "\n")

    records = read_and_verify(path)
    assert len(records) == 1
    assert records[0]["trial_id"] == "T1"


def test_anchor_round_trip_and_default_path(tmp_path):
    path = tmp_path / "trials.jsonl"
    append_trial(path, trial_id="T1", hypothesis_id="H0001", status="failed",
                 result={"sharpe": -0.2})
    second_hash = append_trial(path, trial_id="T2", hypothesis_id="H0001",
                               status="failed", result={"sharpe": -0.1})

    anchor = write_anchor(path)
    assert anchor["record_count"] == 2
    assert anchor["latest_record_hash"] == second_hash
    assert anchor["ledger_file"] == "trials.jsonl"
    assert (tmp_path / "trials.jsonl.anchor").exists()

    records = read_and_verify(path, anchor_path=tmp_path / "trials.jsonl.anchor")
    assert len(records) == 2


def test_anchor_detects_truncation(tmp_path):
    path = tmp_path / "trials.jsonl"
    anchor_path = tmp_path / "anchor.json"
    append_trial(path, trial_id="T1", hypothesis_id="H0001", status="completed",
                 result={"sharpe": 0.5})
    append_trial(path, trial_id="T2", hypothesis_id="H0001", status="failed",
                 result={"reason": "no out-of-sample effect"})
    write_anchor(path, anchor_path)

    lines = path.read_text().splitlines()
    path.write_text(lines[0] + "\n")
    with pytest.raises(ValueError, match="does not match its anchor"):
        read_and_verify(path, anchor_path=anchor_path)


def test_anchor_detects_full_ledger_deletion(tmp_path):
    path = tmp_path / "trials.jsonl"
    anchor_path = tmp_path / "anchor.json"
    append_trial(path, trial_id="T1", hypothesis_id="H0001", status="failed",
                 result={"sharpe": -0.2})
    write_anchor(path, anchor_path)

    path.unlink()
    with pytest.raises(ValueError, match="does not match its anchor"):
        read_and_verify(path, anchor_path=anchor_path)


def test_anchor_of_empty_ledger_uses_genesis_hash(tmp_path):
    path = tmp_path / "trials.jsonl"
    anchor = write_anchor(path, tmp_path / "anchor.json")
    assert anchor["record_count"] == 0
    assert anchor["latest_record_hash"] == GENESIS_HASH
    assert read_and_verify(path, anchor_path=tmp_path / "anchor.json") == []


def test_anchor_verification_fails_closed_on_missing_or_malformed_anchor(tmp_path):
    path = tmp_path / "trials.jsonl"
    append_trial(path, trial_id="T1", hypothesis_id="H0001", status="failed",
                 result={"sharpe": -0.2})

    with pytest.raises(FileNotFoundError, match="anchor file not found"):
        read_and_verify(path, anchor_path=tmp_path / "missing.json")

    bad_anchor = tmp_path / "bad.json"
    bad_anchor.write_text("not json")
    with pytest.raises(ValueError, match="not valid JSON"):
        read_and_verify(path, anchor_path=bad_anchor)

    bad_anchor.write_text(json.dumps({"schema_version": 1, "record_count": -1,
                                      "latest_record_hash": "x" * 64}))
    with pytest.raises(ValueError, match="invalid record data"):
        read_and_verify(path, anchor_path=bad_anchor)
