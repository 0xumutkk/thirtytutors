// ThirtyTutors - the exam clock (scenarios/erasmus_exam.py). The examiner starts
// and stops it through its exam_timer tool. It runs here rather than on the
// server so it carries on across a Live reconnect, and ends by ending the
// candidate's turn and telling the examiner that time is up.

const examTimer = document.getElementById('examTimer');
const examTimerLabel = document.getElementById('examTimerLabel');
const examTimerClock = document.getElementById('examTimerClock');
const EXAM_TIMER_ENDING_SECONDS = 15;
const EXAM_TIMER_LABELS = { preparation: 'Prepare - take notes', answer: 'Your answer' };

let examTimerInterval = null;

function stopExamTimer() {
  clearInterval(examTimerInterval);
  examTimerInterval = null;
  examTimer.hidden = true;
}

async function finishExamTimer(phase) {
  stopExamTimer();
  if (isRecording) stopRecording();
  // An open hands-free turn would run on into the examiner's next line.
  if (phase === 'answer' && handsFreeActive) await setHandsFreeActive(false);
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'exam_time_up', phase }));
}

function renderExamClock(secondsLeft) {
  const minutes = Math.floor(secondsLeft / 60);
  examTimerClock.textContent = `${minutes}:${String(secondsLeft % 60).padStart(2, '0')}`;
  examTimer.classList.toggle('ending', secondsLeft <= EXAM_TIMER_ENDING_SECONDS);
}

function runExamTimer(phase, seconds) {
  stopExamTimer();
  if (!seconds) return; // phase "stop"
  const endsAt = Date.now() + seconds * 1000; // a throttled background tab still ends on time
  examTimerLabel.textContent = EXAM_TIMER_LABELS[phase] || '';
  examTimer.hidden = false;
  renderExamClock(seconds);
  examTimerInterval = setInterval(() => {
    const secondsLeft = Math.ceil((endsAt - Date.now()) / 1000);
    if (secondsLeft <= 0) finishExamTimer(phase);
    else renderExamClock(secondsLeft);
  }, 250);
}
