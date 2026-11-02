// ThirtyTutors - lesson page's word saving and read-aloud helpers. Tapping a
// word in the dialogue (or selecting a phrase) opens a small sheet to hear or
// save it; saved words live per profile on the server and come back in lessons
// through live_session.py's review terms.

const wordSheet = document.getElementById('wordSheet');
const wordSheetTerm = document.getElementById('wordSheetTerm');
const wordSheetMeaning = document.getElementById('wordSheetMeaning');
const wordSheetSaveBtn = document.getElementById('wordSheetSaveBtn');
const savedWordsQuizLink = document.getElementById('savedWordsQuizLink');
const wordSheetCloseBtn = document.getElementById('wordSheetCloseBtn');
const savedWordsOverlay = document.getElementById('savedWordsOverlay');
const savedWordsList = document.getElementById('savedWordsList');
const savedWordsBtn = document.getElementById('savedWordsBtn');
const savedWordsCloseBtn = document.getElementById('savedWordsCloseBtn');

const MAX_SAVED_TERM_LENGTH = 120;
const MAX_SAVED_CONTEXT_LENGTH = 400;

let sheetSelection = null; // { term, context, meaning }
const fetchedMeanings = new Map(); // so tapping a word again doesn't spend another API call

// Reads text in the tutor's voice, for anything with no recording of it.
// Remembered per text, since each reading is an API call.
const spokenAudio = new Map();

async function fetchTutorSpeech(text) {
  if (spokenAudio.has(text)) return spokenAudio.get(text);
  const res = await fetch(`/api/profiles/${currentProfile.id}/conversations/${currentConversationId}/speak`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  }).catch(() => null);
  const data = res && res.ok ? await res.json().catch(() => null) : null;
  if (!data) throw new Error('speech-failed');
  spokenAudio.set(text, data.audio);
  return data.audio;
}

async function speakText(text) {
  if (isRecording || isTutorSpeaking()) return;
  try {
    playReplayChunks([await fetchTutorSpeech(text)]);
  } catch (e) {
    showError("Couldn't read this aloud - try again in a moment.");
  }
}

function cleanTerm(text) {
  return text.replace(/\s+/g, ' ').trim().replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, '').slice(0, MAX_SAVED_TERM_LENGTH);
}

function caretAt(x, y) {
  if (document.caretRangeFromPoint) {
    const range = document.caretRangeFromPoint(x, y);
    return range ? { node: range.startContainer, offset: range.startOffset } : null;
  }
  if (document.caretPositionFromPoint) {
    const position = document.caretPositionFromPoint(x, y);
    return position ? { node: position.offsetNode, offset: position.offset } : null;
  }
  return null;
}

function wordRangeAt(x, y) {
  const caret = caretAt(x, y);
  if (!caret || caret.node.nodeType !== Node.TEXT_NODE) return null;
  const text = caret.node.textContent;
  const isWordChar = (ch) => ch && /[\p{L}\p{N}'’-]/u.test(ch);
  let start = caret.offset;
  let end = caret.offset;
  while (start > 0 && isWordChar(text[start - 1])) start--;
  while (end < text.length && isWordChar(text[end])) end++;
  if (start === end) return null;
  const range = document.createRange();
  range.setStart(caret.node, start);
  range.setEnd(caret.node, end);
  return range;
}

// The dashed oval around the tapped word. A span in the bubble's text, so it
// moves with scrolling; if the reply is still streaming, new text replaces it.
let wordMark = null;

function clearWordMark() {
  if (!wordMark) return;
  const parent = wordMark.parentNode;
  if (parent) {
    wordMark.replaceWith(...wordMark.childNodes);
    parent.normalize();
  }
  wordMark = null;
}

function markWord(range) {
  const mark = document.createElement('span');
  mark.className = 'word-mark';
  try {
    range.surroundContents(mark);
    wordMark = mark;
  } catch (e) {
    /* a selection crossing other elements just goes unmarked */
  }
}

function openWordSheet(term, context) {
  sheetSelection = { term, context: context.trim().slice(0, MAX_SAVED_CONTEXT_LENGTH) };
  wordSheetTerm.textContent = term;
  wordSheetSaveBtn.textContent = 'Save word';
  wordSheetSaveBtn.disabled = false;
  wordSheet.classList.add('visible');
  showWordMeaning(sheetSelection);
}

async function showWordMeaning(selection) {
  const known = fetchedMeanings.get(selection.term.toLowerCase());
  if (known) {
    selection.meaning = known;
    wordSheetMeaning.textContent = known;
    return;
  }
  wordSheetMeaning.textContent = 'Finding the meaning...';
  const res = await fetch(`/api/profiles/${currentProfile.id}/word-meaning`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ term: selection.term, context: selection.context, conversation_id: currentConversationId }),
  }).catch(() => null);
  const data = res && res.ok ? await res.json().catch(() => null) : null;
  if (sheetSelection !== selection) return; // another word was tapped meanwhile
  if (!data) {
    wordSheetMeaning.textContent = "Couldn't get the meaning - you can still save the word.";
    return;
  }
  selection.meaning = data.meaning;
  fetchedMeanings.set(selection.term.toLowerCase(), data.meaning);
  wordSheetMeaning.textContent = data.meaning;
}

function closeWordSheet() {
  wordSheet.classList.remove('visible');
  sheetSelection = null;
  clearWordMark();
}

transcriptArea.addEventListener('click', (e) => {
  const textEl = e.target.closest('.bubble-text');
  if (!textEl) return;
  clearWordMark(); // first, so the positions below are in the plain text
  const selected = window.getSelection();
  const hasSelection = selected && !selected.isCollapsed && textEl.contains(selected.anchorNode);
  const range = hasSelection ? selected.getRangeAt(0) : wordRangeAt(e.clientX, e.clientY);
  const term = range ? cleanTerm(range.toString()) : '';
  if (!term) {
    closeWordSheet();
    return;
  }
  const context = textEl.textContent;
  markWord(range);
  if (hasSelection) selected.removeAllRanges();
  openWordSheet(term, context);
});

wordSheetCloseBtn.addEventListener('click', closeWordSheet);

wordSheetSaveBtn.addEventListener('click', async () => {
  if (!sheetSelection || !currentProfile) return;
  wordSheetSaveBtn.disabled = true;
  const res = await fetch(`/api/profiles/${currentProfile.id}/saved-words`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...sheetSelection, conversation_id: currentConversationId }),
  }).catch(() => null);
  if (!res || !res.ok) {
    wordSheetSaveBtn.disabled = false;
    showError('Could not save this word - try again.');
    return;
  }
  wordSheetSaveBtn.textContent = 'Saved';
  // So the tutor can start using it in this lesson, not only the next one.
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'word_saved' }));
});

async function renderSavedWords() {
  savedWordsList.textContent = 'Loading...';
  const res = await fetch(`/api/profiles/${currentProfile.id}/saved-words`).catch(() => null);
  if (!res || !res.ok) {
    savedWordsList.textContent = 'Could not load your words.';
    return;
  }
  const { words } = await res.json();
  savedWordsList.textContent = words.length ? '' : 'Nothing saved yet - tap a word in the dialogue.';
  words.forEach((word) => {
    const row = document.createElement('div');
    row.className = 'saved-word-row';

    const body = document.createElement('div');
    body.className = 'saved-word-body';
    const term = document.createElement('strong');
    term.textContent = word.term;
    body.appendChild(term);
    if (word.meaning) {
      const meaning = document.createElement('em');
      meaning.textContent = word.meaning;
      body.appendChild(meaning);
    }
    if (word.context) {
      const context = document.createElement('span');
      context.textContent = word.context;
      body.appendChild(context);
    }

    const hear = document.createElement('button');
    hear.type = 'button';
    hear.className = 'icon-btn';
    hear.title = `Hear ${word.term}`;
    hear.textContent = '\u{1F50A}';
    hear.addEventListener('click', () => speakText(word.term));

    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'icon-btn';
    remove.title = `Remove ${word.term}`;
    remove.textContent = '×';
    remove.addEventListener('click', async () => {
      const deleted = await fetch(`/api/profiles/${currentProfile.id}/saved-words/${word.id}`, { method: 'DELETE' }).catch(() => null);
      if (deleted && deleted.ok) renderSavedWords();
      else showError('Could not remove this word - try again.');
    });

    row.append(body, hear, remove);
    savedWordsList.appendChild(row);
  });
}

savedWordsBtn.addEventListener('click', () => {
  if (!currentProfile) return;
  closeWordSheet();
  savedWordsQuizLink.href = `/quiz-mode?profile_id=${encodeURIComponent(currentProfile.id)}&conversation_id=${encodeURIComponent(currentConversationId || '')}`;
  savedWordsOverlay.classList.add('visible');
  renderSavedWords();
});
savedWordsCloseBtn.addEventListener('click', () => savedWordsOverlay.classList.remove('visible'));
savedWordsOverlay.addEventListener('click', (e) => {
  if (e.target === savedWordsOverlay) savedWordsOverlay.classList.remove('visible');
});
