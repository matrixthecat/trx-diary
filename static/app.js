function formatLocalDate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function setTodayDefaults() {
  const dateInput = document.getElementById('workout-date');
  if (dateInput && !dateInput.value) {
    dateInput.value = formatLocalDate(new Date());
  }

  const weekInput = document.getElementById('week-start');
  if (weekInput && !weekInput.value) {
    const today = new Date();
    const day = today.getDay();
    const diff = (day === 0 ? -6 : 1) - day;
    today.setDate(today.getDate() + diff);
    weekInput.value = formatLocalDate(today);
  }
}

function setupExerciseOptions() {
  const routineNode = document.getElementById('routine-data');
  const daySelect = document.getElementById('day-select');
  const exerciseSelect = document.getElementById('exercise-select');

  if (!routineNode || !daySelect || !exerciseSelect) {
    return;
  }

  const routine = JSON.parse(routineNode.textContent || '{}');

  const refreshExercises = () => {
    const day = daySelect.value;
    const exercises = routine[day] || [];

    exerciseSelect.innerHTML = '';
    exercises.forEach((exercise) => {
      const option = document.createElement('option');
      option.value = exercise;
      option.textContent = exercise;
      exerciseSelect.appendChild(option);
    });
  };

  daySelect.addEventListener('change', refreshExercises);
  refreshExercises();
}

async function renderDashboard() {
  const repsCanvas = document.getElementById('repsChart');
  const weightCanvas = document.getElementById('weightChart');

  if (!repsCanvas || !weightCanvas || typeof Chart === 'undefined') {
    return;
  }

  let data;
  try {
    const response = await fetch('/api/dashboard');
    if (!response.ok) {
      return;
    }
    data = await response.json();
  } catch (_error) {
    return;
  }

  new Chart(repsCanvas, {
    type: 'line',
    data: {
      labels: data.reps.labels,
      datasets: [
        {
          label: 'Ripetizioni totali per giorno',
          data: data.reps.values,
          borderColor: '#0a6a73',
          backgroundColor: 'rgba(10, 106, 115, 0.15)',
          fill: true,
          tension: 0.25,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: true } },
      scales: { y: { beginAtZero: true } },
    },
  });

  new Chart(weightCanvas, {
    type: 'bar',
    data: {
      labels: data.weight.labels,
      datasets: [
        {
          label: 'Peso settimanale (kg)',
          data: data.weight.values,
          backgroundColor: '#d16a3d',
          borderRadius: 6,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: true } },
      scales: { y: { beginAtZero: false } },
    },
  });
}

function setupWorkoutTimer() {
  const display = document.getElementById('timer-display');
  const startBtn = document.getElementById('timer-start');
  const pauseBtn = document.getElementById('timer-pause');
  const resetBtn = document.getElementById('timer-reset');
  const presetInput = document.getElementById('timer-seconds');
  const applyBtn = document.getElementById('timer-apply');

  if (!display || !startBtn || !pauseBtn || !resetBtn || !presetInput || !applyBtn) {
    return;
  }

  let seconds = Number(presetInput.value) || 60;
  let timerId = null;

  const render = () => {
    const mm = String(Math.floor(seconds / 60)).padStart(2, '0');
    const ss = String(seconds % 60).padStart(2, '0');
    display.textContent = `${mm}:${ss}`;
  };

  const stopTimer = () => {
    if (timerId) {
      clearInterval(timerId);
      timerId = null;
    }
  };

  startBtn.addEventListener('click', () => {
    if (timerId) {
      return;
    }
    timerId = setInterval(() => {
      if (seconds > 0) {
        seconds -= 1;
        render();
      } else {
        stopTimer();
      }
    }, 1000);
  });

  pauseBtn.addEventListener('click', stopTimer);

  resetBtn.addEventListener('click', () => {
    stopTimer();
    seconds = Number(presetInput.value) || 60;
    render();
  });

  applyBtn.addEventListener('click', () => {
    stopTimer();
    seconds = Number(presetInput.value) || 60;
    render();
  });

  render();
}

function setupMobileMenu() {
  const toggle = document.getElementById('menu-toggle');
  const nav = document.getElementById('main-nav');

  if (!toggle || !nav) {
    return;
  }

  const setOpen = (open) => {
    toggle.classList.toggle('is-open', open);
    toggle.setAttribute('aria-expanded', String(open));
    nav.classList.toggle('is-open', open);
  };

  toggle.addEventListener('click', () => {
    const isOpen = toggle.getAttribute('aria-expanded') === 'true';
    setOpen(!isOpen);
  });

  nav.querySelectorAll('a').forEach((link) => {
    link.addEventListener('click', () => setOpen(false));
  });

  document.addEventListener('click', (event) => {
    const clickedInsideToggle = toggle.contains(event.target);
    const clickedInsideNav = nav.contains(event.target);

    if (!clickedInsideToggle && !clickedInsideNav) {
      setOpen(false);
    }
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      setOpen(false);
    }
  });

  setOpen(false);
}

function setupWorkoutCompletion() {
  const checks = document.querySelectorAll('.completion-check');
  if (!checks.length) {
    return;
  }

  checks.forEach((check) => {
    check.addEventListener('change', async () => {
      const formData = new FormData();
      formData.append('exercise_name', check.dataset.exercise || '');
      formData.append('workout_date', check.dataset.date || '');
      formData.append('completed', check.checked ? '1' : '0');

      try {
        const response = await fetch('/workout/toggle_completion', {
          method: 'POST',
          body: formData,
        });
        if (!response.ok) {
          check.checked = !check.checked;
        }
      } catch (_error) {
        check.checked = !check.checked;
      }
    });
  });
}

function setupWorkoutPlaylist() {
  const node = document.getElementById('workout-playlist');
  const stage = document.getElementById('playlist-stage');
  const meta = document.getElementById('playlist-meta');
  const prevBtn = document.getElementById('playlist-prev');
  const nextBtn = document.getElementById('playlist-next');

  if (!node || !stage || !meta || !prevBtn || !nextBtn) {
    return;
  }

  let playlist;
  try {
    playlist = JSON.parse(node.textContent || '[]');
  } catch (_error) {
    return;
  }

  if (!Array.isArray(playlist) || playlist.length === 0) {
    return;
  }

  let index = 0;
  let autoId = null;

  const renderItem = () => {
    const item = playlist[index];
    stage.innerHTML = '';
    meta.textContent = `${index + 1}/${playlist.length} - ${item.exercise} - ${item.title}`;

    if (item.type === 'video_file') {
      const video = document.createElement('video');
      video.controls = true;
      video.preload = 'metadata';
      video.src = item.url;
      stage.appendChild(video);
    } else {
      const link = document.createElement('a');
      link.href = item.url;
      link.target = '_blank';
      link.rel = 'noopener';
      link.textContent = `Apri video: ${item.url}`;
      link.className = 'inline-link';
      stage.appendChild(link);
    }
  };

  const next = () => {
    index = (index + 1) % playlist.length;
    renderItem();
  };

  const prev = () => {
    index = (index - 1 + playlist.length) % playlist.length;
    renderItem();
  };

  prevBtn.addEventListener('click', prev);
  nextBtn.addEventListener('click', next);

  autoId = setInterval(next, 25000);
  window.addEventListener('beforeunload', () => {
    if (autoId) {
      clearInterval(autoId);
    }
  });

  renderItem();
}

setTodayDefaults();
setupExerciseOptions();
renderDashboard();
setupWorkoutTimer();
setupMobileMenu();
setupWorkoutCompletion();
setupWorkoutPlaylist();
