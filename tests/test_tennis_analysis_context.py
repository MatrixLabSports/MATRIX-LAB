from uuid import UUID
from dataclasses import FrozenInstanceError
import pytest

from app.sports.tennis.analysis_context import TennisAnalysisContext


def test_tennis_analysis_context_can_be_created():
    context = TennisAnalysisContext.create(
        engine_version="0.1.0",
        policy_version="0.1.0",
    )

    assert isinstance(UUID(context.analysis_id), UUID)
    assert context.engine_version == "0.1.0"
    assert context.policy_version == "0.1.0"

def test_tennis_analysis_context_created_at_is_utc():
    context = TennisAnalysisContext.create(
        engine_version="0.1.0",
        policy_version="0.1.0",
    )

    assert context.created_at.tzinfo is not None
    assert context.created_at.utcoffset().total_seconds() == 0

def test_tennis_analysis_context_generates_unique_analysis_ids():
    first_context = TennisAnalysisContext.create(
        engine_version="0.1.0",
        policy_version="0.1.0",
    )

    second_context = TennisAnalysisContext.create(
        engine_version="0.1.0",
        policy_version="0.1.0",
    )

    assert first_context.analysis_id != second_context.analysis_id

def test_tennis_analysis_context_is_immutable():
    context = TennisAnalysisContext.create(
        engine_version="0.1.0",
        policy_version="0.1.0",
    )

    with pytest.raises(FrozenInstanceError):
        context.engine_version = "9.9.9"

def test_tennis_analysis_context_rejects_empty_engine_version():
    with pytest.raises(ValueError):
        TennisAnalysisContext.create(
            engine_version="",
            policy_version="0.1.0",
        )

def test_tennis_analysis_context_rejects_empty_policy_version():
    with pytest.raises(ValueError):
        TennisAnalysisContext.create(
            engine_version="0.1.0",
            policy_version="",
        )

def test_tennis_analysis_context_rejects_non_string_engine_version():
    with pytest.raises(TypeError):
        TennisAnalysisContext.create(
            engine_version=None,
            policy_version="0.1.0",
        )

def test_tennis_analysis_context_rejects_non_string_policy_version():
    with pytest.raises(TypeError):
        TennisAnalysisContext.create(
            engine_version="0.1.0",
            policy_version=None,
        )
