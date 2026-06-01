<?php
defined('MOODLE_INTERNAL') || die();

if ($hassiteconfig) {
    $settings = new admin_settingpage(
        'local_coderunner_agent_settings',
        get_string('agentsettings', 'local_coderunner_agent')
    );
    $settings->add(new admin_setting_configtext(
        'local_coderunner_agent/dashboard_timezone',
        get_string('dashboardtimezone', 'local_coderunner_agent'),
        get_string('dashboardtimezone_desc', 'local_coderunner_agent'),
        'Asia/Tokyo',
        PARAM_TEXT
    ));
    $ADMIN->add('localplugins', $settings);

    $ADMIN->add('reports', new admin_externalpage(
        'local_coderunner_agent_dashboard',
        get_string('dashboard', 'local_coderunner_agent'),
        new moodle_url('/local/coderunner_agent/index.php'),
        'local/coderunner_agent:viewdashboard'
    ));
}
