import json

import pytest

from myquant.registry import append_trial, read_and_verify


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
