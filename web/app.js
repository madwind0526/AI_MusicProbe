const AUDIO_EXTENSIONS = /\.(wav|flac|mp3|m4a|aac|ogg|opus|aiff|aif)$/i;
const PAGE_META = { analyze: ['음원 분석', 'Analyze'], detectors: ['탐지기', 'Detectors'], reports: ['리포트', 'Reports'], settings: ['설정', 'Settings'] };
const DEFAULT_SETTINGS = { scoreBands: { thresholds: [20, 50, 80, 90], colors: ['#ffffff', '#8ec5ff', '#ffe07a', '#ffad66', '#ff78c8'] }, historyLimit: 0, recursiveFolders: true, historyCardSize: 250, variableHistoryCards: true, paths: { music: '', reports: '', models: '' }, waveformPeaks: 180 };
const state = { files: [], localPaths: [], detectors: [], history: [], historySort: 'newest', historyFilter: 'all', settings: structuredClone(DEFAULT_SETTINGS), browser: { mode: 'files', listing: null, selectedFiles: new Set(), selectedFolder: null, settingsTarget: null } };
const $ = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character]);
}

function toast(message) {
  const node = $('toast');
  node.textContent = message;
  node.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { node.hidden = true; }, 3600);
}

function formatSize(bytes) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function addFiles(fileList) {
  const known = new Set(state.files.map((file) => `${file.name}:${file.size}:${file.lastModified}`));
  for (const file of fileList) {
    const key = `${file.name}:${file.size}:${file.lastModified}`;
    if (AUDIO_EXTENSIONS.test(file.name) && !known.has(key)) {
      state.files.push(file);
      known.add(key);
    }
  }
  renderFiles();
}

function addLocalPaths(paths) {
  const known = new Set(state.localPaths.map((path) => path.toLocaleLowerCase()));
  for (const path of paths) {
    if (!known.has(path.toLocaleLowerCase())) {
      state.localPaths.push(path);
      known.add(path.toLocaleLowerCase());
    }
  }
  renderFiles();
}

function renderFiles() {
  const items = [
    ...state.localPaths.map((path, index) => ({ type: 'path', path, index })),
    ...state.files.map((file, index) => ({ type: 'upload', file, index })),
  ];
  if (!items.length) {
    $('file-list').innerHTML = '<p class="empty-text">선택된 파일이 없습니다.</p>';
    return;
  }
  $('file-list').innerHTML = items.map((item) => item.type === 'path'
    ? `<div class="file-item"><span title="${escapeHtml(item.path)}">${escapeHtml(item.path)}</span><small>로컬 경로</small><button data-remove-path="${item.index}" aria-label="경로 제거">×</button></div>`
    : `<div class="file-item"><span>${escapeHtml(item.file.name)}</span><small>${formatSize(item.file.size)}</small><button data-remove-upload="${item.index}" aria-label="파일 제거">×</button></div>`).join('');
  document.querySelectorAll('[data-remove-path]').forEach((button) => button.onclick = () => { state.localPaths.splice(Number(button.dataset.removePath), 1); renderFiles(); });
  document.querySelectorAll('[data-remove-upload]').forEach((button) => button.onclick = () => { state.files.splice(Number(button.dataset.removeUpload), 1); renderFiles(); });
}

async function browse(path = '') {
  const response = await fetch(`/api/files/browse${path ? `?path=${encodeURIComponent(path)}` : ''}`);
  if (!response.ok) throw new Error((await response.json()).detail || '폴더를 열지 못했습니다.');
  state.browser.listing = await response.json();
  renderBrowser();
}

async function openBrowser(mode, settingsTarget = null, startPath = '') {
  state.browser = { mode, listing: null, selectedFiles: new Set(), selectedFolder: null, settingsTarget };
  $('browser-title').textContent = mode === 'files' ? '음원 파일 선택' : '음원 폴더 선택';
  $('browser-description').textContent = mode === 'files'
    ? '체크박스로 여러 파일을 선택하세요. 폴더는 두 번 클릭하거나 열기 버튼으로 이동합니다.'
    : '폴더를 한 번 클릭하면 선택하고, 두 번 클릭하면 해당 폴더로 이동합니다.';
  $('browser-confirm').textContent = mode === 'files' ? '파일 추가' : '폴더 추가';
  $('browser-dialog').hidden = false;
  document.body.classList.add('dialog-open');
  try { await browse(startPath); } catch (error) { closeDialog('browser-dialog'); toast(error.message); }
}

function closeDialog(id) {
  if (id === 'result-dialog') $('detail-audio')?.pause();
  $(id).hidden = true;
  if ($('browser-dialog').hidden && $('result-dialog').hidden) document.body.classList.remove('dialog-open');
}

function renderBrowser() {
  const listing = state.browser.listing;
  const folderMode = state.browser.mode === 'folder';
  if (!listing) return;
  $('browser-path').textContent = listing.displayPath;
  $('browser-path').title = listing.displayPath;
  $('browser-up').disabled = !listing.parent;
  $('browser-current').hidden = !folderMode || listing.path === '::drives';
  $('current-folder-name').textContent = listing.displayPath;
  $('select-current-folder').classList.toggle('selected', state.browser.selectedFolder === listing.path);
  const entries = folderMode ? listing.entries.filter((entry) => entry.type === 'directory') : listing.entries;
  $('browser-list').innerHTML = entries.length ? entries.map((entry) => {
    const selected = entry.type === 'file' ? state.browser.selectedFiles.has(entry.path) : state.browser.selectedFolder === entry.path;
    if (entry.type === 'directory') return `<button type="button" class="browser-entry directory ${selected ? 'selected' : ''}" data-directory="${escapeHtml(entry.path)}"><span class="browser-folder-icon">▸</span><span class="browser-entry-name">${escapeHtml(entry.name)}</span>${folderMode ? '<small>폴더</small>' : '<span class="browser-open-label">열기</span>'}</button>`;
    return `<label class="browser-entry file ${selected ? 'selected' : ''}"><input type="checkbox" data-file-path="${escapeHtml(entry.path)}" ${selected ? 'checked' : ''}><span class="browser-file-icon">♫</span><span class="browser-entry-name">${escapeHtml(entry.name)}</span><small>${formatSize(entry.size || 0)}</small></label>`;
  }).join('') : '<p class="browser-empty">표시할 폴더나 음원 파일이 없습니다.</p>';
  document.querySelectorAll('[data-directory]').forEach((button) => {
    button.onclick = () => { if (folderMode) { state.browser.selectedFolder = button.dataset.directory; renderBrowser(); } };
    button.ondblclick = () => browse(button.dataset.directory).catch((error) => toast(error.message));
    const open = button.querySelector('.browser-open-label');
    if (open) open.onclick = (event) => { event.stopPropagation(); browse(button.dataset.directory).catch((error) => toast(error.message)); };
  });
  document.querySelectorAll('[data-file-path]').forEach((checkbox) => checkbox.onchange = () => {
    if (checkbox.checked) state.browser.selectedFiles.add(checkbox.dataset.filePath);
    else state.browser.selectedFiles.delete(checkbox.dataset.filePath);
    renderBrowser();
  });
  const count = state.browser.selectedFiles.size;
  $('browser-selection').textContent = folderMode ? (state.browser.selectedFolder ? `선택: ${state.browser.selectedFolder}` : '선택된 폴더가 없습니다.') : (count ? `${count}개 파일 선택됨` : '선택된 파일이 없습니다.');
  $('browser-confirm').disabled = folderMode ? !state.browser.selectedFolder : count === 0;
}

function metricEntries(parameters) {
  const meta = parameters?.meta || {}, spectral = parameters?.spectral || {}, levels = parameters?.levels || {}, stereo = parameters?.stereo || {}, transient = parameters?.transient || {};
  return [
    ['재생 시간', meta.durationS == null ? '—' : `${meta.durationS.toFixed(1)}초`],
    ['코덱', meta.codec || '—'], ['샘플레이트', meta.sampleRate ? `${(meta.sampleRate / 1000).toFixed(1)} kHz` : '—'],
    ['채널', meta.channels ?? '—'], ['LUFS-I', levels.integratedLufs == null ? '—' : `${levels.integratedLufs.toFixed(2)} LUFS`],
    ['True Peak', levels.truePeakDbtp == null ? '—' : `${levels.truePeakDbtp.toFixed(2)} dBTP`], ['Crest', levels.crestDb == null ? '—' : `${levels.crestDb.toFixed(2)} dB`],
    ['Rolloff 99%', spectral.rolloff99Hz == null ? '—' : `${Math.round(spectral.rolloff99Hz)} Hz`], ['스펙트럼 기울기', spectral.tiltDbPerOctave == null ? '—' : `${spectral.tiltDbPerOctave.toFixed(3)} dB/oct`],
    ['스테레오 상관', stereo.correlation == null ? '—' : stereo.correlation.toFixed(3)], ['Onset', transient.onsetCount ?? '—'],
  ];
}

function scoreBand(score) {
  const value = Number(score);
  const [first, second, third, fourth] = state.settings.scoreBands.thresholds;
  if (value < first) return 'score-band-0';
  if (value < second) return 'score-band-20';
  if (value < third) return 'score-band-50';
  if (value < fourth) return 'score-band-80';
  return 'score-band-90';
}

function syncVariableHistoryCardHeights() {
  if (!state.settings.variableHistoryCards) return;
  document.querySelectorAll('.history-card').forEach((card) => {
    const height = `${Math.round(card.getBoundingClientRect().width)}px`;
    if (card.style.height !== height) card.style.height = height;
  });
}

function applyHistoryCardLayout() {
  const list = $('history-list');
  const size = Math.max(200, Math.min(360, Number(state.settings.historyCardSize) || 250));
  list.style.setProperty('--history-card-size', `${size}px`);
  list.classList.toggle('variable-history-cards', Boolean(state.settings.variableHistoryCards));
  document.querySelectorAll('.history-card').forEach((card) => { card.style.height = ''; });
  if (state.settings.variableHistoryCards) requestAnimationFrame(syncVariableHistoryCardHeights);
}

function compactConclusion(result) {
  if (result.status !== 'completed') return result.error || '분석 결과 없음';
  const score = Number(result.totalScore);
  if (!Number.isFinite(score)) return result.conclusion || '분석 결과 없음';
  const [first, second, third, fourth] = state.settings.scoreBands.thresholds;
  if (score < first) return 'AI 생성 흔적이 거의 없음';
  if (score < second) return 'AI 생성 흔적이 매우 약함';
  if (score < third) return 'AI 생성 흔적이 비교적 약함';
  if (score < fourth) return 'AI 생성 흔적이 비교적 강함';
  return 'AI 생성 흔적이 매우 강함';
}

function openReportDetails(name) {
  fetch(`/api/reports/${encodeURIComponent(name)}`).then((response) => {
    if (!response.ok) throw new Error('리포트를 읽지 못했습니다.');
    return response.json();
  }).then((report) => {
    $('result-dialog-title').textContent = name;
    const rows = Array.isArray(report.results) ? report.results : Array.isArray(report.pairs) ? report.pairs : [];
    const cards = rows.map((item, index) => {
      const label = item.name || item.sourceName || item.file || item.target || item.id || `항목 ${index + 1}`;
      const score = item.totalScore == null ? '' : `<strong class="report-score">${Number(item.totalScore).toFixed(1)}점</strong>`;
      const conclusion = item.totalScore == null ? (item.conclusion || item.status || item.description || item.output || '세부 결과가 저장되어 있습니다.') : compactConclusion(item);
      return `<article class="report-result"><div><h3>${escapeHtml(label)}</h3><p>${escapeHtml(conclusion)}</p></div>${score}</article>`;
    }).join('');
    const summary = report.summary || {};
    const meta = [`생성 시각: ${report.generatedAt || '—'}`, `항목 수: ${report.inputCount ?? rows.length}`, summary.completed == null ? '' : `완료 ${summary.completed}건`, summary.failed == null ? '' : `실패 ${summary.failed}건`].filter(Boolean).join(' · ');
    $('result-dialog-body').innerHTML = `<div class="report-overview"><h3>리포트 요약</h3><p>${escapeHtml(meta)}</p></div><section class="detail-section"><h3>파일별 결과</h3><div class="report-results">${cards || '<p class="empty-text">표시할 파일별 결과가 없습니다.</p>'}</div></section>`;
    $('result-dialog').hidden = false;
    document.body.classList.add('dialog-open');
  }).catch((error) => toast(error.message));
}

function openResult(result) {
  const panel = $('result-dialog-body');
  $('result-dialog-title').textContent = result.name || '측정 파라미터';
  if (result.status !== 'completed') {
    panel.innerHTML = `<p class="conclusion">${escapeHtml(result.error || '분석하지 못했습니다.')}</p>`;
  } else {
    const score = Number(result.totalScore || 0);
    const query = new URLSearchParams({ path: result.file || '' }).toString();
    const metrics = metricEntries(result.parameters).map(([label, value]) => `<div class="metric-box"><span>${label}</span><strong>${escapeHtml(value)}</strong></div>`).join('');
    const detectors = (result.detectors || []).map((item) => `<div class="detector-row"><span>${escapeHtml(item.label || item.name)}${item.includedInTotal === false ? ' · 평가만' : ''}</span><strong>${Math.round(Number(item.score || 0) * 100)}</strong></div>`).join('');
    panel.innerHTML = `<div class="result-overview"><div class="score-ring ${scoreBand(score)}" style="--score:${score}"><span>${score.toFixed(1)}</span><small>TOTAL</small></div><div><h3>최종 분석 점수</h3><p>${escapeHtml(compactConclusion(result))}</p><small>신뢰 지표 ${Number(result.confidence || 0).toFixed(1)} · 확률값이 아닌 잠정 종합 점수</small></div></div>
      <section class="source-information"><h3>원본 파일 정보</h3><p title="${escapeHtml(result.file)}">${escapeHtml(result.file)}</p></section>
      <section class="audio-visuals"><div class="audio-chart waveform-chart compare-waveform" id="waveform-chart"><svg id="detail-waveform-svg" viewBox="0 0 1000 100" preserveAspectRatio="none" role="img" aria-label="전체 음원 파형, 재생 위치 0%"><line class="waveform-loading" x1="0" x2="1000" y1="50" y2="50" /></svg></div><div class="compare-spectrogram"><div class="compare-frequency-axis"><span>22.1 kHz</span><span>16.5 kHz</span><span>11.0 kHz</span><span>5.5 kHz</span><span>0 Hz</span></div><div class="compare-spectrogram-body"><div class="audio-chart spectrogram-chart compare-spectrogram-plot"><img class="visual-base" src="/api/audio/spectrogram?${query}" alt="음원 스펙트로그램" loading="lazy"><div class="visual-played" id="spectrogram-played"><img src="/api/audio/spectrogram?${query}" alt="" loading="lazy"></div><div class="visual-playhead" id="spectrogram-playhead"></div></div><div class="compare-time-axis" id="compare-time-axis"><span>0:00</span><span>0:00</span><span>0:00</span><span>0:00</span><span>0:00</span></div></div><div class="compare-db-axis"><span>0</span><i></i><span>-100</span><small>dBFS</small></div></div><audio id="detail-audio" preload="metadata" src="/api/media?${query}"></audio><div class="audio-seek"><span id="audio-current">0:00</span><input id="audio-seek-slider" type="range" min="0" max="1000" value="0" step="1" aria-label="오디오 재생 위치"><span id="audio-duration">0:00</span></div><div class="audio-controls"><button type="button" data-audio-action="back" title="10초 뒤로" aria-label="10초 뒤로">&lt;&lt;</button><button type="button" class="audio-play" data-audio-action="play" title="재생" aria-label="재생"><svg viewBox="0 0 24 24"><path d="m9 6 10 6-10 6z"/></svg></button><button type="button" data-audio-action="forward" title="10초 앞으로" aria-label="10초 앞으로">&gt;&gt;</button><button type="button" class="audio-speed" data-audio-action="speed" title="재생 속도" aria-label="재생 속도">1x</button><span class="audio-volume-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M4 10v4h4l5 4V6l-5 4zM17 9a4 4 0 0 1 0 6M19 6a8 8 0 0 1 0 12"/></svg></span><input class="audio-volume" id="audio-volume-slider" type="range" min="0" max="1" step="0.01" value="1" aria-label="볼륨"></div></section>
      <section class="detail-section"><h3>측정 파라미터</h3><div class="details-grid">${metrics}</div></section>
      <section class="detail-section"><h3>탐지기별 결과</h3><div class="detector-detail">${detectors || '<p class="empty-text">탐지 결과가 없습니다.</p>'}</div></section>`;
    setupAudioControls(query);
  }
  $('result-dialog').hidden = false;
  document.body.classList.add('dialog-open');
}

function updateVisualProgress(fraction) {
  const safeFraction = Math.min(1, Math.max(0, fraction || 0));
  const seek = $('audio-seek-slider');
  if (seek) seek.style.background = `linear-gradient(to right, #b58bf3 0%, #b58bf3 ${safeFraction * 100}%, #100e14 ${safeFraction * 100}%, #100e14 100%)`;
  const svg = $('detail-waveform-svg');
  if (svg) {
    svg.querySelectorAll('.waveform-peak').forEach((line) => line.setAttribute('stroke', Number(line.dataset.position) <= safeFraction ? '#c8a7ff' : '#68547b'));
    const playhead = svg.querySelector('.waveform-svg-playhead');
    if (playhead) { playhead.setAttribute('x1', safeFraction * 1000); playhead.setAttribute('x2', safeFraction * 1000); }
  }
  ['waveform-playhead', 'spectrogram-playhead'].forEach((id) => { if ($(id)) $(id).style.left = `${safeFraction * 100}%`; });
  if ($('spectrogram-played')) {
    const played = $('spectrogram-played');
    played.style.width = `${safeFraction * 100}%`;
    const image = played.querySelector('img');
    if (image) image.style.width = `${played.parentElement.clientWidth}px`;
  }
}

async function loadWaveformPeaks(query) {
  try {
    const response = await fetch(`/api/audio/peaks?${query}&count=${state.settings.waveformPeaks}`);
    if (!response.ok) throw new Error('파형을 불러오지 못했습니다.');
    const payload = await response.json();
    const svg = $('detail-waveform-svg');
    if (!svg) return;
    const peaks = payload.peaks || [];
    svg.innerHTML = peaks.map((peak, index) => { const x = (index + 0.5) / peaks.length * 1000; const height = Math.max(2, Math.min(1, peak) * 46); const position = index / peaks.length; return `<line class="waveform-peak" data-position="${position}" x1="${x}" x2="${x}" y1="${50 - height}" y2="${50 + height}" stroke="#68547b" stroke-width="1.5" vector-effect="non-scaling-stroke"/>`; }).join('') + '<line class="waveform-svg-playhead" x1="0" x2="0" y1="0" y2="100" stroke="#fff" stroke-width="1" vector-effect="non-scaling-stroke"/>';
    updateVisualProgress(0);
  } catch { /* The spectrogram remains available when peak extraction fails. */ }
}

function setupAudioControls(query) {
  const audio = $('detail-audio');
  const seek = $('audio-seek-slider');
  if (!audio || !seek) return;
  void loadWaveformPeaks(query);
  const formatTime = (seconds) => {
    if (!Number.isFinite(seconds)) return '0:00';
    const minutes = Math.floor(seconds / 60);
    return `${minutes}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
  };
  const updateProgress = () => {
    seek.value = audio.duration ? String(Math.round((audio.currentTime / audio.duration) * 1000)) : '0';
    $('audio-current').textContent = formatTime(audio.currentTime);
    updateVisualProgress(audio.duration ? audio.currentTime / audio.duration : 0);
  };
  audio.addEventListener('loadedmetadata', () => { $('audio-duration').textContent = formatTime(audio.duration); const axis = $('compare-time-axis'); if (axis) axis.innerHTML = [0, .25, .5, .75, 1].map((fraction) => `<span>${formatTime(audio.duration * fraction)}</span>`).join(''); });
  audio.addEventListener('timeupdate', updateProgress);
  audio.addEventListener('play', () => { const button = $('result-dialog').querySelector('[data-audio-action="play"]'); button.innerHTML = '<svg viewBox="0 0 24 24"><path d="M8 6v12M16 6v12"/></svg>'; button.title = '일시정지'; button.setAttribute('aria-label', '일시정지'); });
  audio.addEventListener('pause', () => { const button = $('result-dialog').querySelector('[data-audio-action="play"]'); button.innerHTML = '<svg viewBox="0 0 24 24"><path d="m9 6 10 6-10 6z"/></svg>'; button.title = '재생'; button.setAttribute('aria-label', '재생'); });
  seek.addEventListener('input', () => { if (audio.duration) audio.currentTime = (Number(seek.value) / 1000) * audio.duration; });
  $('audio-volume-slider').addEventListener('input', (event) => { audio.volume = Number(event.target.value); });
  const speeds = [1, 1.25, 1.5, 2];
  document.querySelectorAll('[data-audio-action]').forEach((button) => button.addEventListener('click', () => {
    const action = button.dataset.audioAction;
    if (action === 'play') { if (audio.paused) void audio.play(); else audio.pause(); }
    if (action === 'back') audio.currentTime = Math.max(0, audio.currentTime - 10);
    if (action === 'forward') audio.currentTime = Math.min(audio.duration || Infinity, audio.currentTime + 10);
    if (action === 'speed') { const index = (speeds.indexOf(audio.playbackRate) + 1) % speeds.length; audio.playbackRate = speeds[index]; button.textContent = `${speeds[index]}x`; }
  }));
}

function renderHistory() {
  $('result-summary').textContent = state.history.length ? `파일별 분석 결과 ${state.history.length}개` : '저장된 분석 결과가 없습니다.';
  if (!state.history.length) {
    $('history-list').innerHTML = '<div class="empty-workspace"><div class="pulse-icon">⌁</div><h2>분석 이력이 없습니다</h2><p>분석을 시작하면 파일별 결과가 여기에 누적됩니다.</p></div>';
    applyHistoryCardLayout();
    return;
  }
  const filter = state.historyFilter;
  const sorting = state.historySort;
  const visible = state.history.filter((result) => filter === 'all' || result.status === filter);
  visible.sort((left, right) => {
    if (sorting === 'oldest') return String(left.generatedAt).localeCompare(String(right.generatedAt));
    if (sorting === 'favorite') return Number(Boolean(right.favorite)) - Number(Boolean(left.favorite)) || String(right.generatedAt).localeCompare(String(left.generatedAt));
    if (sorting === 'score-desc') return Number(right.totalScore ?? -1) - Number(left.totalScore ?? -1);
    if (sorting === 'score-asc') return Number(left.totalScore ?? 101) - Number(right.totalScore ?? 101);
    if (sorting === 'name-asc') return String(left.name || '').localeCompare(String(right.name || ''), 'ko');
    if (sorting === 'name-desc') return String(right.name || '').localeCompare(String(left.name || ''), 'ko');
    return String(right.generatedAt).localeCompare(String(left.generatedAt));
  });
  $('history-list').innerHTML = visible.map((result) => {
    const score = result.totalScore == null ? '—' : Number(result.totalScore).toFixed(1);
    const date = result.generatedAt ? new Date(result.generatedAt).toLocaleString('ko-KR', { dateStyle: 'short', timeStyle: 'short' }) : '';
    const favoriteLabel = result.favorite ? '좋아요 해제' : '좋아요 추가';
    const appliedDetectorCount = (result.detectors || []).filter((item) => Number.isFinite(Number(item.score))).length;
    return `<article class="result-card history-card"><button type="button" class="card-favorite${result.favorite ? ' active' : ''}" data-favorite-id="${escapeHtml(result.id)}" title="${favoriteLabel}" aria-label="${favoriteLabel}" aria-pressed="${Boolean(result.favorite)}"><svg viewBox="0 0 24 24"><path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8l1.1 1.1L12 21l7.8-7.5 1.1-1.1a5.5 5.5 0 0 0-.1-7.8Z"/></svg></button><div class="card-actions"><button type="button" data-result-id="${escapeHtml(result.id)}" title="세부 내용 보기" aria-label="세부 내용 보기"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="6"/><path d="m16 16 4 4"/></svg></button><button type="button" class="delete" data-delete-id="${escapeHtml(result.id)}" title="분석 이력 삭제" aria-label="분석 이력 삭제"><svg viewBox="0 0 24 24"><path d="M5 7h14M9 7V4h6v3m2 0-1 13H8L7 7m3 4v5m4-5v5"/></svg></button></div><div class="score-ring ${scoreBand(Number(result.totalScore || 0))}" style="--score:${Number(result.totalScore || 0)}"><span>${score}</span><small>TOTAL</small></div><div class="result-copy"><h3 title="${escapeHtml(result.name)}">${escapeHtml(result.name || '이름 없는 파일')}</h3><p class="conclusion">${escapeHtml(compactConclusion(result))}</p><small class="history-date">${escapeHtml(date)}</small><button type="button" class="parameter-button" data-result-id="${escapeHtml(result.id)}">측정 파라미터 보기</button></div><span class="card-detector-count" title="적용 탐지기 ${appliedDetectorCount}개" aria-label="적용 탐지기 ${appliedDetectorCount}개">${appliedDetectorCount}</span></article>`;
  }).join('');
  document.querySelectorAll('[data-result-id]').forEach((button) => button.onclick = () => openResult(state.history.find((item) => item.id === button.dataset.resultId)));
  document.querySelectorAll('[data-delete-id]').forEach((button) => button.onclick = () => removeHistory(button.dataset.deleteId));
  document.querySelectorAll('[data-favorite-id]').forEach((button) => button.onclick = () => setHistoryFavorite(button.dataset.favoriteId));
  applyHistoryCardLayout();
}

async function setHistoryFavorite(id) {
  const result = state.history.find((item) => item.id === id);
  if (!result) return;
  const favorite = !Boolean(result.favorite);
  try {
    const response = await fetch(`/api/history/favorite/${encodeURIComponent(id)}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ favorite }) });
    if (!response.ok) throw new Error((await response.json()).detail || '좋아요를 변경하지 못했습니다.');
    await loadHistory();
    toast(favorite ? '좋아요에 추가했습니다.' : '좋아요에서 제거했습니다.');
  } catch (error) { toast(error.message); }
}

async function removeHistory(id) {
  const result = state.history.find((item) => item.id === id);
  if (!window.confirm(`'${result?.name || '이 분석 이력'}'을 삭제할까요?`)) return;
  try {
    const response = await fetch(`/api/history/${encodeURIComponent(id)}`, { method: 'DELETE' });
    if (!response.ok) throw new Error((await response.json()).detail || '분석 이력을 삭제하지 못했습니다.');
    await loadHistory();
    toast('분석 이력을 삭제했습니다.');
  } catch (error) { toast(error.message); }
}

async function loadHistory() {
  try {
    const response = await fetch('/api/history');
    if (!response.ok) throw new Error('분석 이력을 불러오지 못했습니다.');
    state.history = (await response.json()).results || [];
    renderHistory();
  } catch (error) { $('history-list').innerHTML = `<p class="empty-text">${escapeHtml(error.message)}</p>`; }
}

async function analyze() {
  const manual = $('path-input').value.split(/\r?\n/).map((value) => value.trim()).filter(Boolean);
  const paths = [...new Set([...state.localPaths, ...manual])];
  if (!state.files.length && !paths.length) return toast('분석할 파일 또는 폴더를 선택해 주세요.');
  const button = $('run-button');
  button.disabled = true; button.textContent = '분석 중…'; $('top-status').textContent = '파일을 분석하고 있습니다';
  try {
    let completed = 0;
    if (state.files.length) {
      const form = new FormData(); state.files.forEach((file) => form.append('files', file, file.name));
      const response = await fetch('/api/analyze/upload', { method: 'POST', body: form });
      if (!response.ok) throw new Error((await response.json()).detail || '업로드 분석에 실패했습니다.');
      completed += (await response.json()).summary.completed;
    }
    if (paths.length) {
      const response = await fetch('/api/analyze', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ paths, recursive: state.settings.recursiveFolders }) });
      if (!response.ok) throw new Error((await response.json()).detail || '경로 분석에 실패했습니다.');
      completed += (await response.json()).summary.completed;
    }
    await loadHistory(); toast(`${completed}개 파일 분석을 완료했습니다.`);
  } catch (error) { toast(error.message || '분석 중 오류가 발생했습니다.'); }
  finally { button.disabled = false; button.textContent = '분석 시작'; $('top-status').textContent = ''; }
}

function resourceMetric(label, value, percent) {
  const level = percent >= 90 ? 'high' : percent >= 70 ? 'mid' : '';
  return `<span><b><em>${label}</em>${escapeHtml(value)}</b><i class="${level}" style="width:${Math.min(100, Math.max(0, percent))}%"></i></span>`;
}

async function loadResources() {
  try {
    const data = await (await fetch('/api/resources')).json();
    const gpu = data.gpu;
    const gpuName = gpu?.name ? gpu.name.replace(/^NVIDIA(?:\s+GeForce)?\s+/i, '') : '';
    $('gpu-name').textContent = gpu ? `${gpuName} · ${(gpu.totalMiB / 1024).toFixed(0)} GB` : 'GPU 없음';
    const vramPercent = gpu?.totalMiB ? (gpu.usedMiB / gpu.totalMiB) * 100 : 0;
    $('resource-usage').innerHTML = resourceMetric('GPU', `${Math.round(gpu?.percent || 0)}%`, gpu?.percent || 0) + resourceMetric('VRAM', `${Math.round(vramPercent)}%`, vramPercent) + resourceMetric('CPU', `${Math.round(data.cpu.percent)}%`, data.cpu.percent) + resourceMetric('RAM', `${Math.round(data.memory.percent)}%`, data.memory.percent);
  } catch { $('gpu-name').textContent = 'GPU 확인 불가'; $('resource-usage').innerHTML = '<span class="resource-unavailable">자원 상태 확인 불가</span>'; }
}

async function toggleDetector(name, enabled) {
  try {
    const response = await fetch(`/api/detectors/${encodeURIComponent(name)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled }),
    });
    if (!response.ok) throw new Error((await response.json()).detail || '탐지기 설정을 변경하지 못했습니다.');
    await loadHealth();
    toast(enabled ? '탐지기를 활성화했습니다.' : '탐지기를 비활성화했습니다.');
  } catch (error) { toast(error.message); }
}

async function loadHealth() {
  try {
    const data = await (await fetch('/health')).json(); state.detectors = data.detectors || [];
    state.detectors.sort((left, right) => String(left.label || left.name).localeCompare(String(right.label || right.name), 'ko', { sensitivity: 'base' }));
    const active = state.detectors.filter((item) => item.active).length;
    const installed = state.detectors.filter((item) => item.available).length;
    const total = state.detectors.length;
    $('health-text').textContent = `탐지기 ${active}/${installed}/${total} · FFmpeg ${data.ffmpeg ? '정상' : '확인 필요'}`; $('detector-count').textContent = `${active}/${installed}/${total}`;
    $('detector-grid').innerHTML = state.detectors.map((item) => { const status = !item.available ? '미설치' : item.active ? '활성' : '비활성'; return `<article class="model-card"><div class="model-card-head"><h3>${escapeHtml(item.label)}</h3><button type="button" class="detector-toggle ${item.active ? 'active' : ''}" data-detector-name="${escapeHtml(item.name)}" data-detector-enabled="${item.active ? 'true' : 'false'}" aria-label="${escapeHtml(item.label)} ${item.active ? '비활성화' : '활성화'}" aria-pressed="${item.active}" ${item.available ? '' : 'disabled'}><span></span></button></div><span class="status-badge ${item.active ? '' : 'off'}">${status}</span><p>${escapeHtml(item.notes)}</p>${item.available ? '' : `<small class="detector-reason">${escapeHtml(item.reason || '사용할 수 없습니다.')}</small><small class="detector-hint">${escapeHtml(item.installHint || '')}</small>`}<small>${escapeHtml(item.license)}</small></article>`; }).join('');
    document.querySelectorAll('[data-detector-name]').forEach((button) => { button.onclick = () => toggleDetector(button.dataset.detectorName, button.dataset.detectorEnabled !== 'true'); });
  } catch { $('health-dot').classList.add('bad'); $('health-text').textContent = '서버 연결 실패'; }
}

async function loadReports() {
  try { const data = await (await fetch('/api/reports')).json(); $('report-list').innerHTML = data.reports.length ? data.reports.map((item) => `<button type="button" class="report-item" data-report-name="${escapeHtml(item.name)}"><span>${escapeHtml(item.name)}</span><small>${formatSize(item.sizeBytes || 0)} · 클릭하여 요약 보기</small></button>`).join('') : '<p class="empty-text">저장된 리포트가 없습니다.</p>'; document.querySelectorAll('[data-report-name]').forEach((button) => { button.onclick = () => openReportDetails(button.dataset.reportName); }); }
  catch { $('report-list').innerHTML = '<p class="empty-text">리포트 목록을 불러오지 못했습니다.</p>'; }
}

function applySettings() {
  state.settings.scoreBands.colors.forEach((color, index) => document.documentElement.style.setProperty(`--score-color-${index}`, color));
  applyHistoryCardLayout();
  renderHistory();
}

function renderSettingsForm() {
  state.settings.scoreBands.thresholds.forEach((value, index) => { $(`score-threshold-${index}`).value = value; });
  state.settings.scoreBands.colors.forEach((value, index) => { $(`score-color-${index}`).value = value; });
  $('history-limit').value = state.settings.historyLimit;
  $('recursive-folders').checked = state.settings.recursiveFolders;
  $('history-card-size').value = String(state.settings.historyCardSize);
  $('history-card-mode').value = state.settings.variableHistoryCards ? 'variable' : 'fixed';
  $('waveform-peaks').value = String(state.settings.waveformPeaks);
  $('settings-music-path').value = state.settings.paths.music;
  $('settings-reports-path').value = state.settings.paths.reports;
  $('settings-models-path').value = state.settings.paths.models;
}

async function loadSettings() {
  try {
    const response = await fetch('/api/settings');
    if (!response.ok) throw new Error('설정을 불러오지 못했습니다.');
    state.settings = (await response.json()).settings || structuredClone(DEFAULT_SETTINGS);
    renderSettingsForm();
    applySettings();
  } catch (error) { toast(error.message); }
}

async function saveSettings(event) {
  event.preventDefault();
  const thresholds = [0, 1, 2, 3].map((index) => Number($(`score-threshold-${index}`).value));
  if (!(thresholds[0] < thresholds[1] && thresholds[1] < thresholds[2] && thresholds[2] < thresholds[3])) return toast('점수 경계는 작은 값부터 차례로 입력해 주세요.');
  const payload = {
    scoreBands: { thresholds, colors: [0, 1, 2, 3, 4].map((index) => $(`score-color-${index}`).value) },
    historyLimit: Number($('history-limit').value || 0),
    recursiveFolders: $('recursive-folders').checked,
    historyCardSize: Number($('history-card-size').value || 250),
    variableHistoryCards: $('history-card-mode').value === 'variable',
    waveformPeaks: Number($('waveform-peaks').value),
    paths: { music: $('settings-music-path').value, reports: $('settings-reports-path').value, models: $('settings-models-path').value },
  };
  const form = $('settings-form');
  form.classList.add('settings-saving');
  try {
    const response = await fetch('/api/settings', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    if (!response.ok) throw new Error((await response.json()).detail || '설정을 저장하지 못했습니다.');
    const result = await response.json();
    state.settings = result.settings;
    renderSettingsForm(); applySettings(); await loadHistory();
    toast(result.restartRequired ? '설정을 저장했습니다. 모델 폴더는 서버 재시작 후 적용됩니다.' : '설정을 저장했습니다.');
  } catch (error) { toast(error.message); }
  finally { form.classList.remove('settings-saving'); }
}

document.querySelectorAll('.nav-item[data-page]').forEach((button) => button.onclick = () => {
  const page = button.dataset.page; document.querySelectorAll('.nav-item[data-page]').forEach((node) => node.classList.toggle('active', node === button));
  document.querySelectorAll('[data-page-panel]').forEach((panel) => { panel.hidden = panel.dataset.pagePanel !== page; });
  [$('page-title').textContent, $('breadcrumb').textContent] = PAGE_META[page]; if (page === 'reports') loadReports(); if (page === 'settings') loadSettings();
});
$('pick-files').onclick = (event) => { event.stopPropagation(); openBrowser('files'); };
$('pick-folder').onclick = (event) => { event.stopPropagation(); openBrowser('folder'); };
$('clear-files').onclick = () => { state.files = []; state.localPaths = []; $('path-input').value = ''; renderFiles(); };
$('run-button').onclick = analyze; $('refresh-history').onclick = loadHistory;
document.querySelectorAll('[data-history-sort]').forEach((button) => button.onclick = () => {
  state.historySort = button.dataset.historySort;
  document.querySelectorAll('[data-history-sort]').forEach((node) => { const active = node === button; node.classList.toggle('active', active); node.setAttribute('aria-pressed', active); });
  renderHistory();
});
document.querySelectorAll('[data-history-filter]').forEach((button) => button.onclick = () => {
  state.historyFilter = button.dataset.historyFilter;
  document.querySelectorAll('[data-history-filter]').forEach((node) => { const active = node === button; node.classList.toggle('active', active); node.setAttribute('aria-pressed', active); });
  renderHistory();
});
$('browser-close').onclick = $('browser-cancel').onclick = () => closeDialog('browser-dialog');
$('browser-confirm').onclick = () => { if (state.browser.settingsTarget) { $(`settings-${state.browser.settingsTarget}-path`).value = state.browser.selectedFolder; } else { addLocalPaths(state.browser.mode === 'files' ? [...state.browser.selectedFiles] : [state.browser.selectedFolder]); } closeDialog('browser-dialog'); };
$('browser-up').onclick = () => state.browser.listing?.parent && browse(state.browser.listing.parent).catch((error) => toast(error.message));
$('select-current-folder').onclick = () => { state.browser.selectedFolder = state.browser.listing.path; renderBrowser(); };
$('result-dialog-close').onclick = $('result-dialog-confirm').onclick = () => closeDialog('result-dialog');
['browser-dialog', 'result-dialog'].forEach((id) => $(id).onclick = (event) => { if (event.target === $(id)) closeDialog(id); });
document.addEventListener('keydown', (event) => { if (event.key === 'Escape') { if (!$('result-dialog').hidden) closeDialog('result-dialog'); else if (!$('browser-dialog').hidden) closeDialog('browser-dialog'); } });
const dropZone = $('drop-zone'); dropZone.onclick = () => openBrowser('files'); dropZone.onkeydown = (event) => { if (event.key === 'Enter' || event.key === ' ') openBrowser('files'); };
['dragenter', 'dragover'].forEach((type) => dropZone.addEventListener(type, (event) => { event.preventDefault(); dropZone.classList.add('dragging'); }));
['dragleave', 'drop'].forEach((type) => dropZone.addEventListener(type, (event) => { event.preventDefault(); dropZone.classList.remove('dragging'); }));
dropZone.addEventListener('drop', (event) => addFiles(event.dataTransfer.files));
document.querySelectorAll('[data-settings-folder]').forEach((button) => button.onclick = () => { const target = button.dataset.settingsFolder; openBrowser('folder', target, $(`settings-${target}-path`).value); });
$('settings-form').addEventListener('submit', saveSettings);
new ResizeObserver(() => requestAnimationFrame(syncVariableHistoryCardHeights)).observe($('history-list'));
renderFiles(); loadHealth(); loadHistory(); loadSettings(); loadResources(); setInterval(loadResources, 3000);
