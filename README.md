# ThirtyTutors: Speaking Coach fork

**A self-hosted AI English speaking coach with real-time voice, instant corrections, and level-based practice.**

This is a modified fork of [wiss84/thirtytutors](https://github.com/wiss84/thirtytutors), a voice language tutor built on the Gemini Live API. The fork focuses on speaking practice and adds an invite-only web mode you can use from a phone. Its changes aren't part of the original project or its `thirtytutors` PyPI package.

---

## What this fork adds

- **Speaking Coach scenario:** talk freely. When you make a mistake, the coach quotes it, gives the correct form, explains why, and asks for a new sentence using it.
- **Mistake tracking:** mistakes are saved as you talk, with their type (verb tense, collocation, word choice, and so on), and come back later as practice and quizzes.
- **Level settings per session:** choose your current CEFR level and goal (for example A2 to B2). Explanations can be in your native language or only in the language you're learning, so English-to-English practice works.
- **Hands-free without setup:** tap once and talk, or hold to speak if you prefer. There's no voice enrollment.
- **Both sides of the dialogue:** your own speech now appears in the conversation.
- **Automatic microphone:** follows your system's default input, including when a headset is connected, and falls back to it if a chosen mic is gone.
- **Working microphone in the macOS window:** the desktop app runs from a small app bundle so macOS can grant microphone access.
- **Web mode:** invite-only accounts, separated user data, encrypted Gemini keys, a phone-friendly lesson screen, and no 3D avatars.

Everything else comes from the original project, including memory across sessions, in-conversation quizzes, roleplay scenarios, and stats.

---

## See it in action

These videos and screenshots come from the original project. They show its desktop app with the 3D avatars, which this fork's web mode doesn't include, so some screens differ here.

![ThirtyTutors AI tutor conversation demo](thirtytutors/static/images/demo.gif)

### Demo videos

- **0.3.0 release:** [ThirtyTutors UI and UX](https://youtu.be/o4WNlLXm4qo)
- **0.2.0 release:** [ThirtyTutors quiz system](https://youtu.be/9d4UrbZbwfU)
- **0.1.0 release:** [ThirtyTutors tutorial](https://youtu.be/0YEskMeH4Gk)

### Screenshots

**Create a new profile**

![Create a new profile](thirtytutors/static/images/home.webp)

**Log in to an existing profile**

![Log in to an existing profile](thirtytutors/static/images/Create_profile.webp)

**Avatar and voice selection**

![Avatar and voice selection](thirtytutors/static/images/Existing_profile.webp)

**Learning session**

![Learning session](thirtytutors/static/images/Pick_Tutor.webp)

**Learning session, full screen**

![Learning session in full screen](thirtytutors/static/images/Session.webp)

---

## Requirements

- Python 3.11+
- A [Google AI Studio](https://aistudio.google.com/apikey) API key
- A microphone and speakers
- macOS for the desktop app. Web mode has been run on Ubuntu 24.04.

---

## Run the desktop app

Install from this repository. `pip install thirtytutors` would give you the original project without these changes.

```bash
git clone -b feat/correction-loop https://github.com/0xumutkk/thirtytutors.git
cd thirtytutors
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .
thirtytutors setup
thirtytutors
```

`thirtytutors setup` downloads the avatars, voices, and photos (about 460 MB) and creates a desktop shortcut. You'll enter your Gemini API key in the app when you create a profile. The desktop app keeps the 3D avatars.

---

## Run web mode

Web mode serves the app to invited users, with one account per person.

```bash
export THIRTYTUTORS_SECRET_KEY="$(openssl rand -hex 32)"
thirtytutors serve
```

- **Keep the secret key:** it encrypts stored Gemini keys, and they can't be read without it. Store it somewhere private, such as a root-only environment file, rather than in the repository.
- **Put an HTTPS proxy in front:** `serve` only listens on `127.0.0.1:8000`, and both login cookies and browser microphones need HTTPS. Caddy works well:

  ```text
  your-domain.example {
      reverse_proxy 127.0.0.1:8000
  }
  ```

- **Keep the port private:** expose only ports 80 and 443 to the internet.

Create a single-use invite code for each person, on the server and as the same user that runs the app:

```bash
thirtytutors invite
```

New users choose **I have an invite code** on the login page, create an account, and add their own Gemini API key.

### What changes in web mode

- Pages and API routes need a login, and each user can only reach their own profiles.
- Gemini keys are encrypted on disk and never sent back to the browser.
- 3D avatars, folder shortcuts, in-app updates, and backup import are turned off.

---

## Known limitations

- **Transcripts can be wrong:** your on-screen text comes from Gemini's transcription, especially imperfect with accented speech. The coach may also mishear you and correct something you said properly, so treat its corrections and mistake statistics as a guide.
- **Hands-free hears everyone:** it reacts to sound level and doesn't check who is speaking. Nearby voices can count as speech, and constant noise can delay a reply.
- **Keep the screen on:** phones may cut the microphone when the screen locks or the browser moves to the background.
- **No account recovery:** there is no password reset, password change, or invite revocation yet.
- **Single server:** data lives in local SQLite and files, and web mode's daily backups aren't included here. Set up your own off-server backups if the data matters.
- **Privacy:** audio and transcripts go to Google's Gemini API. Conversations are stored as plain text on the server, so whoever runs it can read them. Tell your users this before inviting them.

---

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check .
ruff format .
```

---

## Credits and license

Based on [ThirtyTutors](https://github.com/wiss84/thirtytutors) by [Wissam Metawee](https://github.com/wiss84).

Licensed under the [PolyForm Noncommercial License 1.0.0](LICENSE). You can use, modify, and share it for noncommercial purposes; commercial use isn't permitted.
