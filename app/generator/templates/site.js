document.getElementById("top-link").addEventListener("click", (event) => {
  event.preventDefault();
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  window.scrollTo({ top: 0, behavior: reducedMotion ? "instant" : "smooth" });
});
