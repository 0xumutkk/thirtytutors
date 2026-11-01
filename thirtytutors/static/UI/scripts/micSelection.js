// ThirtyTutors - which microphone a profile uses. A profile follows the OS
// default input unless a specific mic was chosen (mic_auto === false).
//
// mic_device_id/mic_label always hold the device actually in use: everything
// keyed per mic (mic_calibrations, voice enrollment, live_session.py's
// hands-free thresholds) reads mic_label, so following the default keeps a
// separate calibration per physical mic rather than one under a placeholder.

function micIsAuto(profile) {
  return !profile || profile.mic_auto !== false;
}

function micConstraints(profile) {
  if (micIsAuto(profile) || !profile.mic_device_id) return { audio: true };
  return { audio: { deviceId: { exact: profile.mic_device_id } } };
}

// Chrome labels the default device "Default - <name>"; the label is a
// calibration key, so it has to match the device's plain name.
function plainMicLabel(label) {
  return (label || '').replace(/^(Default|Communications) - /, '');
}

// Records the device a stream really opened. Only saved when following the
// default - a chosen mic stays chosen even while it's unplugged, so it's
// picked up again once it's back.
async function syncProfileMicFromStream(profile, stream) {
  const track = stream.getAudioTracks()[0];
  const label = plainMicLabel(track && track.label);
  if (!profile || !label) return;
  const deviceId = (track.getSettings && track.getSettings().deviceId) || null;
  const changed = profile.mic_label !== label;
  profile.mic_label = label;
  if (!micIsAuto(profile)) return;
  profile.mic_device_id = deviceId;
  if (!changed || !profile.id) return;
  await fetch(`/api/profiles/${profile.id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mic_device_id: deviceId, mic_label: label }),
  }).catch(() => {});
}

// Opens the profile's mic, falling back to the OS default if a chosen one is
// gone. getUserMedia is passed in so callers keep their own timeout wrapper.
async function openProfileMic(profile, getUserMedia) {
  let stream;
  let fellBack = false;
  try {
    stream = await getUserMedia(micConstraints(profile));
  } catch (e) {
    const deviceMissing = e && (e.name === 'OverconstrainedError' || e.name === 'NotFoundError');
    if (micIsAuto(profile) || !deviceMissing) throw e;
    stream = await getUserMedia({ audio: true });
    fellBack = true;
  }
  await syncProfileMicFromStream(profile, stream);
  return { stream, fellBack };
}
