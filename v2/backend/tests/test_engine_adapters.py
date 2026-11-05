from unittest.mock import patch
import pytest
from app.engine import execute
from app.contracts import JobInput, ArtifactEdit
from background_jobs import JobProgress

@pytest.mark.parametrize('kind',['forms','images','characters'])
def test_removed_jobs_rejected_before_ai(kind):
    with patch('app.text_pipeline.generate_text') as call:
        with pytest.raises(ValueError): execute(kind,{},JobProgress())
        call.assert_not_called()

@pytest.mark.parametrize('kind',['forms','images','characters'])
def test_removed_jobs_rejected_by_contract(kind):
    from uuid import uuid4
    with pytest.raises(ValueError):JobInput(kind=kind,revision=0,request_id=uuid4())

@pytest.mark.parametrize('field',['scene','character_bible'])
def test_visual_artifact_edits_disabled(field):
    with pytest.raises(ValueError):ArtifactEdit(field=field,revision=0,value='unused')
