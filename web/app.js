const AUDIO_EXTENSIONS = /\.(wav|flac|mp3|m4a|aac|ogg|opus|aiff|aif)$/i;
const PAGE_META = { analyze: ['음원 분석', 'Analyze'], history: ['분석 이력', 'History'], detectors: ['탐지기', 'Detectors'], reports: ['리포트', 'Reports'], settings: ['설정', 'Settings'] };
const DEFAULT_SETTINGS = { scoreBands: { thresholds: [20, 50, 80, 90], colors: ['#ffffff', '#8ec5ff', '#ffe07a', '#ffad66', '#ff78c8'] }, historyLimit: 0, recursiveFolders: true, historyCardSize: 250, variableHistoryCards: true, paths: { music: '', reports: '', models: '' }, waveformPeaks: 180 };
const state = { files: [], localPaths: [], detectors: [], detectorOptions: null, history: [], reports: [], historySignature: '', analyzing: false, historySort: 'newest', historyFilter: 'all', reportSort: 'newest', settings: structuredClone(DEFAULT_SETTINGS), browser: { mode: 'files', listing: null, selectedFiles: new Set(), selectedFolder: null, settingsTarget: null, compareTarget: null } };
const $ = (id) => document.getElementById(id);
let audioCompare = null;

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

async function openBrowser(mode, settingsTarget = null, startPath = '', compareTarget = null) {
  state.browser = { mode, listing: null, selectedFiles: new Set(), selectedFolder: null, settingsTarget, compareTarget };
  $('browser-title').textContent = compareTarget ? `음원-${compareTarget} 선택` : mode === 'files' ? '음원 파일 선택' : '음원 폴더 선택';
  $('browser-description').textContent = compareTarget ? '비교할 음원 파일 하나를 선택하세요.' : mode === 'files'
    ? '체크박스로 여러 파일을 선택하세요. 폴더는 두 번 클릭하거나 열기 버튼으로 이동합니다.'
    : '폴더를 한 번 클릭하면 선택하고, 두 번 클릭하면 해당 폴더로 이동합니다.';
  $('browser-confirm').textContent = compareTarget ? '음원 선택' : mode === 'files' ? '파일 추가' : '폴더 추가';
  $('browser-dialog').hidden = false;
  document.body.classList.add('dialog-open');
  try { await browse(startPath); } catch (error) { closeDialog('browser-dialog'); toast(error.message); }
}

function closeDialog(id) {
  if (id === 'result-dialog') $('detail-audio')?.pause();
  $(id).hidden = true;
  if (['browser-dialog', 'result-dialog', 'detector-options-dialog', 'audio-compare-dialog'].every((key) => $(key).hidden)) document.body.classList.remove('dialog-open');
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
    if (checkbox.checked) {
      if (state.browser.compareTarget) state.browser.selectedFiles.clear();
      state.browser.selectedFiles.add(checkbox.dataset.filePath);
    }
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

function detectorCount(result) {
  // Counts the detectors that actually produced a score for this file. This is
  // genuinely variable: a run can include ArtifactNet (3) while a report built
  // without it stores only sonics + lofcz (2), so do not force it to a constant.
  return (result.detectors || []).filter((item) => Number.isFinite(Number(item.score))).length;
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

function frequencyAxisLabels(sampleRate) {
  // ffmpeg's showspectrumpic places 0 Hz at the bottom row and Nyquist at the top row
  // on a LINEAR frequency axis (verified: scale=lin and scale=log give identical rows).
  // So the stops are even fractions of Nyquist, and Nyquist must come from the file's
  // own sample rate instead of a hardcoded 22.1 kHz, which mislabels every 48 kHz source.
  const rate = Number(sampleRate);
  const nyquist = (rate > 0 ? rate : 44100) / 2;
  return [1, 0.75, 0.5, 0.25, 0].map((ratio, index) => {
    if (index === 4) return '0 Hz';
    const hz = nyquist * ratio;
    return hz >= 1000 ? `${(hz / 1000).toFixed(1)} kHz` : `${Math.round(hz)} Hz`;
  });
}

function detectorScoreSummary(result) {
  const analyzed = new Map((result.detectors || []).map((item) => [item.name, item]));
  const failed = new Set((result.detectorErrors || []).map((item) => item.name));
  const configured = state.detectors.length
    ? state.detectors
    : (state.detectorOptions?.detectors || []).map((item) => ({ ...item, available: false }));
  const catalog = configured.length ? configured : (result.detectors || []);
  const rows = catalog.map((detector) => {
    const item = analyzed.get(detector.name);
    const rawScore = Number(item?.score);
    let value = '미사용';
    let status = 'unused';
    if (item && Number.isFinite(rawScore)) {
      value = (rawScore * 100).toFixed(1);
      status = 'scored';
    } else if (failed.has(detector.name)) {
      value = '분석 실패';
      status = 'failed';
    } else if (!detector.available) {
      value = '미설치';
      status = 'unavailable';
    }
    const dotClass = status === 'scored' ? scoreBand(rawScore * 100) : 'muted';
    return `<tr><th scope="row"><span class="detector-score-name"><i class="detector-score-dot ${dotClass}" aria-hidden="true"></i>${escapeHtml(detector.label || detector.name)}</span></th><td class="detector-score-${status}">${escapeHtml(value)}</td></tr>`;
  }).join('');
  return `<section class="detector-score-summary" aria-labelledby="detector-score-summary-title"><h3 id="detector-score-summary-title">탐지기별 점수</h3><table><thead><tr><th scope="col">탐지기</th><th scope="col">점수</th></tr></thead><tbody>${rows}</tbody></table></section>`;
}

function shortTime(seconds) {
  const safe = Math.max(0, Number(seconds) || 0);
  return `${Math.floor(safe / 60)}:${String(Math.floor(safe % 60)).padStart(2, '0')}`;
}

function detectorTimeline(item, fallbackDuration) {
  const segments = (item.segments || []).map((segment) => ({
    start: Number(segment.startSeconds ?? segment.startS),
    end: Number(segment.endSeconds ?? segment.endS),
    score: segment.score == null ? null : Number(segment.score),
    error: segment.error || '',
  })).filter((segment) => Number.isFinite(segment.start) && Number.isFinite(segment.end) && segment.end > segment.start);
  if (!segments.length) return '';
  const duration = Math.max(Number(fallbackDuration) || 0, ...segments.map((segment) => segment.end));
  if (!(duration > 0)) return '';
  const laneEnds = [];
  const positioned = segments.map((segment) => {
    let lane = laneEnds.findIndex((end) => end <= segment.start);
    if (lane < 0) lane = laneEnds.length;
    laneEnds[lane] = segment.end;
    return { ...segment, lane };
  });
  const bars = positioned.map((segment, index) => {
    const left = Math.max(0, Math.min(100, segment.start / duration * 100));
    const width = Math.max(0.35, Math.min(100 - left, (segment.end - segment.start) / duration * 100));
    const score = segment.score == null || !Number.isFinite(segment.score) ? null : Math.max(0, Math.min(1, segment.score));
    const title = score == null
      ? `${index + 1}번 구간 · ${shortTime(segment.start)}–${shortTime(segment.end)} · 점수 없음${segment.error ? ` · ${segment.error}` : ''}`
      : `${index + 1}번 구간 · ${shortTime(segment.start)}–${shortTime(segment.end)} · ${(score * 100).toFixed(1)}점`;
    const style = `left:${left.toFixed(3)}%;width:${width.toFixed(3)}%;top:${1 + segment.lane * 7}px;${score == null ? '' : `--segment-opacity:${(.25 + score * .75).toFixed(4)};`}`;
    return `<i class="detector-segment${score == null ? ' invalid' : ''}" style="${style}" title="${escapeHtml(title)}" aria-label="${escapeHtml(title)}"></i>`;
  }).join('');
  return `<div class="detector-timeline" role="img" aria-label="${escapeHtml(item.label || item.name)} 구간별 탐지 점수"><div class="detector-timeline-track" style="--timeline-lanes:${laneEnds.length}">${bars}</div><div class="detector-timeline-axis"><span>0:00</span><span>${shortTime(duration)}</span></div></div>`;
}

// scoreInfo.components.method stores the internal versioned id (probe/file_analysis.py's
// METHOD_LABELS), so it needs its own Korean label here - the same 5 entries as the ensemble
// dropdown, keyed by that long id instead of the short method value.
const ENSEMBLE_METHOD_ID_LABELS = {
  'detector-geometric-mean-v1': '기하평균',
  'detector-arithmetic-mean-v1': '산술평균',
  'detector-median-v1': '중앙값',
  'detector-weighted-geometric-mean-v1': '가중 기하평균',
  'detector-robust-mean-v1': '이상치 제외 평균',
};

function scoreMethodHeading(result) {
  const components = result.scoreInfo?.components || {};
  const methodLabel = ENSEMBLE_METHOD_ID_LABELS[components.method] || components.method;
  return `최종 분석 점수${methodLabel ? ` (${escapeHtml(methodLabel)} 사용)` : ''}`;
}

function scoreMethodNote(result) {
  const components = result.scoreInfo?.components || {};
  const detectorLabel = (name) => (result.detectors || []).find((item) => item.name === name)?.label || name;
  const outliers = (components.outliersExcluded || []).map(detectorLabel);
  const excluded = (components.excluded || []).map(detectorLabel);
  const notes = [];
  if (outliers.length) notes.push(`이상치로 제외됨: ${outliers.join(', ')}`);
  if (excluded.length) notes.push(`평가만(Total 미반영): ${excluded.join(', ')}`);
  return notes.length ? `<small class="score-method-note">${escapeHtml(notes.join(' · '))}</small>` : '';
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
    const duration = Number(result.parameters?.meta?.durationS || 0);
    const detectors = (result.detectors || []).map((item) => {
      const tags = [];
      if (item.includedInTotal === false) tags.push('평가만');
      if (item.verdict) tags.push(item.verdict);
      if (item.aggregation) tags.push(item.aggregation);
      const optionText = Object.entries(item.options || {}).map(([key, value]) => `${(item.optionLabels || {})[key] || key} ${value}`).join(' · ');
      return `<div class="detector-result-block"><div class="detector-row"><span>${escapeHtml(item.label || item.name)}${tags.length ? ` · ${escapeHtml(tags.join(' · '))}` : ''}<small class="detector-row-options">${escapeHtml(optionText)}</small></span><strong>${Math.round(Number(item.score || 0) * 100)}</strong></div>${detectorTimeline(item, duration)}</div>`;
    }).join('');
    panel.innerHTML = `<div class="result-overview"><div class="score-ring ${scoreBand(score)}" style="--score:${score}"><span>${score.toFixed(1)}</span><small>TOTAL</small></div><div class="result-overview-copy"><h3>${scoreMethodHeading(result)}</h3><p>${escapeHtml(compactConclusion(result))}</p><small>신뢰 지표 ${Number(result.confidence || 0).toFixed(1)} · 확률값이 아닌 잠정 종합 점수</small>${scoreMethodNote(result)}</div>${detectorScoreSummary(result)}</div>
      <section class="source-information"><h3>원본 파일 정보</h3><p title="${escapeHtml(result.file)}">${escapeHtml(result.file)}</p></section>
      <section class="audio-visuals"><div class="audio-chart waveform-chart compare-waveform" id="waveform-chart"><svg id="detail-waveform-svg" viewBox="0 0 1000 100" preserveAspectRatio="none" role="img" aria-label="전체 음원 파형, 재생 위치 0%"><line class="waveform-loading" x1="0" x2="1000" y1="50" y2="50" /></svg></div><div class="compare-spectrogram"><div class="compare-frequency-axis">${frequencyAxisLabels(result.parameters?.meta?.sampleRate).map((label) => `<span>${label}</span>`).join('')}</div><div class="compare-spectrogram-body"><div class="audio-chart spectrogram-chart compare-spectrogram-plot"><img class="visual-base" src="/api/audio/spectrogram?${query}" alt="음원 스펙트로그램" loading="lazy"><div class="visual-played" id="spectrogram-played"><img src="/api/audio/spectrogram?${query}" alt="" loading="lazy"></div><div class="visual-playhead" id="spectrogram-playhead"></div></div><div class="compare-time-axis" id="compare-time-axis"><span>0:00</span><span>0:00</span><span>0:00</span><span>0:00</span><span>0:00</span></div></div><div class="compare-db-axis"><span>0</span><i></i><span>-100</span><small>dBFS</small></div></div><audio id="detail-audio" preload="metadata" src="/api/media?${query}"></audio><div class="audio-seek"><span id="audio-current">0:00</span><input id="audio-seek-slider" type="range" min="0" max="1000" value="0" step="1" aria-label="오디오 재생 위치"><span id="audio-duration">0:00</span></div><div class="audio-controls"><button type="button" data-audio-action="back" title="10초 뒤로" aria-label="10초 뒤로">&lt;&lt;</button><button type="button" class="audio-play" data-audio-action="play" title="재생" aria-label="재생"><svg viewBox="0 0 24 24"><path d="m9 6 10 6-10 6z"/></svg></button><button type="button" data-audio-action="forward" title="10초 앞으로" aria-label="10초 앞으로">&gt;&gt;</button><button type="button" class="audio-speed" data-audio-action="speed" title="재생 속도" aria-label="재생 속도">1x</button><span class="audio-volume-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M4 10v4h4l5 4V6l-5 4zM17 9a4 4 0 0 1 0 6M19 6a8 8 0 0 1 0 12"/></svg></span><input class="audio-volume" id="audio-volume-slider" type="range" min="0" max="1" step="0.01" value="1" aria-label="볼륨"></div></section>
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
  renderRecentList();
  if (!state.history.length) {
    $('history-list').innerHTML = '<div class="empty-workspace"><h2>분석 이력이 없습니다</h2><p>분석을 시작하면 파일별 결과가 여기에 누적됩니다.</p></div>';
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
    if (sorting === 'detectors-desc') return detectorCount(right) - detectorCount(left) || String(right.generatedAt).localeCompare(String(left.generatedAt));
    if (sorting === 'detectors-asc') return detectorCount(left) - detectorCount(right) || String(right.generatedAt).localeCompare(String(left.generatedAt));
    return String(right.generatedAt).localeCompare(String(left.generatedAt));
  });
  $('history-list').innerHTML = visible.map((result) => {
    const score = result.totalScore == null ? '—' : Number(result.totalScore).toFixed(1);
    const date = result.generatedAt ? new Date(result.generatedAt).toLocaleString('ko-KR', { dateStyle: 'short', timeStyle: 'short' }) : '';
    const favoriteLabel = result.favorite ? '좋아요 해제' : '좋아요 추가';
    const appliedDetectorCount = detectorCount(result);
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

function historySignature() {
  return state.history.map((item) => item.id).join('|');
}

async function loadHistory() {
  const scroller = document.querySelector('#history-view')?.closest('.workspace,.page-scroll');
  const keptScroll = scroller ? scroller.scrollTop : 0;
  try {
    const response = await fetch('/api/history');
    if (!response.ok) throw new Error('분석 이력을 불러오지 못했습니다.');
    state.history = (await response.json()).results || [];
    state.historySignature = historySignature();
    renderHistory();
    // Re-rendering the grid collapses its height, so put the reader back where
    // they were instead of snapping to the top on every background update.
    if (scroller && keptScroll) scroller.scrollTop = keptScroll;
  } catch (error) { $('history-list').innerHTML = `<p class="empty-text">${escapeHtml(error.message)}</p>`; }
}

async function pollHistorySignature() {
  if (document.visibilityState !== 'visible') return;
  if (state.analyzing) return;
  try {
    const response = await fetch('/api/history/signature', { cache: 'no-store' });
    if (!response.ok) return;
    const { signature } = await response.json();
    if (signature === state.historySignature) return;
    await loadHistory();
  } catch (error) { /* transient: the next tick retries */ }
}

function showAnalysisProgress(index, total, name) {
  const panel = $('analysis-progress');
  const sidebarPanel = $('sidebar-analysis-progress');
  const safeTotal = Math.max(0, Number(total) || 0);
  const safeIndex = Math.max(0, Math.min(safeTotal || Number(index) || 0, Number(index) || 0));
  panel.hidden = false;
  sidebarPanel.hidden = false;
  $('analysis-progress-count').textContent = safeTotal && safeIndex
    ? `전체 ${safeTotal}개 중 ${safeIndex}번째`
    : safeTotal ? `전체 ${safeTotal}개 · 준비 중` : '파일 확인 중';
  $('analysis-progress-name').textContent = name || (safeIndex ? '음원을 분석하고 있습니다.' : '분석을 준비하고 있습니다.');
  $('sidebar-analysis-progress-label').textContent = safeIndex ? '작업 진행 중…' : '작업 대기 중…';
  $('sidebar-analysis-progress-count').textContent = safeTotal ? `${safeIndex}/${safeTotal}` : '0/0';
  $('sidebar-analysis-progress-name').textContent = name || (safeIndex ? '음원을 분석하고 있습니다.' : '분석을 준비하고 있습니다.');
  const track = $('analysis-progress-track');
  track.setAttribute('aria-valuemax', String(safeTotal));
  track.setAttribute('aria-valuenow', String(safeIndex));
  const sidebarTrack = $('sidebar-analysis-progress-track');
  sidebarTrack.setAttribute('aria-valuemax', String(safeTotal));
  sidebarTrack.setAttribute('aria-valuenow', String(safeIndex));
  $('analysis-progress-bar').style.width = safeTotal ? `${safeIndex / safeTotal * 100}%` : '0%';
  $('sidebar-analysis-progress-bar').style.width = safeTotal ? `${safeIndex / safeTotal * 100}%` : '0%';
}

async function analyze() {
  const manual = $('path-input').value.split(/\r?\n/).map((value) => value.trim()).filter(Boolean);
  const paths = [...new Set([...state.localPaths, ...manual])];
  if (!state.files.length && !paths.length) return toast('분석할 파일 또는 폴더를 선택해 주세요.');
  const button = $('run-button');
  button.disabled = true; button.textContent = '분석 중…'; $('top-status').textContent = '파일을 분석하고 있습니다';
  const status = $('top-status');
  let completed = 0;
  const show = (index, total, name) => {
    const counter = total ? ` (${index}/${total})` : '';
    status.textContent = `음원 분석${counter} · ${name || (index ? '분석 중' : '준비 중')}`;
    button.textContent = `음원 분석${counter}`;
    showAnalysisProgress(index, total, name);
  };
  try {
    state.analyzing = true;
    if (state.files.length) {
      const form = new FormData(); state.files.forEach((file) => form.append('files', file, file.name));
      show(0, state.files.length, '업로드 확인 중');
      completed += (await streamProgress('/api/analyze/upload/progress', { method: 'POST', body: form }, show)).summary.completed;
    }
    if (paths.length) {
      show(0, 0, '폴더 탐색 중');
      completed += (await streamProgress('/api/analyze/progress', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ paths, recursive: state.settings.recursiveFolders }),
      }, show)).summary.completed;
    }
    await loadHistory(); toast(`${completed}개 파일 분석을 완료했습니다.`);
    $('analysis-progress-count').textContent = `전체 ${completed}개 완료`;
    $('analysis-progress-name').textContent = '모든 분석 작업을 완료했습니다.';
    $('analysis-progress-bar').style.width = '100%';
    $('sidebar-analysis-progress-label').textContent = '작업 완료';
    $('sidebar-analysis-progress-count').textContent = `${completed}/${completed}`;
    $('sidebar-analysis-progress-name').textContent = '모든 분석 작업을 완료했습니다.';
    $('sidebar-analysis-progress-bar').style.width = '100%';
  } catch (error) {
    const message = error.message || '분석 중 오류가 발생했습니다.';
    $('analysis-progress-name').textContent = message;
    $('sidebar-analysis-progress-label').textContent = '작업 오류';
    $('sidebar-analysis-progress-name').textContent = message;
    toast(message);
  }
  finally {
    state.analyzing = false; button.disabled = false; button.textContent = '분석 시작'; status.textContent = '';
    setTimeout(() => {
      if (!state.analyzing) {
        $('analysis-progress').hidden = true;
        $('sidebar-analysis-progress').hidden = true;
      }
    }, 4000);
  }
}

async function streamProgress(url, options, onProgress) {
  const response = await fetch(url, options);
  if (!response.ok || !response.body) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail || '분석 요청에 실패했습니다.');
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let result = null;
  let failure = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      const event = JSON.parse(line.slice(6));
      if (event.error) { failure = event.error; continue; }
      if (event.result) { result = event.result; continue; }
      onProgress(event.done, event.total, event.name);
    }
  }
  if (failure) throw new Error(failure);
  if (!result) throw new Error('분석 결과를 받지 못했습니다.');
  return result;
}

function resourceMetric(label, value, percent) {
  const level = percent >= 90 ? 'high' : percent >= 70 ? 'mid' : '';
  return `<span><b><em>${label}</em>${escapeHtml(value)}</b><i class="${level}" style="width:${Math.min(100, Math.max(0, percent))}%"></i></span>`;
}

async function loadResources() {
  // The top bar showing this is visible on every page, but the tab itself may not be
  // (minimized, backgrounded) - skip the request entirely rather than polling into the void.
  if (document.visibilityState !== 'visible') return;
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

const GEAR_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9 7 7M17 17l2.1 2.1M19.1 4.9 17 7M7 17l-2.1 2.1"/></svg>';

function detectorSchema(name) {
  return (state.detectorOptions?.detectors || []).find((item) => item.name === name) || null;
}

function optionValueLabel(option, value) {
  if (option.type !== 'choice') return String(value);
  const match = (option.choices || []).find((choice) => String(choice.value) === String(value));
  return match ? match.label : String(value);
}

function effectTagLabel(effect) {
  return (state.detectorOptions?.effectLabels || {})[effect] || '';
}

function detectorOptionChips(name, values) {
  const schema = detectorSchema(name);
  if (!schema) return '';
  const chips = schema.options.map((option) => {
    const raw = values?.[option.key];
    if (raw === undefined) return '';
    const unit = option.type === 'choice' ? '' : (option.unit ? ` ${option.unit}` : '');
    const text = `${option.label} ${optionValueLabel(option, raw)}${unit}`;
    return `<span class="${option.effect === 'verdict' ? 'total-off' : ''}" title="${escapeHtml(option.hint)}">${escapeHtml(text)}</span>`;
  });
  chips.push(values?.includedInTotal === false
    ? '<span class="total-off" title="원점수는 계산하지만 총점에는 넣지 않습니다.">평가만</span>'
    : '<span>Total 반영</span>');
  return `<div class="detector-card-flags">${chips.filter(Boolean).join('')}</div>`;
}

const RECENT_LIMIT = 5;

function renderRecentList() {
  const list = $('recent-list');
  const recent = [...state.history].slice(0, RECENT_LIMIT);
  $('history-count').textContent = String(state.history.length);
  if (!recent.length) { list.innerHTML = '<p class="sidebar-empty">최근 분석이 없습니다.<br/>분석을 시작해 보세요.</p>'; return; }
  list.innerHTML = recent.map((result) => {
    const failed = result.status === 'failed';
    const score = result.totalScore == null ? '—' : Number(result.totalScore).toFixed(1);
    return `<button type="button" class="recent-item${failed ? ' recent-failed' : ''}" data-recent-id="${escapeHtml(result.id)}" title="${escapeHtml(result.name || '이름 없는 파일')}"${result.favorite ? ' aria-label="좋아요 표시된 분석"' : ''}><span class="recent-dot"></span><span>${escapeHtml(result.name || '이름 없는 파일')}</span><em class="recent-score">${escapeHtml(score)}</em></button>`;
  }).join('');
  document.querySelectorAll('[data-recent-id]').forEach((button) => button.onclick = () => openResult(state.history.find((item) => item.id === button.dataset.recentId)));
}

function renderDetectorRail() {
  const rail = $('detector-rail');
  const installed = state.detectors.filter((item) => item.available);
  if (!installed.length) { rail.innerHTML = '<p class="sidebar-empty">설치된 탐지기가 없습니다.</p>'; return; }
  rail.innerHTML = installed.map((item) => `<div class="detector-rail-item${item.active ? '' : ' is-off'}" data-rail-name="${escapeHtml(item.name)}">
    <span class="detector-rail-name" title="${escapeHtml(item.label)}">${escapeHtml(item.label)}</span>
    <button type="button" class="detector-rail-gear" data-rail-options="${escapeHtml(item.name)}" title="${escapeHtml(item.label)} 설정" aria-label="${escapeHtml(item.label)} 설정">${GEAR_ICON}</button>
    <button type="button" class="detector-toggle ${item.active ? 'active' : ''}" data-rail-toggle="${escapeHtml(item.name)}" data-rail-enabled="${item.active ? 'true' : 'false'}" aria-label="${escapeHtml(item.label)} ${item.active ? '비활성화' : '활성화'}" aria-pressed="${item.active}"><span></span></button>
  </div>`).join('');
  document.querySelectorAll('[data-rail-options]').forEach((button) => button.onclick = () => openDetectorOptions(button.dataset.railOptions));
  document.querySelectorAll('[data-rail-toggle]').forEach((button) => button.onclick = () => toggleDetector(button.dataset.railToggle, button.dataset.railEnabled !== 'true'));
}

function renderDetectorGrid() {
  const grid = $('detector-grid');
  grid.innerHTML = state.detectors.map((item) => {
    const status = !item.available ? '미설치' : item.active ? '활성' : '비활성';
    const gear = item.available ? `<button type="button" class="detector-options-button" data-detector-options="${escapeHtml(item.name)}" title="${escapeHtml(item.label)} 설정" aria-label="${escapeHtml(item.label)} 설정">${GEAR_ICON}</button>` : '';
    const chips = item.available ? detectorOptionChips(item.name, item.options) : '';
    return `<article class="model-card${item.available && !item.active ? ' is-off' : ''}"><div class="model-card-head"><h3>${escapeHtml(item.label)}</h3><div class="model-card-actions">${gear}<button type="button" class="detector-toggle ${item.active ? 'active' : ''}" data-detector-name="${escapeHtml(item.name)}" data-detector-enabled="${item.active ? 'true' : 'false'}" aria-label="${escapeHtml(item.label)} ${item.active ? '비활성화' : '활성화'}" aria-pressed="${item.active}" ${item.available ? '' : 'disabled'}><span></span></button></div></div><span class="status-badge ${item.active ? '' : 'off'}">${status}</span><p>${escapeHtml(item.notes)}</p>${chips}${item.available ? '' : `<small class="detector-reason">${escapeHtml(item.reason || '사용할 수 없습니다.')}</small><small class="detector-hint">${escapeHtml(item.installHint || '')}</small>`}<small>${escapeHtml(item.license)}</small></article>`;
  }).join('');
  document.querySelectorAll('[data-detector-name]').forEach((button) => { button.onclick = () => toggleDetector(button.dataset.detectorName, button.dataset.detectorEnabled !== 'true'); });
  document.querySelectorAll('[data-detector-options]').forEach((button) => { button.onclick = () => openDetectorOptions(button.dataset.detectorOptions); });
}

function renderEnsemblePanel() {
  const options = state.detectorOptions;
  if (!options) return;
  const ensemble = options.ensemble;
  const select = $('ensemble-method');
  select.innerHTML = ensemble.methods.map((method) => `<option value="${escapeHtml(method.value)}">${escapeHtml(method.label)}</option>`).join('');
  select.value = ensemble.method;
  const active = ensemble.methods.find((method) => method.value === ensemble.method);
  $('ensemble-hint').textContent = active ? active.hint : '';
  // The dropdown only ever shows the *selected* method's hint above - this reference list keeps
  // every method's explanation and worked example visible at once, so switching methods to compare
  // them isn't required just to read how each one works.
  $('ensemble-methods-reference').innerHTML = ensemble.methods.map((method) => `<div class="ensemble-method-entry${method.value === ensemble.method ? ' active' : ''}"><h4>${escapeHtml(method.label)}${method.value === ensemble.method ? ' <span class="ensemble-method-current">현재 선택됨</span>' : ''}</h4><p>${escapeHtml(method.hint)}</p></div>`).join('');
  const weights = $('ensemble-weights');
  const weighted = ensemble.method === 'weightedGeometric';
  weights.hidden = !weighted;
  if (!weighted) return;
  weights.innerHTML = options.detectors.map((item) => {
    const value = ensemble.weights?.[item.name];
    return `<label for="ensemble-weight-${escapeHtml(item.name)}"><span>${escapeHtml(item.label)}</span><input id="ensemble-weight-${escapeHtml(item.name)}" type="number" min="0" max="10" step="0.1" data-ensemble-weight="${escapeHtml(item.name)}" value="${value === undefined ? '1' : value}"><small>0이면 Total에서 빠집니다.</small></label>`;
  }).join('');
}

function collectEnsemble() {
  const select = $('ensemble-method');
  const weights = {};
  document.querySelectorAll('[data-ensemble-weight]').forEach((input) => { weights[input.dataset.ensembleWeight] = Number(input.value); });
  return { method: select.value, weights };
}

function validateEnsemble(ensemble) {
  if (ensemble.method !== 'weightedGeometric') return;
  const included = (state.detectorOptions?.detectors || []).filter((item) => item.values?.includedInTotal !== false);
  if (included.length && !included.some((item) => Number(ensemble.weights?.[item.name] ?? 1) > 0)) {
    throw new Error('가중 기하평균은 Total에 반영할 탐지기 중 하나 이상의 가중치가 0보다 커야 합니다.');
  }
}

function optionRow(option, value) {
  const control = option.type === 'toggle'
    ? `<input type="checkbox" id="detector-opt-${escapeHtml(option.key)}" data-option-key="${escapeHtml(option.key)}" data-option-type="toggle" ${value ? 'checked' : ''}>`
    : option.type === 'number'
      ? `<input type="number" id="detector-opt-${escapeHtml(option.key)}" data-option-key="${escapeHtml(option.key)}" data-option-type="number" min="${option.min}" max="${option.max}" step="${option.step}" value="${value}">`
      : `<select id="detector-opt-${escapeHtml(option.key)}" data-option-key="${escapeHtml(option.key)}" data-option-type="choice">${option.choices.map((choice) => `<option value="${escapeHtml(choice.value)}" ${String(choice.value) === String(value) ? 'selected' : ''}>${escapeHtml(choice.label)}</option>`).join('')}</select>`;
  const tag = effectTagLabel(option.effect);
  return `<div class="option-row"><label for="detector-opt-${escapeHtml(option.key)}"><span>${escapeHtml(option.label)}${option.unit ? ` (${escapeHtml(option.unit)})` : ''}</span><small>${escapeHtml(option.hint)}</small></label><div class="option-control">${control}${tag ? `<span class="effect-tag ${option.effect === 'verdict' ? 'effect-verdict' : ''}">${escapeHtml(tag)}</span>` : ''}</div></div>`;
}

function syncDetectorOptionDependencies() {
  const dialog = $('detector-options-dialog');
  if (dialog.dataset.detectorName !== 'sonics') return;
  const body = $('detector-options-body');
  const aggregation = body.querySelector('[data-option-key="aggregation"]');
  const topK = body.querySelector('[data-option-key="topK"]');
  if (!aggregation || !topK) return;
  const disabled = aggregation.value !== 'topk';
  topK.disabled = disabled;
  topK.closest('.option-row')?.classList.toggle('option-disabled', disabled);
}

function openDetectorOptions(name) {
  const schema = detectorSchema(name);
  if (!schema) return toast('탐지기 설정을 불러오지 못했습니다.');
  const slot = state.detectors.find((item) => item.name === name);
  const values = schema.values || {};
  $('detector-options-title').textContent = schema.label;
  $('detector-options-subtitle').textContent = '저장하면 다음 분석부터 적용됩니다.';
  $('detector-options-note').textContent = slot?.available ? '저장하면 다음 분석부터 적용됩니다.' : (slot?.reason || '가중치가 없어 점수는 계산되지 않습니다.');
  const locked = `<section class="detector-options-section"><h3>모델 고정값 <code>변경 불가</code></h3><p>${escapeHtml(schema.lockedNote || '')}</p><div class="locked-list">${(schema.locked || []).map((item) => `<div><span>${escapeHtml(item.label)}</span><strong>${escapeHtml(item.value)}</strong></div>`).join('')}</div></section>`;
  const rows = schema.options.map((option) => optionRow(option, values[option.key])).join('');
  const include = schema.includedInTotalOption;
  const body = `${locked}<section class="detector-options-section"><h3>Total 반영</h3>${optionRow(include, values.includedInTotal)}</section>${rows ? `<section class="detector-options-section"><h3>분석 옵션</h3>${rows}</section>` : ''}${slot && !slot.available ? `<div class="detector-unavailable">${escapeHtml(slot.reason || '가중치가 없습니다.')}<br>${escapeHtml(slot.installHint || '')}</div>` : ''}`;
  $('detector-options-body').innerHTML = body;
  $('detector-options-dialog').dataset.detectorName = name;
  $('detector-options-dialog').hidden = false;
  document.body.classList.add('dialog-open');
  syncDetectorOptionDependencies();
  $('detector-options-body').querySelector('[data-option-key="aggregation"]')?.addEventListener('change', syncDetectorOptionDependencies);
}

function collectDetectorOptions() {
  const name = $('detector-options-dialog').dataset.detectorName;
  const schema = detectorSchema(name);
  const values = { ...(schema?.values || {}) };
  $('detector-options-body').querySelectorAll('[data-option-key]').forEach((input) => {
    const key = input.dataset.optionKey;
    if (input.dataset.optionType === 'toggle') values[key] = input.checked;
    else if (input.dataset.optionType === 'number') values[key] = Number(input.value);
    else values[key] = input.value;
  });
  return { [name]: values };
}

async function putDetectorOptions(detectors, ensemble) {
  validateEnsemble(ensemble);
  const response = await fetch('/api/detector-options', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ detectors, ensemble }) });
  if (!response.ok) throw new Error((await response.json()).detail || '탐지기 설정을 저장하지 못했습니다.');
  return response.json();
}

async function saveDetectorOptions() {
  const name = $('detector-options-dialog').dataset.detectorName;
  const body = $('detector-options-body');
  const label = detectorSchema(name)?.label || name;
  body.classList.add('settings-saving');
  try {
    await putDetectorOptions(collectDetectorOptions(), collectEnsemble());
    await loadDetectorOptions();
    await loadHealth();
    $('detector-options-dialog').hidden = true;
    if ($('browser-dialog').hidden) document.body.classList.remove('dialog-open');
    toast(`${label} 설정을 저장했습니다. 다음 분석부터 적용됩니다.`);
  } catch (error) { toast(error.message); }
  finally { body.classList.remove('settings-saving'); }
}

async function saveEnsemble() {
  try {
    await putDetectorOptions({}, collectEnsemble());
    await loadDetectorOptions();
    await loadHealth();
    toast('Total 결합 방식을 저장했습니다. 다음 분석부터 적용됩니다.');
  } catch (error) { toast(error.message); }
}

async function loadDetectorOptions() {
  try {
    const response = await fetch('/api/detector-options');
    if (!response.ok) throw new Error('탐지기 설정을 불러오지 못했습니다.');
    state.detectorOptions = await response.json();
    renderEnsemblePanel();
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
    renderDetectorRail();
    renderDetectorGrid();
  } catch { $('health-dot').classList.add('bad'); $('health-text').textContent = '서버 연결 실패'; }
}

function renderReports() {
  const reports = [...state.reports];
  reports.sort((left, right) => {
    if (state.reportSort === 'oldest') return String(left.createdAt).localeCompare(String(right.createdAt));
    if (state.reportSort === 'name-asc') return String(left.name).localeCompare(String(right.name), 'ko');
    if (state.reportSort === 'name-desc') return String(right.name).localeCompare(String(left.name), 'ko');
    if (state.reportSort === 'size-desc') return Number(right.sizeBytes || 0) - Number(left.sizeBytes || 0);
    if (state.reportSort === 'size-asc') return Number(left.sizeBytes || 0) - Number(right.sizeBytes || 0);
    return String(right.createdAt).localeCompare(String(left.createdAt));
  });
  $('report-list').innerHTML = reports.length ? reports.map((item) => {
    const created = item.createdAt ? new Date(item.createdAt).toLocaleString('ko-KR', { dateStyle: 'medium', timeStyle: 'short' }) : '생성 시각 정보 없음';
    const encodedName = encodeURIComponent(item.name);
    return `<article class="report-item"><button type="button" class="report-open" data-open-report="${escapeHtml(item.name)}"><span>${escapeHtml(item.name)}</span><small>${escapeHtml(created)} · ${formatSize(item.sizeBytes || 0)} · 클릭하여 요약 보기</small></button><a class="report-export" href="/api/reports/${encodedName}/export?format=json" download title="JSON 내보내기" aria-label="${escapeHtml(item.name)} JSON 내보내기">JSON</a><a class="report-export" href="/api/reports/${encodedName}/export?format=csv" download title="CSV 내보내기" aria-label="${escapeHtml(item.name)} CSV 내보내기">CSV</a><button type="button" class="report-delete" data-delete-report="${escapeHtml(item.name)}" title="리포트 삭제" aria-label="${escapeHtml(item.name)} 삭제"><svg viewBox="0 0 24 24"><path d="M5 7h14M9 7V4h6v3m2 0-1 13H8L7 7m3 4v5m4-5v5"/></svg></button></article>`;
  }).join('') : '<p class="empty-text">저장된 리포트가 없습니다.</p>';
  document.querySelectorAll('[data-open-report]').forEach((button) => { button.onclick = () => openReportDetails(button.dataset.openReport); });
  document.querySelectorAll('[data-delete-report]').forEach((button) => { button.onclick = () => removeReport(button.dataset.deleteReport); });
}

async function loadReports() {
  try {
    const response = await fetch('/api/reports');
    if (!response.ok) throw new Error('리포트 목록을 불러오지 못했습니다.');
    state.reports = (await response.json()).reports || [];
    renderReports();
  } catch (error) { $('report-list').innerHTML = `<p class="empty-text">${escapeHtml(error.message)}</p>`; }
}

async function removeReport(name) {
  if (!window.confirm(`'${name}' 리포트를 삭제할까요?`)) return;
  try {
    const response = await fetch(`/api/reports/${encodeURIComponent(name)}`, { method: 'DELETE' });
    if (!response.ok) throw new Error((await response.json()).detail || '리포트를 삭제하지 못했습니다.');
    await loadReports();
    toast('리포트를 삭제했습니다.');
  } catch (error) { toast(error.message); }
}

function applySettings() {
  state.settings.scoreBands.colors.forEach((color, index) => document.documentElement.style.setProperty(`--score-color-${index}`, color));
  applyHistoryCardLayout();
  renderHistory();
}

function renderSettingsForm() {
  state.settings.scoreBands.thresholds.forEach((value, index) => { $(`score-threshold-${index}`).value = value; });
  updateScoreRangeStarts();
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

function updateScoreRangeStarts() {
  [1, 2, 3, 4].forEach((index) => {
    const value = $(`score-threshold-${index - 1}`)?.value;
    if ($(`score-range-start-${index}`)) $(`score-range-start-${index}`).textContent = value || '—';
  });
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

const HISTORY_TOOLBAR = `<div class="history-toolbar" role="group" aria-label="분석 이력 새로고침, 정렬과 필터">
  <button type="button" id="refresh-history" title="새로고침" aria-label="새로고침"><svg viewBox="0 0 24 24"><path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/></svg></button>
  <i class="toolbar-separator" aria-hidden="true"></i>
  <button type="button" class="active" data-history-sort="newest" title="최신 분석순" aria-label="최신 분석순" aria-pressed="true"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8"/><path d="M12 7v5l3 2"/></svg></button>
  <button type="button" data-history-sort="oldest" title="오래된 분석순" aria-label="오래된 분석순" aria-pressed="false"><svg viewBox="0 0 24 24"><path d="M4 12a8 8 0 1 0 2-5.3L4 9"/><path d="M4 4v5h5M12 7v5l3 2"/></svg></button>
  <button type="button" data-history-sort="favorite" title="좋아요 우선" aria-label="좋아요 우선" aria-pressed="false"><svg viewBox="0 0 24 24"><path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8l1.1 1.1L12 21l7.8-7.5 1.1-1.1a5.5 5.5 0 0 0-.1-7.8Z"/></svg></button>
  <button type="button" data-history-sort="score-desc" title="점수 높은순" aria-label="점수 높은순" aria-pressed="false"><svg viewBox="0 0 24 24"><path d="M7 4v16m-3-3 3 3 3-3M14 7h6M14 12h4M14 17h2"/></svg></button>
  <button type="button" data-history-sort="score-asc" title="점수 낮은순" aria-label="점수 낮은순" aria-pressed="false"><svg viewBox="0 0 24 24"><path d="M7 20V4m-3 3 3-3 3 3M14 7h2M14 12h4M14 17h6"/></svg></button>
  <button type="button" data-history-sort="name-asc" title="제목 오름차순" aria-label="제목 오름차순" aria-pressed="false"><svg viewBox="0 0 24 24"><path d="m4 16 4-8 4 8M6 13h4M15 7h5l-5 10h5"/></svg></button>
  <button type="button" data-history-sort="name-desc" title="제목 내림차순" aria-label="제목 내림차순" aria-pressed="false"><svg viewBox="0 0 24 24"><path d="M4 7h5L4 17h5m6-1 3-8 3 8m-5-3h4"/></svg></button>
  <button type="button" data-history-sort="detectors-desc" title="탐지기 많은순" aria-label="탐지기 많은순" aria-pressed="false"><svg viewBox="0 0 24 24"><rect x="3.5" y="3.5" width="5" height="5" rx="1"/><rect x="3.5" y="9.5" width="5" height="5" rx="1"/><rect x="3.5" y="15.5" width="5" height="5" rx="1"/><path d="M16 5v14m-3-3 3 3 3-3"/></svg></button>
  <button type="button" data-history-sort="detectors-asc" title="탐지기 적은순" aria-label="탐지기 적은순" aria-pressed="false"><svg viewBox="0 0 24 24"><rect x="3.5" y="3.5" width="5" height="5" rx="1"/><rect x="3.5" y="9.5" width="5" height="5" rx="1"/><rect x="3.5" y="15.5" width="5" height="5" rx="1"/><path d="M16 19V5m-3 3 3-3 3 3"/></svg></button>
  <i class="toolbar-separator" aria-hidden="true"></i>
  <button type="button" class="active" data-history-filter="all" title="전체 결과" aria-label="전체 결과" aria-pressed="true"><svg viewBox="0 0 24 24"><rect x="4" y="4" width="6" height="6" rx="1"/><rect x="14" y="4" width="6" height="6" rx="1"/><rect x="4" y="14" width="6" height="6" rx="1"/><rect x="14" y="14" width="6" height="6" rx="1"/></svg></button>
  <button type="button" data-history-filter="completed" title="분석 완료만" aria-label="분석 완료만" aria-pressed="false"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8"/><path d="m8 12 3 3 5-6"/></svg></button>
  <button type="button" data-history-filter="failed" title="분석 실패만" aria-label="분석 실패만" aria-pressed="false"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8"/><path d="m9 9 6 6m0-6-6 6"/></svg></button>
</div>`;

// One history view serves both the analyze page's right column and the
// standalone history page. Reparenting keeps a single #history-list so the
// cards, sort state and delete handlers never have to exist twice.
const historyView = document.createElement('div');
historyView.className = 'history-workspace';
historyView.id = 'history-view';
historyView.innerHTML = `<div class="history-heading"><div><span class="eyebrow">ANALYSIS HISTORY</span><h2>분석 이력</h2><p id="result-summary">저장된 분석 결과를 불러오는 중입니다.</p></div>${HISTORY_TOOLBAR}</div><div class="history-list" id="history-list"></div>`;
$('history-slot').append(historyView);

function mountHistoryView(page) {
  const standalone = page === 'history';
  const target = standalone ? $('history-slot-standalone') : $('history-slot');
  if (historyView.parentElement !== target) target.append(historyView);
  historyView.classList.toggle('standalone', standalone);
}

function navigate(page) {
  document.querySelectorAll('.nav-item[data-page],.brand[data-page]').forEach((node) => node.classList.toggle('active', node.dataset.page === page));
  document.querySelectorAll('[data-page-panel]').forEach((panel) => { panel.hidden = panel.dataset.pagePanel !== page; });
  [$('page-title').textContent, $('breadcrumb').textContent] = PAGE_META[page] || ['', ''];
  if (page === 'analyze' || page === 'history') mountHistoryView(page);
  if (page === 'reports') loadReports();
  if (page === 'settings') loadSettings();
  if (page === 'detectors') loadDetectorOptions();
  if (page === 'history') loadHistory();
}

document.querySelectorAll('.nav-item[data-page],.brand[data-page]').forEach((button) => button.onclick = () => navigate(button.dataset.page));
$('pick-files').onclick = (event) => { event.stopPropagation(); openBrowser('files'); };
$('pick-folder').onclick = (event) => { event.stopPropagation(); openBrowser('folder'); };
$('clear-files').onclick = () => { state.files = []; state.localPaths = []; $('path-input').value = ''; renderFiles(); };
$('run-button').onclick = analyze; $('refresh-history').onclick = loadHistory; $('recent-refresh').onclick = loadHistory;
$('refresh-reports').onclick = loadReports;
document.querySelectorAll('[data-report-sort]').forEach((button) => button.onclick = () => {
  state.reportSort = button.dataset.reportSort;
  document.querySelectorAll('[data-report-sort]').forEach((node) => { const active = node === button; node.classList.toggle('active', active); node.setAttribute('aria-pressed', active); });
  renderReports();
});
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
$('detector-options-close').onclick = $('detector-options-cancel').onclick = () => closeDialog('detector-options-dialog');
$('detector-options-save').onclick = saveDetectorOptions;
$('ensemble-save').onclick = saveEnsemble;
$('browser-confirm').onclick = () => {
  if (state.browser.compareTarget) audioCompare?.selectPath(state.browser.compareTarget, [...state.browser.selectedFiles][0]);
  else if (state.browser.settingsTarget) $(`settings-${state.browser.settingsTarget}-path`).value = state.browser.selectedFolder;
  else addLocalPaths(state.browser.mode === 'files' ? [...state.browser.selectedFiles] : [state.browser.selectedFolder]);
  closeDialog('browser-dialog');
};
$('browser-up').onclick = () => state.browser.listing?.parent && browse(state.browser.listing.parent).catch((error) => toast(error.message));
$('select-current-folder').onclick = () => { state.browser.selectedFolder = state.browser.listing.path; renderBrowser(); };
$('result-dialog-close').onclick = $('result-dialog-confirm').onclick = () => closeDialog('result-dialog');
['browser-dialog', 'result-dialog', 'detector-options-dialog'].forEach((id) => $(id).onclick = (event) => { if (event.target === $(id)) closeDialog(id); });
document.addEventListener('keydown', (event) => { if (event.key === 'Escape') { if (!$('browser-dialog').hidden) closeDialog('browser-dialog'); else if (!$('result-dialog').hidden) closeDialog('result-dialog'); else if (!$('detector-options-dialog').hidden) closeDialog('detector-options-dialog'); else if (audioCompare?.isOpen()) audioCompare.close(); } });
const dropZone = $('drop-zone'); dropZone.onclick = () => openBrowser('files'); dropZone.onkeydown = (event) => { if (event.key === 'Enter' || event.key === ' ') openBrowser('files'); };
['dragenter', 'dragover'].forEach((type) => dropZone.addEventListener(type, (event) => { event.preventDefault(); dropZone.classList.add('dragging'); }));
['dragleave', 'drop'].forEach((type) => dropZone.addEventListener(type, (event) => { event.preventDefault(); dropZone.classList.remove('dragging'); }));
dropZone.addEventListener('drop', (event) => addFiles(event.dataTransfer.files));
document.querySelectorAll('[data-settings-folder]').forEach((button) => button.onclick = () => { const target = button.dataset.settingsFolder; openBrowser('folder', target, $(`settings-${target}-path`).value); });
$('settings-form').addEventListener('submit', saveSettings);
document.querySelectorAll('[id^="score-threshold-"]').forEach((input) => input.addEventListener('input', updateScoreRangeStarts));
audioCompare = window.createAudioCompare({
  pickFile: (row) => openBrowser('files', null, state.settings.paths.music, row),
  getPeakCount: () => state.settings.waveformPeaks,
  toast,
  onClose: () => { if (['browser-dialog', 'result-dialog', 'detector-options-dialog'].every((key) => $(key).hidden)) document.body.classList.remove('dialog-open'); },
});
$('audio-compare-open').onclick = () => audioCompare.open();
new ResizeObserver(() => requestAnimationFrame(syncVariableHistoryCardHeights)).observe($('history-list'));
renderFiles(); loadDetectorOptions(); loadHealth(); loadHistory(); loadSettings(); loadResources(); setInterval(loadResources, 3000);

// Pick up analyses finished outside this tab (API, CLI, another window) by
// polling a cheap token rather than the full result payload.
setInterval(pollHistorySignature, 2500);
document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') pollHistorySignature(); });
