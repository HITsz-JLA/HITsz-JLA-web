// 滚动检测淡入动画
document.addEventListener('DOMContentLoaded', function () {
  const elements = document.querySelectorAll('[data-animate]');

  const observer = new IntersectionObserver(
    entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('in-view');
        }
      });
    },
    { threshold: 0.1 }
  );

  elements.forEach(el => observer.observe(el));
});
