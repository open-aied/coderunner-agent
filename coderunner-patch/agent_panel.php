<?php
/**
 * CodeRunner Agent UI Panel
 *
 * Include this file at the end of specific_feedback() in renderer.php:
 *
 *   require_once(__DIR__ . '/agent_panel.php');
 *   $html .= coderunner_agent_panel($qa, $options, $PAGE);
 *
 * Or call coderunner_agent_panel() directly and append to $html.
 */

defined('MOODLE_INTERNAL') || die();

/**
 * Renders the CodeRunner Agent panel HTML and registers the AMD module.
 *
 * @param  question_attempt $qa       The current question attempt.
 * @param  question_display_options $options Display options.
 * @param  moodle_page $PAGE          Global $PAGE object.
 * @return string  HTML fragment to append after test results.
 */
function coderunner_agent_panel(
    $qa,
    $options,
    $PAGE
): string {
    global $USER, $COURSE, $CFG;

    // Do not show the agent panel after "submit all and finish" (review mode).
    if (!empty($options->readonly)) {
        return '';
    }

    // Agent backend URL — set via Admin > Site administration > Plugins >
    // Local plugins > CodeRunner Agent > Settings, or fall back to env/config.
    $agent_url = get_config('local_coderunner_agent', 'agent_url');
    if (empty($agent_url)) {
        $agent_url = defined('CODERUNNER_AGENT_URL')
            ? CODERUNNER_AGENT_URL
            : 'http://localhost:8001';
    }

    $question     = $qa->get_question();
    $question_id  = $question->id ?? '';
    $exercise_label = $question->name ?? '';
    $question_text = strip_tags($question->questiontext ?? '');
    $user_id      = $USER->id ?? 'anonymous';
    $course_id    = $COURSE->id ?? '';
    $session_key  = 'student-question:' . $user_id . ':' . $question_id;
    $preferred_language = '';
    if (!empty($USER->lang)) {
        $preferred_language = $USER->lang;
    } else if (function_exists('current_language')) {
        $preferred_language = current_language();
    }
    if ($preferred_language === '') {
        $preferred_language = 'en';
    }

    // Unique DOM id so multiple questions on one page don't conflict.
    $panel_id = 'cra-panel-' . $qa->get_slot();

    // Auto phase detection: determine suggested phase from student state.
    $locked_phase = '';
    $auto_phase = !empty($question->agentphasefree);
    if (!empty($auto_phase)) {
        $current_answer = $qa->get_last_qt_var('answer');
        $has_code = !empty(trim($current_answer ?? ''));
        $test_outcome = $qa->get_last_qt_var('_testoutcome');
        $has_submitted = !empty($test_outcome);

        if (!$has_code) {
            // No code written yet.
            $locked_phase = 'planning';
        } else if (!$has_submitted) {
            // Code exists but not submitted.
            $locked_phase = 'program_creation';
        } else {
            // Submitted — check if correct or has errors.
            $outcome = @unserialize($test_outcome);
            if ($outcome && method_exists($outcome, 'all_correct') && $outcome->all_correct()) {
                $locked_phase = 'self_reflection';
            } else {
                $locked_phase = 'error_correction';
            }
        }
    }
    $selected_phase = $locked_phase ?: 'planning';

    // Register AMD module (compiled to amd/build/agent_panel.min.js by Moodle).
    $PAGE->requires->js_call_amd('qtype_coderunner/agent_panel', 'init', [
        [
            'panelId'      => $panel_id,
            'agentUrl'     => $agent_url,
            'userId'       => (string) $user_id,
            'courseId'     => (string) $course_id,
            'exerciseId'    => (string) $question_id,
            'exerciseLabel' => (string) $exercise_label,
            'sessionKey'    => (string) $session_key,
            'questionText' => $question_text,
            'lockedPhase'  => $locked_phase,
            'preferredLanguage' => (string) $preferred_language,
        ]
    ]);

    // Build panel HTML.
    $html  = html_writer::start_div('cra-panel', ['id' => $panel_id]);

    // Header
    $html .= html_writer::start_div('cra-header');
    $html .= html_writer::tag('span', '&#129302; ' . get_string('agenttitle', 'qtype_coderunner'), ['class' => 'cra-title']);
    $html .= html_writer::tag('button', '&#8964;', [
        'class'        => 'cra-toggle',
        'aria-label'   => 'Toggle agent panel',
        'data-panel'   => $panel_id,
    ]);
    $html .= html_writer::end_div(); // cra-header

    // Body (collapsible)
    $html .= html_writer::start_div('cra-body');

    // Phase selector
    $html .= html_writer::start_div('cra-row');
    $html .= html_writer::label(
        get_string('phase', 'qtype_coderunner'),
        $panel_id . '-phase',
        true,
        ['class' => 'cra-label']
    );
    $html .= html_writer::select(
        [
            'planning'         => get_string('phase_planning', 'qtype_coderunner'),
            'program_creation' => get_string('phase_program_creation', 'qtype_coderunner'),
            'error_correction' => get_string('phase_error_correction', 'qtype_coderunner'),
            'self_reflection'  => get_string('phase_self_reflection', 'qtype_coderunner'),
        ],
        $panel_id . '-phase',
        $selected_phase,
        [],
        ['id' => $panel_id . '-phase', 'class' => 'cra-select']
    );
    $html .= html_writer::end_div(); // cra-row

    // Strategy selector (populated by JS based on phase)
    $html .= html_writer::start_div('cra-row');
    $html .= html_writer::label(
        get_string('strategy', 'qtype_coderunner'),
        $panel_id . '-strategy',
        true,
        ['class' => 'cra-label']
    );
    $html .= html_writer::tag('select', '', [
        'id'    => $panel_id . '-strategy',
        'class' => 'cra-select',
        'name'  => $panel_id . '-strategy',
    ]);
    $html .= html_writer::end_div(); // cra-row

    // Submit button
    $html .= html_writer::start_div('cra-row');
    $html .= html_writer::tag('button', get_string('askagent', 'qtype_coderunner'), [
        'id'    => $panel_id . '-submit',
        'class' => 'cra-btn btn btn-primary',
        'type'  => 'button',
    ]);
    $html .= html_writer::end_div(); // cra-row

    // Response area
    $html .= html_writer::start_div('cra-response-wrap');
    $html .= html_writer::tag('div', '', [
        'id'    => $panel_id . '-response',
        'class' => 'cra-response',
        'aria-live' => 'polite',
    ]);
    $html .= html_writer::end_div(); // cra-response-wrap

    $html .= html_writer::end_div(); // cra-body
    $html .= html_writer::end_div(); // cra-panel

    return $html;
}
