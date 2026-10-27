(function () {
  document.querySelectorAll("[data-copy]").forEach(function (button) {
    button.addEventListener("click", function () {
      var value = button.getAttribute("data-copy") || "";
      navigator.clipboard.writeText(value).then(function () {
        button.textContent = "Скопировано";
        window.setTimeout(function () {
          button.textContent = "Копировать";
        }, 1600);
      }).catch(function () {
        button.textContent = "Не скопировалось";
      });
    });
  });

  document.querySelectorAll("[data-print]").forEach(function (button) {
    button.addEventListener("click", function () {
      window.print();
    });
  });

  var audio = document.querySelector("audio[data-audio]");
  var dock = document.querySelector("[data-player]");
  if (audio && dock) {
    setupPlayer(audio, dock);
  }

  var dialog = document.querySelector("[data-lightbox]");
  if (dialog) {
    setupLightbox(dialog);
  }

  function setupPlayer(audioElement, player) {
    var start = player.querySelector("[data-start]");
    var transport = player.querySelector("[data-transport]");
    var toggle = player.querySelector("[data-toggle]");
    var label = player.querySelector("[data-toggle-label]");
    var playIcon = player.querySelector("[data-icon-play]");
    var pauseIcon = player.querySelector("[data-icon-pause]");
    var seek = player.querySelector("[data-seek]");
    var current = player.querySelector("[data-current]");
    var duration = player.querySelector("[data-duration]");
    var speed = player.querySelector("[data-speed]");
    var error = player.querySelector("[data-error]");
    var ctaDuration = player.querySelector("[data-cta-duration]");
    var speeds = [1, 1.25, 1.5];
    var speedIndex = 0;
    var scrubbing = false;
    var started = false;

    player.removeAttribute("hidden");
    audioElement.setAttribute("aria-hidden", "true");
    audioElement.tabIndex = -1;
    audioElement.removeAttribute("controls");

    function formatTime(seconds) {
      if (!Number.isFinite(seconds) || seconds < 0) {
        return "0:00";
      }
      var whole = Math.floor(seconds);
      var minutes = Math.floor(whole / 60);
      var rest = whole % 60;
      return minutes + ":" + String(rest).padStart(2, "0");
    }

    function formatRate(rate) {
      var text = rate === 1 ? "1" : String(rate).replace(".", ",");
      return text + "×";
    }

    function paintToggle() {
      var playing = !audioElement.paused && !audioElement.ended;
      label.textContent = playing ? "Пауза" : "Продолжить";
      toggle.setAttribute("aria-label", playing ? "Пауза" : "Продолжить аудиоописание");
      toggle.setAttribute("aria-pressed", playing ? "true" : "false");
      playIcon.hidden = playing;
      pauseIcon.hidden = !playing;
    }

    function paintTime() {
      var dur = audioElement.duration;
      current.textContent = formatTime(audioElement.currentTime);
      duration.textContent = formatTime(dur);
      if (Number.isFinite(dur) && dur > 0) {
        ctaDuration.hidden = false;
        ctaDuration.textContent = formatTime(dur);
        if (!scrubbing) {
          var value = Math.round((audioElement.currentTime / dur) * 1000);
          seek.value = String(value);
          seek.setAttribute("aria-valuenow", String(value));
          seek.setAttribute("aria-valuetext", formatTime(audioElement.currentTime) + " из " + formatTime(dur));
          seek.style.setProperty("--pct", value / 10 + "%");
        }
      }
    }

    function revealTransport() {
      started = true;
      start.hidden = true;
      transport.hidden = false;
    }

    function play() {
      var pending = audioElement.play();
      if (pending && typeof pending.catch === "function") {
        pending.catch(function () {
          error.hidden = false;
          paintToggle();
        });
      }
    }

    start.addEventListener("click", function () {
      error.hidden = true;
      revealTransport();
      play();
    });

    toggle.addEventListener("click", function () {
      if (audioElement.paused || audioElement.ended) {
        if (audioElement.ended) {
          audioElement.currentTime = 0;
        }
        play();
      } else {
        audioElement.pause();
      }
    });

    audioElement.addEventListener("play", paintToggle);
    audioElement.addEventListener("pause", paintToggle);
    audioElement.addEventListener("ended", function () {
      paintToggle();
      paintTime();
    });
    audioElement.addEventListener("timeupdate", paintTime);
    audioElement.addEventListener("loadedmetadata", paintTime);
    audioElement.addEventListener("durationchange", paintTime);
    audioElement.addEventListener("error", function () {
      error.hidden = false;
    });

    function releaseScrub() {
      scrubbing = false;
    }

    seek.addEventListener("pointerdown", function () {
      scrubbing = true;
    });
    seek.addEventListener("pointerup", releaseScrub);
    seek.addEventListener("pointercancel", releaseScrub);
    seek.addEventListener("blur", releaseScrub);
    seek.addEventListener("input", function () {
      var dur = audioElement.duration;
      if (!Number.isFinite(dur) || dur <= 0) {
        return;
      }
      var ratio = Number(seek.value) / 1000;
      audioElement.currentTime = ratio * dur;
      seek.style.setProperty("--pct", ratio * 100 + "%");
      current.textContent = formatTime(audioElement.currentTime);
      seek.setAttribute("aria-valuenow", seek.value);
      seek.setAttribute("aria-valuetext", formatTime(audioElement.currentTime) + " из " + formatTime(dur));
    });

    speed.addEventListener("click", function () {
      speedIndex = (speedIndex + 1) % speeds.length;
      var rate = speeds[speedIndex];
      audioElement.playbackRate = rate;
      var text = formatRate(rate);
      speed.textContent = text;
      speed.setAttribute("aria-label", "Скорость воспроизведения " + text);
    });

    document.addEventListener("keydown", function (event) {
      if (event.code !== "Space" || event.repeat) {
        return;
      }
      var target = event.target;
      if (!(target instanceof Element) || target.closest("input, textarea, button, a, select")) {
        return;
      }
      event.preventDefault();
      if (!started) {
        error.hidden = true;
        revealTransport();
        play();
        return;
      }
      if (audioElement.paused || audioElement.ended) {
        if (audioElement.ended) {
          audioElement.currentTime = 0;
        }
        play();
      } else {
        audioElement.pause();
      }
    });

    paintTime();
  }

  function setupLightbox(lightbox) {
    var stage = lightbox.querySelector(".lightbox__stage");
    var closer = lightbox.querySelector("[data-close]");

    document.querySelectorAll("[data-zoom]").forEach(function (opener) {
      opener.addEventListener("click", function () {
        if (typeof lightbox.showModal === "function") {
          lightbox.showModal();
        }
      });
    });

    if (closer) {
      closer.addEventListener("click", function () {
        lightbox.close();
      });
    }

    lightbox.addEventListener("click", function (event) {
      if (event.target === lightbox) {
        lightbox.close();
      }
    });

    if (stage) {
      stage.addEventListener("click", function (event) {
        if (event.target === stage) {
          lightbox.close();
        }
      });
    }
  }
})();
