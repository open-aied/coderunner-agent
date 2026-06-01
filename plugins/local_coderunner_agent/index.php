<?php
require_once(__DIR__ . '/../../config.php');

$courseid = optional_param('course_id', 0, PARAM_INT);

if ($courseid > 0) {
    require_login($courseid);
    $context = context_course::instance($courseid);
    require_capability('local/coderunner_agent:viewdashboard', $context);
    $PAGE->set_url(new moodle_url('/local/coderunner_agent/index.php', ['course_id' => $courseid]));
    $PAGE->set_pagelayout('incourse');
} else {
    require_login();
    $context = context_system::instance();
    require_capability('local/coderunner_agent:viewdashboard', $context);
    $PAGE->set_url(new moodle_url('/local/coderunner_agent/index.php'));
    $PAGE->set_pagelayout('admin');
}

$PAGE->set_context($context);
$PAGE->set_title(get_string('dashboard', 'local_coderunner_agent'));
$PAGE->set_heading(get_string('dashboard', 'local_coderunner_agent'));

$dashboardtimezone = get_config('local_coderunner_agent', 'dashboard_timezone') ?: 'Asia/Tokyo';

$PAGE->requires->js(new moodle_url('https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js'), true);
$PAGE->requires->js_call_amd('local_coderunner_agent/dashboard', 'init', [[
    'proxyUrl' => (new moodle_url('/local/coderunner_agent/api.php'))->out(false),
    'dashboardTimezone' => $dashboardtimezone,
    'courseId' => $courseid ?: '',
]]);

echo $OUTPUT->header();
?>

<div class="cra-dashboard">
    <!-- Filter bar -->
    <div class="cra-filters mb-3 pb-3">
        <div class="cra-filter-group">
            <label for="cra-filter-course"><?php echo get_string('course', 'local_coderunner_agent'); ?></label>
            <input type="text" id="cra-filter-course" class="form-control" placeholder="<?php echo get_string('course', 'local_coderunner_agent'); ?>">
        </div>
        <div class="cra-filter-group">
            <label for="cra-filter-datefrom"><?php echo get_string('datefrom', 'local_coderunner_agent'); ?></label>
            <input type="text" id="cra-filter-datefrom" class="form-control" placeholder="YYYY-MM-DD" pattern="\d{4}-\d{2}-\d{2}" inputmode="numeric">
        </div>
        <div class="cra-filter-group">
            <label for="cra-filter-dateto"><?php echo get_string('dateto', 'local_coderunner_agent'); ?></label>
            <input type="text" id="cra-filter-dateto" class="form-control" placeholder="YYYY-MM-DD" pattern="\d{4}-\d{2}-\d{2}" inputmode="numeric">
        </div>
        <div class="cra-export-buttons d-flex align-items-end">
            <button id="cra-btn-refresh" class="btn btn-primary mr-2"><?php echo get_string('refresh', 'local_coderunner_agent'); ?></button>
            <button id="cra-btn-export-raw" class="btn btn-outline-secondary mr-2"><?php echo get_string('exportraw', 'local_coderunner_agent'); ?></button>
            <button id="cra-btn-export-summary" class="btn btn-outline-secondary"><?php echo get_string('exportsummary', 'local_coderunner_agent'); ?></button>
        </div>
    </div>

    <!-- Overview cards -->
    <div class="cra-overview-cards mb-4">
        <div class="cra-card">
            <div class="cra-card-value" id="cra-total-interactions">-</div>
            <div class="cra-card-label"><?php echo get_string('totalinteractions', 'local_coderunner_agent'); ?></div>
        </div>
        <div class="cra-card">
            <div class="cra-card-value" id="cra-active-students">-</div>
            <div class="cra-card-label"><?php echo get_string('activestudents', 'local_coderunner_agent'); ?></div>
        </div>
        <div class="cra-card">
            <div class="cra-card-value" id="cra-exercises-used">-</div>
            <div class="cra-card-label"><?php echo get_string('exercisesused', 'local_coderunner_agent'); ?></div>
        </div>
        <div class="cra-card">
            <div class="cra-card-value" id="cra-avg-response-time">-</div>
            <div class="cra-card-label"><?php echo get_string('avgresponsetime', 'local_coderunner_agent'); ?></div>
        </div>
        <div class="cra-card">
            <div class="cra-card-value" id="cra-thumbs-up">-</div>
            <div class="cra-card-label"><?php echo get_string('thumbsup', 'local_coderunner_agent'); ?></div>
        </div>
        <div class="cra-card">
            <div class="cra-card-value" id="cra-thumbs-down">-</div>
            <div class="cra-card-label"><?php echo get_string('thumbsdown', 'local_coderunner_agent'); ?></div>
        </div>
        <div class="cra-card">
            <div class="cra-card-value" id="cra-satisfaction-pct">-</div>
            <div class="cra-card-label"><?php echo get_string('satisfaction', 'local_coderunner_agent'); ?></div>
        </div>
    </div>

    <!-- Charts row 1 -->
    <div class="cra-chart-row mb-4">
        <div class="cra-chart-box">
            <h5><?php echo get_string('phasedistribution', 'local_coderunner_agent'); ?></h5>
            <canvas id="cra-chart-phase"></canvas>
        </div>
        <div class="cra-chart-box">
            <h5><?php echo get_string('usagetimeline', 'local_coderunner_agent'); ?></h5>
            <canvas id="cra-chart-timeline"></canvas>
        </div>
    </div>

    <!-- Charts row 2 -->
    <div class="cra-chart-row mb-4">
        <div class="cra-chart-box">
            <h5><?php echo get_string('exerciseheatmap', 'local_coderunner_agent'); ?></h5>
            <div id="cra-heatmap" class="cra-heatmap"></div>
        </div>
        <div class="cra-chart-box">
            <h5><?php echo get_string('strategyusage', 'local_coderunner_agent'); ?></h5>
            <canvas id="cra-chart-strategy"></canvas>
        </div>
    </div>

    <!-- Student Activity -->
    <div class="cra-student-section mb-4 p-3">
        <div class="cra-student-header mb-3">
            <h4><?php echo get_string('studentactivity', 'local_coderunner_agent'); ?></h4>
            <input type="text" id="cra-student-search" class="form-control" placeholder="<?php echo get_string('student', 'local_coderunner_agent'); ?>...">
        </div>
        <table class="table table-striped" id="cra-student-table">
            <thead>
                <tr>
                    <th><?php echo get_string('student', 'local_coderunner_agent'); ?></th>
                    <th><?php echo get_string('interactions', 'local_coderunner_agent'); ?></th>
                    <th><?php echo get_string('topphase', 'local_coderunner_agent'); ?></th>
                    <th><?php echo get_string('exercises', 'local_coderunner_agent'); ?></th>
                    <th><?php echo get_string('lastactive', 'local_coderunner_agent'); ?></th>
                    <th></th>
                </tr>
            </thead>
            <tbody id="cra-student-tbody"></tbody>
        </table>
    </div>

    <!-- Student Detail (hidden) -->
    <div class="cra-student-detail mb-4 p-3" id="cra-student-detail" style="display:none;">
        <div class="cra-detail-header mb-3">
            <h4 id="cra-detail-title"></h4>
            <button class="btn btn-sm btn-outline-secondary" id="cra-detail-close">&times;</button>
        </div>
        <div class="cra-detail-body">
            <div>
                <canvas id="cra-detail-phase-chart"></canvas>
            </div>
            <div>
                <table class="table table-sm table-striped" id="cra-detail-interactions-table">
                    <thead>
                        <tr>
                            <th><?php echo get_string('exercises', 'local_coderunner_agent'); ?></th>
                            <th><?php echo get_string('topphase', 'local_coderunner_agent'); ?></th>
                            <th><?php echo get_string('interactions', 'local_coderunner_agent'); ?></th>
                            <th><?php echo get_string('lastactive', 'local_coderunner_agent'); ?></th>
                        </tr>
                    </thead>
                    <tbody id="cra-detail-interactions-tbody"></tbody>
                </table>
            </div>
        </div>
    </div>
</div>

<?php
echo $OUTPUT->footer();
