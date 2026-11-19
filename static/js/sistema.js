(function () {
  "use strict";

  const modalEl = document.getElementById("modalConfirmar");
  if (!modalEl) return;
  const modal = new bootstrap.Modal(modalEl);
  const texto = modalEl.querySelector("[data-confirmar-texto]");
  const botonSi = modalEl.querySelector("[data-confirmar-si]");
  let formularioPendiente = null;

  document.addEventListener("submit", function (evento) {
    const form = evento.target;
    if (!form.dataset.confirmar || form.dataset.confirmado === "1") return;
    evento.preventDefault();
    formularioPendiente = form;
    texto.textContent = form.dataset.confirmar;
    botonSi.textContent = form.dataset.confirmarBoton || "Sí, continuar";
    botonSi.className =
      "btn " +
      (form.dataset.confirmarPeligro !== undefined
        ? "btn-danger"
        : "btn-primary");
    modal.show();
  });

  botonSi.addEventListener("click", function () {
    if (!formularioPendiente) return;
    formularioPendiente.dataset.confirmado = "1";
    modal.hide();
    formularioPendiente.requestSubmit();
  });
})();
