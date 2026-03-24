(function () {
  const appData = window.__BILIBILI_KB_DATA__;

  const state = {
    search: "",
    category: "all",
    status: "all",
    sort: "play_desc",
    highlightReview: false,
    activeVideoId: null,
  };

  const elements = {
    heroStats: document.getElementById("hero-stats"),
    generatedAt: document.getElementById("generated-at"),
    categoryOverview: document.getElementById("category-overview"),
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
    detailCard: document.getElementById("detail-card"),
  };

  if (!appData || !Array.isArray(appData.videos)) {
    elements.resultsSummary.textContent = "没有可用的数据。";
    elements.emptyState.classList.remove("hidden");
    return;
  }

  const allVideos = appData.videos.slice();
  const categorySummary = appData.categories || [];

  initialize();

  function initialize() {
    populateHero();
    populateFilters();
    bindEvents();
    state.activeVideoId = allVideos[0] ? allVideos[0].video_id : null;
    render();
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
      render();
    });
  }

  function populateHero() {
    elements.generatedAt.textContent = formatDateTime(appData.generated_at);
    const stats = [
      ["视频总数", `${appData.summary.total_videos}`],
      ["总时长", appData.summary.total_duration_text],
      ["分类数", `${appData.summary.total_categories}`],
      ["UP主数", `${appData.summary.total_uploaders}`],
    ];
    elements.heroStats.innerHTML = stats
      .map(
        ([label, value]) => `
          <article class="stat-card">
            <span class="stat-label">${label}</span>
            <strong class="stat-value">${escapeHtml(value)}</strong>
          </article>
        `
      )
      .join("");

    elements.categoryOverview.innerHTML = categorySummary
      .slice(0, 6)
      .map(
        (item) => `
          <article class="mini-category">
            <span class="mini-label">${escapeHtml(item.name)}</span>
            <strong>${item.count} 条</strong>
            <div class="meta-text">${escapeHtml(item.total_duration_text)}</div>
          </article>
        `
      )
      .join("");
  }

  function populateFilters() {
    const options = ['<option value="all">全部分类</option>']
      .concat(
        categorySummary.map(
          (item) => `<option value="${escapeAttr(item.name)}">${escapeHtml(item.name)} (${item.count})</option>`
        )
      )
      .join("");
    elements.categorySelect.innerHTML = options;

    elements.categoryChips.innerHTML = ['<button class="category-chip active" data-category="all" type="button">全部</button>']
      .concat(
        categorySummary.map(
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
  }

  function syncChipState() {
    elements.categoryChips.querySelectorAll(".category-chip").forEach((button) => {
      button.classList.toggle("active", (button.dataset.category || "all") === state.category);
    });
  }

  function render() {
    const filtered = filterVideos(allVideos);
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
            <span class="video-tag">${escapeHtml(video.uploader)}</span>
            <span class="video-tag">${escapeHtml(video.duration_text)}</span>
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
          <span class="inline-chip primary">${escapeHtml(selected.primary_category)}</span>
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
          <strong>${escapeHtml(selected.uploader)}</strong>
        </div>
        <div class="detail-box">
          <span class="detail-label">播放量</span>
          <strong>${formatNumber(selected.play_count)}</strong>
        </div>
        <div class="detail-box">
          <span class="detail-label">时长</span>
          <strong>${escapeHtml(selected.duration_text)}</strong>
        </div>
        <div class="detail-box">
          <span class="detail-label">发布时间</span>
          <strong>${escapeHtml(formatDate(selected.publish_time))}</strong>
        </div>
      </div>

      <div class="detail-section">
        <span class="detail-label">命中关键词</span>
        <div class="detail-tags">${matchedKeywords.map((item) => `<span class="video-tag">${escapeHtml(item)}</span>`).join("") || '<span class="meta-text">无</span>'}</div>
      </div>

      <div class="detail-section">
        <span class="detail-label">视频标签</span>
        <div class="detail-tags">${tags.map((item) => `<span class="video-tag">${escapeHtml(item)}</span>`).join("") || '<span class="meta-text">无</span>'}</div>
      </div>

      <div class="detail-section">
        <span class="detail-label">次分类</span>
        <div class="detail-tags">${secondaryCategories.map((item) => `<span class="video-tag">${escapeHtml(item)}</span>`).join("") || '<span class="meta-text">无</span>'}</div>
      </div>

      <div class="detail-section">
        <span class="detail-label">来源页与查询词</span>
        <p class="detail-text">查询词：${escapeHtml((selected.query_keywords || []).join(" / ") || "-")}</p>
        <p class="detail-text">来源页：${escapeHtml((selected.source_pages || []).join(" / ") || "-")}</p>
      </div>
    `;
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

  function uniqueStrings(values) {
    return Array.from(new Set((values || []).filter(Boolean)));
  }
})();
