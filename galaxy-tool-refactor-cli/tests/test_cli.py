import pytest
from click.testing import CliRunner

@pytest.fixture
def runner():
    return CliRunner()

def test_version(runner):
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "version" in result.output