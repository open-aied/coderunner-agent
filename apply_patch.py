#!/usr/bin/env python3
"""
Apply CodeRunner Agent patch to the cloned CodeRunner plugin.

Modifies:
  plugins/coderunner/renderer.php  — injects Agent panel call
  plugins/coderunner/agent_panel.php   — copied from coderunner-patch/
  plugins/coderunner/amd/src/agent_panel.js  — copied
  plugins/coderunner/styles.css    — appended
  plugins/coderunner/lang/en/qtype_coderunner.php  — lang strings appended
"""
import re
import shutil
from pathlib import Path

ROOT        = Path(__file__).parent
PLUGIN_DIR  = ROOT / "plugins" / "coderunner"
PATCH_DIR   = ROOT / "coderunner-patch"
RENDERER    = PLUGIN_DIR / "renderer.php"

LANG_STRINGS = """
// ── CodeRunner Agent strings ──────────────────────────────────────────────
$string['agenttitle']                 = 'AI Learning Assistant';
$string['phase']                      = 'SRL Phase';
$string['phase_planning']             = 'Planning';
$string['phase_program_creation']     = 'Program Creation';
$string['phase_error_correction']     = 'Error Correction';
$string['phase_self_monitoring']      = 'Self-Monitoring';
$string['phase_self_reflection']      = 'Self-Reflection';
$string['strategy']                   = 'Strategy';
$string['customquestion']             = 'Your question (optional)';
$string['customquestion_placeholder'] = 'e.g. Why is my loop not working?';
$string['askagent']                   = 'Ask Agent';
$string['agentphasefree']             = 'Auto SRL phase detection';
$string['agentphasefree_label']       = 'When enabled, SRL phase is suggested based on student state and can still be changed manually.';
$string['agentphasefree_help']        = 'If checked, the AI Learning Assistant will suggest which SRL phase the student is in while still allowing manual phase selection.';
"""


def copy_files():
    # agent_panel.php
    shutil.copy(PATCH_DIR / "agent_panel.php", PLUGIN_DIR / "agent_panel.php")
    print("  Copied agent_panel.php")

    # AMD JS — copy to both src/ and build/ (no grunt in this setup)
    js_src = PATCH_DIR / "amd" / "src" / "agent_panel.js"
    js_dest = PLUGIN_DIR / "amd" / "src" / "agent_panel.js"
    js_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(js_src, js_dest)
    print("  Copied amd/src/agent_panel.js")

    js_build = PLUGIN_DIR / "amd" / "build" / "agent_panel.min.js"
    js_build.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(js_src, js_build)
    print("  Copied amd/build/agent_panel.min.js")

    # CSS — remove old agent CSS block, then re-append fresh version
    css_src = PATCH_DIR / "styles" / "agent_panel.css"
    css_dest = PLUGIN_DIR / "styles.css"
    if css_dest.exists():
        existing = css_dest.read_text()
        # Strip any previously appended agent CSS
        marker = "/* ── CodeRunner Agent ── */"
        if marker in existing:
            existing = existing[:existing.index(marker)].rstrip() + "\n"
        with open(css_dest, "w") as f:
            f.write(existing)
            f.write("\n\n/* ── CodeRunner Agent ── */\n")
            f.write(css_src.read_text())
        print("  Updated CSS in styles.css")
    else:
        shutil.copy(css_src, css_dest)
        print("  Created styles.css from agent patch")


def patch_renderer():
    if not RENDERER.exists():
        print(f"  ERROR: {RENDERER} not found.")
        return False

    content = RENDERER.read_text(encoding="utf-8")

    if "agent_panel.php" in content:
        print("  renderer.php already patched — skipping.")
        return True

    # 1. Add require_once near the top of the file
    require_line = "require_once(__DIR__ . '/agent_panel.php');"
    # Try MOODLE_INTERNAL guard first, then fall back to 'use' statement
    moodle_guard = "defined('MOODLE_INTERNAL') || die();"
    if moodle_guard in content:
        content = content.replace(
            moodle_guard,
            moodle_guard + "\n" + require_line,
            1,
        )
        print("  Added require_once to renderer.php (after MOODLE_INTERNAL)")
    else:
        # Fall back: insert after the last 'use' statement
        use_match = None
        for m in re.finditer(r"^use\s+[^;]+;", content, re.MULTILINE):
            use_match = m
        if use_match:
            pos = use_match.end()
            content = content[:pos] + "\n" + require_line + content[pos:]
            print("  Added require_once to renderer.php (after use statement)")
        else:
            print("  WARNING: Could not find injection point for require_once. Add manually.")

    # 2. Inject panel call inside formulation_and_controls(), before its return
    injection = (
        "\n        // ── CodeRunner Agent Panel ──\n"
        "        global $PAGE;\n"
        "        $qtext .= coderunner_agent_panel($qa, $options, $PAGE);\n"
        "        // ────────────────────────────\n"
    )

    # Find formulation_and_controls method and its `return $qtext;`
    pattern = re.compile(
        r"(function\s+formulation_and_controls\s*\(.*?\{.*?)(return\s+\$qtext\s*;)",
        re.DOTALL,
    )
    match = pattern.search(content)
    if match:
        new_content = (
            content[: match.start(2)]
            + injection
            + content[match.start(2):]
        )
        RENDERER.write_text(new_content, encoding="utf-8")
        print("  Injected Agent panel into formulation_and_controls()")
    else:
        RENDERER.write_text(content, encoding="utf-8")
        print(
            "  WARNING: Could not auto-inject into formulation_and_controls().\n"
            "  See coderunner-patch/renderer.php.diff for manual instructions."
        )

    return True


def patch_lang():
    lang_file = PLUGIN_DIR / "lang" / "en" / "qtype_coderunner.php"
    if not lang_file.exists():
        print("  WARNING: lang file not found, skipping lang strings.")
        return
    existing = lang_file.read_text(encoding="utf-8")
    if "agenttitle" in existing:
        print("  Lang strings already present.")
        return
    with open(lang_file, "a", encoding="utf-8") as f:
        f.write(LANG_STRINGS)
    print("  Added lang strings to qtype_coderunner.php")


def patch_question_settings():
    """Add agentphasefree field to question type, form, model, and DB schema."""

    # 1. db/install.xml — add agentphasefree field
    install_xml = PLUGIN_DIR / "db" / "install.xml"
    if install_xml.exists():
        content = install_xml.read_text(encoding="utf-8")
        if "agentphasefree" not in content:
            marker = '<FIELD NAME="prototypeextra"'
            line = marker
            # Find the full line including the closing />
            idx = content.find(marker)
            if idx != -1:
                end = content.find("/>", idx)
                if end != -1:
                    insert_after = end + 2
                    new_field = '\n        <FIELD NAME="agentphasefree" TYPE="int" LENGTH="1" NOTNULL="true" DEFAULT="0" SEQUENCE="false" COMMENT="When enabled, SRL phase is suggested based on student state."/>'
                    content = content[:insert_after] + new_field + content[insert_after:]
                    install_xml.write_text(content, encoding="utf-8")
                    print("  Added agentphasefree field to db/install.xml")
        else:
            print("  db/install.xml already has agentphasefree")
    else:
        print("  WARNING: db/install.xml not found")

    # 2. db/upgrade.php — add upgrade step
    upgrade_php = PLUGIN_DIR / "db" / "upgrade.php"
    if upgrade_php.exists():
        content = upgrade_php.read_text(encoding="utf-8")
        if "autophasedetection" in content and "agentphasefree" not in content:
            content = content.replace("autophasedetection", "agentphasefree")
            upgrade_php.write_text(content, encoding="utf-8")
            print("  Corrected stale autophasedetection upgrade field to agentphasefree")
        elif "agentphasefree" not in content:
            marker = "require_once(__DIR__ . '/upgradelib.php');"
            if marker in content:
                upgrade_block = (
                    "    if ($oldversion < 2026031500) {\n"
                    "        $dbman = $DB->get_manager();\n"
                    "        $table = new xmldb_table('question_coderunner_options');\n"
                    "        $field = new xmldb_field('agentphasefree', XMLDB_TYPE_INTEGER, '1', null, XMLDB_NOTNULL, null, '0', 'prototypeextra');\n"
                    "        if (!$dbman->field_exists($table, $field)) {\n"
                    "            $dbman->add_field($table, $field);\n"
                    "        }\n"
                    "        upgrade_plugin_savepoint(true, 2026031500, 'qtype', 'coderunner');\n"
                    "    }\n\n    "
                )
                content = content.replace(marker, upgrade_block + marker)
                upgrade_php.write_text(content, encoding="utf-8")
                print("  Added upgrade step to db/upgrade.php")
        else:
            print("  db/upgrade.php already has agent upgrade step")
    else:
        print("  WARNING: db/upgrade.php not found")

    # 3. edit_coderunner_form.php — add checkbox
    form_php = PLUGIN_DIR / "edit_coderunner_form.php"
    if form_php.exists():
        content = form_php.read_text(encoding="utf-8")
        if "agentphasefree" not in content:
            marker = "$mform->setType('displayfeedback', PARAM_INT);"
            if marker in content:
                form_block = (
                    marker + "\n\n"
                    "        // Auto SRL phase detection.\n"
                    "        $mform->addElement(\n"
                    "            'advcheckbox',\n"
                    "            'agentphasefree',\n"
                    "            get_string('agentphasefree', 'qtype_coderunner'),\n"
                    "            get_string('agentphasefree_label', 'qtype_coderunner')\n"
                    "        );\n"
                    "        $mform->setDefault('agentphasefree', 0);\n"
                    "        $mform->addHelpButton('agentphasefree', 'agentphasefree', 'qtype_coderunner');"
                )
                content = content.replace(marker, form_block)
                form_php.write_text(content, encoding="utf-8")
                print("  Added agentphasefree checkbox to edit_coderunner_form.php")
        else:
            print("  edit_coderunner_form.php already has agentphasefree")
    else:
        print("  WARNING: edit_coderunner_form.php not found")

    # 4. question.php — add property
    question_php = PLUGIN_DIR / "question.php"
    if question_php.exists():
        content = question_php.read_text(encoding="utf-8")
        if "agentphasefree" not in content:
            marker = "public $prototypeextra;"
            if marker in content:
                content = content.replace(
                    marker,
                    marker + "\n\n    /** @var int Whether to auto-detect SRL phase based on student state. */\n    public $agentphasefree;",
                )
                question_php.write_text(content, encoding="utf-8")
                print("  Added agentphasefree property to question.php")
        else:
            print("  question.php already has agentphasefree")
    else:
        print("  WARNING: question.php not found")

    # 5. questiontype.php — add to extra_question_fields and save lists
    qtype_php = PLUGIN_DIR / "questiontype.php"
    if qtype_php.exists():
        content = qtype_php.read_text(encoding="utf-8")
        if "agentphasefree" not in content:
            # Add to extra_question_fields
            content = content.replace(
                "'prototypeextra',\n        ];",
                "'prototypeextra',\n            'agentphasefree',\n        ];",
                1,
            )
            # Add to save fields list
            content = content.replace(
                "'giveupallowed',\n        ];",
                "'giveupallowed',\n            'agentphasefree',\n        ];",
                1,
            )
            qtype_php.write_text(content, encoding="utf-8")
            print("  Added agentphasefree to questiontype.php")
        else:
            print("  questiontype.php already has agentphasefree")
    else:
        print("  WARNING: questiontype.php not found")


def main():
    print("\n=== Applying CodeRunner Agent patch ===\n")

    if not PLUGIN_DIR.exists():
        print("ERROR: plugins/coderunner/ not found.\nRun setup.sh first to clone the plugin.")
        exit(1)

    copy_files()
    patch_renderer()
    patch_lang()
    patch_question_settings()

    print("\nPatch applied successfully.\n")


if __name__ == "__main__":
    main()
