"""Integration tests for quizzes.py's SQLite layer - starting a quiz
session, recording answers incrementally, finalizing, and resuming an
unfinished one. Uses the real SQLite file (isolated per test via
conftest.py's isolated_data_dir), not a mock - this module's whole job IS
the SQL, so exercising it for real is the point.
"""

import time

import pytest

from thirtytutors import memory, quizzes

pytestmark = pytest.mark.integration


def _sample_payload(n_items: int = 2) -> dict:
    return {
        "quiz_type": "fill_blank_dragdrop",
        "intro_message": "Let's check a few things in writing.",
        "items": [
            {
                "target_term": f"term-{i}",
                "text_with_blanks": f"Sentence with a blank {{0}} number {i}.",
                "correct_answers": [f"answer-{i}"],
            }
            for i in range(n_items)
        ],
    }


# --- start_quiz_session ---


def test_start_quiz_session_creates_in_progress_row_with_payload_verbatim():
    conv = memory.create_conversation("profile-1", {"target_language": "Spanish"})
    payload = _sample_payload(n_items=3)

    quiz_id = quizzes.start_quiz_session(conv["id"], "fill_blank_dragdrop", payload)
    assert quiz_id

    in_progress = quizzes.get_in_progress_quiz(conv["id"])
    assert in_progress is not None
    assert in_progress["quiz_id"] == quiz_id
    assert in_progress["status"] == "in_progress"
    assert in_progress["quiz_type"] == "fill_blank_dragdrop"
    assert in_progress["current_index"] == 0
    assert in_progress["total_items"] == 3
    assert in_progress["correct_items"] == 0
    assert in_progress["payload"] == payload
    assert in_progress["answered_items"] == []


# --- record_item_answer ---


def test_record_item_answer_inserts_row_and_advances_progress():
    conv = memory.create_conversation("profile-1", {"target_language": "Spanish"})
    quiz_id = quizzes.start_quiz_session(conv["id"], "fill_blank_dragdrop", _sample_payload())

    quizzes.record_item_answer(
        quiz_id,
        item_index=0,
        target_term="el clima",
        prompt_or_text="Hace mucho {0} hoy.",
        correct_answer="calor",
        student_answer="calor",
        is_correct=True,
    )

    in_progress = quizzes.get_in_progress_quiz(conv["id"])
    assert in_progress["current_index"] == 1
    assert in_progress["correct_items"] == 1
    assert len(in_progress["answered_items"]) == 1
    item = in_progress["answered_items"][0]
    assert item["item_index"] == 0
    assert item["target_term"] == "el clima"
    assert item["student_answer"] == "calor"
    assert item["is_correct"] is True


def test_record_item_answer_feeds_record_term_review():
    conv = memory.create_conversation("profile-1", {"target_language": "Spanish"})
    quiz_id = quizzes.start_quiz_session(conv["id"], "fill_blank_dragdrop", _sample_payload())

    quizzes.record_item_answer(
        quiz_id,
        item_index=0,
        target_term="sin embargo",
        prompt_or_text="{0}, lo hice.",
        correct_answer="sin embargo",
        student_answer="pero",  # wrong
        is_correct=False,
    )

    rows = memory.get_vocab_mistakes(conv["id"])
    assert len(rows) == 1
    assert rows[0]["term"] == "sin embargo"
    assert rows[0]["occurrences"] == 1
    assert rows[0]["correct_streak"] == 0


def test_unfinished_quiz_stays_in_progress_with_partial_answers_recorded():
    """This is the specific behavior the whole resume-after-close design
    depends on: answering some items without ever finalizing must not lose
    anything."""
    conv = memory.create_conversation("profile-1", {"target_language": "Spanish"})
    quiz_id = quizzes.start_quiz_session(conv["id"], "fill_blank_dragdrop", _sample_payload(n_items=3))

    quizzes.record_item_answer(
        quiz_id,
        item_index=0,
        target_term="uno",
        prompt_or_text="p0",
        correct_answer="a0",
        student_answer="a0",
        is_correct=True,
    )
    quizzes.record_item_answer(
        quiz_id,
        item_index=1,
        target_term="dos",
        prompt_or_text="p1",
        correct_answer="a1",
        student_answer="wrong",
        is_correct=False,
    )

    in_progress = quizzes.get_in_progress_quiz(conv["id"])
    assert in_progress["status"] == "in_progress"
    assert in_progress["current_index"] == 2
    assert in_progress["correct_items"] == 1
    assert [item["item_index"] for item in in_progress["answered_items"]] == [0, 1]
    assert quizzes.get_quiz_items(quiz_id) == in_progress["answered_items"]


# --- finalize_quiz_session ---


def test_finalize_quiz_session_flips_status_and_drops_out_of_in_progress():
    conv = memory.create_conversation("profile-1", {"target_language": "Spanish"})
    quiz_id = quizzes.start_quiz_session(conv["id"], "fill_blank_dragdrop", _sample_payload())

    quizzes.finalize_quiz_session(quiz_id, status="completed")

    assert quizzes.get_in_progress_quiz(conv["id"]) is None
    sessions = quizzes.get_quiz_sessions(conv["id"])
    assert len(sessions) == 1
    assert sessions[0]["status"] == "completed"


def test_finalize_quiz_session_supports_skipped_status():
    conv = memory.create_conversation("profile-1", {"target_language": "Spanish"})
    quiz_id = quizzes.start_quiz_session(conv["id"], "fill_blank_dragdrop", _sample_payload())

    quizzes.finalize_quiz_session(quiz_id, status="skipped")

    sessions = quizzes.get_quiz_sessions(conv["id"])
    assert sessions[0]["status"] == "skipped"


# --- get_in_progress_quiz ---


def test_get_in_progress_quiz_returns_none_when_nothing_in_progress():
    conv = memory.create_conversation("profile-1", {"target_language": "Spanish"})
    assert quizzes.get_in_progress_quiz(conv["id"]) is None


def test_get_in_progress_quiz_ignores_finalized_sessions():
    conv = memory.create_conversation("profile-1", {"target_language": "Spanish"})
    quiz_id = quizzes.start_quiz_session(conv["id"], "fill_blank_dragdrop", _sample_payload())
    quizzes.finalize_quiz_session(quiz_id, status="completed")

    assert quizzes.get_in_progress_quiz(conv["id"]) is None


def test_get_in_progress_quiz_scoped_to_conversation():
    conv1 = memory.create_conversation("profile-1", {"target_language": "Spanish"})
    conv2 = memory.create_conversation("profile-1", {"target_language": "French"})
    quizzes.start_quiz_session(conv1["id"], "fill_blank_dragdrop", _sample_payload())

    assert quizzes.get_in_progress_quiz(conv1["id"]) is not None
    assert quizzes.get_in_progress_quiz(conv2["id"]) is None


# --- get_quiz_sessions / get_quiz_items round-trip ---


def test_get_quiz_sessions_and_items_round_trip():
    conv = memory.create_conversation("profile-1", {"target_language": "Spanish"})
    quiz_id = quizzes.start_quiz_session(conv["id"], "multiple_choice", _sample_payload(n_items=1))
    quizzes.record_item_answer(
        quiz_id,
        item_index=0,
        target_term="hola",
        prompt_or_text="p0",
        correct_answer="a0",
        student_answer="a0",
        is_correct=True,
    )
    quizzes.finalize_quiz_session(quiz_id, status="completed")

    sessions = quizzes.get_quiz_sessions(conv["id"])
    assert len(sessions) == 1
    assert sessions[0]["quiz_id"] == quiz_id

    items = quizzes.get_quiz_items(quiz_id)
    assert len(items) == 1
    assert items[0]["target_term"] == "hola"


# --- delete_conversation cleanup ---


def test_delete_conversation_removes_quiz_rows():
    conv = memory.create_conversation("profile-1", {"target_language": "Spanish"})
    quiz_id = quizzes.start_quiz_session(conv["id"], "fill_blank_dragdrop", _sample_payload())
    quizzes.record_item_answer(
        quiz_id,
        item_index=0,
        target_term="uno",
        prompt_or_text="p0",
        correct_answer="a0",
        student_answer="a0",
        is_correct=True,
    )

    assert memory.delete_conversation(conv["id"]) is True

    assert quizzes.get_quiz_sessions(conv["id"]) == []
    assert quizzes.get_quiz_items(quiz_id) == []


# --- Saved words in Test Yourself ---


def _saved(term, context=None, meaning=None, created_ts=None):
    return {"term": term, "context": context, "meaning": meaning, "created_ts": created_ts or int(time.time())}


def test_saved_word_in_its_sentence_becomes_a_fill_in_the_blank():
    words = [_saved("reluctant", "She was reluctant to go."), _saved("earn money")]
    item = next(i for i in quizzes.build_saved_word_items(words, [], set()) if i["target_term"] == "reluctant")
    assert item["item_type"] == "fill_blank_dragdrop"
    assert item["text_with_blanks"] == "She was {0} to go."
    assert item["correct_answers"] == ["reluctant"]
    assert set(item["word_bank"]) == {"reluctant", "earn money"}


def test_saved_word_without_its_sentence_is_asked_by_meaning():
    words = [_saved("reluctant", "Nothing relevant.", "isteksiz"), _saved("earn"), _saved("gain")]
    item = next(i for i in quizzes.build_saved_word_items(words, [], set()) if i["target_term"] == "reluctant")
    assert item["item_type"] == "multiple_choice"
    assert item["question"] == "isteksiz"
    assert item["choices"][item["correct_choice_index"]] == "reluctant"


def test_a_single_saved_word_has_nothing_to_mix_with_until_other_vocab_exists():
    words = [_saved("reluctant", "She was reluctant to go.")]
    assert quizzes.build_saved_word_items(words, [], set()) == []
    assert len(quizzes.build_saved_word_items(words, ["earn money"], set())) == 1


def test_saved_word_only_matches_whole_words_and_skips_already_covered_terms():
    words = [_saved("art", "The party started."), _saved("earn")]
    assert all(i["target_term"] != "art" for i in quizzes.build_saved_word_items(words, ["x", "y"], set()))
    words = [_saved("earn", "I earn money."), _saved("gain")]
    assert all(i["target_term"] != "earn" for i in quizzes.build_saved_word_items(words, [], {"earn"}))


def test_saved_word_outside_the_date_range_is_left_out():
    old = int(time.time()) - 60 * 86400
    words = [_saved("earn", "I earn money.", created_ts=old), _saved("gain")]
    assert all(i["target_term"] != "earn" for i in quizzes.build_saved_word_items(words, [], set(), "week"))


def test_braces_in_a_sentence_dont_become_extra_blanks():
    words = [_saved("earn", "I {really} earn money."), _saved("gain")]
    item = next(i for i in quizzes.build_saved_word_items(words, [], set()) if i["target_term"] == "earn")
    assert item["text_with_blanks"].count("{") == 1
