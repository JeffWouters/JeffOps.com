/* Trusted Types policy. Must load before anything that writes to the DOM.
 *
 * The Content Security Policy on every page carries
 * `require-trusted-types-for 'script'`, which turns every assignment to
 * innerHTML into a type error unless the string came from a policy. This is
 * that policy, and it sanitises rather than waving things through.
 *
 * The sink that matters is one line in app.js:
 *
 *     post-content.innerHTML = marked.parse(post.markdown)
 *
 * marked dropped its `sanitize` option in v8, so raw HTML in a markdown file
 * reaches the DOM untouched. Nothing exploitable is in the writing today —
 * every post is Jeff's and none contains a script, iframe, object, embed or
 * form — but that is a property of the current content, not of the code. This
 * makes it a property of the code.
 *
 * A default policy, not a named one, because the alternative is threading a
 * policy object through 29 call sites. Everything the app writes is ordinary
 * markup and survives sanitisation unchanged; what does not survive is exactly
 * what should not be there.
 */
(function (global) {
  'use strict';

  if (!global.trustedTypes || !global.trustedTypes.createPolicy) return;

  // SVG and its attributes are allowed because Mermaid renders diagrams by
  // writing SVG into the document. It is loaded on demand and no post uses it
  // yet, but the policy has to be right on the day one does.
  var CONFIG = {
    USE_PROFILES: { html: true, svg: true, svgFilters: true },
    ADD_TAGS: ['picture', 'source', 'use'],
    ADD_ATTR: ['srcset', 'type', 'loading', 'fetchpriority', 'data-idx',
               'data-target', 'data-page', 'data-share', 'data-action',
               'data-set-tag', 'data-set-series', 'data-filter', 'data-tags',
               'data-series', 'data-portraits', 'data-noop'],
    // Inline handlers are gone from this site on purpose; refusing them here
    // means a stray one can never come back through a rendered string.
    FORBID_ATTR: ['onerror', 'onload', 'onclick', 'onmouseover', 'onfocus'],
    FORBID_TAGS: ['script', 'iframe', 'object', 'embed', 'form', 'base']
  };

  function clean(input) {
    if (global.DOMPurify) return global.DOMPurify.sanitize(input, CONFIG);
    // DOMPurify is a blocking script above this one, so this should not
    // happen. If it ever does, refuse rather than pass markup through
    // unchecked — a missing sanitiser must not become an open door.
    console.error('DOMPurify missing; refusing to render untrusted HTML');
    return '';
  }

  try {
    global.trustedTypes.createPolicy('default', {
      createHTML: clean,
      // No script or script URL is ever built from a string here. Returning
      // nothing makes that explicit instead of leaving a hole shaped like one.
      createScript: function () { return ''; },
      createScriptURL: function (url) {
        // post-enhance.js loads highlight.js and mermaid by assigning .src.
        var allowed = ['/vendor/', 'https://cdnjs.cloudflare.com/ajax/libs/mermaid/'];
        for (var i = 0; i < allowed.length; i++) {
          if (url.indexOf(allowed[i]) === 0) return url;
        }
        console.error('Blocked script URL:', url);
        return '';
      }
    });
  } catch (e) {
    // A second default policy throws. Nothing else creates one, but a failure
    // here would otherwise take the whole page down with it.
    console.warn('Trusted Types policy not installed:', e && e.message);
  }
})(window);
