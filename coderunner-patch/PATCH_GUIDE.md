# CodeRunner Agent — Patch Guide

How to integrate the Agent panel into the CodeRunner fork.

## Files in this patch

| File | Destination in CodeRunner fork |
|---|---|
| `agent_panel.php` | `question/type/coderunner/agent_panel.php` |
| `amd/src/agent_panel.js` | `question/type/coderunner/amd/src/agent_panel.js` |
| `styles/agent_panel.css` | Append to `question/type/coderunner/styles.css` |

## Step-by-step

### 1. Copy files into the CodeRunner plugin directory

```bash
cd /path/to/moodle/question/type/coderunner

cp /path/to/coderunner-patch/agent_panel.php .
cp /path/to/coderunner-patch/amd/src/agent_panel.js amd/src/
cat /path/to/coderunner-patch/styles/agent_panel.css >> styles.css
```

### 2. Modify renderer.php

Open `renderer.php` and make three additions:

**a) After `defined('MOODLE_INTERNAL') || die();`:**
```php
require_once(__DIR__ . '/agent_panel.php');
```

**b) At the end of `specific_feedback()`, before `return $html;`:**
```php
// CodeRunner Agent panel
global $PAGE;
$html .= coderunner_agent_panel($qa, $options, $PAGE);
```

**c) Also in `specific_feedback()`, add the CSS (once per page):**
```php
$PAGE->requires->css('/question/type/coderunner/styles.css');
```
(If `styles.css` is already loaded by CodeRunner, skip this.)

See `renderer.php.diff` for the exact context.

### 3. Add lang strings

Append to `lang/en/qtype_coderunner.php`:
```php
$string['agenttitle']                 = 'AI Learning Assistant';
$string['phase']                      = 'SRL Phase';
$string['phase_planning']             = 'Planning';
$string['phase_program_creation']     = 'Program Creation';
$string['phase_error_correction']     = 'Error Correction';
$string['phase_self_reflection']      = 'Self-Reflection';
$string['strategy']                   = 'Strategy';
$string['customquestion']             = 'Your question (optional)';
$string['customquestion_placeholder'] = 'e.g. Why is my loop not working?';
$string['askagent']                   = 'Ask Agent';
```

### 4. Build AMD (for production)

From Moodle root:
```bash
npm install   # first time only
grunt amd --root=question/type/coderunner
```

**Development shortcut** (no grunt): Add to `config.php`:
```php
$CFG->cachejs = false;
$CFG->jsrev   = -1;
```
Moodle will then serve the un-minified `amd/src/agent_panel.js` directly.

### 5. Set Agent URL

In Moodle Admin:
- Site administration → Plugins → Question types → CodeRunner → Settings
- Set **Agent URL** to `http://localhost:8001` (or Docker service name if on same network)

Or add to `config.php`:
```php
define('CODERUNNER_AGENT_URL', 'http://localhost:8001');
```

### 6. Purge caches

```
Site administration → Development → Purge all caches
```

## Verification

1. Open a CodeRunner question in a quiz.
2. Write some code, click **Check**.
3. After test results appear, the **AI Learning Assistant** panel should show below.
4. Select a phase, optionally enter a question, click **Ask Agent**.
5. Feedback appears in the response box — no complete code solutions should appear.
