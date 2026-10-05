/* Private feedback widget behaviour — shared by retrofits.html and retrofit-insights.html.
   Posts to /api/feedback (Cloudflare Pages Function, functions/api/feedback.js).
   Ported from the same pattern on madeclear.ca. */
(function () {
  var root = document.querySelector('[data-feedback]');
  if (!root) return;
  var form = root.querySelector('.feedback-form');
  var choices = Array.prototype.slice.call(root.querySelectorAll('.feedback-choice'));
  var textarea = root.querySelector('textarea');
  var status = root.querySelector('.feedback-status');
  var send = root.querySelector('.feedback-send');
  var rating = '';

  choices.forEach(function (choice) {
    choice.addEventListener('click', function () {
      rating = choice.dataset.rating;
      choices.forEach(function (item) { item.setAttribute('aria-pressed', item === choice ? 'true' : 'false'); });
      form.hidden = false;
      status.textContent = '';
    });
  });

  function pageSlug() {
    var file = location.pathname.split('/').pop() || '';
    return file.replace(/\.html?$/i, '').toLowerCase() || 'page';
  }

  function currentContext() {
    var values = [];
    Array.prototype.forEach.call(document.querySelectorAll('[role="slider"]'), function (slider) {
      var label = slider.getAttribute('aria-label') || 'Control';
      var value = slider.getAttribute('aria-valuetext') || slider.getAttribute('aria-valuenow');
      if (value) values.push(label + ': ' + value);
    });
    Array.prototype.forEach.call(document.querySelectorAll('select'), function (select) {
      var label = select.getAttribute('aria-label') || select.name || 'Selection';
      var option = select.options[select.selectedIndex];
      if (option) values.push(label + ': ' + option.textContent.trim());
    });
    return values.slice(0, 20);
  }

  form.addEventListener('submit', function (event) {
    event.preventDefault();
    if (!rating) return;
    if (location.protocol === 'file:') {
      status.textContent = 'Feedback can be sent from energy.madeclear.ca.';
      return;
    }
    send.disabled = true;
    status.textContent = 'Sending…';
    fetch('/api/feedback', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        page: pageSlug(),
        rating: rating,
        comment: textarea.value,
        website: form.elements.website.value,
        context: currentContext()
      })
    }).then(function (response) {
      if (!response.ok) throw new Error('request failed');
      status.textContent = 'Thank you — your feedback is private.';
      textarea.value = '';
    }).catch(function () {
      status.innerHTML = 'Could not send. Try <a href="mailto:hello@madeclear.ca">hello@madeclear.ca</a>.';
    }).then(function () { send.disabled = false; });
  });
})();
