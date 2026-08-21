import pytest

from product_help import (
    PRODUCT_HELP_ANSWER,
    PRODUCT_HELP_POLICY_VERSION,
    PRODUCT_HELP_RENDERER_VERSION,
    is_product_help_question,
    render_product_help_answer,
)


@pytest.mark.parametrize(
    "question",
    (
        "What do you do?",
        "What do you do here?",
        "WHAT CAN YOU DO?!",
        "What is Archivist?",
        "What is the Archivist?",
        "What's Archivist?",
        "What is your purpose?",
        "What are you here for?",
        "How can you help me?",
        "What can you help me with?",
        "What can I ask you?",
        "What should I ask you?",
        "How does Archivist work?",
        "How does this work?",
        "How do I use the Archivist?",
        "How do I use this?",
    ),
)
def test_product_help_classifier_accepts_only_direct_capability_questions(question):
    assert is_product_help_question(question) is True


@pytest.mark.parametrize(
    "question",
    (
        pytest.param("How can you helpe me?", id="one-insertion-screenshot-regression"),
        pytest.param("How can you hep me?", id="one-deletion"),
        pytest.param("How can you hekp me?", id="one-substitution"),
        pytest.param("How can you hlep me?", id="one-adjacent-transposition"),
        pytest.param("What dop you do?", id="function-word-insertion"),
        pytest.param("What do youd do?", id="pronoun-insertion"),
        pytest.param("What can you doo?", id="predicate-insertion"),
        pytest.param("How can you hlpe me?", id="two-edits-in-one-token"),
        pytest.param("What do you do there?", id="meaning-preserving-location"),
        pytest.param("How can you help us?", id="meaning-preserving-pronoun"),
        pytest.param("How can you yelp me?", id="real-word-shaped-typo"),
    ),
)
def test_product_help_classifier_accepts_one_typographical_edit(question):
    assert is_product_help_question(question) is True


@pytest.mark.parametrize(
    "question",
    (
        "What is Archvist?",
        "What is your purpsoe?",
        "What can I aks you?",
    ),
)
def test_product_help_classifier_accepts_key_word_typos(question):
    assert is_product_help_question(question) is True


@pytest.mark.parametrize(
    "question",
    (
        pytest.param("what dop youd do", id="reported-two-insertions"),
        pytest.param("  WHAT DOP YOUD DO >?!  ", id="reported-case-spacing-punctuation"),
        pytest.param("Waht od you do?", id="two-function-word-transpositions"),
        pytest.param("What cna yuo do?", id="two-token-transpositions"),
        pytest.param("How cna you hlep me?", id="capability-two-transpositions"),
        pytest.param("Waht can I aks you?", id="ask-two-transpositions"),
        pytest.param("How does Archvist wrok?", id="operation-deletion-transposition"),
        pytest.param("What is yuor purpsoe?", id="purpose-two-transpositions"),
        pytest.param("what dop youdo", id="typo-plus-missing-space"),
    ),
)
def test_product_help_classifier_accepts_two_recognizable_typographical_edits(question):
    assert is_product_help_question(question) is True


@pytest.mark.parametrize(
    "question",
    (
        "How does his work?",
        "How does this word?",
        "How does this war?",
        "How can you tell me?",
        "How can you heal me?",
        "How can you harm me?",
        "How can you hold me?",
        "How can you hear me?",
        "How can you keep me?",
        "How can you helm me?",
        "How do I sue this?",
        "How does this look?",
        "How does this form?",
        "How does this walk?",
        "What is our purpose?",
        "What is your purse?",
        "What is archivism?",
        "What is archive?",
        "What did you do?",
        "What can he do?",
        "What can she do?",
        "What can your dog do?",
        "What can I ask him?",
        "What do you see here?",
    ),
)
def test_typo_tolerance_does_not_blur_semantically_distinct_words(question):
    assert is_product_help_question(question) is False


@pytest.mark.parametrize(
    "question",
    (
        "What did Edwin Sandys do?",
        "What do you do in the manuscript?",
        "What can you tell me about Jamestown?",
        "How did the Virginia Company work?",
        "What do you do, and who was Edwin Sandys?",
        "What do you do?\nNow tell me about Virginia.",
        "What are you doing now?",
        "What is this argument about?",
    ),
)
def test_product_help_classifier_rejects_grounded_compound_and_social_questions(question):
    assert is_product_help_question(question) is False


@pytest.mark.parametrize(
    "question",
    (
        "How can you helpe me with Jamestown?",
        "How can you helpe me, and who was Edwin Sandys?",
        "How can you helpe me?\nNow tell me about Virginia.",
        "How does thsi work in the manuscript?",
    ),
)
def test_typo_tolerance_does_not_accept_appended_context(question):
    assert is_product_help_question(question) is False


def test_product_help_classifier_rejects_four_distributed_typographical_edits():
    assert is_product_help_question("Whta cna yuo hlep me?") is False


def test_product_help_copy_is_fixed_and_truthful_about_the_product_boundary():
    answer = render_product_help_answer()

    assert answer == PRODUCT_HELP_ANSWER
    assert "Cradle of the Empire" in answer
    assert "not the open web" in answer
    assert "supporting sources" in answer
    assert "Perspectives" in answer
    assert PRODUCT_HELP_POLICY_VERSION == "product-help-v1"
    assert PRODUCT_HELP_RENDERER_VERSION == "product-help-renderer-v1"


def test_explicit_product_help_survives_history_but_deictic_help_does_not():
    assert is_product_help_question("What do you do?", has_history=True) is True
    assert is_product_help_question("How does Archivist work?", has_history=True) is True
    assert is_product_help_question("How does this work?", has_history=True) is False
    assert is_product_help_question("How do I use this?", has_history=True) is False


def test_deictic_help_is_typo_tolerant_but_remains_first_turn_only():
    assert is_product_help_question("How does this work?") is True
    assert is_product_help_question("How does thsi work?") is True
    assert is_product_help_question("How do I use ths?") is True
    assert is_product_help_question("How dose this wrok?") is True
    assert is_product_help_question("How does this work?", has_history=True) is False
    assert is_product_help_question("How dose this wrok?", has_history=True) is False


def test_typo_tolerant_explicit_help_still_survives_history():
    assert is_product_help_question("How can you helpe me?", has_history=True) is True
    assert is_product_help_question("what dop youd do>?", has_history=True) is True
