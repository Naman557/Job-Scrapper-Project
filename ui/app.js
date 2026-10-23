/**
 * Job Radar — Interactive Dashboard Controller
 * ==============================================
 * Flow: Search Modal → POST /api/scrape → Poll /api/status → Load results → Dashboard
 */
document.addEventListener('DOMContentLoaded', () => {
    'use strict';

    // ─── STATE ────────────────────────────────────────────────────
    const state = {
        jobs: [],
        filteredJobs: [],
        stats: {},
        updatedAt: '',
        viewMode: 'grid',
        activeFilters: {
            search: '',
            portal: 'all',
            type: 'all',
            location: 'all',
            sortBy: 'location_priority'
        },
        scraping: {
            active: false,
            pollInterval: null,
            startTime: null,
            timerInterval: null
        }
    };

    // ─── DOM REFS ─────────────────────────────────────────────────
    const elements = {
        // Modal
        searchModal: document.getElementById('searchModal'),
        searchForm: document.getElementById('searchForm'),
        modalJobTitle: document.getElementById('modalJobTitle'),
        modalExperience: document.getElementById('modalExperience'),
        modalTimeRange: document.getElementById('modalTimeRange'),
        modalLocation: document.getElementById('modalLocation'),
        startScrapeBtn: document.getElementById('startScrapeBtn'),

        // Loader
        scrapeLoader: document.getElementById('scrapeLoader'),
        loaderTitle: document.getElementById('loaderTitle'),
        loaderQuery: document.getElementById('loaderQuery'),
        loaderProgressFill: document.getElementById('loaderProgressFill'),
        loaderStatus: document.getElementById('loaderStatus'),
        loaderTimer: document.getElementById('loaderTimer'),

        // Dashboard
        dashboardContainer: document.getElementById('dashboardContainer'),
        lastUpdatedText: document.getElementById('lastUpdatedText'),
        newSearchBtn: document.getElementById('newSearchBtn'),
        refreshBtn: document.getElementById('refreshBtn'),
        exportCsvBtn: document.getElementById('exportCsvBtn'),

        // Stats
        statTotalJobs: document.getElementById('statTotalJobs'),
        statPortalsCount: document.getElementById('statPortalsCount'),
        statPuneCount: document.getElementById('statPuneCount'),
        statTypesRatio: document.getElementById('statTypesRatio'),

        // Search & Filters
        searchInput: document.getElementById('searchInput'),
        clearSearchBtn: document.getElementById('clearSearchBtn'),
        sortBySelect: document.getElementById('sortBySelect'),
        portalPillsContainer: document.getElementById('portalPillsContainer'),
        typePillsContainer: document.getElementById('typePillsContainer'),
        locationPillsContainer: document.getElementById('locationPillsContainer'),
        resetAllFiltersBtn: document.getElementById('resetAllFiltersBtn'),

        // View
        viewGridBtn: document.getElementById('viewGridBtn'),
        viewTableBtn: document.getElementById('viewTableBtn'),
        jobsGrid: document.getElementById('jobsGrid'),
        jobsTableSection: document.getElementById('jobsTableSection'),
        jobsTableBody: document.getElementById('jobsTableBody'),
        emptyState: document.getElementById('emptyState'),
        resultsCount: document.getElementById('resultsCount'),

        // Toast
        toast: document.getElementById('toast')
    };

    // ─── INIT ─────────────────────────────────────────────────────
    init();

    async function init() {
        setupEventListeners();

        try {
            const response = await fetch('/api/status', { cache: 'no-store' });
            if (response.ok) {
                const status = await response.json();
                if (status.is_scraping || status.running) {
                    const info = status.info || {};
                    elements.loaderQuery.textContent = info.job_title || '.NET Developer';
                    elements.loaderStatus.textContent = status.status || 'Searching configured portals...';
                    elements.searchModal.classList.remove('active');
                    elements.scrapeLoader.style.display = 'flex';
                    elements.dashboardContainer.style.display = 'none';
                    state.scraping.active = true;
                    state.scraping.startTime = Date.now() - (status.elapsed || 0) * 1000;
                    state.scraping.timerInterval = setInterval(updateTimerDisplay, 1000);
                    startPolling();
                    return;
                }
            }
        } catch (error) {
            console.warn('Could not check current scrape status:', error);
        }

        // Show saved results only when no initial or user-triggered scrape is running.
        if (await tryLoadExistingData()) {
            showDashboard();
        } else {
            showSearchModal();
        }
    }

    // ─── SEARCH MODAL ─────────────────────────────────────────────
    function showSearchModal() {
        elements.searchModal.classList.add('active');
        elements.scrapeLoader.style.display = 'none';
        elements.dashboardContainer.style.display = 'none';
        elements.modalJobTitle.focus();
    }

    function hideSearchModal() {
        elements.searchModal.classList.remove('active');
    }

    // ─── SCRAPING FLOW ────────────────────────────────────────────
    async function startScraping(jobTitle, experience, timeRange, location) {
        hideSearchModal();

        // Show loader
        elements.scrapeLoader.style.display = 'flex';
        elements.dashboardContainer.style.display = 'none';
        elements.loaderQuery.textContent = jobTitle;
        elements.loaderStatus.textContent = 'Initializing concurrent scrapers...';
        elements.loaderProgressFill.style.width = '5%';

        // Start timer
        state.scraping.active = true;
        state.scraping.startTime = Date.now();
        state.scraping.timerInterval = setInterval(updateTimerDisplay, 1000);

        // Fire the POST
        try {
            const res = await fetch('/api/scrape', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    job_title: jobTitle,
                    experience: experience,
                    max_age_days: parseInt(timeRange, 10),
                    location: location
                })
            });

            if (!res.ok) throw new Error(`Server error: ${res.status}`);

            const json = await res.json();

            if (json.started === false) {
                elements.loaderStatus.textContent = 'Scraper already running — waiting for results...';
            } else {
                elements.loaderStatus.textContent = 'Scraping all job boards concurrently...';
            }

            // Begin polling
            startPolling();
        } catch (err) {
            console.error('Failed to start scrape:', err);
            elements.loaderStatus.textContent = `Error: ${err.message}. Retrying...`;
            // Retry once after 3s
            setTimeout(() => startPolling(), 3000);
        }
    }

    function startPolling() {
        if (state.scraping.pollInterval) clearInterval(state.scraping.pollInterval);
        state.scraping.pollInterval = setInterval(pollScrapeStatus, 2000);
        pollScrapeStatus();
    }

    async function pollScrapeStatus() {
        try {
            const res = await fetch('/api/status', { cache: 'no-store' });
            const status = await res.json();

            const elapsed = status.elapsed || 0;
            const isRunning = status.is_scraping ?? status.running ?? false;
            const statusText = status.status || status.info?.status_message || 'scraping';

            // Animate the progress bar gradually
            if (isRunning) {
                const pctEstimate = Math.min(90, 5 + elapsed * 0.5);
                elements.loaderProgressFill.style.width = pctEstimate + '%';
                elements.loaderStatus.textContent = `Status: ${statusText} (${elapsed}s elapsed)`;
            } else {
                // Done!
                clearInterval(state.scraping.pollInterval);
                state.scraping.pollInterval = null;
                if (status.error) {
                    stopTimer();
                    showSearchModal();
                    showToast(`Scraping failed: ${status.error}`);
                    return;
                }

                elements.loaderProgressFill.style.width = '100%';
                elements.loaderStatus.textContent = 'Scraping complete! Loading consolidated results...';

                // Short delay for visual feedback, then load
                setTimeout(async () => {
                    await loadJobData(false);
                    stopTimer();
                    showDashboard();
                    showToast(`Loaded ${state.jobs.length} jobs from all boards!`);
                }, 800);
            }
        } catch (err) {
            console.error('Poll error:', err);
            elements.loaderStatus.textContent = 'Connection lost — retrying...';
        }
    }

    function updateTimerDisplay() {
        if (!state.scraping.startTime) return;
        const elapsed = Math.floor((Date.now() - state.scraping.startTime) / 1000);
        const mins = Math.floor(elapsed / 60);
        const secs = elapsed % 60;
        elements.loaderTimer.textContent = `Elapsed: ${mins > 0 ? mins + 'm ' : ''}${secs}s`;
    }

    function stopTimer() {
        state.scraping.active = false;
        if (state.scraping.timerInterval) {
            clearInterval(state.scraping.timerInterval);
            state.scraping.timerInterval = null;
        }
    }

    // ─── DASHBOARD DISPLAY ────────────────────────────────────────
    function showDashboard() {
        elements.searchModal.classList.remove('active');
        elements.scrapeLoader.style.display = 'none';
        elements.dashboardContainer.style.display = 'block';
    }

    // ─── DATA LOADING ─────────────────────────────────────────────
    async function tryLoadExistingData() {
        try {
            let res;
            try {
                res = await fetch('/api/jobs');
                if (!res.ok) throw new Error('API unavailable');
            } catch {
                res = await fetch('data/jobs.json');
            }
            const data = await res.json();
            if (data.jobs && data.jobs.length > 0) {
                state.jobs = data.jobs;
                state.stats = data.stats || {};
                state.updatedAt = data.updated_at || 'Just now';
                renderHeaderStats();
                renderPortalPills();
                applyFilters();
                return true;
            }
            return false;
        } catch {
            return false;
        }
    }

    async function loadJobData(isRefresh) {
        try {
            const endpoint = isRefresh ? '/api/refresh' : '/api/jobs';
            let res;
            try {
                res = await fetch(endpoint);
                if (!res.ok) throw new Error('API request failed');
            } catch {
                res = await fetch('data/jobs.json');
            }

            const data = await res.json();
            state.jobs = data.jobs || [];
            state.stats = data.stats || {};
            state.updatedAt = data.updated_at || 'Just now';

            renderHeaderStats();
            renderPortalPills();
            applyFilters();

            if (isRefresh) {
                showToast('Job listings re-synced successfully!');
            }
        } catch (error) {
            console.error('Failed to load job listings:', error);
            elements.lastUpdatedText.textContent = 'Failed to load data';
            showToast('Could not load job listings. Please check server.');
        }
    }

    // ─── TRIGGER SCRAPER (Refresh button — re-scrape with same params) ──
    async function triggerScraper() {
        elements.refreshBtn.querySelector('.spin-icon')?.classList.add('spinning');
        try {
            const res = await fetch('/api/refresh');
            if (res.ok) {
                await loadJobData(true);
            }
        } catch (err) {
            showToast('Refresh failed — check server');
        } finally {
            elements.refreshBtn.querySelector('.spin-icon')?.classList.remove('spinning');
        }
    }

    // ─── RENDER: HEADER STATS ─────────────────────────────────────
    function renderHeaderStats() {
        elements.lastUpdatedText.textContent = `Updated: ${state.updatedAt}`;
        elements.statTotalJobs.textContent = state.jobs.length;

        const portalCount = Object.keys(state.stats.portals || {}).length;
        elements.statPortalsCount.textContent = portalCount;

        const puneCount = state.jobs.filter(j =>
            (j.location || '').toLowerCase().includes('pune')
        ).length;
        elements.statPuneCount.textContent = puneCount;

        const perm = (state.stats.job_types && state.stats.job_types.permanent) || state.jobs.length;
        const free = (state.stats.job_types && state.stats.job_types.freelance) || 0;
        elements.statTypesRatio.textContent = `${perm} / ${free}`;
    }

    // ─── RENDER: PORTAL PILLS ─────────────────────────────────────
    function renderPortalPills() {
        const portals = state.stats.portals || {};
        const total = state.jobs.length;

        let pillsHtml = `
            <button class="pill ${state.activeFilters.portal === 'all' ? 'active' : ''}" data-portal="all">
                All Portals <span class="pill-count">${total}</span>
            </button>
        `;

        const sortedPortals = Object.entries(portals).sort((a, b) => b[1] - a[1]);

        sortedPortals.forEach(([portal, count]) => {
            const cleanName = formatPortalName(portal);
            const isActive = state.activeFilters.portal === portal ? 'active' : '';
            pillsHtml += `
                <button class="pill ${isActive}" data-portal="${portal}">
                    ${cleanName} <span class="pill-count">${count}</span>
                </button>
            `;
        });

        elements.portalPillsContainer.innerHTML = pillsHtml;

        elements.portalPillsContainer.querySelectorAll('.pill').forEach(btn => {
            btn.addEventListener('click', () => {
                elements.portalPillsContainer.querySelectorAll('.pill').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                state.activeFilters.portal = btn.getAttribute('data-portal');
                applyFilters();
            });
        });
    }

    // ─── HELPERS ──────────────────────────────────────────────────
    function formatPortalName(raw) {
        if (!raw) return 'General';
        const str = raw.replace(/^www\./, '').replace(/\.(com|tech|in|org|net)$/, '');
        return str.charAt(0).toUpperCase() + str.slice(1);
    }

    function getPortalBadgeClass(portal) {
        const p = (portal || '').toLowerCase();
        if (p.includes('naukri')) return 'naukri';
        if (p.includes('linkedin')) return 'linkedin';
        if (p.includes('glassdoor')) return 'glassdoor';
        if (p.includes('indeed')) return 'indeed';
        if (p.includes('hirist')) return 'hirist';
        if (p.includes('google')) return 'google';
        if (p.includes('foundit') || p.includes('monster')) return 'foundit';
        if (p.includes('shine')) return 'shine';
        if (p.includes('timesjobs') || p.includes('times')) return 'timesjobs';
        if (p.includes('remoteok')) return 'remoteok';
        if (p.includes('weworkremotely') || p.includes('wwr')) return 'weworkremotely';
        if (p.includes('upwork')) return 'upwork';
        if (p.includes('remotive')) return 'remotive';
        if (p.includes('wellfound') || p.includes('angel')) return 'wellfound';
        return 'default';
    }

    function getLocationWeight(loc) {
        const l = (loc || '').toLowerCase();
        if (l.includes('pune')) return 0;
        if (l.includes('bangalore') || l.includes('bengaluru')) return 1;
        if (l.includes('hyderabad')) return 2;
        if (l.includes('mumbai')) return 3;
        if (l.includes('delhi') || l.includes('gurgaon') || l.includes('noida')) return 4;
        if (l.includes('remote')) return 5;
        return 6;
    }

    function formatPostedAge(value) {
        if (value === null || value === undefined || value === '') return '';
        const days = Number(value);
        if (!Number.isFinite(days)) return '';
        if (days < 1) return 'Posted within 24 hours';
        if (days < 2) return 'Posted 1 day ago';
        if (days < 30) return `Posted ${Math.floor(days)} days ago`;
        if (days < 365) return `Posted ${Math.floor(days / 30.4375)} months ago`;
        return `Posted ${Math.floor(days / 365.25)} years ago`;
    }

    function getApplyLink(job) {
        const link = String(job.apply_link || '').trim();
        return /^https?:\/\/\S+$/i.test(link) ? link : '';
    }

    function csvCell(value) {
        return `"${String(value ?? '').replace(/"/g, '""')}"`;
    }

    // ─── APPLY FILTERS ───────────────────────────────────────────
    function applyFilters() {
        const { search, portal, type, location, sortBy } = state.activeFilters;
        const q = search.trim().toLowerCase();

        state.filteredJobs = state.jobs.filter(job => {
            if (q) {
                const title = (job.title || '').toLowerCase();
                const company = (job.company || '').toLowerCase();
                const loc = (job.location || '').toLowerCase();
                const exp = (job.experience || '').toLowerCase();
                const p = (job.portal || '').toLowerCase();
                if (!title.includes(q) && !company.includes(q) && !loc.includes(q) && !exp.includes(q) && !p.includes(q)) {
                    return false;
                }
            }
            if (portal !== 'all' && job.portal !== portal) return false;
            if (type !== 'all' && (job.job_type || 'permanent').toLowerCase() !== type) return false;
            if (location !== 'all') {
                const locStr = (job.location || '').toLowerCase();
                if (location === 'pune' && !locStr.includes('pune')) return false;
                if (location === 'remote' && !locStr.includes('remote')) return false;
                if (location === 'hybrid' && !locStr.includes('hybrid')) return false;
            }
            return true;
        });

        state.filteredJobs.sort((a, b) => {
            if (sortBy === 'location_priority') {
                const diff = getLocationWeight(a.location) - getLocationWeight(b.location);
                if (diff !== 0) return diff;
                return (a.title || '').localeCompare(b.title || '');
            } else if (sortBy === 'company_asc') {
                return (a.company || '').localeCompare(b.company || '');
            } else if (sortBy === 'title_asc') {
                return (a.title || '').localeCompare(b.title || '');
            } else if (sortBy === 'portal_asc') {
                return (a.portal || '').localeCompare(b.portal || '');
            }
            return 0;
        });

        renderListings();
    }

    // ─── RENDER LISTINGS ──────────────────────────────────────────
    function renderListings() {
        const count = state.filteredJobs.length;
        elements.resultsCount.textContent = `Showing ${count} of ${state.jobs.length} jobs`;

        if (count === 0) {
            elements.jobsGrid.style.display = 'none';
            elements.jobsTableSection.style.display = 'none';
            elements.emptyState.style.display = 'block';
            return;
        }

        elements.emptyState.style.display = 'none';

        if (state.viewMode === 'grid') {
            elements.jobsGrid.style.display = 'grid';
            elements.jobsTableSection.style.display = 'none';
            renderGrid();
        } else {
            elements.jobsGrid.style.display = 'none';
            elements.jobsTableSection.style.display = 'block';
            renderTable();
        }
    }

    // ─── RENDER GRID ──────────────────────────────────────────────
    function renderGrid() {
        const html = state.filteredJobs.map(job => {
            const portalClass = getPortalBadgeClass(job.portal);
            const portalName = formatPortalName(job.portal);
            const applyLink = getApplyLink(job);
            const isApplyValid = Boolean(applyLink);
            const typeLabel = (job.job_type || 'permanent').toUpperCase();
            const postedAge = formatPostedAge(job.posted_age_days);

            return `
                <div class="job-card" data-id="${job.id}">
                    <div>
                        <div class="card-top">
                            <span class="portal-badge ${portalClass}">${portalName}</span>
                            <span class="type-pill">${typeLabel}</span>
                        </div>
                        <h2 class="job-title">${escapeHtml(job.title)}</h2>
                        <div class="company-name">
                            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M3 21h18M3 7v14M21 7v14M6 11h4M6 15h4M14 11h4M14 15h4M9 3h6v4H9z"></path>
                            </svg>
                            ${escapeHtml(job.company)}
                        </div>
                        <div class="job-specs">
                            <div class="spec-item">
                                <svg class="spec-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M12 2a8 8 0 0 0-8 8c0 5.25 8 12 8 12s8-6.75 8-12a8 8 0 0 0-8-8z"></path>
                                    <circle cx="12" cy="10" r="3"></circle>
                                </svg>
                                <span>${escapeHtml(job.location)}</span>
                            </div>
                            <div class="spec-item">
                                <svg class="spec-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <rect x="2" y="7" width="20" height="14" rx="2" ry="2"></rect>
                                    <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"></path>
                                </svg>
                                <span>Exp: ${escapeHtml(job.experience)}</span>
                            </div>
                            <div class="spec-item">
                                <svg class="spec-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
                                    <circle cx="12" cy="7" r="4"></circle>
                                </svg>
                                <span>${escapeHtml(job.recruiter_contact)}</span>
                            </div>
                            ${postedAge ? `<div class="spec-item"><span>${escapeHtml(postedAge)}</span></div>` : ''}
                        </div>
                    </div>
                    <div class="card-footer">
                        ${isApplyValid ? `
                            <a href="${escapeHtml(applyLink)}" target="_blank" rel="noopener noreferrer" class="btn-apply">
                                <span>Direct Apply</span>
                                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                                    <line x1="7" y1="17" x2="17" y2="7"></line>
                                    <polyline points="7 7 17 7 17 17"></polyline>
                                </svg>
                            </a>
                        ` : `
                            <span class="btn-apply" style="opacity: 0.5; cursor: not-allowed;">No Direct Link</span>
                        `}
                        <button class="btn-icon-only copy-link-btn" data-link="${escapeHtml(applyLink)}" title="Copy application link">
                            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                            </svg>
                        </button>
                    </div>
                </div>
            `;
        }).join('');

        elements.jobsGrid.innerHTML = html;
        attachItemActions();
    }

    // ─── RENDER TABLE ─────────────────────────────────────────────
    function renderTable() {
        const rows = state.filteredJobs.map(job => {
            const portalClass = getPortalBadgeClass(job.portal);
            const portalName = formatPortalName(job.portal);
            const applyLink = getApplyLink(job);
            const isApplyValid = Boolean(applyLink);

            return `
                <tr>
                    <td><span class="portal-badge ${portalClass}">${portalName}</span></td>
                    <td style="font-weight: 600; color: #fff;">${escapeHtml(job.title)}</td>
                    <td style="color: #93c5fd;">${escapeHtml(job.company)}</td>
                    <td>${escapeHtml(job.location)}</td>
                    <td>${escapeHtml(job.experience)}</td>
                    <td>${escapeHtml(formatPostedAge(job.posted_age_days) || 'Not provided')}</td>
                    <td style="font-size: 0.8rem; color: #94a3b8;">${escapeHtml(job.recruiter_contact)}</td>
                    <td style="text-align: right;">
                        ${isApplyValid ? `
                            <a href="${escapeHtml(applyLink)}" target="_blank" rel="noopener noreferrer" class="btn-apply" style="padding: 5px 12px; font-size: 0.78rem;">
                                Apply
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <line x1="7" y1="17" x2="17" y2="7"></line>
                                    <polyline points="7 7 17 7 17 17"></polyline>
                                </svg>
                            </a>
                        ` : '<span style="color: #64748b;">N/A</span>'}
                    </td>
                </tr>
            `;
        }).join('');

        elements.jobsTableBody.innerHTML = rows;
    }

    // ─── ACTIONS ──────────────────────────────────────────────────
    function attachItemActions() {
        document.querySelectorAll('.copy-link-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const link = btn.getAttribute('data-link');
                if (link && link !== '#' && link !== 'N/A') {
                    navigator.clipboard.writeText(link).then(() => {
                        showToast('Direct job link copied!');
                    }).catch(() => showToast('Link copied!'));
                } else {
                    showToast('No direct link available for this listing');
                }
            });
        });
    }

    function showToast(message) {
        elements.toast.textContent = message;
        elements.toast.classList.add('show');
        setTimeout(() => elements.toast.classList.remove('show'), 2800);
    }

    // ─── CSV EXPORT ───────────────────────────────────────────────
    function exportToCsv() {
        if (!state.filteredJobs.length) {
            showToast('No jobs available to export');
            return;
        }

        const headers = ['Portal', 'Title', 'Company', 'Location', 'Experience', 'Posted', 'Recruiter Contact', 'Job Type', 'Apply Link'];
        const csvRows = [headers.map(csvCell).join(',')];

        state.filteredJobs.forEach(j => {
            const row = [
                j.portal || '',
                j.title || '',
                j.company || '',
                j.location || '',
                j.experience || '',
                formatPostedAge(j.posted_age_days),
                j.recruiter_contact || '',
                j.job_type || 'permanent',
                getApplyLink(j)
            ];
            csvRows.push(row.map(csvCell).join(','));
        });

        const csvContent = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csvRows.join('\n'));
        const link = document.createElement('a');
        link.setAttribute('href', csvContent);
        link.setAttribute('download', `job_radar_${Date.now()}.csv`);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        showToast(`Exported ${state.filteredJobs.length} jobs to CSV`);
    }

    // ─── EVENT LISTENERS ──────────────────────────────────────────
    function setupEventListeners() {
        // Search Form Submit — kicks off scraping
        elements.searchForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const jobTitle = elements.modalJobTitle.value.trim();
            const experience = elements.modalExperience.value;
            const timeRange = elements.modalTimeRange.value;
            const location = elements.modalLocation.value.trim();

            if (!jobTitle) {
                elements.modalJobTitle.focus();
                return;
            }

            startScraping(jobTitle, experience, timeRange, location);
        });

        // New Search button — show modal again
        elements.newSearchBtn.addEventListener('click', () => {
            showSearchModal();
        });

        // Search Input (filter within loaded results)
        let searchTimeout;
        elements.searchInput.addEventListener('input', (e) => {
            clearTimeout(searchTimeout);
            const val = e.target.value;
            elements.clearSearchBtn.style.display = val ? 'block' : 'none';
            searchTimeout = setTimeout(() => {
                state.activeFilters.search = val;
                applyFilters();
            }, 180);
        });

        elements.clearSearchBtn.addEventListener('click', () => {
            elements.searchInput.value = '';
            elements.clearSearchBtn.style.display = 'none';
            state.activeFilters.search = '';
            applyFilters();
        });

        elements.sortBySelect.addEventListener('change', (e) => {
            state.activeFilters.sortBy = e.target.value;
            applyFilters();
        });

        // Type Pills
        elements.typePillsContainer.querySelectorAll('.pill').forEach(btn => {
            btn.addEventListener('click', () => {
                elements.typePillsContainer.querySelectorAll('.pill').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                state.activeFilters.type = btn.getAttribute('data-type');
                applyFilters();
            });
        });

        // Location Pills
        elements.locationPillsContainer.querySelectorAll('.pill').forEach(btn => {
            btn.addEventListener('click', () => {
                elements.locationPillsContainer.querySelectorAll('.pill').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                state.activeFilters.location = btn.getAttribute('data-location');
                applyFilters();
            });
        });

        // Reset All Filters
        elements.resetAllFiltersBtn.addEventListener('click', () => {
            state.activeFilters = {
                search: '',
                portal: 'all',
                type: 'all',
                location: 'all',
                sortBy: 'location_priority'
            };
            elements.searchInput.value = '';
            elements.clearSearchBtn.style.display = 'none';
            elements.sortBySelect.value = 'location_priority';

            elements.portalPillsContainer.querySelectorAll('.pill').forEach((b, idx) => {
                b.classList.toggle('active', idx === 0);
            });
            elements.typePillsContainer.querySelectorAll('.pill').forEach((b, idx) => {
                b.classList.toggle('active', idx === 0);
            });
            elements.locationPillsContainer.querySelectorAll('.pill').forEach((b, idx) => {
                b.classList.toggle('active', idx === 0);
            });

            applyFilters();
            showToast('All filters reset');
        });

        // View Mode Toggles
        elements.viewGridBtn.addEventListener('click', () => {
            state.viewMode = 'grid';
            elements.viewGridBtn.classList.add('active');
            elements.viewTableBtn.classList.remove('active');
            renderListings();
        });

        elements.viewTableBtn.addEventListener('click', () => {
            state.viewMode = 'table';
            elements.viewTableBtn.classList.add('active');
            elements.viewGridBtn.classList.remove('active');
            renderListings();
        });

        // Refresh & Export
        elements.refreshBtn.addEventListener('click', () => triggerScraper());
        elements.exportCsvBtn.addEventListener('click', exportToCsv);
    }

    // ─── UTILITIES ────────────────────────────────────────────────
    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }
});
