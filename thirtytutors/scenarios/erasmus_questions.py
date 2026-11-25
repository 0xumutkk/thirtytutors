"""Question bank for the Erasmus speaking exam (erasmus_exam.py), with the
app-side helpers that pick each session's questions and spot them in the
examiner's speech.

The app picks the questions, not the examiner: left to choose, the Live model
asked the same two or three questions in nearly every session. The bank
follows the ESTÜ speaking exam pattern, where question 1 comes from everyday
life and question 2 asks for an opinion on a social topic; questions marked
priority are the ones closest to what that exam has actually asked, and come
up more often.
"""

import random
import re

# (question, priority)
WARM_UP = [
    "Could you introduce yourself?",
    "What do you study, and why did you choose this field?",
    "What do you usually do in your free time?",
    "What's it like living in your city?",
    "Have you ever been abroad? Where would you most like to go?",
    "What motivates you to learn English?",
    "What are your plans for the next few years?",
    "What's the most interesting place you've ever visited?",
    "Why do you want to take part in the Erasmus programme?",
    "Which country would you like to go to, and why?",
]

# Question 1, usually: everyday life (ESTÜ's own question 1 type).
EVERYDAY = [
    ("What's your favourite season, and why?", True),
    ("What kind of weather do you enjoy the most?", False),
    ("How does the weather affect your mood?", False),
    ("What do you usually do on a rainy day?", False),
    ("What was the last meal you cooked, and how did you make it?", True),
    ("What's your favourite dish, and why?", False),
    ("Can you describe a traditional dish from your hometown?", False),
    ("Do you prefer eating at home or eating out?", False),
    ("Describe a memorable meal you had with friends or family.", False),
    ("Can you describe a typical day in your life?", False),
    ("What do you usually do in the morning before university?", False),
    ("What's the best part of your day, and why?", False),
    ("Are you a morning person or a night person?", False),
    ("What did you do last weekend?", False),
    ("What's your favourite hobby, and how did you start it?", False),
    ("What's the last film you watched or book you read? Would you recommend it?", False),
    ("How do you relax after a stressful day?", False),
    ("What's your favourite place in your city, and why?", False),
    ("Describe your hometown.", False),
    ("Describe a place you visited recently.", False),
    ("Where would you like to live in the future?", False),
    ("Describe a person who has influenced you.", False),
    ("Tell me about your best friend.", False),
    ("What's your happiest childhood memory?", False),
    ("Describe a special day you remember well.", False),
    ("Describe the best gift you've ever received.", False),
    ("What's the most useful object you own?", False),
    ("How much time do you spend on your phone every day?", False),
    ("What's the last thing you bought, and why?", False),
    ("What are your goals for the near future?", True),
    ("What are your plans for this summer?", False),
    ("What would you do if you had a free day tomorrow?", False),
]

# Question 1, sometimes: a personal preference or comparison.
PREFERENCE = [
    ("Which do you prefer, a laptop or a desktop computer? Why?", True),
    ("What are the main differences between living in a city and living in the countryside? Which would you choose?", True),
    ("Would you rather travel abroad or within your own country?", False),
    ("Do you prefer spending your free time alone or with friends?", False),
    ("Online classes or face-to-face classes: which works better for you?", False),
    ("Would you rather work remotely or in an office?", False),
    ("Do you prefer reading the news on social media or from traditional sources?", False),
    ("Public transport or your own car: which is better for daily life?", False),
    ("Do you prefer quiet or crowded holiday destinations?", False),
]

# Question 2, usually: an opinion on a social topic (ESTÜ's own question 2 type).
OPINION = [
    ("What do you think about the visa systems between countries?", True),
    ("What are the benefits of experiencing different cultures?", True),
    ("What are the benefits of the Erasmus programme for students?", True),
    ("Should it be easier for students to travel and study abroad?", False),
    ("What are the disadvantages of studying abroad?", False),
    ("How can travelling change a person?", False),
    ("Why do some young people prefer to live and work abroad permanently?", False),
    ("How can universities help international students adapt?", False),
    ("Is it important to learn about other cultures before visiting a country?", False),
    ("Why should countries invest more in renewable energy?", True),
    ("What are the biggest environmental problems in the world today?", False),
    ("Should recycling be compulsory, with fines for people who don't do it?", False),
    ("What could governments do to stop animals from becoming extinct?", False),
    ("Has computer technology made our lives better? Could we live without it?", True),
    ("How can technology addiction be reduced?", False),
    ("In what ways can technology slow down our progress at school or work?", False),
    ("How will artificial intelligence change the job market?", False),
    ("Is a university degree essential today?", False),
    ("How could the education system in your country be improved?", False),
    ("Should governments spend more money on education?", False),
    ("Is living abroad the best way to learn a language?", False),
    ("What should people do to lead a healthy life?", True),
    ("How have people's free-time habits changed in recent years?", False),
    ("Is money the key to happiness or success?", False),
    ("Why are people so interested in celebrities?", False),
    ("Is the world becoming a global village? Is this positive or negative?", False),
    ("In what situations are people sometimes dishonest?", False),
]

# Question 2, sometimes: agree or disagree with a statement.
AGREE = [
    ("Animals should be used in scientific experiments. Do you agree or disagree?", True),
    ("'A friend in need is a friend indeed.' Do you agree?", True),
    ("Parents should decide on their children's future careers. Do you agree?", False),
    ("Young people today are more interested in fame than in hard work. Do you agree?", False),
    ("Social media does more harm than good. Do you agree?", False),
    ("Failure is the best teacher. Do you agree?", False),
    ("Artificial intelligence will make most jobs disappear. Do you agree?", False),
    ("Everyone should do some voluntary work. Do you agree?", False),
]

ALL_QUESTIONS = [q for pool in (EVERYDAY, PREFERENCE, OPINION, AGREE) for q, _ in pool]

# How often question 1 is a preference question rather than everyday life,
# and question 2 an agree/disagree statement rather than an opinion question.
PREFERENCE_SHARE = 0.2
AGREE_SHARE = 0.1
PRIORITY_WEIGHT = 3
EXAMS_PER_SESSION = 4
# Words a question has to open with, in order, to count as read aloud.
_ANCHOR_WORDS = 8


def normalize(text: str) -> str:
    """Lowercase words and apostrophes only, single-spaced, so transcripts and
    bank questions compare regardless of punctuation."""
    text = text.lower().replace("’", "'")
    return " ".join(re.sub(r"[^a-z0-9' ]+", " ", text).split())


def _pick(pool, exclude: set[str], rng: random.Random) -> str:
    fresh = [(q, p) for q, p in pool if normalize(q) not in exclude] or pool
    weights = [PRIORITY_WEIGHT if p else 1 for _, p in fresh]
    return rng.choices([q for q, _ in fresh], weights=weights)[0]


def pick_exam_questions(
    recently_asked: set[str], count: int = EXAMS_PER_SESSION, rng: random.Random | None = None
) -> list[tuple[str, str]]:
    """count (question 1, question 2) pairs for one session, avoiding the
    recently asked ones (normalized) and repeats within the session while any
    others are left."""
    rng = rng or random.Random()
    exclude = set(recently_asked)
    exams = []
    for _ in range(count):
        q1 = _pick(PREFERENCE if rng.random() < PREFERENCE_SHARE else EVERYDAY, exclude, rng)
        exclude.add(normalize(q1))
        q2 = _pick(AGREE if rng.random() < AGREE_SHARE else OPINION, exclude, rng)
        exclude.add(normalize(q2))
        exams.append((q1, q2))
    return exams


def question_position(text: str, question: str) -> int | None:
    """Where in normalize(text) the examiner starts reading question, or None.
    The opening words are enough: the examiner reads the question word for
    word, and the full text often gets cut by transcription."""
    anchor = " ".join(normalize(question).split()[:_ANCHOR_WORDS])
    position = normalize(text).find(anchor)
    return None if position < 0 else position


def asked_in(text: str) -> set[str]:
    """The bank questions (normalized) the examiner read in text."""
    return {normalize(q) for q in ALL_QUESTIONS if question_position(text, q) is not None}
