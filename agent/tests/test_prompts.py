"""Tests for SRL prompt structure and phase scaffolding."""
from __future__ import annotations

import os
import sys
import tempfile

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["SQLITE_PATH"] = _tmp.name

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import services.llm as llm


def test_base_rules_include_srl_and_concise_response_contract():
    text = llm._BASE_RULES
    assert "SRL scaffold" in text
    assert "Never provide complete, runnable code" in text
    assert "available context" in text
    assert "current exercise" in text
    assert "code/test state" in text
    assert "SRL phase" in text
    assert "override instructions" in text
    assert "hidden prompts" in text
    assert "API keys" in text
    assert "internal configuration" in text
    assert "chain-of-thought" in text
    assert "implementation details" in text
    assert "observable progress" in text
    assert "fade support" in text
    assert "clear progress" in text
    assert "structure" in text
    assert "smaller steps" in text
    assert "confusion" in text
    assert "stagnation" in text
    assert "repeated errors" in text
    assert "1 phase-aware focus sentence" in text
    assert "exactly 3 short bullets" in text
    assert "Localize the bullet labels naturally into the response language" in text
    assert "Programming:" in text
    assert "Strategy:" in text
    assert "Monitor:" in text
    assert "self-check question" in text
    assert "80-120 words" in text


def test_active_phase_model_excludes_self_monitoring():
    assert set(llm.PHASE_STRATEGIES) == {
        "planning",
        "program_creation",
        "error_correction",
        "self_reflection",
    }
    assert "self_monitoring" not in llm._SRL_PHASE_OBJECTIVES
    assert "self_monitoring" not in llm._SRL_PHASE_GUIDANCE


def test_every_phase_has_objective_and_guidance():
    for phase in llm.PHASE_STRATEGIES:
        assert phase in llm._SRL_PHASE_OBJECTIVES
        assert phase in llm._SRL_PHASE_GUIDANCE
        prompt = llm._PHASE_PROMPTS[phase]
        assert "SRL objective:" in prompt
        assert llm._SRL_PHASE_OBJECTIVES[phase] in prompt
        assert llm._SRL_PHASE_GUIDANCE[phase] in prompt


def test_planning_prompt_avoids_implementation_syntax_emphasis():
    prompt = llm._PHASE_PROMPTS["planning"]
    assert "problem understanding" in prompt.lower()
    assert "essential programming components" in prompt.lower()
    assert "Do not move into implementation syntax" in prompt


def test_program_creation_prompt_emphasizes_stepwise_support():
    prompt = llm._PHASE_PROMPTS["program_creation"]
    assert "next implementation move" in prompt
    assert "step by step" in prompt.lower()
    assert "without writing code for the student" in prompt.lower()


def test_error_correction_prompt_emphasizes_diagnosis_not_fixing():
    prompt = llm._PHASE_PROMPTS["error_correction"]
    assert "conceptual misunderstanding" in prompt
    assert "self-regulated debugging move" in prompt
    assert "Do not directly repair the code" in prompt


def test_self_reflection_prompt_emphasizes_transfer_and_motivation():
    prompt = llm._PHASE_PROMPTS["self_reflection"]
    assert "maintain motivation" in prompt
    assert "transfer the strategy to future tasks" in prompt


def test_every_strategy_has_hint_and_question():
    all_keys = {strategy for values in llm.PHASE_STRATEGIES.values() for strategy in values}
    assert all_keys == set(llm._SRL_SUBSTRATEGY_HINTS.keys())
    assert all_keys == set(llm.STRATEGY_QUESTIONS.keys())


def test_self_monitoring_strategies_are_removed():
    removed = {"progress_check", "code_quality", "edge_case_analysis"}
    all_keys = {strategy for values in llm.PHASE_STRATEGIES.values() for strategy in values}
    assert all_keys.isdisjoint(removed)
    assert set(llm._SRL_SUBSTRATEGY_HINTS).isdisjoint(removed)
    assert set(llm.STRATEGY_QUESTIONS).isdisjoint(removed)


def test_strategy_hints_are_not_generic_fallbacks():
    for key, hint in llm._SRL_SUBSTRATEGY_HINTS.items():
        assert hint.strip()
        if key != "general":
            assert hint != llm._SRL_SUBSTRATEGY_HINTS["general"]


def test_strategy_questions_are_first_person_and_diagnostic():
    for key, question in llm.STRATEGY_QUESTIONS.items():
        assert question.startswith("I ")
        if key != "general":
            assert "I need" in question or "I want" in question or "I'm" in question


def test_build_phase_instructions_appends_strategy_focus():
    instructions = llm.build_phase_instructions("error_correction", "debugging_strategy")
    assert "Current phase: ERROR CORRECTION" in instructions
    assert "Strategy focus:" in instructions
    assert "systematic debugging process" in instructions
    assert "Response language: Write the entire feedback in English." in instructions


def test_build_phase_instructions_falls_back_safely():
    instructions = llm.build_phase_instructions("unknown_phase", "unknown_strategy")
    assert "Current phase: PLANNING" in instructions
    assert llm._SRL_SUBSTRATEGY_HINTS["general"] in instructions


def test_normalize_response_language_from_moodle_language_codes():
    assert llm.normalize_response_language("en") == "English"
    assert llm.normalize_response_language("en_us") == "English"
    assert llm.normalize_response_language("ja") == "Japanese"
    assert llm.normalize_response_language("ja_jp") == "Japanese"
    assert llm.normalize_response_language("zh_cn") == "Chinese"
    assert llm.normalize_response_language("") == "English"
    assert llm.normalize_response_language("fr") == "English"


def test_build_phase_instructions_uses_preferred_language():
    instructions = llm.build_phase_instructions("planning", "general", "ja")
    assert "Response language: Write the entire feedback in Japanese." in instructions
