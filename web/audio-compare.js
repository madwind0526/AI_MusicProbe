(function () {
  const PLAY_ICON = '<svg viewBox="0 0 24 24"><path d="m9 6 10 6-10 6z"/></svg>';
  const PAUSE_ICON = '<svg viewBox="0 0 24 24"><path d="M8 6v12M16 6v12"/></svg>';

  function formatTime(seconds) {
    if (!Number.isFinite(seconds)) return '0:00';
    const minutes = Math.floor(seconds / 60);
    return `${minutes}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
  }

  function createAudioCompare(options) {
    const byId = (id) => document.getElementById(id);
    const dialog = byId('audio-compare-dialog');
    const slots = [{ path: '', sampleRate: 48000 }, { path: '', sampleRate: 48000 }];
    let activeRow = 0;
    let positionSeconds = 0;
    let playbackRate = 1;
    let volume = 1;
    let comparisonRequest = 0;
    const peakRequests = [0, 0];

    function audio(row) { return byId(`compare-audio-${row}`); }
    function activeAudio() { return activeRow ? audio(activeRow) : null; }

    function frequencyLabels(sampleRate) {
      const nyquist = (sampleRate || 48000) / 2;
      return [1, .75, .5, .25, 0].map((part) => part ? `${(nyquist * part / 1000).toFixed(1)} kHz` : '0 Hz');
    }

    function spectrogramMarkup(row, path, sampleRate) {
      if (!path) return '<div class="compare-spectrogram-body"><div class="compare-spectrogram-plot"><span class="compare-chart-status">음원을 불러오세요</span></div></div>';
      const query = `path=${encodeURIComponent(path)}`;
      const labels = frequencyLabels(sampleRate).map((label) => `<span>${label}</span>`).join('');
      return `<div class="compare-frequency-axis">${labels}</div><div class="compare-spectrogram-body"><div class="compare-spectrogram-plot"><img class="visual-base" src="/api/audio/spectrogram?${query}" alt="음원-${row} 스펙트로그램"><div class="visual-played" id="compare-spectrogram-played-${row}"><img src="/api/audio/spectrogram?${query}" alt=""></div><div class="visual-playhead" id="compare-spectrogram-playhead-${row}"></div></div><div class="compare-time-axis" id="compare-time-axis-${row}"><span>0:00</span><span>0:00</span><span>0:00</span><span>0:00</span><span>0:00</span></div></div><div class="compare-db-axis"><span>0</span><i></i><span>-100</span><small>dBFS</small></div>`;
    }

    function renderTimeAxis(row) {
      const target = byId(`compare-time-axis-${row}`);
      const duration = audio(row).duration;
      if (target && Number.isFinite(duration)) target.innerHTML = [0, .25, .5, .75, 1].map((part) => `<span>${formatTime(duration * part)}</span>`).join('');
      byId(`compare-duration-${row}`).textContent = formatTime(duration);
    }

    function updateButtons() {
      const current = activeAudio();
      const playing = Boolean(current && !current.paused);
      document.querySelectorAll('[data-compare-play]').forEach((button) => {
        const row = Number(button.dataset.comparePlay);
        const isPlaying = row === activeRow && playing;
        button.innerHTML = isPlaying ? PAUSE_ICON : PLAY_ICON;
        button.setAttribute('aria-label', `음원-${row} ${isPlaying ? '일시정지' : '재생'}`);
      });
      const main = dialog.querySelector('[data-compare-action="play"]');
      main.innerHTML = playing ? PAUSE_ICON : PLAY_ICON;
      main.title = playing ? '일시정지' : '재생';
      main.setAttribute('aria-label', playing ? '일시정지' : '재생');
      [1, 2].forEach((row) => byId(`compare-row-${row}`).classList.toggle('is-playing', row === activeRow && playing));
    }

    function updateVisuals() {
      const current = activeAudio();
      if (current && Number.isFinite(current.currentTime)) positionSeconds = current.currentTime;
      [1, 2].forEach((row) => {
        const duration = audio(row).duration || 0;
        const fraction = duration ? Math.min(1, positionSeconds / duration) : 0;
        const svg = byId(`compare-waveform-${row}`);
        svg.querySelectorAll('.waveform-peak').forEach((line) => line.setAttribute('stroke', Number(line.dataset.position) <= fraction ? '#c8a7ff' : '#68547b'));
        const playhead = svg.querySelector('.waveform-svg-playhead');
        if (playhead) { playhead.setAttribute('x1', fraction * 1000); playhead.setAttribute('x2', fraction * 1000); }
        const spectrogramHead = byId(`compare-spectrogram-playhead-${row}`);
        if (spectrogramHead) spectrogramHead.style.left = `${fraction * 100}%`;
        const played = byId(`compare-spectrogram-played-${row}`);
        if (played) {
          played.style.width = `${fraction * 100}%`;
          const image = played.querySelector('img');
          if (image) image.style.width = `${played.parentElement.clientWidth}px`;
        }
      });
      const duration = current?.duration || 0;
      byId('compare-current').textContent = formatTime(positionSeconds);
      byId('compare-total').textContent = formatTime(duration);
      const slider = byId('compare-seek-slider');
      const fraction = duration ? Math.min(1, positionSeconds / duration) : 0;
      slider.value = String(Math.round(fraction * 1000));
      slider.style.background = `linear-gradient(to right,#b58bf3 0%,#b58bf3 ${fraction * 100}%,#100e14 ${fraction * 100}%,#100e14 100%)`;
      updateButtons();
    }

    function pauseAll() {
      [1, 2].forEach((row) => audio(row).pause());
      updateButtons();
    }

    async function playRow(row) {
      const target = audio(row);
      if (!slots[row - 1].path) return;
      if (row === activeRow && !target.paused) { target.pause(); updateButtons(); return; }
      const previous = activeAudio();
      if (previous && Number.isFinite(previous.currentTime)) positionSeconds = previous.currentTime;
      pauseAll();
      activeRow = row;
      target.playbackRate = playbackRate;
      target.volume = volume;
      target.currentTime = Math.min(positionSeconds, Math.max(0, (target.duration || 0) - .02));
      try { await target.play(); } catch { options.toast('음원을 재생하지 못했습니다.'); }
      updateVisuals();
    }

    function seekTo(seconds) {
      positionSeconds = Math.max(0, seconds);
      [1, 2].forEach((row) => {
        const target = audio(row);
        if (Number.isFinite(target.duration)) target.currentTime = Math.min(positionSeconds, Math.max(0, target.duration - .02));
      });
      updateVisuals();
    }

    function formatDb(value) {
      const number = Number(value) || 0;
      return `${number >= 0 ? '+' : ''}${number.toFixed(1)} dB`;
    }

    function renderComparison(payload) {
      const panel = byId('compare-diff-panel');
      const grid = byId('compare-diff-grid');
      const summary = byId('compare-diff-summary');
      if (!panel || !grid || !summary) return;
      const bands = Array.isArray(payload?.bands) ? payload.bands : [];
      const max = Math.max(1, ...bands.map((item) => Math.abs(Number(item.changeDb) || 0)));
      grid.innerHTML = bands.map((item) => {
        const change = Number(item.changeDb) || 0;
        const width = Math.min(100, Math.abs(change) / max * 100);
        const direction = change >= 0 ? 'is-positive' : 'is-negative';
        return `<div class="compare-diff-item"><span class="compare-diff-label">${item.label}</span><span class="compare-diff-track"><i class="${direction}" style="width:${width}%"></i></span><strong>${formatDb(change)}</strong></div>`;
      }).join('');
      const level = payload?.summary || {};
      summary.textContent = `전체 음량 ${formatDb(level.rmsDb)} · 최고점 ${formatDb(level.peakDb)} · True peak ${formatDb(level.truePeakDb)}`;
      panel.hidden = false;
    }

    async function loadComparison() {
      if (!slots[0].path || !slots[1].path) return;
      const source = slots[0].path;
      const target = slots[1].path;
      const request = ++comparisonRequest;
      const query = `source=${encodeURIComponent(source)}&target=${encodeURIComponent(target)}`;
      try {
        const response = await fetch(`/api/audio/compare?${query}`);
        if (!response.ok) throw new Error('변화량을 계산하지 못했습니다.');
        const payload = await response.json();
        if (request !== comparisonRequest || slots[0].path !== source || slots[1].path !== target) return;
        renderComparison(payload);
      } catch (error) {
        if (request !== comparisonRequest) return;
        const panel = byId('compare-diff-panel');
        if (panel) panel.hidden = true;
        options.toast(error.message);
      }
    }

    async function loadPeaks(row, path) {
      const request = ++peakRequests[row - 1];
      const query = `path=${encodeURIComponent(path)}`;
      const response = await fetch(`/api/audio/peaks?${query}&count=${options.getPeakCount()}`);
      if (!response.ok) throw new Error('파형을 불러오지 못했습니다.');
      const payload = await response.json();
      if (request !== peakRequests[row - 1] || slots[row - 1].path !== path) return;
      slots[row - 1].sampleRate = payload.sampleRate || 48000;
      const peaks = payload.peaks || [];
      const svg = byId(`compare-waveform-${row}`);
      svg.innerHTML = peaks.map((peak, index) => {
        const x = (index + .5) / peaks.length * 1000;
        const height = Math.max(2, Math.min(1, peak) * 46);
        return `<line class="waveform-peak" data-position="${index / peaks.length}" x1="${x}" x2="${x}" y1="${50 - height}" y2="${50 + height}" stroke="#68547b" stroke-width="1.5" vector-effect="non-scaling-stroke"/>`;
      }).join('') + '<line class="waveform-svg-playhead" x1="0" x2="0" y1="0" y2="100" stroke="#fff" stroke-width="1" vector-effect="non-scaling-stroke"/>';
      byId(`compare-spectrogram-${row}`).innerHTML = spectrogramMarkup(row, path, slots[row - 1].sampleRate);
      renderTimeAxis(row);
      updateVisuals();
    }

    function selectPath(row, path) {
      if (!path) return;
      if (row === activeRow) pauseAll();
      slots[row - 1].path = path;
      byId(`compare-name-${row}`).textContent = path.split(/[\\/]/).pop() || path;
      byId(`compare-name-${row}`).title = path;
      const target = audio(row);
      target.src = `/api/media?path=${encodeURIComponent(path)}`;
      target.load();
      dialog.querySelector(`[data-compare-play="${row}"]`).disabled = false;
      if (!activeRow) activeRow = row;
      loadPeaks(row, path).catch((error) => options.toast(error.message));
      void loadComparison();
    }

    function open() {
      dialog.hidden = false;
      document.body.classList.add('dialog-open');
      updateVisuals();
    }

    function close() {
      pauseAll();
      dialog.hidden = true;
      if (options.onClose) options.onClose();
    }

    [1, 2].forEach((row) => {
      const target = audio(row);
      target.addEventListener('loadedmetadata', () => { renderTimeAxis(row); updateVisuals(); });
      target.addEventListener('timeupdate', () => { if (row === activeRow) updateVisuals(); });
      target.addEventListener('play', updateButtons);
      target.addEventListener('pause', updateButtons);
      target.addEventListener('ended', () => { positionSeconds = 0; updateVisuals(); });
    });
    document.querySelectorAll('[data-compare-load]').forEach((button) => button.addEventListener('click', () => options.pickFile(Number(button.dataset.compareLoad))));
    document.querySelectorAll('[data-compare-play]').forEach((button) => button.addEventListener('click', () => void playRow(Number(button.dataset.comparePlay))));
    byId('compare-seek-slider').addEventListener('input', (event) => { const duration = activeAudio()?.duration || 0; seekTo(duration * Number(event.target.value) / 1000); });
    byId('compare-volume').addEventListener('input', (event) => { volume = Number(event.target.value); [1, 2].forEach((row) => { audio(row).volume = volume; }); });
    document.querySelectorAll('[data-compare-action]').forEach((button) => button.addEventListener('click', () => {
      const action = button.dataset.compareAction;
      if (action === 'play') { const row = activeRow || (slots[0].path ? 1 : slots[1].path ? 2 : 0); if (row) void playRow(row); }
      if (action === 'back') seekTo(positionSeconds - 5);
      if (action === 'forward') seekTo(positionSeconds + 5);
      if (action === 'speed') { playbackRate = playbackRate >= 2 ? 1 : 2; [1, 2].forEach((row) => { audio(row).playbackRate = playbackRate; }); button.textContent = `${playbackRate}x`; }
    }));
    byId('audio-compare-close').addEventListener('click', close);
    byId('audio-compare-confirm').addEventListener('click', close);
    dialog.addEventListener('click', (event) => { if (event.target === dialog) close(); });

    return { open, close, selectPath, isOpen: () => !dialog.hidden };
  }

  window.createAudioCompare = createAudioCompare;
}());
