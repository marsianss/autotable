import os
import pytest
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / 'tools' / 'quick_javoli_test.py'

@pytest.mark.skipif(os.getenv('RUN_UNAS_INTEGRATION', 'false').lower() != 'true', reason='Integration test disabled by default')
def test_quick_javoli_export_runs():
    # Run the quick test script programmatically
    import runpy
    res = runpy.run_path(str(SCRIPT), run_name='__main__')
    # After running, ensure output file was created and has rows
    out = Path(__file__).parents[1] / 'data' / 'test_javoli_100.csv'
    assert out.exists(), 'Output CSV not created'
    # Basic sanity: file size > 100 bytes
    assert out.stat().st_size > 100, 'Output CSV looks empty'
