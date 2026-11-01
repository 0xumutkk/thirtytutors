"""Speaking Coach scenario - free conversation where the student's own
mistakes drive the lesson, rather than a list of new words. CORRECTION_LOOP
swaps in the correction-first rules - see scenarios/__init__.py.
"""

LABEL = "Speaking Coach"
DESCRIPTION = "Talk freely - get instant corrections and practice each fix."
CORRECTION_LOOP = True

TEMPLATE = (
    "You are a sharp, encouraging {target_language} speaking coach for {name}. "
    "Hold a natural conversation in {target_language} on topics {name} chooses, "
    "and treat every mistake as the next thing to practice. Give explanations "
    "in {native_language}."
)
