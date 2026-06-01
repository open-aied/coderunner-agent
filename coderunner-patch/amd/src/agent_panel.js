// amd/src/agent_panel.js
// AMD module for CodeRunner Agent panel

define([], function() {

    var PHASE_STRATEGIES = {
        planning: {
            label: 'Planning',
            strategies: {
                general: 'General guidance',
                problem_understanding: 'Problem understanding',
                problem_decomposition: 'Problem decomposition',
                solution_architecture: 'Solution architecture',
            },
        },
        program_creation: {
            label: 'Program Creation',
            strategies: {
                general: 'General guidance',
                knowledge_recall: 'Knowledge recall',
                construct_selection: 'Construct selection',
                step_by_step_implementation: 'Step-by-step implementation',
            },
        },
        error_correction: {
            label: 'Error Correction',
            strategies: {
                general: 'General guidance',
                error_diagnosis: 'Error diagnosis',
                debugging_strategy: 'Debugging strategy',
                concept_clarification: 'Concept clarification',
            },
        },
        self_reflection: {
            label: 'Self-Reflection',
            strategies: {
                general: 'General guidance',
                learning_summary: 'Learning summary',
                improvement_identification: 'Improvement identification',
                future_strategy: 'Future strategy',
            },
        },
    };

    function renderMarkdown(md) {
        return md
            .replace(/^### (.+)$/gm, '<h5>$1</h5>')
            .replace(/^## (.+)$/gm, '<h4>$1</h4>')
            .replace(/^# (.+)$/gm, '<h3>$1</h3>')
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.+?)\*/g, '<em>$1</em>')
            .replace(/`([^`]+)`/g, '<code>$1</code>')
            .replace(/^[-*] (.+)$/gm, '<li>$1</li>')
            .replace(/^\d+\. (.+)$/gm, '<li>$1</li>')
            .replace(/(<li>[\s\S]*?<\/li>\n?)+/g, function(m) { return '<ul>' + m + '</ul>'; })
            .replace(/\n\n+/g, '</p><p>')
            .replace(/^([^<])/, '<p>$1')
            .replace(/([^>])$/, '$1</p>');
    }

    function findAnswerTextarea(container) {
        var fields = container.querySelectorAll(
            'textarea[name="answer"], ' +
            'textarea[name$="_answer"], ' +
            'textarea[id$="_answer"], ' +
            'textarea.coderunner-answer, ' +
            '.coderunner-answer textarea'
        );
        for (var i = 0; i < fields.length; i++) {
            if (!fields[i].closest('.ace_editor') && !fields[i].classList.contains('ace_text-input')) {
                return fields[i];
            }
        }
        return fields.length ? fields[0] : null;
    }

    function getAceEditor(container) {
        if (window.ace) {
            var aceEl = container.querySelector('.ace_editor');
            if (aceEl) {
                try {
                    return window.ace.edit(aceEl);
                } catch (e) {
                    if (aceEl.id) {
                        try {
                            return window.ace.edit(aceEl.id);
                        } catch (ignore) {
                            // Fall through.
                        }
                    }
                }
            }
        }
        return null;
    }

    function readStudentCode(container) {
        var editor = getAceEditor(container);
        if (editor) {
            return editor.getValue();
        }
        var ta = findAnswerTextarea(container);
        return ta ? ta.value : '';
    }

    function syncStudentCodeToAnswer(container) {
        var editor = getAceEditor(container);
        var ta = findAnswerTextarea(container);
        if (!editor || !ta) {
            return;
        }
        var code = editor.getValue();
        if (ta.value === code) {
            return;
        }
        ta.value = code;
        ta.dispatchEvent(new Event('input', {bubbles: true}));
        ta.dispatchEvent(new Event('change', {bubbles: true}));
    }

    function attachAnswerSync(container) {
        var attempts = 0;
        var retryTimer = null;
        var containerEvents = ['keyup', 'input', 'change', 'paste', 'compositionend'];
        var syncSoon = function() {
            setTimeout(function() {
                syncStudentCodeToAnswer(container);
            }, 0);
        };

        for (var i = 0; i < containerEvents.length; i++) {
            container.addEventListener(containerEvents[i], syncSoon, true);
        }

        function tryAttachAceSync() {
            var editor = getAceEditor(container);
            var session = editor && editor.getSession ? editor.getSession() : (editor && editor.session);
            if (session && session.on) {
                session.on('change', syncSoon);
                syncSoon();
                return;
            }
            attempts++;
            if (attempts < 40) {
                retryTimer = setTimeout(tryAttachAceSync, 250);
            }
        }

        tryAttachAceSync();

        return function() {
            if (retryTimer) {
                clearTimeout(retryTimer);
            }
            for (var i = 0; i < containerEvents.length; i++) {
                container.removeEventListener(containerEvents[i], syncSoon, true);
            }
        };
    }

    function attachCodeStartDetector(container, callback) {
        var detached = false;
        var retryTimer = null;
        var attempts = 0;
        var cleanup = [];
        var pendingCheck = false;
        var detach = function() {
            var i;
            if (detached) {
                return;
            }
            detached = true;
            if (retryTimer) {
                clearTimeout(retryTimer);
                retryTimer = null;
            }
            for (i = 0; i < cleanup.length; i++) {
                cleanup[i]();
            }
            cleanup = [];
        };
        var onChange = function() {
            if (detached || pendingCheck) {
                return;
            }
            pendingCheck = true;
            setTimeout(function() {
                pendingCheck = false;
                if (detached || readStudentCode(container).trim().length === 0) {
                    return;
                }
                detach();
                callback();
            }, 0);
        };
        var containerEvents = ['keydown', 'keyup', 'input', 'change', 'paste', 'compositionend'];
        for (var i = 0; i < containerEvents.length; i++) {
            (function(type) {
                container.addEventListener(type, onChange, true);
                cleanup.push(function() {
                    container.removeEventListener(type, onChange, true);
                });
            })(containerEvents[i]);
        }

        function tryAttach() {
            if (detached) {
                return;
            }

            var editor = getAceEditor(container);
            var session = editor && editor.getSession ? editor.getSession() : (editor && editor.session);
            if (session && session.on) {
                session.on('change', onChange);
                cleanup.push(function() {
                    if (session.off) {
                        session.off('change', onChange);
                    } else if (session.removeListener) {
                        session.removeListener('change', onChange);
                    }
                });
                onChange();
                return;
            }

            var ta = findAnswerTextarea(container);
            if (ta) {
                ta.addEventListener('input', onChange);
                ta.addEventListener('change', onChange);
                cleanup.push(function() {
                    ta.removeEventListener('input', onChange);
                    ta.removeEventListener('change', onChange);
                });
                onChange();
                return;
            }

            attempts++;
            if (attempts < 40) {
                retryTimer = setTimeout(tryAttach, 250);
            }
        }

        tryAttach();
        return detach;
    }

    function readTestResults(container) {
        var table = container.querySelector('.coderunner-test-results, table.testresults');
        if (!table) {
            return '';
        }
        return table.innerText.replace(/\s+/g, ' ').trim().slice(0, 800);
    }

    function populateStrategies(strategyEl, phase) {
        strategyEl.innerHTML = '';
        var phaseData = PHASE_STRATEGIES[phase];
        var strategies = phaseData ? phaseData.strategies : {general: 'General guidance'};
        var keys = Object.keys(strategies);
        for (var i = 0; i < keys.length; i++) {
            var opt = document.createElement('option');
            opt.value = keys[i];
            opt.textContent = strategies[keys[i]];
            strategyEl.appendChild(opt);
        }
    }

    function attachRatingHandlers(ratingRow, interactionId, agentUrl) {
        var currentRating = null;
        var buttons = ratingRow.querySelectorAll('.cra-rate-btn');
        for (var i = 0; i < buttons.length; i++) {
            (function(btn) {
                btn.addEventListener('click', function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    var value = btn.dataset.value;
                    var newRating = (currentRating === value) ? null : value;
                    currentRating = newRating;
                    var allBtns = ratingRow.querySelectorAll('.cra-rate-btn');
                    for (var j = 0; j < allBtns.length; j++) {
                        if (allBtns[j].dataset.value === newRating) {
                            allBtns[j].classList.add('cra-rate-active');
                        } else {
                            allBtns[j].classList.remove('cra-rate-active');
                        }
                    }
                    var xhr = new XMLHttpRequest();
                    xhr.open('PATCH', agentUrl + '/api/v1/interactions/' + interactionId + '/rating', true);
                    xhr.setRequestHeader('Content-Type', 'application/json');
                    xhr.send(JSON.stringify({rating: newRating}));
                });
            })(buttons[i]);
        }
    }

    return {
        init: function(config) {
            var panelId = config.panelId;
            var agentUrl = config.agentUrl;
            var userId = config.userId;
            var courseId = config.courseId;
            var exerciseId = config.exerciseId;
            var exerciseLabel = config.exerciseLabel || '';
            var sessionKey = config.sessionKey || '';
            var questionText = config.questionText;
            var lockedPhase = config.lockedPhase || '';
            var preferredLanguage = config.preferredLanguage || '';
            var manualPhaseOverride = false;

            var panel = document.getElementById(panelId);
            if (!panel) {
                return;
            }

            var phaseEl = document.getElementById(panelId + '-phase');
            var strategyEl = document.getElementById(panelId + '-strategy');
            var submitBtn = document.getElementById(panelId + '-submit');
            var responseEl = document.getElementById(panelId + '-response');
            var toggleBtn = panel.querySelector('.cra-toggle');

            var queContainer = panel.closest('.que') || panel.closest('.formulation') || document.body;
            var form = queContainer.closest('form');
            attachAnswerSync(queContainer);
            if (form) {
                form.addEventListener('submit', function() {
                    syncStudentCodeToAnswer(queContainer);
                }, true);
            }
            queContainer.addEventListener('click', function(e) {
                if (e.target.closest('button, input[type="submit"]')) {
                    syncStudentCodeToAnswer(queContainer);
                }
            }, true);

            // Auto phase detection suggests a phase, but students can reselect it.
            // A one-time listener moves planning to program_creation after code starts.
            function updateSuggestedPhase(newPhase) {
                if (newPhase && PHASE_STRATEGIES[newPhase]) {
                    phaseEl.value = newPhase;
                    populateStrategies(strategyEl, newPhase);
                }
            }

            if (lockedPhase) {
                updateSuggestedPhase(lockedPhase);

                // Detect the first local code entry only; do not poll afterward.
                if (lockedPhase === 'planning') {
                    attachCodeStartDetector(queContainer, function() {
                        if (!manualPhaseOverride) {
                            updateSuggestedPhase('program_creation');
                        }
                    });
                }
            }

            populateStrategies(strategyEl, phaseEl.value);

            phaseEl.addEventListener('change', function() {
                manualPhaseOverride = true;
                populateStrategies(strategyEl, phaseEl.value);
            });

            if (toggleBtn) {
                toggleBtn.addEventListener('click', function() {
                    var body = panel.querySelector('.cra-body');
                    body.style.display = body.style.display === 'none' ? '' : 'none';
                    toggleBtn.textContent = body.style.display === 'none' ? '\u25B8' : '\u25BE';
                });
            }

            submitBtn.addEventListener('click', function() {
                var phase = phaseEl.value;
                var strategy = strategyEl.value;
                var studentCode = readStudentCode(queContainer);
                var testResults = readTestResults(queContainer);

                var oldRating = responseEl.querySelector('.cra-rating');
                if (oldRating) { oldRating.remove(); }

                submitBtn.disabled = true;
                submitBtn.textContent = 'Asking\u2026';
                responseEl.innerHTML = '<em>Generating feedback\u2026</em>';

                var xhr = new XMLHttpRequest();
                xhr.open('POST', agentUrl + '/api/v1/feedback', true);
                xhr.setRequestHeader('Content-Type', 'application/json');
                xhr.onreadystatechange = function() {
                    if (xhr.readyState !== 4) {
                        return;
                    }
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Ask Agent';
                    if (xhr.status >= 200 && xhr.status < 300) {
                        try {
                            var data = JSON.parse(xhr.responseText);
                            responseEl.innerHTML = renderMarkdown(data.feedback);

                            // Append rating buttons
                            var interactionId = data.interaction_id;
                            var ratingRow = document.createElement('div');
                            ratingRow.className = 'cra-rating';
                            ratingRow.dataset.interactionId = interactionId;
                            ratingRow.innerHTML =
                                '<span class="cra-rate-label">Was this helpful?</span>' +
                                '<button type="button" class="cra-rate-btn" data-value="up" title="\u6709\u5E2E\u52A9">\uD83D\uDC4D</button>' +
                                '<button type="button" class="cra-rate-btn" data-value="down" title="\u6CA1\u5E2E\u52A9">\uD83D\uDC4E</button>';
                            responseEl.appendChild(ratingRow);
                            attachRatingHandlers(ratingRow, interactionId, agentUrl);
                        } catch (e) {
                            responseEl.innerHTML = '<span class="cra-error">Error: Invalid response</span>';
                        }
                    } else {
                        var msg = 'Request failed';
                        try {
                            var errData = JSON.parse(xhr.responseText);
                            msg = errData.detail || msg;
                        } catch (e) {
                            // Use default message.
                        }
                        responseEl.innerHTML = '<span class="cra-error">Error: ' + msg + '</span>';
                    }
                };
                xhr.send(JSON.stringify({
                    user_id: userId,
                    course_id: courseId,
                    exercise_id: exerciseId,
                    exercise_label: exerciseLabel,
                    session_key: sessionKey,
                    question_text: questionText,
                    student_code: studentCode,
                    test_results: testResults,
                    srl_phase: phase,
                    strategy: strategy,
                    preferred_language: preferredLanguage,
                    custom_question: '',
                }));
            });
        }
    };
});
