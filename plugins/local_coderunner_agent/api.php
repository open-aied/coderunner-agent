<?php
require_once(__DIR__ . '/../../config.php');
require_login();

$endpoint = required_param('endpoint', PARAM_TEXT);

$is_dashboard = strpos($endpoint, '/analytics') !== false || strpos($endpoint, '/export') !== false;
$courseid = optional_param('course_id', 0, PARAM_INT);
if ($is_dashboard) {
    if ($courseid > 0) {
        // Course-scoped: a teacher must hold the capability in this specific course.
        require_capability('local/coderunner_agent:viewdashboard', context_course::instance($courseid));
    } else {
        // Site-wide view is restricted to system-level roles (admin/manager).
        require_capability('local/coderunner_agent:viewdashboard', context_system::instance());
    }
}

$api = new \local_coderunner_agent\agent_api();

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $body = file_get_contents('php://input');
    $result = $api->post($endpoint, $body);
} elseif ($_SERVER['REQUEST_METHOD'] === 'PATCH') {
    $body = file_get_contents('php://input');
    $result = $api->patch($endpoint, $body);
} else {
    $params = $_GET;
    unset($params['endpoint']);
    if ($is_dashboard && $courseid > 0) {
        // Force course isolation regardless of any client-supplied value.
        $params['course_id'] = (string) $courseid;
    }
    $result = $api->get($endpoint, $params);
}

if (strpos($endpoint, '/export') !== false) {
    $content_type = (isset($params['format']) && $params['format'] === 'json')
        ? 'application/json'
        : 'text/csv; charset=utf-8';
    header('Content-Type: ' . $content_type);

    $disposition = $result['content_disposition'] ?? '';
    if ($disposition !== '') {
        header('Content-Disposition: ' . $disposition);
    } else {
        $filename = local_coderunner_agent_export_download_filename($endpoint, $params);
        header('Content-Disposition: attachment; filename="' . $filename . '"');
    }

    echo $result['body'];
    exit;
}

header('Content-Type: application/json');
http_response_code($result['status'] ?: 502);
echo $result['body'];
