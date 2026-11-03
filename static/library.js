// Show the fallback if the cover fails to load.
document.querySelectorAll('[data-book-cover]').forEach((image) => {
  const hideBrokenCover = () => { image.hidden = true; };
  image.addEventListener('error', hideBrokenCover);
  if (image.complete && image.naturalWidth === 0) hideBrokenCover();
});

// Disable the button while waiting for a recommendation.
document.querySelectorAll('[data-recommendation-form]').forEach((form) => {
  form.addEventListener('submit', () => {
    form.querySelector('button').disabled = true;
    form.querySelector('[role="status"]').hidden = false;
  });
});

// Confirm before deleting an author and all their books.
document.querySelectorAll('[data-delete-author]').forEach((form) => {
  form.addEventListener('submit', (event) => {
    if (!window.confirm('Delete this author and all their books? This cannot be undone.')) {
      event.preventDefault();
    }
  });
});
