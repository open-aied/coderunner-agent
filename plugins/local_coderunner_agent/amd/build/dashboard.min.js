define([], function() {
    'use strict';

    var proxyUrl = '';
    var dashboardTimezone = 'Asia/Tokyo';
    var fixedCourseId = '';

    var PHASE_COLORS = {
        planning:         '#4e79a7',
        program_creation: '#f28e2b',
        error_correction: '#e15759',
        self_reflection:  '#59a14f'
    };

    var PHASE_LABELS = {
        planning:         'Planning',
        program_creation: 'Program Creation',
        error_correction: 'Error Correction',
        self_reflection:  'Self-Reflection'
    };

    var chartInstances = {};
    var allStudents = [];

    function escapeHtml(text) {
        var div = document.createElement('div');
        div.textContent = text == null ? '' : String(text);
        return div.innerHTML;
    }

    function formatExerciseLabel(exerciseId, exerciseLabel) {
        var label = (exerciseLabel || '').trim();
        if (label) {
            return label;
        }
        return String(exerciseId == null ? '' : exerciseId);
    }

    function getFilters() {
        var courseEl = document.getElementById('cra-filter-course');
        var courseId = fixedCourseId || (courseEl ? courseEl.value.trim() : '');
        var dateFrom = document.getElementById('cra-filter-datefrom').value;
        var dateTo = document.getElementById('cra-filter-dateto').value;
        var params = {};
        if (courseId) { params.course_id = courseId; }
        if (dateFrom) { params.date_from = dateFrom; }
        if (dateTo) { params.date_to = dateTo; }
        return params;
    }

    function buildUrl(endpoint, extraParams) {
        var url = proxyUrl + '?endpoint=' + encodeURIComponent(endpoint);
        var params = Object.assign({}, getFilters(), extraParams || {});
        Object.keys(params).forEach(function(key) {
            if (params[key] !== undefined && params[key] !== '') {
                url += '&' + encodeURIComponent(key) + '=' + encodeURIComponent(params[key]);
            }
        });
        return url;
    }

    function fetchApi(endpoint, extraParams) {
        var url = buildUrl(endpoint, extraParams);
        return fetch(url).then(function(response) {
            if (!response.ok) { throw new Error('API error: ' + response.status); }
            return response.json();
        }).catch(function(err) {
            console.error('Dashboard fetch error:', endpoint, err);
            return null;
        });
    }

    function destroyChart(id) {
        if (chartInstances[id]) {
            chartInstances[id].destroy();
            delete chartInstances[id];
        }
    }

    function isValidTimeZone(timeZone) {
        try {
            new Intl.DateTimeFormat('en-US', {timeZone: timeZone});
            return true;
        } catch (e) {
            return false;
        }
    }

    function formatDashboardTime(value, options) {
        if (!value) { return ''; }

        var length = (options && options.length) || 19;
        var timeZone = isValidTimeZone(dashboardTimezone) ? dashboardTimezone : 'UTC';
        var normalized = value;

        if (/^\d{4}-\d{2}-\d{2}T/.test(normalized) && !/[zZ]|[+-]\d{2}:\d{2}$/.test(normalized)) {
            normalized += '+00:00';
        }

        var date = new Date(normalized);
        if (Number.isNaN(date.getTime())) {
            return value.replace('T', ' ').substring(0, length);
        }

        return date.toLocaleString('sv-SE', {
            timeZone: timeZone,
            hour12: false
        }).substring(0, length);
    }

    // ── Overview Cards ──────────────────────────────────────────────────────

    function loadOverview() {
        return fetchApi('/api/v1/analytics/overview').then(function(data) {
            if (!data) { return; }
            document.getElementById('cra-total-interactions').textContent = data.total_interactions || 0;
            document.getElementById('cra-active-students').textContent = data.unique_students || 0;
            document.getElementById('cra-exercises-used').textContent = data.unique_exercises || 0;
            var avg = data.avg_latency_ms;
            document.getElementById('cra-avg-response-time').textContent =
                (typeof avg === 'number' && avg > 0) ? (avg / 1000).toFixed(1) + 's' : '-';
            document.getElementById('cra-thumbs-up').textContent =
                (data.thumbs_up != null) ? data.thumbs_up : 0;
            document.getElementById('cra-thumbs-down').textContent =
                (data.thumbs_down != null) ? data.thumbs_down : 0;
            document.getElementById('cra-satisfaction-pct').textContent =
                (data.satisfaction_pct != null) ? data.satisfaction_pct.toFixed(1) + '%' : '-';
        });
    }

    // ── Phase Distribution ──────────────────────────────────────────────────

    function loadPhaseDistribution() {
        return fetchApi('/api/v1/analytics/phase-distribution').then(function(data) {
            if (!data || !data.length) { return; }
            var labels = data.map(function(d) { return PHASE_LABELS[d.phase] || d.phase; });
            var values = data.map(function(d) { return d.count; });
            var colors = data.map(function(d) { return PHASE_COLORS[d.phase] || '#999'; });

            destroyChart('phase');
            var ctx = document.getElementById('cra-chart-phase').getContext('2d');
            chartInstances.phase = new Chart(ctx, {
                type: 'doughnut',
                data: { labels: labels, datasets: [{ data: values, backgroundColor: colors }] },
                options: { responsive: true, plugins: { legend: { position: 'right' } } }
            });
        });
    }

    // ── Timeline ────────────────────────────────────────────────────────────

    function loadTimeline() {
        return fetchApi('/api/v1/analytics/timeline').then(function(data) {
            if (!data || !data.length) { return; }
            var labels = data.map(function(d) { return d.date; });
            var counts = data.map(function(d) { return d.count; });
            var students = data.map(function(d) { return d.unique_students; });

            destroyChart('timeline');
            var ctx = document.getElementById('cra-chart-timeline').getContext('2d');
            chartInstances.timeline = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [
                        { label: 'Interactions', data: counts, backgroundColor: '#4e79a7' },
                        { label: 'Unique Students', data: students, backgroundColor: '#76b7b2' }
                    ]
                },
                options: {
                    responsive: true,
                    plugins: { legend: { position: 'bottom' } },
                    scales: { y: { beginAtZero: true } }
                }
            });
        });
    }

    // ── Exercise Heatmap ────────────────────────────────────────────────────

    function loadHeatmap() {
        return fetchApi('/api/v1/analytics/exercise-heatmap').then(function(data) {
            var container = document.getElementById('cra-heatmap');
            if (!data || !data.length) {
                container.innerHTML = '<p class="text-muted">No data</p>';
                return;
            }

            var phases = ['planning', 'program_creation', 'error_correction', 'self_reflection'];
            var maxCount = 0;
            data.forEach(function(ex) {
                phases.forEach(function(p) {
                    var v = (ex.by_phase && ex.by_phase[p]) || 0;
                    if (v > maxCount) { maxCount = v; }
                });
            });

            var html = '<table class="table table-bordered table-sm"><thead><tr><th>Exercise</th>';
            phases.forEach(function(p) { html += '<th>' + (PHASE_LABELS[p] || p) + '</th>'; });
            html += '<th>Total</th></tr></thead><tbody>';

            data.forEach(function(ex) {
                var rowLabel = formatExerciseLabel(ex.exercise_id, ex.exercise_label);
                html += '<tr><td><strong title="' + escapeHtml(ex.exercise_id) + '">' +
                    escapeHtml(rowLabel) + '</strong></td>';
                phases.forEach(function(p) {
                    var v = (ex.by_phase && ex.by_phase[p]) || 0;
                    var intensity = maxCount > 0 ? v / maxCount : 0;
                    var bg = 'rgba(225, 87, 89, ' + (0.1 + intensity * 0.8).toFixed(2) + ')';
                    var color = intensity > 0.5 ? 'white' : '#333';
                    html += '<td style="text-align:center;background:' + bg + ';color:' + color + '">' + v + '</td>';
                });
                html += '<td style="text-align:center;font-weight:bold">' + ex.total + '</td></tr>';
            });
            html += '</tbody></table>';
            container.innerHTML = html;
        });
    }

    // ── Strategy Usage ──────────────────────────────────────────────────────

    function loadStrategyUsage() {
        return fetchApi('/api/v1/analytics/strategy-usage').then(function(data) {
            if (!data || !data.length) { return; }

            var allStrategies = [];
            var phaseNames = [];
            data.forEach(function(p) {
                phaseNames.push(p.phase);
                p.strategies.forEach(function(s) {
                    if (allStrategies.indexOf(s.strategy) === -1) {
                        allStrategies.push(s.strategy);
                    }
                });
            });

            var datasets = phaseNames.map(function(phase) {
                var phaseData = data.find(function(d) { return d.phase === phase; });
                var values = allStrategies.map(function(s) {
                    var found = phaseData.strategies.find(function(st) { return st.strategy === s; });
                    return found ? found.count : 0;
                });
                return {
                    label: PHASE_LABELS[phase] || phase,
                    data: values,
                    backgroundColor: PHASE_COLORS[phase] || '#999'
                };
            });

            destroyChart('strategy');
            var ctx = document.getElementById('cra-chart-strategy').getContext('2d');
            chartInstances.strategy = new Chart(ctx, {
                type: 'bar',
                data: { labels: allStrategies, datasets: datasets },
                options: {
                    indexAxis: 'y',
                    responsive: true,
                    plugins: { legend: { position: 'bottom' } },
                    scales: { x: { stacked: true, beginAtZero: true }, y: { stacked: true } }
                }
            });
        });
    }

    // ── Student Table ───────────────────────────────────────────────────────

    function loadStudents() {
        return fetchApi('/api/v1/analytics/students', { limit: 200 }).then(function(data) {
            if (!data) { return; }
            allStudents = data.students || [];
            renderStudentTable(allStudents);
        });
    }

    function renderStudentTable(students) {
        var tbody = document.getElementById('cra-student-tbody');
        if (!students || !students.length) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">No data</td></tr>';
            return;
        }
        var html = '';
        students.forEach(function(s) {
            var color = PHASE_COLORS[s.top_phase] || '#6c757d';
            var lastActive = formatDashboardTime(s.last_active, {length: 16});
            html += '<tr>';
            html += '<td>' + s.user_id + '</td>';
            html += '<td style="text-align:center">' + s.total_interactions + '</td>';
            html += '<td style="text-align:center"><span class="badge" style="background:' + color +
                    ';color:white;padding:2px 8px;border-radius:10px">' +
                    (PHASE_LABELS[s.top_phase] || s.top_phase) + '</span></td>';
            html += '<td style="text-align:center">' + s.unique_exercises + '</td>';
            html += '<td style="text-align:center;color:#666">' + lastActive + '</td>';
            html += '<td style="text-align:center"><a href="#" class="cra-view-detail" data-userid="' +
                    s.user_id + '">View Detail</a></td>';
            html += '</tr>';
        });
        tbody.innerHTML = html;
    }

    // ── Student Detail ──────────────────────────────────────────────────────

    function showStudentDetail(userId) {
        return fetchApi('/api/v1/analytics/student/' + encodeURIComponent(userId)).then(function(data) {
            if (!data) { return; }
            var detail = document.getElementById('cra-student-detail');
            detail.style.display = 'block';
            document.getElementById('cra-detail-title').textContent = 'Student: ' + data.user_id;

            // Phase doughnut
            var dist = data.phase_distribution || [];
            destroyChart('detailPhase');
            var ctx = document.getElementById('cra-detail-phase-chart').getContext('2d');
            chartInstances.detailPhase = new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: dist.map(function(p) { return PHASE_LABELS[p.phase] || p.phase; }),
                    datasets: [{
                        data: dist.map(function(p) { return p.count; }),
                        backgroundColor: dist.map(function(p) { return PHASE_COLORS[p.phase] || '#999'; })
                    }]
                },
                options: { responsive: true, plugins: { legend: { position: 'right' } } }
            });

            // Interaction table
            var interactions = data.interactions || [];
            var tbody = document.getElementById('cra-detail-interactions-tbody');
            if (!interactions.length) {
                tbody.innerHTML = '<tr><td colspan="4" class="text-muted text-center">No data</td></tr>';
                return;
            }
            var html = '';
            interactions.forEach(function(i) {
                var phaseColor = PHASE_COLORS[i.srl_phase] || '#6c757d';
                html += '<tr>';
                html += '<td>' + escapeHtml(formatExerciseLabel(i.exercise_id, i.exercise_label)) + '</td>';
                html += '<td><span class="badge" style="background:' + phaseColor +
                        ';color:#fff;">' + (PHASE_LABELS[i.srl_phase] || i.srl_phase) + '</span></td>';
                html += '<td>' + i.strategy + '</td>';
                html += '<td>' + formatDashboardTime(i.timestamp, {length: 19}) + '</td>';
                html += '</tr>';
            });
            tbody.innerHTML = html;

            detail.scrollIntoView({ behavior: 'smooth' });
        });
    }

    // ── Export ───────────────────────────────────────────────────────────────

    function triggerExport(endpoint, extraParams) {
        var url = buildUrl(endpoint, extraParams);
        window.open(url, '_blank');
    }

    // ── Refresh All ─────────────────────────────────────────────────────────

    function refreshAll() {
        return Promise.all([
            loadOverview(),
            loadPhaseDistribution(),
            loadTimeline(),
            loadHeatmap(),
            loadStrategyUsage(),
            loadStudents()
        ]);
    }

    // ── Init ────────────────────────────────────────────────────────────────

    return {
        init: function(config) {
            proxyUrl = config.proxyUrl;
            dashboardTimezone = config.dashboardTimezone || 'Asia/Tokyo';
            fixedCourseId = config.courseId ? String(config.courseId) : '';

            if (fixedCourseId) {
                var courseEl = document.getElementById('cra-filter-course');
                if (courseEl) {
                    courseEl.value = fixedCourseId;
                    courseEl.readOnly = true;
                    courseEl.disabled = true;
                }
            }

            document.getElementById('cra-btn-refresh').addEventListener('click', function() {
                refreshAll();
            });

            document.getElementById('cra-btn-export-raw').addEventListener('click', function() {
                triggerExport('/api/v1/export/raw', { format: 'csv' });
            });

            document.getElementById('cra-btn-export-summary').addEventListener('click', function() {
                triggerExport('/api/v1/export/summary', { format: 'csv', group_by: 'student' });
            });

            document.getElementById('cra-student-tbody').addEventListener('click', function(e) {
                var target = e.target;
                if (target.classList.contains('cra-view-detail')) {
                    e.preventDefault();
                    var userId = target.getAttribute('data-userid');
                    if (userId) { showStudentDetail(userId); }
                }
            });

            document.getElementById('cra-detail-close').addEventListener('click', function() {
                document.getElementById('cra-student-detail').style.display = 'none';
            });

            document.getElementById('cra-student-search').addEventListener('input', function() {
                var q = this.value.toLowerCase();
                var filtered = allStudents.filter(function(s) {
                    return s.user_id.toLowerCase().indexOf(q) !== -1;
                });
                renderStudentTable(filtered);
            });

            // Initial load
            refreshAll();
        }
    };
});
