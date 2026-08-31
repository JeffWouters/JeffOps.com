/* The two enquiry forms, on whichever page they appear.
 *
 * Both forms exist twice: inside the single-page app, and on the promoted
 * /speaking/ and /consulting/ pages that the build lifts out of it. Those
 * promoted pages loaded no JavaScript at all, so the Send button did nothing
 * and the topic dropdown held a single '— Select —'. A form that looks
 * complete and silently discards what you typed is the same failure as the
 * subscribe box that used to say "You're subscribed!" while storing nothing.
 *
 * The build now renders the topic options into the static page, and this file
 * is loaded by both views so the buttons behave the same in each.
 */
(function (global) {
  'use strict';

  function value(id) {
    var el = document.getElementById(id);
    return el ? el.value.trim() : '';
    }

  function compose(subject, lines, message) {
    var body = lines.filter(function (l) { return l; }).join('\n');
    if (message) body += '\n\n' + message;
    return 'mailto:jeff@jeffops.com?subject=' + encodeURIComponent(subject)
         + '&body=' + encodeURIComponent(body);
  }

  function reveal(id) {
    var el = document.getElementById(id);
    if (el) el.style.display = 'block';
  }

  // ── validation feedback ───────────────────────────────────────────────────
  //
  // Both submit paths used to `return` on invalid input and do nothing else: no message, no field
  // marked, no focus moved. Pressing Send with a blank name produced no observable change at all.
  // There is no <form> element on any page either, so native validation never runs to cover it.
  // This file's own header calls that failure out — "a form that looks complete and silently
  // discards what you typed" — and then did it on every invalid path.
  //
  // Built with createElement and textContent rather than innerHTML: these pages ship
  // require-trusted-types-for 'script', and a sink here would be the one place this file has none.

  function fieldError(id) {
    return document.getElementById(id + '-error');
  }

  function clearError(id) {
    var el = document.getElementById(id);
    var msg = fieldError(id);
    if (el) el.removeAttribute('aria-invalid');
    if (el) el.removeAttribute('aria-describedby');
    if (msg && msg.parentNode) msg.parentNode.removeChild(msg);
  }

  function markInvalid(id, message) {
    var el = document.getElementById(id);
    if (!el) return;
    el.setAttribute('aria-invalid', 'true');
    var msg = fieldError(id);
    if (!msg) {
      msg = document.createElement('p');
      msg.className = 'form-error';
      msg.id = id + '-error';
      // role=alert so it is announced when it appears, not only when focus lands on the field
      msg.setAttribute('role', 'alert');
      el.parentNode.insertBefore(msg, el.nextSibling);
    }
    msg.textContent = message;
    el.setAttribute('aria-describedby', msg.id);
  }

  // Returns true when everything passed. Clears previous messages first, so a corrected field
  // stops being announced as broken.
  function validate(checks) {
    var i, first = null;
    for (i = 0; i < checks.length; i++) clearError(checks[i][0]);
    for (i = 0; i < checks.length; i++) {
      if (!checks[i][2]) {
        markInvalid(checks[i][0], checks[i][1]);
        if (!first) first = checks[i][0];
      }
    }
    if (first) {
      var el = document.getElementById(first);
      if (el && el.focus) el.focus();
      return false;
    }
    return true;
  }

  function looksLikeEmail(v) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);
  }

  // 'Other' reveals a free-text field. Called on load as well as on change,
  // so a browser that restored a previous selection is not left with the
  // field hidden while 'Other' is chosen.
  global.handleTopicChange = function () {
    var select = document.getElementById('eq-topic');
    var other = document.getElementById('eq-topic-other-field');
    if (!select || !other) return;
    other.style.display = select.value === 'other' ? 'block' : 'none';
  };

  global.submitEnquiry = function () {
    var name = value('eq-name');
    var email = value('eq-email');

    var select = document.getElementById('eq-topic');
    var topic = '';
    if (select && select.value === 'other') {
      topic = value('eq-topic-other');
    } else if (select && select.selectedOptions && select.selectedOptions[0] && select.value) {
      topic = select.selectedOptions[0].textContent;
    }

    if (!validate([
      ['eq-name', 'Please tell us your name.', !!name],
      ['eq-email', 'We need an email address to reply to.', looksLikeEmail(email)],
      [select && select.value === 'other' ? 'eq-topic-other' : 'eq-topic',
       'Please choose a topic.', !!topic]
    ])) return;

    global.location.href = compose('Speaking Enquiry from ' + name, [
      'Name: ' + name,
      'Email: ' + email,
      'Event: ' + value('eq-event'),
      'Date: ' + value('eq-date'),
      'Topic: ' + topic
    ], value('eq-msg'));
    reveal('eq-success');
  };

  global.submitConsulting = function () {
    var name = value('con-name');
    var email = value('con-email');

    if (!validate([
      ['con-name', 'Please tell us your name.', !!name],
      ['con-email', 'We need an email address to reply to.', looksLikeEmail(email)]
    ])) return;

    global.location.href = compose('Consulting Enquiry from ' + name, [
      'Name: ' + name,
      'Email: ' + email,
      'Role: ' + value('con-role'),
      'Service: ' + value('con-service')
    ], value('con-msg'));
    reveal('con-success');
  };

  // Delegated for the same reason the app's are: no inline handlers means the
  // Content Security Policy can refuse inline script outright.
  document.addEventListener('click', function (event) {
    var el = event.target.closest('[data-action]');
    if (!el) return;
    if (el.dataset.action === 'submit-enquiry') global.submitEnquiry();
    if (el.dataset.action === 'submit-consulting') global.submitConsulting();
  });
  document.addEventListener('change', function (event) {
    if (event.target.dataset && event.target.dataset.action === 'topic-change') {
      global.handleTopicChange();
    }
  });

  document.addEventListener('DOMContentLoaded', global.handleTopicChange);
})(window);
