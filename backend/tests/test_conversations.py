"""Every scripted conversation must pass with the offline demo provider.

These are behaviour tests of the state machine and business rules, not a model evaluation: the demo
provider's keyword rules were written alongside these scripts.
"""

import pytest

from evals.conversations import SCRIPTS
from evals.runner import run_script


@pytest.mark.parametrize("script", SCRIPTS, ids=[s.id for s in SCRIPTS])
def test_script(db, script) -> None:
    r = run_script(db, script)
    assert r.passed, "\n".join(r.problems + [f"{who}: {text}" for who, text in r.transcript])
