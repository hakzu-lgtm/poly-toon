/* ===== 웹툰 메이커 — 앱 코어 ===== */

const API = {
  async _parseError(r) {
    try {
      const data = await r.json();
      return data.detail || JSON.stringify(data);
    } catch {
      return await r.text() || `HTTP ${r.status}`;
    }
  },
  async get(path) {
    const r = await fetch(path);
    if (!r.ok) throw new Error(await this._parseError(r));
    return r.json();
  },
  async post(path, body) {
    const r = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(await this._parseError(r));
    return r.json();
  },
  async put(path, body) {
    const r = await fetch(path, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(await this._parseError(r));
    return r.json();
  },
};

const Toast = {
  show(message, type = 'info', duration = 4000) {
    const container = document.getElementById('toastContainer');
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.textContent = message;
    container.appendChild(el);
    setTimeout(() => {
      el.classList.add('fade-out');
      setTimeout(() => el.remove(), 300);
    }, duration);
  },
  success(msg) { this.show(msg, 'success'); },
  error(msg) { this.show(msg, 'error', 6000); },
  info(msg) { this.show(msg, 'info'); },
};

const App = {
  currentStage: 0,
  totalStages: 7,
  config: null,
  story: null,

  async init() {
    this.bindNav();
    this.bindSteps();
    this.initStage0();
    this.initStage1();
    this.initStage2();
    this.initStage3();
    this.initStage4();
    this.initStage5();
    this.initStage6();
    this.initStage7();
    this.initProjectButtons();
    this.showStage(0);
    await this.loadConfig();
    await this.loadUsage();
    await this.restoreState();
  },

  // ── 새로고침 시 서버에 남아있는 이전 작업 복원 ────────────────

  async restoreState() {
    try {
      const settings = await API.get('/api/stage1/settings');
      if (settings && settings.keywords) {
        document.getElementById('sKeywords').value = settings.keywords || '';
        document.getElementById('sGenre').value = settings.genre || '일상/코미디';
        document.getElementById('sMood').value = settings.mood || '밝고 유쾌한';
        document.getElementById('sArtStyle').value = settings.art_style || '';
        document.getElementById('sChapterCount').value = settings.chapter_count || 1;
        document.getElementById('sCharCount').value = settings.character_count || 2;
        document.getElementById('sDialogueTone').value = settings.dialogue_tone || '자연스러운 일상체';
        document.getElementById('sCanvasWidth').value = settings.canvas_width || 800;
        document.getElementById('sExtraNotes').value = settings.extra_notes || '';

        this.updateChaptersConfig();
        const byChapter = {};
        (settings.chapters_config || []).forEach(c => { byChapter[c.chapter] = c.panel_count; });
        document.querySelectorAll('.chapter-panel-input').forEach(inp => {
          const ch = parseInt(inp.dataset.chapter, 10);
          if (byChapter[ch] != null) inp.value = byChapter[ch];
        });
        this.updateChaptersSummary();

        const selectedCard = document.querySelector(`.style-card[data-prompt="${CSS.escape(settings.art_style || '')}"]`);
        if (selectedCard) {
          document.querySelectorAll('.style-card').forEach(c => c.classList.remove('selected'));
          selectedCard.classList.add('selected');
        }
      }
    } catch { /* 저장된 설정 없음 */ }

    try {
      const story = await API.get('/api/stage2/story');
      if (story && story.title) {
        this.story = story;
        this.renderStory(story);
        document.getElementById('generateStoryBtn').classList.add('hidden');
        document.getElementById('regenerateStoryBtn').classList.remove('hidden');
      }
    } catch { /* 저장된 스토리 없음 */ }

    try {
      const sheets = await API.get('/api/stage3/sheets');
      if (sheets && sheets.characters && sheets.characters.length) {
        const grid = document.getElementById('charSheetsGrid');
        grid.innerHTML = '';
        sheets.characters.forEach(c => this.appendCharacterSheet(c));
        if (sheets.cover && sheets.cover.b64_preview) {
          this.showCover(sheets.cover.b64_preview);
        }
      }
    } catch { /* 저장된 캐릭터 시트 없음 */ }

    try {
      const panelData = await API.get('/api/stage4/panels');
      if (panelData && panelData.panels && panelData.panels.length) {
        const gallery = document.getElementById('panelsGallery');
        gallery.innerHTML = '';
        panelData.panels.forEach(p => this.appendPanelGalleryItem(p));
      }
    } catch { /* 저장된 컷 이미지 없음 */ }
  },

  // ── 네비게이션 ──────────────────────────────────────────────

  bindNav() {
    document.getElementById('prevBtn').addEventListener('click', () => this.goStage(this.currentStage - 1));
    document.getElementById('nextBtn').addEventListener('click', () => this.goStage(this.currentStage + 1));
  },

  bindSteps() {
    document.querySelectorAll('.step').forEach(el => {
      el.addEventListener('click', () => this.goStage(parseInt(el.dataset.step, 10)));
    });
  },

  goStage(n) {
    if (n < 0 || n > this.totalStages) return;
    this.showStage(n);
  },

  showStage(n) {
    this.currentStage = n;
    document.querySelectorAll('.stage').forEach(el => el.classList.add('hidden'));
    const target = document.getElementById(`stage-${n}`);
    if (target) target.classList.remove('hidden');
    document.querySelectorAll('.step').forEach(el => {
      const s = parseInt(el.dataset.step, 10);
      el.classList.toggle('active', s === n);
    });
    document.getElementById('prevBtn').disabled = n === 0;
    document.getElementById('nextBtn').disabled = n === this.totalStages;
    document.getElementById('stageNavInfo').textContent = `Stage ${n} / ${this.totalStages}`;
  },

  setConnected(ok) {
    const badge = document.getElementById('connectionBadge');
    badge.classList.toggle('connected', ok);
    badge.classList.toggle('disconnected', !ok);
    badge.querySelector('.badge-text').textContent = ok ? '연결됨' : '미연결';
  },

  // ── 사용량 ──────────────────────────────────────────────────

  async loadUsage() {
    try {
      const u = await API.get('/api/usage');
      const img = (u.image_calls || 0) + (u.image_edit_calls || 0);
      const failed = u.image_failed_requests || 0;
      document.getElementById('usageText').textContent =
        `텍스트 ${u.text_calls} · 이미지 ${img}` + (failed ? ` (실패 요청 ${failed})` : '');
    } catch { /* 첫 실행 */ }
  },

  // ── Stage 0: 설정/연결 ─────────────────────────────────────

  initStage0() {
    document.getElementById('saveConfigBtn').addEventListener('click', () => this.saveConfig());
    document.getElementById('testConnBtn').addEventListener('click', () => this.testConnection());
    document.getElementById('toggleKeyVis').addEventListener('click', () => {
      const inp = document.getElementById('cfgApiKey');
      inp.type = inp.type === 'password' ? 'text' : 'password';
    });
  },

  async loadConfig() {
    try {
      const cfg = await API.get('/api/config');
      this.config = cfg;
      document.getElementById('cfgHost').value = cfg.host || '';
      if (cfg.has_key) {
        document.getElementById('cfgApiKey').placeholder = cfg.api_key_masked;
        document.getElementById('keyStatus').textContent = '저장된 키: ' + cfg.api_key_masked;
        document.getElementById('keyStatus').className = 'form-hint success';
      }
      if (cfg.models) {
        document.querySelectorAll('.model-input').forEach(el => {
          const key = el.dataset.key;
          if (cfg.models[key]) el.value = cfg.models[key];
        });
      }
      if (cfg.image_quality) {
        document.getElementById('imageQuality').value = cfg.image_quality;
      }
      if (cfg.max_frames_per_panel) {
        document.getElementById('maxFrames').value = String(cfg.max_frames_per_panel);
      }
      document.getElementById('useRefImages').value = String(!!cfg.use_reference_images);
    } catch { /* 첫 실행 */ }
  },

  async saveConfig() {
    const btn = document.getElementById('saveConfigBtn');
    btn.disabled = true;
    btn.textContent = '저장 중...';
    try {
      const models = {};
      document.querySelectorAll('.model-input').forEach(el => {
        models[el.dataset.key] = el.value.trim();
      });
      const body = {
        host: document.getElementById('cfgHost').value.trim(),
        api_key: document.getElementById('cfgApiKey').value.trim(),
        models,
        image_quality: document.getElementById('imageQuality').value,
        max_frames_per_panel: Number(document.getElementById('maxFrames').value),
        use_reference_images: document.getElementById('useRefImages').value === 'true',
      };
      const result = await API.post('/api/config', body);
      const status = document.getElementById('keyStatus');
      status.textContent = '저장 완료 — ' + result.api_key_masked;
      status.className = 'form-hint success';
      document.getElementById('cfgApiKey').value = '';
      document.getElementById('cfgApiKey').placeholder = result.api_key_masked;
    } catch (e) {
      const status = document.getElementById('keyStatus');
      status.textContent = '저장 실패: ' + e.message;
      status.className = 'form-hint error';
    } finally {
      btn.disabled = false;
      btn.textContent = '설정 저장';
    }
  },

  async testConnection() {
    const btn = document.getElementById('testConnBtn');
    const card = document.getElementById('testResultCard');
    const results = document.getElementById('testResults');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> 테스트 중...';
    card.classList.remove('hidden');
    results.innerHTML = '<div style="text-align:center;padding:20px"><span class="spinner"></span><p style="margin-top:8px;color:var(--text-secondary);font-size:0.85rem">연결 테스트 진행 중...</p></div>';
    try {
      const r = await API.post('/api/test-connection', {});
      let html = '';
      html += this._resultItem('텍스트 생성 (LLM)', r.text, r.text_error);
      html += this._resultItem('이미지 모델 확인 (크레딧 차감 없음)', r.image, r.image_error);
      results.innerHTML = html;
      this.setConnected(r.text && r.image);
      await this.loadUsage();
      if (r.text) this.fetchSuggestions(0);
    } catch (e) {
      results.innerHTML = this._resultItem('연결', false, e.message);
      this.setConnected(false);
    } finally {
      btn.disabled = false;
      btn.innerHTML = '연결 테스트';
    }
  },

  _resultItem(label, ok, error) {
    const cls = ok ? 'pass' : 'fail';
    const status = ok ? '성공' : '실패';
    const detail = error ? `<span class="test-result-detail">${this.escapeHtml(error).substring(0, 80)}</span>` : '';
    return `<div class="test-result-item ${cls}"><span class="test-result-dot"></span>${label}: ${status}${detail}</div>`;
  },

  // ── Stage 1: 웹툰 설정 (장 시스템 + 그림체 그리드) ────────

  initStage1() {
    document.getElementById('saveSettingsBtn').addEventListener('click', () => this.saveSettings());
    document.getElementById('sChapterCount').addEventListener('change', () => this.updateChaptersConfig());
    this.updateChaptersConfig();
    this.loadStylePreviews();
  },

  async loadStylePreviews() {
    try {
      const r = await API.get('/api/style-previews');
      this.renderStyleGrid(r.styles);
    } catch { /* ignore */ }
  },

  renderStyleGrid(styles) {
    const grid = document.getElementById('styleGrid');
    grid.innerHTML = '';
    const currentVal = document.getElementById('sArtStyle').value;

    styles.forEach(s => {
      const card = document.createElement('div');
      card.className = 'style-card' + (s.prompt === currentVal ? ' selected' : '');
      card.dataset.prompt = s.prompt;
      card.dataset.key = s.key;

      if (s.b64) {
        card.innerHTML = `<div class="style-card-imgwrap"><img class="style-card-img" src="data:image/png;base64,${s.b64}" alt="${s.label}"></div><div class="style-card-label">${s.label}</div>`;
      } else if (s.has_preview) {
        card.innerHTML = `<div class="style-card-imgwrap"><img class="style-card-img" src="/outputs/style_previews/${s.key}.png?t=${Date.now()}" alt="${s.label}"></div><div class="style-card-label">${s.label}</div>`;
      } else {
        card.innerHTML = `<div class="style-card-placeholder">${s.label}</div><div class="style-card-label">${s.label}</div>`;
      }

      card.addEventListener('click', () => {
        grid.querySelectorAll('.style-card').forEach(c => c.classList.remove('selected'));
        card.classList.add('selected');
        document.getElementById('sArtStyle').value = s.prompt;
      });

      grid.appendChild(card);
    });

    if (!currentVal && styles.length > 0) {
      document.getElementById('sArtStyle').value = styles[0].prompt;
      grid.querySelector('.style-card')?.classList.add('selected');
    }
  },

  updateChaptersConfig() {
    const count = parseInt(document.getElementById('sChapterCount').value, 10) || 1;
    const list = document.getElementById('chaptersConfigList');
    const existing = list.querySelectorAll('.chapter-config-row');
    const currentValues = {};
    existing.forEach(row => {
      const ch = row.dataset.chapter;
      const inp = row.querySelector('input');
      if (inp) currentValues[ch] = inp.value;
    });

    list.innerHTML = '';
    for (let i = 1; i <= count; i++) {
      const val = currentValues[i] || '6';
      list.innerHTML += `
        <div class="chapter-config-row" data-chapter="${i}">
          <span class="chapter-label">${i}장</span>
          <input class="form-input chapter-panel-input" type="number" min="1" max="20" value="${val}" data-chapter="${i}">
          <span class="chapter-unit">컷</span>
        </div>`;
    }

    list.querySelectorAll('.chapter-panel-input').forEach(inp => {
      inp.addEventListener('change', () => this.updateChaptersSummary());
    });
    this.updateChaptersSummary();
  },

  updateChaptersSummary() {
    const inputs = document.querySelectorAll('.chapter-panel-input');
    let total = 0;
    inputs.forEach(inp => { total += parseInt(inp.value, 10) || 0; });
    document.getElementById('chaptersSummary').textContent = `총 ${total}컷`;
  },

  async saveSettings() {
    const btn = document.getElementById('saveSettingsBtn');
    btn.disabled = true;
    btn.textContent = '저장 중...';
    try {
      const chaptersConfig = [];
      document.querySelectorAll('.chapter-panel-input').forEach(inp => {
        chaptersConfig.push({
          chapter: parseInt(inp.dataset.chapter, 10),
          panel_count: parseInt(inp.value, 10) || 6,
        });
      });
      const totalPanels = chaptersConfig.reduce((s, c) => s + c.panel_count, 0);

      const body = {
        keywords: document.getElementById('sKeywords').value.trim(),
        genre: document.getElementById('sGenre').value,
        mood: document.getElementById('sMood').value,
        art_style: document.getElementById('sArtStyle').value,
        chapter_count: chaptersConfig.length,
        chapters_config: chaptersConfig,
        panel_count: totalPanels,
        character_count: parseInt(document.getElementById('sCharCount').value, 10),
        dialogue_tone: document.getElementById('sDialogueTone').value,
        canvas_width: parseInt(document.getElementById('sCanvasWidth').value, 10),
        extra_notes: document.getElementById('sExtraNotes').value.trim(),
      };
      if (!body.keywords) { Toast.error('핵심 키워드를 입력해주세요.'); return; }
      await API.post('/api/stage1/settings', body);
      this.fetchSuggestions(1, `키워드: ${body.keywords}, ${body.chapter_count}장, 총 ${totalPanels}컷`);
      this.goStage(2);
    } catch (e) {
      Toast.error('설정 저장 실패: ' + e.message);
    } finally {
      btn.disabled = false;
      btn.textContent = '설정 저장 후 다음 →';
    }
  },

  // ── Stage 2: 스토리 생성 (장 기반) ─────────────────────────

  initStage2() {
    document.getElementById('generateStoryBtn').addEventListener('click', () => this.generateStory());
    document.getElementById('regenerateStoryBtn').addEventListener('click', () => this.generateStory());
    document.getElementById('toggleJsonBtn').addEventListener('click', () => this.toggleJsonEdit());
    document.getElementById('applyJsonBtn').addEventListener('click', () => this.applyJsonEdit());
  },

  async generateStory() {
    const genBtn = document.getElementById('generateStoryBtn');
    const regenBtn = document.getElementById('regenerateStoryBtn');
    const loading = document.getElementById('storyLoading');
    genBtn.disabled = true;
    regenBtn.disabled = true;
    loading.classList.remove('hidden');
    try {
      const story = await API.post('/api/stage2/generate', {});
      this.story = story;
      this.renderStory(story);
      genBtn.classList.add('hidden');
      regenBtn.classList.remove('hidden');
      regenBtn.disabled = false;
      await this.loadUsage();
      const chCount = (story.chapters || []).length;
      const panelCount = (story.chapters || []).reduce((s, ch) => s + (ch.panels || []).length, 0) || (story.panels || []).length;
      this.fetchSuggestions(2, `제목: ${story.title}, ${chCount}장 ${panelCount}컷, 인물: ${(story.characters||[]).map(c=>c.name).join(', ')}`);
    } catch (e) {
      Toast.error('스토리 생성 실패: ' + e.message);
      genBtn.disabled = false;
      regenBtn.disabled = false;
    } finally {
      loading.classList.add('hidden');
    }
  },

  renderStory(story) {
    if (!story || !story.title) return;

    document.getElementById('storyTitle').textContent = story.title;
    document.getElementById('storySynopsis').textContent = story.synopsis;
    document.getElementById('synopsisCard').classList.remove('hidden');

    // 등장인물
    const charList = document.getElementById('charactersList');
    charList.innerHTML = '';
    (story.characters || []).forEach(c => {
      charList.innerHTML += `
        <div class="character-card">
          <h4>${this.escapeHtml(c.name)}</h4>
          <div class="char-role">${this.escapeHtml(c.role)}</div>
          <div class="char-detail"><strong>외모:</strong> ${this.escapeHtml(c.appearance)}</div>
          <div class="char-detail"><strong>의상:</strong> ${this.escapeHtml(c.outfit)}</div>
          <div class="char-detail"><strong>성격:</strong> ${this.escapeHtml(c.personality)}</div>
        </div>`;
    });
    document.getElementById('charactersCard').classList.remove('hidden');

    // 장(Chapter) 기반 컷 시나리오
    const panelsList = document.getElementById('panelsList');
    panelsList.innerHTML = '';

    const chapters = story.chapters || [{ chapter_number: 1, chapter_title: '', panels: story.panels || [] }];
    chapters.forEach(ch => {
      if (chapters.length > 1) {
        panelsList.innerHTML += `<div class="chapter-divider"><span class="chapter-divider-num">${ch.chapter_number}장</span><span class="chapter-divider-title">${this.escapeHtml(ch.chapter_title || '')}</span></div>`;
      }
      (ch.panels || []).forEach(p => {
        let dialogueHtml = '';
        (p.dialogue || []).forEach(d => {
          const type = d.type || 'speech';
          const speaker = d.character && type === 'speech'
            ? `<span class="speaker">${this.escapeHtml(this._charName(story, d.character))}:</span>` : '';
          const prefix = type === 'narration' ? '<span class="speaker">[나레이션]</span> ' : '';
          dialogueHtml += `<div class="panel-dialogue ${type}">${prefix}${speaker}${this.escapeHtml(d.text)}</div>`;
        });
        panelsList.innerHTML += `
          <div class="panel-item">
            <div class="panel-item-header">
              <span class="panel-num">${p.panel_number}</span>
              <span class="panel-mood">${this.escapeHtml(p.mood || '')}</span>
            </div>
            <div class="panel-scene">${this.escapeHtml(p.scene)}</div>
            <div class="panel-dialogues">${dialogueHtml}</div>
          </div>`;
      });
    });
    document.getElementById('panelsCard').classList.remove('hidden');
    document.getElementById('jsonEditCard').classList.remove('hidden');
  },

  _charName(story, charId) {
    const c = (story.characters || []).find(ch => ch.id === charId);
    return c ? c.name : charId;
  },

  toggleJsonEdit() {
    const area = document.getElementById('jsonEditArea');
    const btn = document.getElementById('toggleJsonBtn');
    if (area.classList.contains('hidden')) {
      document.getElementById('storyJsonEditor').value = JSON.stringify(this.story, null, 2);
      area.classList.remove('hidden');
      btn.textContent = 'JSON 편집 닫기';
    } else {
      area.classList.add('hidden');
      btn.textContent = 'JSON 편집 열기';
    }
  },

  async applyJsonEdit() {
    try {
      const json = JSON.parse(document.getElementById('storyJsonEditor').value);
      await API.put('/api/stage2/story', json);
      this.story = json;
      this.renderStory(json);
      Toast.success('JSON이 적용되었습니다.');
    } catch (e) {
      Toast.error('JSON 파싱 오류: ' + e.message);
    }
  },

  // ── Stage 3: 캐릭터 시트 + 표지 (SSE) ─────────────────────

  initStage3() {
    document.getElementById('generateCharsBtn').addEventListener('click', () => this.generateCharactersSSE());
    document.getElementById('regenCoverBtn').addEventListener('click', () => this.regenerateCover());
  },

  async generateCharactersSSE() {
    const btn = document.getElementById('generateCharsBtn');
    const progressWrap = document.getElementById('charProgressWrap');
    const progressBar = document.getElementById('charProgressBar');
    const progressText = document.getElementById('charProgressText');
    const grid = document.getElementById('charSheetsGrid');

    btn.disabled = true;
    progressWrap.classList.remove('hidden');
    progressBar.style.width = '0%';
    progressText.textContent = '캐릭터 시트 생성 시작...';
    grid.innerHTML = '';

    const totalChars = (this.story?.characters || []).length;
    const totalSteps = totalChars * 3 + 1; // 3 views per char + cover
    let completed = 0;

    try {
      const response = await fetch('/api/stage3/generate-stream', { method: 'POST' });
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const data = JSON.parse(line.slice(6));

          if (data.type === 'character') {
            const pct = Math.round((data.current / data.total) * 100);
            progressBar.style.width = pct + '%';
            progressText.textContent = `${data.current}/${data.total} 캐릭터 완료 — ${data.data.name}`;
            this.appendCharacterSheet(data.data);
            await this.loadUsage();
          } else if (data.type === 'progress') {
            if (data.current && data.total) {
              const pct = Math.round((data.current / data.total) * 100);
              progressBar.style.width = pct + '%';
            }
            progressText.textContent = data.message;
          } else if (data.type === 'error') {
            Toast.error(data.message || '캐릭터 생성 중 오류 발생');
          } else if (data.type === 'cover') {
            progressBar.style.width = '100%';
            progressText.textContent = '표지 생성 완료!';
            this.showCover(data.url || data.b64_preview);
            await this.loadUsage();
          } else if (data.type === 'cover_error') {
            Toast.error('표지 생성 실패: ' + (data.error || ''));
            progressText.textContent = '표지 생성 실패 — 다시 시도할 수 있습니다.';
          } else if (data.type === 'done') {
            progressText.textContent = '모든 생성 완료!';
            this.fetchSuggestions(3, `캐릭터 시트 + 표지 생성 완료`);
          }
        }
      }
    } catch (e) {
      Toast.error('캐릭터 시트 생성 실패: ' + e.message);
    } finally {
      btn.disabled = false;
    }
  },

  appendCharacterSheet(charData) {
    const grid = document.getElementById('charSheetsGrid');
    const card = document.createElement('div');
    card.className = 'char-sheet-card';
    card.dataset.charid = charData.id;

    const mainView = charData.views[0] || {};
    let viewThumbs = '';
    (charData.views || []).forEach((v, i) => {
      viewThumbs += `
        <div style="text-align:center">
          <img class="char-view-thumb ${i === 0 ? 'active' : ''}"
               src="${v.url || ''}"
               data-full="${v.url || ''}"
               alt="${v.label}" title="${v.label}">
          <div class="char-view-label">${v.label}</div>
        </div>`;
    });

    card.innerHTML = `
      <img class="char-sheet-img" src="${mainView.url || ''}" alt="${this.escapeHtml(charData.name)}">
      <div class="char-sheet-info">
        <h4>${this.escapeHtml(charData.name)}</h4>
        <div class="char-sheet-views">${viewThumbs}</div>
        <div class="char-sheet-actions" style="margin-top:8px">
          <button class="btn btn-secondary btn-sm">전체 다시 생성</button>
        </div>
      </div>`;

    // 뷰 썸네일 클릭 → 메인 이미지 교체
    card.querySelectorAll('.char-view-thumb').forEach(thumb => {
      thumb.addEventListener('click', () => {
        card.querySelector('.char-sheet-img').src = thumb.dataset.full;
        card.querySelectorAll('.char-view-thumb').forEach(t => t.classList.remove('active'));
        thumb.classList.add('active');
      });
    });

    card.querySelector('.char-sheet-actions button').addEventListener('click', () => this.regenerateCharacter(charData.id, card));
    grid.appendChild(card);
  },

  async regenerateCharacter(charId, cardEl) {
    const btn = cardEl.querySelector('.char-sheet-actions button');
    btn.disabled = true;
    btn.textContent = '생성 중...';
    try {
      const r = await API.post(`/api/stage3/regenerate/${charId}`, {});
      cardEl.querySelector('.char-sheet-img').src = r.views[0]?.url || '';
      const viewsWrap = cardEl.querySelector('.char-sheet-views');
      viewsWrap.innerHTML = '';
      (r.views || []).forEach((v, i) => {
        const div = document.createElement('div');
        div.style.textAlign = 'center';
        div.innerHTML = `
          <img class="char-view-thumb ${i === 0 ? 'active' : ''}"
               src="${v.url || ''}"
               data-full="${v.url || ''}"
               alt="${v.label}" title="${v.label}">
          <div class="char-view-label">${v.label}</div>`;
        div.querySelector('.char-view-thumb').addEventListener('click', () => {
          cardEl.querySelector('.char-sheet-img').src = div.querySelector('.char-view-thumb').dataset.full;
          cardEl.querySelectorAll('.char-view-thumb').forEach(t => t.classList.remove('active'));
          div.querySelector('.char-view-thumb').classList.add('active');
        });
        viewsWrap.appendChild(div);
      });
      await this.loadUsage();
    } catch (e) {
      Toast.error('재생성 실패: ' + e.message);
    } finally {
      btn.disabled = false;
      btn.textContent = '전체 다시 생성';
    }
  },

  showCover(b64) {
    const card = document.getElementById('coverCard');
    card.classList.remove('hidden');
    const el = document.getElementById('coverImg');
    if (typeof b64 === 'string' && b64.startsWith('/')) el.src = b64;
    else el.src = `data:image/jpeg;base64,${b64}`;
  },

  async regenerateCover() {
    const btn = document.getElementById('regenCoverBtn');
    btn.disabled = true;
    btn.textContent = '생성 중...';
    try {
      const r = await API.post('/api/stage3/regenerate-cover', {});
      document.getElementById('coverImg').src = `data:image/jpeg;base64,${r.b64_preview}`;
      await this.loadUsage();
    } catch (e) {
      Toast.error('표지 재생성 실패: ' + e.message);
    } finally {
      btn.disabled = false;
      btn.textContent = '표지 다시 생성';
    }
  },

  // ── Stage 4: 컷 이미지 (SSE + 개별 재생성) ────────────────

  initStage4() {
    document.getElementById('generatePanelsBtn').addEventListener('click', () => this.generatePanelsSSE());
  },

  async generatePanelsSSE() {
    const btn = document.getElementById('generatePanelsBtn');
    const progressWrap = document.getElementById('panelProgressWrap');
    const progressBar = document.getElementById('panelProgressBar');
    const progressText = document.getElementById('panelProgressText');
    const gallery = document.getElementById('panelsGallery');
    const variantCount = 1;

    btn.disabled = true;
    progressWrap.classList.remove('hidden');
    progressBar.style.width = '0%';
    progressText.textContent = '컷 이미지 생성 시작...';
    gallery.innerHTML = '';

    try {
      const response = await fetch('/api/stage4/generate-stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ variant_count: variantCount }),
      });
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const data = JSON.parse(line.slice(6));

          if (data.type === 'progress') {
            const pct = Math.round((data.current / data.total) * 100);
            progressBar.style.width = pct + '%';
            progressText.textContent = `${data.current}/${data.total} 컷 생성 중...`;
          } else if (data.type === 'panel') {
            this.appendPanelGalleryItem(data);
            await this.loadUsage();
          } else if (data.type === 'error') {
            Toast.error(data.message || '컷 생성 중 오류');
          } else if (data.type === 'done') {
            progressBar.style.width = '100%';
            progressText.textContent = '모든 컷 생성 완료!';
            this.fetchSuggestions(4, `컷 이미지 생성 완료`);
          }
        }
      }
    } catch (e) {
      Toast.error('컷 이미지 생성 실패: ' + e.message);
    } finally {
      btn.disabled = false;
    }
  },

  appendPanelGalleryItem(panelData) {
    const gallery = document.getElementById('panelsGallery');
    const item = document.createElement('div');
    item.className = 'panel-gallery-item';
    item.dataset.panelnum = panelData.panel_number;

    let variantsHtml = '';
    (panelData.variants || []).forEach(v => {
      const sel = v.variant === panelData.selected ? 'selected' : '';
      variantsHtml += `
        <div class="panel-variant ${sel}" data-panel="${panelData.panel_number}" data-variant="${v.variant}">
          <img src="${v.url || `data:image/jpeg;base64,${v.b64_preview || ''}`}" alt="컷 ${panelData.panel_number} 후보 ${v.variant + 1}">
          <div class="panel-variant-label">후보 ${v.variant + 1}</div>
        </div>`;
    });

    item.innerHTML = `
      <div class="panel-gallery-header">
        <span class="panel-num">${panelData.panel_number}</span>
        <span class="panel-gallery-scene">${this.escapeHtml((panelData.scene || '').substring(0, 80))}...</span>
      </div>
      <div class="panel-variants">${variantsHtml}</div>
      <div class="panel-regen-row">
        <input class="panel-regen-input" placeholder="프롬프트 수정 후 재생성 (비우면 원본 사용)" data-panel="${panelData.panel_number}">
        <button class="btn btn-secondary btn-sm" data-panel="${panelData.panel_number}">재생성</button>
      </div>`;

    item.querySelectorAll('.panel-variant').forEach(el => {
      el.addEventListener('click', () => this.selectPanelVariant(
        parseInt(el.dataset.panel, 10),
        parseInt(el.dataset.variant, 10),
        item
      ));
    });

    item.querySelector('.panel-regen-row button').addEventListener('click', () => {
      const inp = item.querySelector('.panel-regen-input');
      this.regenerateSinglePanel(panelData.panel_number, inp.value.trim(), item);
    });

    gallery.appendChild(item);
  },

  async selectPanelVariant(panelNum, variant, containerEl) {
    try {
      await API.post('/api/stage4/select', { panel_number: panelNum, selected: variant });
      containerEl.querySelectorAll('.panel-variant').forEach(el => {
        el.classList.toggle('selected', parseInt(el.dataset.variant, 10) === variant);
      });
    } catch (e) {
      Toast.error('선택 저장 실패: ' + e.message);
    }
  },

  async regenerateSinglePanel(panelNum, customPrompt, containerEl) {
    const btn = containerEl.querySelector('.panel-regen-row button');
    btn.disabled = true;
    btn.textContent = '생성 중...';
    try {
      const r = await API.post('/api/stage4/regenerate', {
        panel_number: panelNum,
        custom_prompt: customPrompt,
      });
      const variantsDiv = containerEl.querySelector('.panel-variants');
      (r.new_variants || []).forEach(v => {
        const el = document.createElement('div');
        el.className = 'panel-variant';
        el.dataset.panel = panelNum;
        el.dataset.variant = v.variant;
        el.innerHTML = `
          <img src="${v.url || `data:image/jpeg;base64,${v.b64_preview || ''}`}" alt="새 후보">
          <div class="panel-variant-label">새 후보</div>`;
        el.addEventListener('click', () => this.selectPanelVariant(panelNum, v.variant, containerEl));
        variantsDiv.appendChild(el);
      });
      await this.loadUsage();
    } catch (e) {
      Toast.error('재생성 실패: ' + e.message);
    } finally {
      btn.disabled = false;
      btn.textContent = '재생성';
    }
  },

  // ── Stage 5: 페이지 배치 ────────────────────────────────────

  initStage5() {
    document.getElementById('generateLayoutBtn').addEventListener('click', () => this.generateLayout());
  },

  async generateLayout() {
    const btn = document.getElementById('generateLayoutBtn');
    const loading = document.getElementById('layoutLoading');
    btn.disabled = true;
    loading.classList.remove('hidden');
    try {
      const r = await API.post('/api/stage5/layout', {});
      document.getElementById('layoutPreviewImg').src = `data:image/jpeg;base64,${r.b64_preview}`;
      document.getElementById('layoutPreviewCard').classList.remove('hidden');
      this.fetchSuggestions(5, `페이지 배치 완료 — ${r.width}x${r.height}px, ${r.panel_count}컷`);
    } catch (e) {
      Toast.error('페이지 배치 실패: ' + e.message);
    } finally {
      btn.disabled = false;
      loading.classList.add('hidden');
    }
  },

  // ── Stage 6: 말풍선 / 대사 합성 ────────────────────────────

  initStage6() {
    document.getElementById('generateBubblesBtn').addEventListener('click', () => this.generateBubbles());
  },

  async generateBubbles() {
    const btn = document.getElementById('generateBubblesBtn');
    const loading = document.getElementById('bubblesLoading');
    btn.disabled = true;
    loading.classList.remove('hidden');
    try {
      const r = await API.post('/api/stage6/bubbles', {});
      document.getElementById('bubblesPreviewImg').src = `data:image/jpeg;base64,${r.b64_preview}`;
      document.getElementById('bubblesPreviewCard').classList.remove('hidden');
      this.fetchSuggestions(6, `말풍선 합성 완료 — ${r.width}x${r.height}px`);
      await this.loadUsage();
    } catch (e) {
      Toast.error('말풍선 합성 실패: ' + e.message);
    } finally {
      btn.disabled = false;
      loading.classList.add('hidden');
    }
  },

  // ── Stage 7: 내보내기 ────────────────────────────────────────

  initStage7() {
    document.getElementById('exportPngBtn').addEventListener('click', () => this.exportPng());
    document.getElementById('exportPdfBtn').addEventListener('click', () => this.exportPdf());
    document.getElementById('exportZipBtn').addEventListener('click', () => this.exportZip());
  },

  async exportPng() {
    const btn = document.getElementById('exportPngBtn');
    const status = document.getElementById('pngStatus');
    btn.disabled = true;
    btn.textContent = '준비 중...';
    status.classList.remove('hidden');
    status.className = 'export-status';
    status.textContent = 'PNG 파일 생성 중...';
    try {
      const r = await API.post('/api/stage7/export-png', {});
      status.className = 'export-status success';
      status.textContent = `완료! 컷 ${r.panel_count}개 + 전체 페이지 PNG 생성됨`;
      this.fetchSuggestions(7, 'PNG 내보내기 완료');
    } catch (e) {
      status.className = 'export-status error';
      status.textContent = '실패: ' + e.message;
    } finally {
      btn.disabled = false;
      btn.textContent = 'PNG 다운로드';
    }
  },

  async exportPdf() {
    const btn = document.getElementById('exportPdfBtn');
    const status = document.getElementById('pdfStatus');
    btn.disabled = true;
    btn.textContent = '변환 중...';
    status.classList.remove('hidden');
    status.className = 'export-status';
    status.textContent = 'PDF 생성 중...';
    try {
      const response = await fetch('/api/stage7/export-pdf', { method: 'POST' });
      if (!response.ok) throw new Error(await response.text());
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'webtoon.pdf';
      a.click();
      URL.revokeObjectURL(url);
      status.className = 'export-status success';
      status.textContent = 'PDF 다운로드 완료!';
    } catch (e) {
      status.className = 'export-status error';
      status.textContent = '실패: ' + e.message;
    } finally {
      btn.disabled = false;
      btn.textContent = 'PDF 다운로드';
    }
  },

  async exportZip() {
    const btn = document.getElementById('exportZipBtn');
    const status = document.getElementById('zipStatus');
    btn.disabled = true;
    btn.textContent = '패키징 중...';
    status.classList.remove('hidden');
    status.className = 'export-status';
    status.textContent = 'ZIP 패키지 생성 중...';
    try {
      const response = await fetch('/api/stage7/export-zip', { method: 'POST' });
      if (!response.ok) throw new Error(await response.text());
      const blob = await response.blob();
      const disposition = response.headers.get('content-disposition') || '';
      const match = disposition.match(/filename="?(.+?)"?$/);
      const filename = match ? match[1] : 'webtoon.zip';
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      status.className = 'export-status success';
      status.textContent = 'ZIP 다운로드 완료!';
    } catch (e) {
      status.className = 'export-status error';
      status.textContent = '실패: ' + e.message;
    } finally {
      btn.disabled = false;
      btn.textContent = 'ZIP 다운로드';
    }
  },

  // ── 추천 카드 ──────────────────────────────────────────────

  async fetchSuggestions(stage, contextSummary = '') {
    const panel = document.getElementById('suggestionsPanel');
    const container = document.getElementById('suggestionsCards');
    panel.classList.remove('hidden');
    container.innerHTML = '<div style="text-align:center;padding:16px"><span class="spinner"></span><p style="margin-top:6px;font-size:0.8rem;color:var(--text-secondary)">추천 생성 중...</p></div>';
    try {
      const r = await API.post('/api/suggestions', { stage, context_summary: contextSummary });
      this.showSuggestions(r.suggestions || []);
      await this.loadUsage();
    } catch {
      container.innerHTML = '<p style="font-size:0.8rem;color:var(--text-secondary);text-align:center;padding:12px">추천을 불러오지 못했습니다.</p>';
    }
  },

  showSuggestions(items) {
    const panel = document.getElementById('suggestionsPanel');
    const container = document.getElementById('suggestionsCards');
    container.innerHTML = '';
    if (!items || items.length === 0) { panel.classList.add('hidden'); return; }
    items.forEach(item => {
      const card = document.createElement('div');
      card.className = 'suggestion-card';
      card.innerHTML = `<h4>${this.escapeHtml(item.title)}</h4><p>${this.escapeHtml(item.desc)}</p>`;
      card.addEventListener('click', () => this.applySuggestion(item));
      container.appendChild(card);
    });
    panel.classList.remove('hidden');
  },

  applySuggestion(item) {
    const action = item.action || '';
    if (action === 'next_stage') { this.goStage(this.currentStage + 1); }
    else if (action === 'edit_settings' || action === 'adjust_settings') { this.goStage(1); }
    else if (action === 'regenerate_story' || action === 'rewrite_story') { this.generateStory(); }
    else if (action.startsWith('add_') || action.startsWith('enrich_') || action.startsWith('insert_')) {
      Toast.info(`"${item.title}" — 해당 단계에서 적용해주세요.`);
      const stage = this._suggestedStageForAction(action);
      if (stage !== null) this.goStage(stage);
    } else { Toast.info(`${item.title}: ${item.desc}`); }
  },

  _suggestedStageForAction(action) {
    if (action.includes('story') || action.includes('dialogue')) return 2;
    if (action.includes('character')) return 3;
    if (action.includes('panel') || action.includes('scene')) return 4;
    if (action.includes('layout')) return 5;
    if (action.includes('bubble')) return 6;
    return null;
  },

  // ── 프로젝트 저장 / 불러오기 ─────────────────────────────

  initProjectButtons() {
    document.getElementById('saveProjectBtn').addEventListener('click', () => this.saveProject());
    document.getElementById('loadProjectBtn').addEventListener('click', () => this.showProjectList());
    document.getElementById('closeProjectModal').addEventListener('click', () => {
      document.getElementById('projectModal').classList.add('hidden');
    });
    document.getElementById('projectModal').addEventListener('click', (e) => {
      if (e.target === document.getElementById('projectModal'))
        document.getElementById('projectModal').classList.add('hidden');
    });
  },

  async saveProject() {
    const btn = document.getElementById('saveProjectBtn');
    btn.disabled = true;
    try {
      const name = this.story?.title || '프로젝트';
      const r = await API.post('/api/project/save', { name });
      Toast.success(`프로젝트 "${name}" 저장 완료!`);
    } catch (e) {
      Toast.error('저장 실패: ' + e.message);
    } finally {
      btn.disabled = false;
    }
  },

  async showProjectList() {
    const modal = document.getElementById('projectModal');
    const list = document.getElementById('projectList');
    modal.classList.remove('hidden');
    list.innerHTML = '<p style="text-align:center;padding:20px"><span class="spinner"></span></p>';
    try {
      const r = await API.get('/api/project/list');
      if (!r.projects || r.projects.length === 0) {
        list.innerHTML = '<p class="placeholder-msg">저장된 프로젝트가 없습니다.</p>';
        return;
      }
      list.innerHTML = '';
      r.projects.forEach(p => {
        const item = document.createElement('div');
        item.className = 'project-item';
        item.innerHTML = `
          <div class="project-item-info">
            <h4>${this.escapeHtml(p.title || p.name)}</h4>
            <p>${p.name} — ${p.created}</p>
          </div>`;
        item.addEventListener('click', () => this.loadProject(p.folder));
        list.appendChild(item);
      });
    } catch (e) {
      list.innerHTML = `<p class="placeholder-msg">불러오기 실패: ${e.message}</p>`;
    }
  },

  async loadProject(folder) {
    try {
      const r = await API.post(`/api/project/load/${folder}`, {});
      document.getElementById('projectModal').classList.add('hidden');
      Toast.success(`프로젝트 "${r.name}" 불러오기 완료! 페이지를 새로고침합니다.`);
      setTimeout(() => location.reload(), 1500);
    } catch (e) {
      Toast.error('불러오기 실패: ' + e.message);
    }
  },

  escapeHtml(str) {
    const d = document.createElement('div');
    d.textContent = str || '';
    return d.innerHTML;
  },
};

document.addEventListener('DOMContentLoaded', () => App.init());
