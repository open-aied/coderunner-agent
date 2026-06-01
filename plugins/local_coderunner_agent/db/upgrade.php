<?php
defined('MOODLE_INTERNAL') || die();

function xmldb_local_coderunner_agent_upgrade($oldversion) {
    global $DB;
    $dbman = $DB->get_manager();

    if ($oldversion < 2026031500) {
        $table = new xmldb_table('local_cra_course_settings');
        $table->add_field('id', XMLDB_TYPE_INTEGER, '10', null, XMLDB_NOTNULL, XMLDB_SEQUENCE, null);
        $table->add_field('courseid', XMLDB_TYPE_INTEGER, '10', null, XMLDB_NOTNULL, null, null);
        $table->add_field('auto_phase_detection', XMLDB_TYPE_INTEGER, '1', null, XMLDB_NOTNULL, null, '0');
        $table->add_key('primary', XMLDB_KEY_PRIMARY, ['id']);
        $table->add_index('courseid_unique', XMLDB_INDEX_UNIQUE, ['courseid']);

        if (!$dbman->table_exists($table)) {
            $dbman->create_table($table);
        }

        upgrade_plugin_savepoint(true, 2026031500, 'local', 'coderunner_agent');
    }

    if ($oldversion < 2026042800) {
        $table = new xmldb_table('local_cra_course_settings');
        if ($dbman->table_exists($table)) {
            $dbman->drop_table($table);
        }

        upgrade_plugin_savepoint(true, 2026042800, 'local', 'coderunner_agent');
    }

    return true;
}
