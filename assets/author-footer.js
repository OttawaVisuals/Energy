/* Author line appended to each tool page's <footer>, for visitors who land on one
   page and never see index.html. One place to edit the credit. Self-contained
   styling: not every page loads assets/site-theme.css (ceud, construction,
   permits don't). Pages include it with <script defer src="assets/author-footer.js">. */
(function () {
  var footer = document.querySelector('footer');
  if (!footer || footer.querySelector('.author-line')) return;

  function link(text, href) {
    var a = document.createElement('a');
    a.textContent = text;
    a.href = href;
    a.style.color = 'inherit';
    a.style.textDecoration = 'underline';
    return a;
  }

  var line = document.createElement('p');
  line.className = 'author-line';
  line.style.margin = '.6rem 0 0';
  line.appendChild(document.createTextNode('Built by Simon · energy engineer (MEng, CEM) · '));
  line.appendChild(link('All tools', 'index.html'));
  line.appendChild(document.createTextNode(' · '));
  line.appendChild(link('Get in touch', 'index.html#contact'));
  footer.appendChild(line);
})();
