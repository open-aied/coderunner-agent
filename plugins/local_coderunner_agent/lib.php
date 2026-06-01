<?php
defined('MOODLE_INTERNAL') || die();

/**
 * Add the Agent Dashboard link to course navigation for teachers.
 */
/**
 * Fallback download filename when Agent does not return Content-Disposition.
 * Must stay aligned with agent/routers/export.py naming.
 */
function local_coderunner_agent_export_download_filename(string $endpoint, array $params): string {
    $format = ($params['format'] ?? 'csv') === 'json' ? 'json' : 'csv';
    $ts = gmdate('Ymd_His');

    if (strpos($endpoint, '/export/raw') !== false) {
        return "interactions_export_{$ts}.{$format}";
    }
    if (strpos($endpoint, '/export/summary') !== false) {
        $groupby = $params['group_by'] ?? 'student';
        if (!in_array($groupby, ['student', 'exercise', 'phase'], true)) {
            $groupby = 'student';
        }
        return "summary_by_{$groupby}_{$ts}.{$format}";
    }

    return "export_{$ts}.{$format}";
}

function local_coderunner_agent_extend_navigation_course(navigation_node $navigation, stdClass $course, context_course $context) {
    if (has_capability('local/coderunner_agent:viewdashboard', $context)) {
        $navigation->add(
            get_string('dashboard', 'local_coderunner_agent'),
            new moodle_url('/local/coderunner_agent/index.php', ['course_id' => $course->id]),
            navigation_node::TYPE_SETTING,
            null,
            'coderunner_agent_dashboard',
            new pix_icon('i/report', '')
        );
    }
}
