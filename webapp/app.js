(function () {
  const serviceConfig = window.__BILIBILI_KB_SERVICE__ || null;
  const staticData = window.__BILIBILI_KB_DATA__ || null;

  const state = {
    packs: [],
    templates: [],
    packSlug: staticData && staticData.pack ? staticData.pack.slug : "",
    payload: null,
    search: "",
    category: "all",
    status: "all",
    sort: "play_desc",
    highlightReview: false,
    activeVideoId: null,
    activeJob: null,
    eventSource: null,
    pollingTimer: null,
    notice: "",
    createSlugDirty: false,
  };

  const elements = {
    pageTitle: document.getElementById("page-title"),
    pageDescription: document.getElementById("page-description"),
    heroStats: document.getElementById("hero-stats"),
    generatedAt: document.getElementById("generated-at"),
    categoryOverview: document.getElementById("category-overview"),
    packSelect: document.getElementById("pack-select"),
    addTopicButton: document.getElementById("add-topic-button"),
    refreshButton: document.getElementById("refresh-button"),
    cancelButton: document.getElementById("cancel-button"),
    serviceStatus: document.getElementById("service-status"),
    lastRefreshed: document.getElementById("last-refreshed"),
    serviceNotice: document.getElementById("service-notice"),
    serviceError: document.getElementById("service-error"),
    categorySelect: document.getElementById("category-select"),
    statusSelect: document.getElementById("status-select"),
    sortSelect: document.getElementById("sort-select"),
    searchInput: document.getElementById("search-input"),
    reviewToggle: document.getElementById("review-only-toggle"),
    resetButton: document.getElementById("reset-button"),
    categoryChips: document.getElementById("category-chips"),
    resultsSummary: document.getElementById("results-summary"),
    videoGrid: document.getElementById("video-grid"),
    emptyState: document.getElementById("empty-state"),
    emptyStateText: document.getElementById("empty-state-text"),
    detailCard: document.getElementById("detail-card"),
    jobBanner: document.getElementById("job-banner"),
    topicModalShell: document.getElementById("topic-modal-shell"),
    topicModalBackdrop: document.getElementById("topic-modal-backdrop"),
    topicModalClose: document.getElementById("topic-modal-close"),
    topicForm: document.getElementById("topic-form"),
    topicTemplateSelect: document.getElementById("topic-template-select"),
    topicDisplayName: document.getElementById("topic-display-name"),
    topicSlug: document.getElementById("topic-slug"),
    topicDescription: document.getElementById("topic-description"),
    topicCoreTerms: document.getElementById("topic-core-terms"),
    topicExpansionTerms: document.getElementById("topic-expansion-terms"),
    topicCustomQueries: document.getElementById("topic-custom-queries"),
    topicMustHaveAny: document.getElementById("topic-must-have-any"),
    topicIrrelevantKeywords: document.getElementById("topic-irrelevant-keywords"),
    topicCategories: document.getElementById("topic-categories"),
    topicAddCategory: document.getElementById("topic-add-category"),
    topicFormError: document.getElementById("topic-form-error"),
    topicFormCancel: document.getElementById("topic-form-cancel"),
    topicFormSubmit: document.getElementById("topic-form-submit"),
  };

  initialize();

  async function initialize() {
    document.body.dataset.mode = serviceConfig ? "service" : "static";
    bindEvents();

    if (serviceConfig) {
      try {
        await Promise.all([loadPacks(), loadTemplates()]);
        const initialPack = state.packSlug || (state.packs[0] && state.packs[0].slug);
        if (!initialPack) {
          showEmpty("没有可用专题。");
          return;
        }
        state.packSlug = initialPack;
        elements.packSelect.value = initialPack;
        await loadPayload(initialPack, "auto");
      } catch (error) {
        showEmpty(`加载服务数据失败：${error.message}`);
      }
      return;
    }

    if (!staticData || !Array.isArray(staticData.videos)) {
      showEmpty("没有可用数据。");
      return;
    }

    state.payload = staticData;
    state.packSlug = staticData.pack ? staticData.pack.slug : "";
    state.packs = staticData.pack ? [{ slug: staticData.pack.slug, display_name: staticData.pack.display_name }] : [];
    populatePackOptions();
    applyPayload(staticData);
  }

  function bindEvents() {
    elements.searchInput.addEventListener("input", (event) => {
      state.search = event.target.value.trim().toLowerCase();
      render();
    });

    elements.categorySelect.addEventListener("change", (event) => {
      state.category = event.target.value;
      syncChipState();
      render();
    });

    elements.statusSelect.addEventListener("change", (event) => {
      state.status = event.target.value;
      render();
    });

    elements.sortSelect.addEventListener("change", (event) => {
      state.sort = event.target.value;
      render();
    });

    elements.reviewToggle.addEventListener("change", (event) => {
      state.highlightReview = event.target.checked;
      render();
    });

    elements.resetButton.addEventListener("click", () => {
      resetFilters();
      render();
    });

    elements.packSelect.addEventListener("change", async (event) => {
      state.notice = "";
      state.packSlug = event.target.value;
      await loadPayload(state.packSlug, "auto");
    });

    elements.refreshButton.addEventListener("click", async () => {
      if (!serviceConfig || !state.packSlug) {
        return;
      }
      state.notice = "";
      try {
        await requestRefresh();
      } catch (error) {
        elements.serviceError.textContent = `刷新失败：${error.message}`;
        elements.serviceError.classList.add("has-error");
      }
    });

    elements.cancelButton.addEventListener("click", async () => {
      if (!serviceConfig || !state.activeJob) {
        return;
      }
      try {
        await requestCancel(state.activeJob.id);
      } catch (error) {
        elements.serviceError.textContent = `停止任务失败：${error.message}`;
        elements.serviceError.classList.add("has-error");
      }
    });

    elements.addTopicButton.addEventListener("click", async () => {
      if (!serviceConfig) {
        return;
      }
      if (!state.templates.length) {
        await loadTemplates();
      }
      openTopicModal();
    });

    elements.topicModalClose.addEventListener("click", closeTopicModal);
    elements.topicModalBackdrop.addEventListener("click", closeTopicModal);
    elements.topicFormCancel.addEventListener("click", closeTopicModal);
    elements.topicTemplateSelect.addEventListener("change", () => {
      const template = getSelectedTemplate();
      if (template) {
        applyTemplateToForm(template, { preserveIdentity: true });
      }
    });
    elements.topicDisplayName.addEventListener("input", () => {
      if (!state.createSlugDirty) {
        elements.topicSlug.value = slugify(elements.topicDisplayName.value);
      }
    });
    elements.topicSlug.addEventListener("input", () => {
      state.createSlugDirty = true;
    });
    elements.topicAddCategory.addEventListener("click", () => {
      addCategoryRow({ id: "", name: "", keywords: [], priority: nextCategoryPriority() });
    });
    elements.topicForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      await submitTopicForm();
    });
  }

  function resetFilters() {
    state.search = "";
    state.category = "all";
    state.status = "all";
    state.sort = "play_desc";
    state.highlightReview = false;
    elements.searchInput.value = "";
    elements.categorySelect.value = "all";
    elements.statusSelect.value = "all";
    elements.sortSelect.value = "play_desc";
    elements.reviewToggle.checked = false;
    syncChipState();
  }

  async function loadPacks() {
    const response = await fetch(`${serviceConfig.apiBase}/packs`);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    state.packs = await response.json();
    populatePackOptions();
  }

  async function loadTemplates() {
    const response = await fetch(`${serviceConfig.apiBase}/pack-templates`);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    state.templates = await response.json();
    populateTemplateOptions();
  }

  function populatePackOptions() {
    elements.packSelect.innerHTML = state.packs
      .map((pack) => `<option value="${escapeAttr(pack.slug)}">${escapeHtml(pack.display_name || pack.slug)}</option>`)
      .join("");
    if (state.packSlug) {
      elements.packSelect.value = state.packSlug;
    }
  }

  function populateTemplateOptions() {
    elements.topicTemplateSelect.innerHTML = state.templates
      .map(
        (pack) =>
          `<option value="${escapeAttr(pack.slug)}">${escapeHtml(pack.display_name || pack.slug)} (${escapeHtml(
            pack.slug
          )})</option>`
      )
      .join("");
  }

  function getSelectedTemplate() {
    const slug = elements.topicTemplateSelect.value;
    return state.templates.find((item) => item.slug === slug) || null;
  }

  function openTopicModal() {
    const template = getSelectedTemplate() || state.templates[0];
    if (!template) {
      setTopicFormError("当前没有可用模板。");
      return;
    }
    applyTemplateToForm(template, { resetTemplateSelect: true, preserveIdentity: false });
    elements.topicModalShell.classList.remove("hidden");
    elements.topicModalShell.setAttribute("aria-hidden", "false");
    document.body.classList.add("modal-open");
  }

  function closeTopicModal() {
    elements.topicModalShell.classList.add("hidden");
    elements.topicModalShell.setAttribute("aria-hidden", "true");
    document.body.classList.remove("modal-open");
    setTopicFormError("");
  }

  function applyTemplateToForm(template, options) {
    const settings = {
      preserveIdentity: false,
      resetTemplateSelect: false,
      ...options,
    };
    if (settings.resetTemplateSelect) {
      elements.topicTemplateSelect.value = template.slug;
    }
    if (!settings.preserveIdentity) {
      state.createSlugDirty = false;
      elements.topicDisplayName.value = "";
      elements.topicSlug.value = "";
      elements.topicDescription.value = template.description || "";
    } else if (!elements.topicDescription.value.trim()) {
      elements.topicDescription.value = template.description || "";
    }
    elements.topicCoreTerms.value = formatListField(template.search.core_terms || []);
    elements.topicExpansionTerms.value = formatListField(template.search.expansion_terms || []);
    elements.topicCustomQueries.value = formatListField(template.search.custom_queries || []);
    elements.topicMustHaveAny.value = formatListField((template.gates && template.gates.must_have_any) || []);
    elements.topicIrrelevantKeywords.value = formatListField(
      (template.gates && template.gates.irrelevant_keywords) || []
    );
    renderCategoryRows(template.categories || []);
    setTopicFormError("");
  }

  function renderCategoryRows(categories) {
    elements.topicCategories.innerHTML = "";
    const items = categories.length ? categories : [{ id: "", name: "", keywords: [], priority: 100 }];
    items.forEach((category) => addCategoryRow(category));
    syncCategoryRemoveButtons();
  }

  function addCategoryRow(category) {
    const row = document.createElement("article");
    row.className = "topic-category-row";
    row.innerHTML = `
      <div class="topic-grid topic-grid-category">
        <label class="field">
          <span>分类 ID</span>
          <input class="category-id" type="text" value="${escapeAttr(category.id || "")}" placeholder="ui-commonui" />
        </label>
        <label class="field">
          <span>分类名称</span>
          <input class="category-name" type="text" value="${escapeAttr(category.name || "")}" placeholder="UI/CommonUI" />
        </label>
        <label class="field">
          <span>优先级</span>
          <input class="category-priority" type="number" value="${escapeAttr(category.priority || 100)}" min="0" step="1" />
        </label>
        <button class="ghost-button danger-button category-remove" type="button">删除</button>
        <label class="field topic-grid-span-4">
          <span>关键词</span>
          <textarea class="category-keywords" rows="3" placeholder="每行一项，也可以逗号分隔。">${escapeHtml(
            formatListField(category.keywords || [])
          )}</textarea>
        </label>
      </div>
    `;
    row.querySelector(".category-remove").addEventListener("click", () => {
      row.remove();
      if (!elements.topicCategories.children.length) {
        addCategoryRow({ id: "", name: "", keywords: [], priority: 100 });
      }
      syncCategoryRemoveButtons();
    });
    elements.topicCategories.appendChild(row);
    syncCategoryRemoveButtons();
  }

  function syncCategoryRemoveButtons() {
    const buttons = Array.from(elements.topicCategories.querySelectorAll(".category-remove"));
    const disabled = buttons.length <= 1;
    buttons.forEach((button) => {
      button.disabled = disabled;
    });
  }

  function nextCategoryPriority() {
    const values = Array.from(elements.topicCategories.querySelectorAll(".category-priority"))
      .map((input) => Number(input.value || 0))
      .filter((value) => Number.isFinite(value));
    const highest = values.length ? Math.max(...values) : 90;
    return highest + 10;
  }

  async function submitTopicForm() {
    const payload = collectTopicFormPayload();
    setTopicFormError("");
    elements.topicFormSubmit.disabled = true;
    try {
      const response = await fetch(`${serviceConfig.apiBase}/packs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || `HTTP ${response.status}`);
      }

      await Promise.all([loadPacks(), loadTemplates()]);
      state.packSlug = data.pack.slug;
      elements.packSelect.value = data.pack.slug;
      state.notice = "专题已创建，请手动点击 Refresh 开始抓取。";
      closeTopicModal();
      resetFilters();
      await loadPayload(data.pack.slug, "auto");
    } catch (error) {
      setTopicFormError(error.message);
    } finally {
      elements.topicFormSubmit.disabled = false;
    }
  }

  function collectTopicFormPayload() {
    const categories = Array.from(elements.topicCategories.querySelectorAll(".topic-category-row")).map((row) => ({
      id: row.querySelector(".category-id").value.trim(),
      name: row.querySelector(".category-name").value.trim(),
      priority: Number(row.querySelector(".category-priority").value || 0),
      keywords: parseListField(row.querySelector(".category-keywords").value),
    }));

    return {
      slug: elements.topicSlug.value.trim(),
      display_name: elements.topicDisplayName.value.trim(),
      description: elements.topicDescription.value.trim(),
      base_template_slug: elements.topicTemplateSelect.value,
      search: {
        core_terms: parseListField(elements.topicCoreTerms.value),
        expansion_terms: parseListField(elements.topicExpansionTerms.value),
        custom_queries: parseListField(elements.topicCustomQueries.value),
      },
      gates: {
        must_have_any: parseListField(elements.topicMustHaveAny.value),
        irrelevant_keywords: parseListField(elements.topicIrrelevantKeywords.value),
      },
      categories,
    };
  }

  function setTopicFormError(message) {
    const text = String(message || "").trim();
    elements.topicFormError.textContent = text;
    elements.topicFormError.classList.toggle("hidden", !text);
    elements.topicFormError.classList.toggle("has-error", Boolean(text));
  }

  async function loadPayload(packSlug, mode) {
    const query = new URLSearchParams({ mode: mode || "auto" });
    const response = await fetch(`${serviceConfig.apiBase}/packs/${encodeURIComponent(packSlug)}/videos?${query}`);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const payload = await response.json();
    applyPayload(payload);
    if (payload.job && ["queued", "running"].includes(payload.job.status)) {
      subscribeToJob(payload.job.id);
    } else {
      stopRealtime();
    }
  }

  function applyPayload(payload) {
    state.payload = payload;
    state.activeJob = payload.job || null;

    elements.pageTitle.textContent = payload.pack ? payload.pack.display_name : "B站知识库";
    const baseDescription =
      (payload.pack && payload.pack.description) || "面向教程检索、专题归档和学习规划的本地知识库。";
    elements.pageDescription.textContent =
      payload.pack && payload.pack.domain_label ? `${baseDescription} 领域：${payload.pack.domain_label}` : baseDescription;

    populateHero(payload);
    populateFilters(payload);
    updateServicePanel(payload);

    const videos = payload.videos || [];
    if (!videos.some((item) => item.video_id === state.activeVideoId)) {
      state.activeVideoId = videos[0] ? videos[0].video_id : null;
    }
    render();
  }

  function populateHero(payload) {
    const snapshot = payload.snapshot || {};
    elements.generatedAt.textContent = formatDateTime(payload.generated_at || snapshot.last_refreshed_at);

    const stats = [
      ["视频总数", `${payload.summary.total_videos || 0}`],
      ["总时长", payload.summary.total_duration_text || humanizeDuration(payload.summary.total_duration_seconds || 0)],
      ["分类数", `${payload.summary.total_categories || 0}`],
      ["UP主数", `${payload.summary.total_uploaders || 0}`],
    ];
    elements.heroStats.innerHTML = stats
      .map(
        ([label, value]) => `
          <article class="stat-card">
            <span class="stat-label">${escapeHtml(label)}</span>
            <strong class="stat-value">${escapeHtml(value)}</strong>
          </article>
        `
      )
      .join("");

    const categories = payload.categories || [];
    if (!categories.length) {
      elements.categoryOverview.innerHTML = '<p class="meta-text">当前还没有分类快照。</p>';
      return;
    }
    elements.categoryOverview.innerHTML = categories
      .slice(0, 6)
      .map(
        (item) => `
          <article class="mini-category">
            <span class="mini-label">${escapeHtml(item.name)}</span>
            <strong>${item.count} 条</strong>
            <div class="meta-text">${escapeHtml(item.total_duration_text || "-")}</div>
          </article>
        `
      )
      .join("");
  }

  function populateFilters(payload) {
    const categories = payload.categories || [];
    elements.categorySelect.innerHTML = ['<option value="all">全部分类</option>']
      .concat(
        categories.map(
          (item) => `<option value="${escapeAttr(item.name)}">${escapeHtml(item.name)} (${item.count})</option>`
        )
      )
      .join("");
    if (![...elements.categorySelect.options].some((option) => option.value === state.category)) {
      state.category = "all";
    }
    elements.categorySelect.value = state.category;

    elements.categoryChips.innerHTML = ['<button class="category-chip active" data-category="all" type="button">全部</button>']
      .concat(
        categories.map(
          (item) =>
            `<button class="category-chip" data-category="${escapeAttr(item.name)}" type="button">${escapeHtml(
              item.name
            )}<span class="chip-count"> ${item.count}</span></button>`
        )
      )
      .join("");

    elements.categoryChips.querySelectorAll(".category-chip").forEach((button) => {
      button.addEventListener("click", () => {
        state.category = button.dataset.category || "all";
        elements.categorySelect.value = state.category;
        syncChipState();
        render();
      });
    });
    syncChipState();
  }

  function updateServicePanel(payload) {
    const snapshot = payload.snapshot || {};
    const job = payload.job || null;
    const lastError = payload.last_error || snapshot.last_error || null;
    const modeLabel = payload.mode === "preview" ? "预览结果" : payload.mode === "snapshot" ? "已提交快照" : "暂无快照";

    elements.serviceStatus.textContent = job ? describeJobStatus(job.status) : modeLabel;
    elements.lastRefreshed.textContent = formatDateTime(snapshot.last_refreshed_at || payload.generated_at);

    const noticeText =
      state.notice ||
      (payload.mode === "empty" && !job ? "当前专题还没有已提交快照，可以先点击 Refresh 开始抓取。" : "");
    elements.serviceNotice.textContent = noticeText;
    elements.serviceNotice.classList.toggle("hidden", !noticeText);

    if (lastError) {
      elements.serviceError.textContent = `${lastError.code || "error"}: ${lastError.message || ""}`;
      elements.serviceError.classList.add("has-error");
    } else {
      elements.serviceError.textContent = "当前没有错误。";
      elements.serviceError.classList.remove("has-error");
    }

    if (job) {
      const counters = job.counters || {};
      const meta = job.meta || {};
      const totalTasks = meta.total_tasks || snapshot.total_tasks || counters.searched_tasks || "?";
      const completedTasks = counters.completed_tasks || 0;
      elements.jobBanner.textContent = `${describeJobStatus(job.status)} · 已完成 ${completedTasks} / ${totalTasks} 个任务`;
      elements.jobBanner.classList.add("is-visible");
    } else if (payload.generated_at || snapshot.last_refreshed_at) {
      elements.jobBanner.textContent = modeLabel;
      elements.jobBanner.classList.add("is-visible");
    } else {
      elements.jobBanner.textContent = "";
      elements.jobBanner.classList.remove("is-visible");
    }

    const jobRunning = Boolean(job && ["queued", "running"].includes(job.status));
    elements.refreshButton.disabled = jobRunning;
    elements.cancelButton.disabled = !jobRunning;
  }

  async function requestRefresh() {
    const response = await fetch(`${serviceConfig.apiBase}/packs/${encodeURIComponent(state.packSlug)}/refresh`, {
      method: "POST",
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    state.activeJob = await response.json();
    subscribeToJob(state.activeJob.id);
    await loadPayload(state.packSlug, "auto");
  }

  async function requestCancel(jobId) {
    const response = await fetch(`${serviceConfig.apiBase}/jobs/${encodeURIComponent(jobId)}/cancel`, {
      method: "POST",
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    state.activeJob = await response.json();
    updateServicePanel(state.payload || defaultEmptyPayload());
  }

  function subscribeToJob(jobId) {
    if (!serviceConfig || !jobId) {
      return;
    }
    if (state.eventSource) {
      state.eventSource.close();
    }
    stopPolling();
    state.eventSource = new EventSource(`${serviceConfig.apiBase}/jobs/${encodeURIComponent(jobId)}/events`);
    [
      "job_started",
      "run_started",
      "task_started",
      "task_completed",
      "task_failed",
      "run_succeeded",
      "run_failed",
      "run_cancelled",
    ].forEach((eventName) => state.eventSource.addEventListener(eventName, handleRealtimeEvent));
    state.eventSource.onerror = () => {
      startPolling(jobId);
    };
  }

  async function handleRealtimeEvent(event) {
    try {
      const eventPayload = JSON.parse(event.data);
      if (eventPayload && eventPayload.job_id) {
        const jobResponse = await fetch(`${serviceConfig.apiBase}/jobs/${encodeURIComponent(eventPayload.job_id)}`);
        if (jobResponse.ok) {
          state.activeJob = await jobResponse.json();
        }
      }
      await loadPayload(state.packSlug, "auto");
      if (["run_succeeded", "run_failed", "run_cancelled"].includes(event.type)) {
        stopRealtime();
      }
    } catch (error) {
      startPolling(state.activeJob ? state.activeJob.id : null);
    }
  }

  function startPolling(jobId) {
    if (!jobId) {
      return;
    }
    if (state.eventSource) {
      state.eventSource.close();
      state.eventSource = null;
    }
    if (state.pollingTimer) {
      return;
    }
    state.pollingTimer = window.setInterval(async () => {
      const response = await fetch(`${serviceConfig.apiBase}/jobs/${encodeURIComponent(jobId)}`);
      if (!response.ok) {
        stopPolling();
        return;
      }
      state.activeJob = await response.json();
      await loadPayload(state.packSlug, "auto");
      if (!state.activeJob || !["queued", "running"].includes(state.activeJob.status)) {
        stopRealtime();
      }
    }, 5000);
  }

  function stopPolling() {
    if (state.pollingTimer) {
      window.clearInterval(state.pollingTimer);
      state.pollingTimer = null;
    }
  }

  function stopRealtime() {
    if (state.eventSource) {
      state.eventSource.close();
      state.eventSource = null;
    }
    stopPolling();
  }

  function render() {
    const payload = state.payload;
    if (!payload || !Array.isArray(payload.videos)) {
      showEmpty("没有可用数据。");
      return;
    }
    const filtered = filterVideos(payload.videos);
    const sorted = sortVideos(filtered);
    renderSummary(sorted);
    renderGrid(sorted);
    renderDetail(sorted);
  }

  function filterVideos(videos) {
    return videos.filter((video) => {
      if (state.category !== "all" && video.primary_category !== state.category) {
        return false;
      }
      if (state.status === "ok" && video.status !== "ok") {
        return false;
      }
      if (state.status === "needs_review" && video.status !== "needs_review") {
        return false;
      }
      if (!state.search) {
        return true;
      }
      const haystack = [
        video.title,
        video.uploader,
        ...(video.tags || []),
        video.desc_excerpt,
        ...(video.match_keywords || []),
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(state.search);
    });
  }

  function sortVideos(videos) {
    const items = videos.slice();
    items.sort((left, right) => {
      if (state.sort === "publish_desc") {
        return (right.publish_time || "").localeCompare(left.publish_time || "");
      }
      if (state.sort === "duration_desc") {
        return (right.duration_seconds || 0) - (left.duration_seconds || 0);
      }
      if (state.sort === "confidence_desc") {
        return (right.category_confidence || 0) - (left.category_confidence || 0);
      }
      return (right.play_count || 0) - (left.play_count || 0);
    });
    return items;
  }

  function renderSummary(videos) {
    const duration = videos.reduce((sum, video) => sum + (video.duration_seconds || 0), 0);
    elements.resultsSummary.textContent = `当前结果 ${videos.length} 条，累计时长 ${humanizeDuration(duration)}。`;
  }

  function renderGrid(videos) {
    elements.videoGrid.innerHTML = "";
    if (!videos.length) {
      elements.emptyState.classList.remove("hidden");
      elements.emptyStateText.textContent = "没有匹配结果。";
      return;
    }
    elements.emptyState.classList.add("hidden");

    const fragment = document.createDocumentFragment();
    videos.forEach((video) => {
      const card = document.createElement("article");
      card.className = "video-card";
      if (state.activeVideoId === video.video_id) {
        card.classList.add("is-active");
      }
      if (state.highlightReview && video.status === "needs_review") {
        card.classList.add("review-highlight");
      }
      card.innerHTML = `
        <div class="video-card-top">
          <div>
            <div class="card-actions">
              <span class="inline-chip primary">${escapeHtml(video.primary_category)}</span>
              ${video.status === "needs_review" ? '<span class="inline-chip review">待复核</span>' : ""}
            </div>
            <h3>${escapeHtml(video.title)}</h3>
          </div>
          <div class="meta-text">置信度 ${formatConfidence(video.category_confidence)}</div>
        </div>
        <div class="video-card-bottom">
          <p class="meta-text">${escapeHtml(video.desc_excerpt || "暂无简介。")}</p>
          <div class="meta-row">
            <span class="video-tag">${escapeHtml(video.uploader || "-")}</span>
            <span class="video-tag">${escapeHtml(video.duration_text || "-")}</span>
            <span class="video-tag">播放 ${formatNumber(video.play_count)}</span>
            <span class="video-tag">${escapeHtml(formatDate(video.publish_time))}</span>
          </div>
        </div>
      `;
      card.addEventListener("click", () => {
        state.activeVideoId = video.video_id;
        renderGrid(videos);
        renderDetail(videos);
      });
      fragment.appendChild(card);
    });
    elements.videoGrid.appendChild(fragment);
  }

  function renderDetail(videos) {
    const selected = videos.find((video) => video.video_id === state.activeVideoId) || videos[0];
    if (!selected) {
      elements.detailCard.innerHTML = '<p class="detail-hint">当前没有可展示的视频。</p>';
      return;
    }

    state.activeVideoId = selected.video_id;
    const matchedKeywords = uniqueStrings(selected.match_keywords || []);
    const tags = uniqueStrings(selected.tags || []);
    const secondaryCategories = uniqueStrings(selected.secondary_categories || []);

    elements.detailCard.innerHTML = `
      <div class="detail-section">
        <div class="card-actions">
          <span class="inline-chip primary">${escapeHtml(selected.primary_category || "未分类")}</span>
          ${selected.status === "needs_review" ? '<span class="inline-chip review">待复核</span>' : ""}
        </div>
        <h2 class="detail-title">${escapeHtml(selected.title)}</h2>
        <p class="detail-text">${escapeHtml(selected.desc_excerpt || "暂无简介。")}</p>
        <div class="detail-actions">
          <a class="open-button" href="${escapeAttr(selected.link)}" target="_blank" rel="noreferrer">打开视频</a>
        </div>
      </div>

      <div class="detail-stats">
        <div class="detail-box">
          <span class="detail-label">UP主</span>
          <strong>${escapeHtml(selected.uploader || "-")}</strong>
        </div>
        <div class="detail-box">
          <span class="detail-label">播放量</span>
          <strong>${formatNumber(selected.play_count)}</strong>
        </div>
        <div class="detail-box">
          <span class="detail-label">时长</span>
          <strong>${escapeHtml(selected.duration_text || "-")}</strong>
        </div>
        <div class="detail-box">
          <span class="detail-label">发布时间</span>
          <strong>${escapeHtml(formatDate(selected.publish_time))}</strong>
        </div>
      </div>

      <div class="detail-section">
        <span class="detail-label">命中关键词</span>
        <div class="detail-tags">${renderTags(matchedKeywords)}</div>
      </div>

      <div class="detail-section">
        <span class="detail-label">视频标签</span>
        <div class="detail-tags">${renderTags(tags)}</div>
      </div>

      <div class="detail-section">
        <span class="detail-label">次分类</span>
        <div class="detail-tags">${renderTags(secondaryCategories)}</div>
      </div>

      <div class="detail-section">
        <span class="detail-label">来源页面与查询词</span>
        <p class="detail-text">查询词：${escapeHtml((selected.query_keywords || []).join(" / ") || "-")}</p>
        <p class="detail-text">来源页：${escapeHtml((selected.source_pages || []).join(" / ") || "-")}</p>
        <p class="detail-text">平台分区：${escapeHtml(selected.platform_partition_name || "-")}</p>
      </div>
    `;
  }

  function showEmpty(message) {
    state.payload = defaultEmptyPayload();
    elements.emptyState.classList.remove("hidden");
    elements.emptyStateText.textContent = message;
    elements.resultsSummary.textContent = message;
    elements.videoGrid.innerHTML = "";
    elements.detailCard.innerHTML = '<p class="detail-hint">当前没有可展示的视频。</p>';
    updateServicePanel(state.payload);
  }

  function defaultEmptyPayload() {
    return {
      pack: { slug: "", display_name: "B站知识库", description: "" },
      generated_at: "",
      summary: {
        total_videos: 0,
        total_categories: 0,
        total_uploaders: 0,
        total_duration_seconds: 0,
        total_duration_text: "0秒",
      },
      categories: [],
      videos: [],
      snapshot: {},
      mode: "empty",
      job: null,
      last_error: null,
    };
  }

  function syncChipState() {
    elements.categoryChips.querySelectorAll(".category-chip").forEach((button) => {
      button.classList.toggle("active", (button.dataset.category || "all") === state.category);
    });
  }

  function renderTags(values) {
    if (!values.length) {
      return '<span class="meta-text">无</span>';
    }
    return values.map((item) => `<span class="video-tag">${escapeHtml(item)}</span>`).join("");
  }

  function describeJobStatus(status) {
    if (status === "queued") return "排队中";
    if (status === "running") return "刷新中";
    if (status === "succeeded") return "刷新成功";
    if (status === "failed") return "刷新失败";
    if (status === "cancelled") return "已取消";
    return "静态快照";
  }

  function parseListField(value) {
    const items = String(value || "")
      .split(/\r?\n|,/)
      .map((item) => item.trim())
      .filter(Boolean);
    return uniqueStrings(items);
  }

  function formatListField(items) {
    return (items || []).join("\n");
  }

  function slugify(value) {
    return String(value || "")
      .trim()
      .toLowerCase()
      .replace(/[_\s]+/g, "-")
      .replace(/[^a-z0-9-]/g, "-")
      .replace(/-+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 49);
  }

  function formatDateTime(value) {
    if (!value) return "-";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString("zh-CN", { hour12: false });
  }

  function formatDate(value) {
    if (!value) return "-";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value.slice(0, 10) || value;
    return date.toLocaleDateString("zh-CN");
  }

  function formatNumber(value) {
    const number = Number(value || 0);
    return Number.isFinite(number) ? number.toLocaleString("zh-CN") : "-";
  }

  function formatConfidence(value) {
    const number = Number(value || 0);
    return `${Math.round(number * 100)}%`;
  }

  function humanizeDuration(totalSeconds) {
    const seconds = Number(totalSeconds || 0);
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const remain = seconds % 60;
    if (hours > 0) return `${hours}小时${minutes}分${remain}秒`;
    if (minutes > 0) return `${minutes}分${remain}秒`;
    return `${remain}秒`;
  }

  function uniqueStrings(values) {
    return Array.from(new Set((values || []).map((item) => String(item).trim()).filter(Boolean)));
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function escapeAttr(value) {
    return escapeHtml(value);
  }
})();
