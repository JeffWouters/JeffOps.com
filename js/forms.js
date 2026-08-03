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
    if (!name || email.indexOf('@') === -1) return;

    var select = document.getElementById('eq-topic');
    var topic = '';
    if (select && select.value === 'other') {
      topic = value('eq-topic-other');
    } else if (select && select.selectedOptions && select.selectedOptions[0]) {
      topic = select.selectedOptions[0].textContent;
    }
    if (!topic) return;

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
    if (!name || email.indexOf('@') === -1) return;

    global.location.href = compose('Consulting Enquiry from ' + name, [
      'Name: ' + name,
      'Email: ' + email,
      'Role: ' + value('con-role'),
      'Service: ' + value('con-service')
    ], value('con-msg'));
    reveal('con-success');
  };

  document.addEventListener('DOMContentLoaded', global.handleTopicChange);
})(window);
