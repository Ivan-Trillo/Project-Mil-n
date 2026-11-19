(function () {
  "use strict";

  const raiz = document.getElementById("caja");
  const $ = (id) => document.getElementById(id);
  const csrf = document.querySelector("[name=csrfmiddlewaretoken]").value;
  const formato = new Intl.NumberFormat("es-MX", {
    style: "currency",
    currency: "MXN",
  });
  const pesos = (v) => formato.format(Number(v || 0)); // RNF-INT-04: $1,234.56

  const urls = {
    estado: raiz.dataset.urlEstado,
    productos: raiz.dataset.urlProductos,
    tickets: raiz.dataset.urlTickets,
    base: raiz.dataset.urlBase,
    ticket: (id) => raiz.dataset.urlTicket.replace("/0/", "/" + id + "/"),
  };

  let estado = JSON.parse($("estado-inicial").textContent);
  let lineaSeleccionada = null;
  let cobrando = false;
  let categoriaActual = "";
  let ultimaVenta = null;
  let ocupado = false;

  const campoCodigo = $("codigo");
  const modalExito = new bootstrap.Modal($("modalExito"));
  const modalError = new bootstrap.Modal($("modalError"));
  const aviso = new bootstrap.Toast($("aviso"), {
    delay: 2500,
    animation: false,
  });

  // ------------------------------------------------------------ Comunicacion con el servidor

  async function llamar(url, datos, metodo) {
    const opciones = {
      method: metodo || (datos === undefined ? "GET" : "POST"),
      headers: { "X-CSRFToken": csrf, "Content-Type": "application/json" },
      credentials: "same-origin",
    };
    if (datos !== undefined) opciones.body = JSON.stringify(datos);
    let respuesta;
    try {
      respuesta = await fetch(url, opciones);
    } catch (e) {
      throw new Error(
        "No hay conexión con el servidor. Revisa la red e intenta de nuevo.",
      );
    }
    if (respuesta.redirected || respuesta.status === 403) {
      // La sesion expiro (RF-AUT-05)
      window.location.reload();
      throw new Error("La sesión expiró.");
    }
    let json;
    try {
      json = await respuesta.json();
    } catch (e) {
      throw new Error("Ocurrió un error inesperado. Intenta de nuevo.");
    }
    if (!json.ok && json.error) {
      const error = new Error(json.error);
      error.codigo = json.codigo;
      throw error;
    }
    return json;
  }

  const urlTicket = (accion) =>
    urls.base + estado.activo.id + "/" + accion + "/";

  async function accion(url, datos, opciones) {
    if (ocupado) return null;
    ocupado = true;
    try {
      const json = await llamar(url, datos);
      if (json.estado) {
        estado = json.estado;
        dibujar();
      }
      return json;
    } catch (error) {
      if (!(opciones && opciones.silencioso))
        mostrarAviso(error.message, "error");
      throw error;
    } finally {
      ocupado = false;
    }
  }

  // ------------------------------------------------------------ Dibujo del ticket

  function dibujar() {
    const t = estado.activo;

    // Pestañas (RF-VEN-09): solo aparecen cuando hay mas de un ticket abierto
    const variosTickets = estado.tickets.length > 1;
    const pestanas = $("pestanas");
    pestanas.innerHTML = "";
    pestanas.hidden = !variosTickets;
    estado.tickets.forEach((ticket) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "pestana" + (ticket.id === t.id ? " activa" : "");
      b.textContent = "Ticket " + ticket.numero;
      b.setAttribute("role", "tab");
      b.setAttribute("aria-selected", ticket.id === t.id);
      b.addEventListener("click", () => cambiarTicket(ticket.id));
      pestanas.appendChild(b);
    });
    if (variosTickets && estado.tickets.length < estado.max_tickets) {
      const mas = document.createElement("button");
      mas.type = "button";
      mas.className = "pestana pestana-nueva";
      mas.title = "Abrir otro ticket";
      mas.innerHTML = '<i class="bi bi-plus-lg"></i>';
      mas.addEventListener("click", nuevoTicket);
      pestanas.appendChild(mas);
    }

    $("numeroTicket").textContent = variosTickets ? t.numero : "";
    $("numLineas").textContent = t.lineas.length;

    // Lineas
    const lista = $("lineas");
    lista.innerHTML = "";
    t.lineas.forEach((l) => {
      // La linea no es un <button> porque adentro lleva el boton de quitar
      const fila = document.createElement("div");
      fila.className =
        "linea" + (l.id === lineaSeleccionada ? " seleccionada" : "");
      fila.dataset.id = l.id;
      fila.setAttribute("role", "button");
      fila.tabIndex = 0;
      fila.title = "Editar cantidad";
      fila.innerHTML =
        '<span class="linea-nombre"></span><span class="linea-importe"></span>' +
        '<button type="button" class="linea-quitar" title="Quitar del ticket" aria-label="Quitar ' +
        escapar(l.nombre) +
        ' del ticket"><i class="bi bi-trash3"></i></button>';
      fila.querySelector(".linea-nombre").innerHTML =
        escapar(l.nombre) +
        (l.cantidad > 1
          ? ' <span class="linea-cantidad">× ' + l.cantidad + "</span>"
          : "");
      fila.querySelector(".linea-importe").textContent = pesos(l.subtotal);
      fila.addEventListener("click", (e) => {
        e.stopPropagation();
        seleccionarLinea(l.id === lineaSeleccionada ? null : l.id);
      });
      fila.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          seleccionarLinea(l.id);
        }
      });
      // RF-VEN-06 (Borrar) directo desde la lista
      fila
        .querySelector(".linea-quitar")
        .addEventListener("click", async (e) => {
          e.stopPropagation();
          if (lineaSeleccionada === l.id) seleccionarLinea(null);
          await accion(
            urls.base + estado.activo.id + "/lineas/" + l.id + "/quitar/",
            {},
          ).catch(() => {});
          enfocar();
        });
      lista.appendChild(fila);
    });
    const vacio = t.lineas.length === 0;
    $("ticketVacio").hidden = !vacio;
    $("totales").hidden = vacio;
    $("tarjetaTicket").classList.toggle("vacia", vacio);
    document
      .querySelector(".caja-izquierda")
      .classList.toggle("con-ticket-vacio", vacio && !cobrando);
    $("btnCobrar").disabled = vacio || cobrando;
    $("btnGuardar").disabled = vacio || cobrando;

    // Totales (RF-VEN-08)
    $("total").textContent = pesos(t.total);
    $("total2").textContent = pesos(t.total);
    $("subtotal").textContent = pesos(t.subtotal);
    $("descuento").textContent =
      Number(t.descuento) > 0 ? "−" + pesos(t.descuento) : pesos(0);
    $("impuesto").textContent = pesos(t.impuesto);

    if (
      lineaSeleccionada &&
      !t.lineas.some((l) => l.id === lineaSeleccionada)
    ) {
      seleccionarLinea(null);
    } else if (lineaSeleccionada) {
      llenarEditor();
    }
    if (cobrando) actualizarCobro();
  }

  function escapar(texto) {
    const div = document.createElement("div");
    div.textContent = texto;
    return div.innerHTML;
  }

  // ------------------------------------------------------------ Tickets

  async function cambiarTicket(id) {
    if (cobrando) cancelarCobro();
    seleccionarLinea(null);
    const json = await llamar(urls.estado + "?ticket=" + id);
    estado = json.estado;
    dibujar();
    enfocar();
  }

  async function nuevoTicket() {
    if (cobrando) cancelarCobro();
    seleccionarLinea(null);
    await accion(urls.tickets, {}).catch(() => {});
    enfocar();
  }

  // Guardar = dejar pendiente (RF-VEN-10) y atender al siguiente cliente en otro ticket
  $("btnGuardar").addEventListener("click", async () => {
    await nuevoTicket();
    mostrarAviso(
      "Ticket guardado como pendiente. Lo encuentras en su pestaña.",
    );
  });

  $("btnNuevoTicket").addEventListener("click", nuevoTicket);

  $("btnDescartar").addEventListener("click", async () => {
    if (
      estado.activo.lineas.length &&
      !confirm("¿Descartar este ticket y todos sus productos?")
    )
      return;
    if (cobrando) cancelarCobro();
    await accion(urlTicket("descartar"), {}).catch(() => {});
    enfocar();
  });

  $("btnPlegarLista").addEventListener("click", () => {
    const lineas = $("lineas");
    const abierta = !lineas.classList.toggle("plegada");
    $("btnPlegarLista").setAttribute("aria-expanded", abierta);
  });

  $("btnDesglose").addEventListener("click", () => {
    const d = $("desglose");
    d.hidden = !d.hidden;
    $("btnDesglose").setAttribute("aria-expanded", !d.hidden);
  });

  $("btnDescuento").addEventListener("click", async () => {
    const actual = Number(estado.activo.descuento) || 0;
    const valor = prompt(
      "Descuento en pesos (subtotal " + pesos(estado.activo.subtotal) + "):",
      actual ? actual : "",
    );
    if (valor === null) return;
    await accion(urlTicket("descuento"), { monto: valor || 0 }).catch(() => {});
    enfocar();
  });

  // ------------------------------------------------------------ Agregar productos

  async function agregarPorCodigo(texto) {
    try {
      await accion(
        urlTicket("agregar"),
        { codigo: texto },
        { silencioso: true },
      );
      campoCodigo.value = "";
      return true;
    } catch (error) {
      if (error.codigo !== "no_encontrado") {
        mostrarAviso(error.message, "error");
        return false;
      }
      // RF-VEN-02 / RF-VEN-03: si no es un codigo, se busca por nombre
      const limpio = texto.replace(/^\d+\*/, "");
      if (/[a-záéíóúñ]/i.test(limpio) && limpio.length >= 3) {
        cargarProductos({ q: limpio });
      } else {
        mostrarAviso("Producto no encontrado", "error");
        campoCodigo.select();
      }
      return false;
    }
  }

  async function agregarProducto(id, cantidad) {
    await accion(urlTicket("agregar"), {
      producto_id: id,
      cantidad: cantidad || 1,
    }).catch(() => {});
    enfocar();
  }

  campoCodigo.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      const texto = campoCodigo.value.trim();
      if (texto) agregarPorCodigo(texto);
    }
  });

  //busqueda por nombre
  let temporizador = null;
  campoCodigo.addEventListener("input", () => {
    clearTimeout(temporizador);
    const texto = campoCodigo.value.trim();
    if (/[a-záéíóúñ]/i.test(texto) && texto.length >= 3) {
      temporizador = setTimeout(() => cargarProductos({ q: texto }), 250);
    } else if (texto === "" && $("tituloGrid").dataset.busqueda) {
      cargarProductos({ categoria: categoriaActual });
    }
  });

  // ------------------------------------------------------------ Cuadricula de productos

  async function cargarProductos(filtro) {
    const params = new URLSearchParams(filtro);
    let json;
    try {
      json = await llamar(urls.productos + "?" + params.toString());
    } catch (error) {
      mostrarAviso(error.message, "error");
      return;
    }
    const grid = $("gridProductos");
    grid.innerHTML = "";
    const titulo = $("tituloGrid");
    if (filtro.q) {
      titulo.textContent = 'Resultados para "' + filtro.q + '"';
      titulo.dataset.busqueda = "1";
    } else {
      const activa = document.querySelector("#categorias .pildora.activa");
      titulo.textContent = activa ? activa.textContent : "Todos";
      delete titulo.dataset.busqueda;
    }
    if (!json.productos.length) {
      const mensaje = filtro.q
        ? "No hay productos que coincidan con «" + escapar(filtro.q) + "»."
        : filtro.categoria
          ? "Esta categoría no tiene productos activos."
          : "Todavía no hay productos. Regístralos en Inventario para empezar a vender.";
      grid.innerHTML =
        '<div class="grid-vacio"><i class="bi bi-box-seam"></i>' +
        mensaje +
        "</div>";
      return;
    }
    json.productos.forEach((p) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "producto" + (p.existencia <= 0 ? " agotado" : "");
      b.title =
        p.nombre + " · " + pesos(p.precio) + " · existencia " + p.existencia;
      const foto = p.imagen
        ? '<img src="' + p.imagen + '" alt="">'
        : '<span class="producto-iniciales">' +
          escapar(p.nombre.slice(0, 2).toUpperCase()) +
          "</span>";
      b.innerHTML =
        '<span class="producto-foto">' +
        foto +
        (p.existencia <= 0
          ? '<span class="producto-etiqueta">Agotado</span>'
          : "") +
        "</span>" +
        '<span class="producto-nombre">' +
        escapar(p.nombre) +
        "</span>" +
        '<span class="producto-precio">' +
        pesos(p.precio) +
        "</span>";
      b.addEventListener("click", () => agregarProducto(p.id));
      grid.appendChild(b);
    });
  }

  document.querySelectorAll("#categorias .pildora").forEach((pildora) => {
    pildora.addEventListener("click", () => {
      document
        .querySelectorAll("#categorias .pildora")
        .forEach((p) => p.classList.remove("activa"));
      pildora.classList.add("activa");
      categoriaActual = pildora.dataset.categoria;
      campoCodigo.value = "";
      cargarProductos({ categoria: categoriaActual });
      enfocar();
    });
  });

  // ------------------------------------------------------------ Editar una linea (Cambiar / Borrar)

  function seleccionarLinea(id) {
    lineaSeleccionada = id;
    document
      .querySelectorAll(".linea")
      .forEach((f) =>
        f.classList.toggle("seleccionada", Number(f.dataset.id) === id),
      );
    const editor = $("editorLinea");
    if (!id) {
      editor.hidden = true;
      return;
    }
    llenarEditor(true);
    editor.hidden = false;
    posicionar(editor, document.querySelector('.linea[data-id="' + id + '"]'));
    const campo = $("editorCantidad");
    campo.value = lineaActual().cantidad;
    campo.focus();
    campo.select();
  }

  function lineaActual() {
    return estado.activo.lineas.find((l) => l.id === lineaSeleccionada);
  }

  function llenarEditor(forzar) {
    const l = lineaActual();
    if (!l) return;
    $("editorNombre").textContent = l.nombre;
    $("editorCategoria").textContent =
      (l.categoria || "Sin categoría") + " · " + pesos(l.precio) + " c/u";
    $("editorExistencia").textContent = l.existencia + " en existencia";
    if (forzar || document.activeElement !== $("editorCantidad"))
      $("editorCantidad").value = l.cantidad;
    $("editorPiezas").textContent = l.cantidad === 1 ? "pieza" : "piezas";
    $("editorFoto").innerHTML = l.imagen
      ? '<img src="' + l.imagen + '" alt="">'
      : '<span class="producto-iniciales">' +
        escapar(l.nombre.slice(0, 2).toUpperCase()) +
        "</span>";
  }

  async function cambiarCantidad(cantidad) {
    const l = lineaActual();
    if (!l) return;
    await accion(urlTicket("lineas/" + l.id + "/cantidad"), {
      cantidad: cantidad,
    }).catch(() => llenarEditor());
  }

  $("editorMas").addEventListener("click", () =>
    cambiarCantidad(lineaActual().cantidad + 1),
  );
  $("editorMenos").addEventListener("click", () => {
    const l = lineaActual();
    if (l.cantidad > 1) cambiarCantidad(l.cantidad - 1);
  });
  $("editorCantidad").addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      const n = parseInt($("editorCantidad").value, 10);
      if (n > 0)
        cambiarCantidad(n).then(() => {
          seleccionarLinea(null);
          enfocar();
        });
    }
  });
  $("editorCantidad").addEventListener("change", () => {
    const n = parseInt($("editorCantidad").value, 10);
    if (n > 0 && lineaActual() && n !== lineaActual().cantidad)
      cambiarCantidad(n);
  });
  $("editorEliminar").addEventListener("click", async () => {
    const l = lineaActual();
    if (!l) return;
    await accion(urlTicket("lineas/" + l.id + "/quitar"), {}).catch(() => {});
    seleccionarLinea(null);
    enfocar();
  });

  // ------------------------------------------------------------ Cobro (RF-VEN-11 y RF-VEN-12)

  function iniciarCobro() {
    if (!estado.activo.lineas.length || cobrando) return;
    seleccionarLinea(null);
    cobrando = true;
    $("tarjetaVenta").hidden = false;
    $("btnCobrar").disabled = true;
    $("btnGuardar").disabled = true;
    const panel = $("panelCobro");
    panel.hidden = false;
    posicionar(panel, $("tarjetaVenta"));
    $("cobroRecibido").value = "";
    $("cobroError").hidden = true;
    actualizarCobro();
    $("cobroRecibido").focus();
  }

  function cancelarCobro() {
    cobrando = false;
    $("tarjetaVenta").hidden = true;
    $("panelCobro").hidden = true;
    dibujar();
    enfocar();
  }

  function montoRecibido() {
    const limpio = $("cobroRecibido").value.replace(/[$,\s]/g, "");
    return limpio === "" ? null : Number(limpio);
  }

  function actualizarCobro() {
    const t = estado.activo;
    const total = Number(t.total);
    $("cobroTotal").textContent = pesos(total);
    $("cobroPiezas").textContent =
      t.piezas + (t.piezas === 1 ? " producto" : " productos");
    const recibido = montoRecibido();
    const cambio = recibido === null || isNaN(recibido) ? 0 : recibido - total;
    $("cobroCambio").textContent = pesos(Math.max(cambio, 0));
    $("btnConfirmar").disabled =
      recibido === null || isNaN(recibido) || recibido < total;

    // Botones de cobro rapido: exacto y billetes comunes
    const rapido = $("cobroRapido");
    const opciones = [total];
    [20, 50, 100, 200, 500, 1000].forEach((b) => {
      if (b > total && opciones.length < 4) opciones.push(b);
    });
    rapido.innerHTML = "";
    opciones.forEach((monto, i) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "btn btn-sm btn-light";
      b.textContent = i === 0 ? "Exacto" : pesos(monto).replace(".00", "");
      b.addEventListener("click", () => {
        $("cobroRecibido").value = monto.toFixed(2);
        actualizarCobro();
        $("cobroRecibido").focus();
      });
      rapido.appendChild(b);
    });
  }

  $("cobroRecibido").addEventListener("input", () => {
    $("cobroError").hidden = true;
    actualizarCobro();
  });

  $("panelCobro").addEventListener("submit", async (e) => {
    e.preventDefault();
    const recibido = montoRecibido();
    if (
      recibido === null ||
      isNaN(recibido) ||
      recibido < Number(estado.activo.total)
    ) {
      // RF-VEN-12
      $("cobroError").textContent =
        "El efectivo recibido es menor que el total.";
      $("cobroError").hidden = false;
      return;
    }
    $("btnConfirmar").disabled = true;
    try {
      const json = await accion(
        urlTicket("cobrar"),
        { monto_recibido: recibido },
        { silencioso: true },
      );
      if (!json) return;
      ultimaVenta = json.venta;
      cobrando = false;
      $("tarjetaVenta").hidden = true;
      $("panelCobro").hidden = true;
      dibujar();
      $("exitoFolio").textContent = ultimaVenta.folio;
      $("exitoCambio").textContent = pesos(ultimaVenta.cambio);
      modalExito.show();
      imprimir();
    } catch (error) {
      $("errorMensaje").textContent = error.message;
      modalError.show();
      $("btnConfirmar").disabled = false;
    }
  });

  $("btnCobrar").addEventListener("click", iniciarCobro);
  $("btnCancelarCobro").addEventListener("click", cancelarCobro);

  // ------------------------------------------------------------ Impresion del ticket

  function anchoPapel() {
    try {
      return localStorage.getItem("papelTicket") || "80";
    } catch (e) {
      return "80";
    }
  }

  document.querySelectorAll("input[name=papel]").forEach((r) => {
    r.checked = r.value === anchoPapel();
    r.addEventListener("change", () => {
      try {
        localStorage.setItem("papelTicket", r.value);
      } catch (e) {
        /* sin almacenamiento */
      }
    });
  });

  function imprimir() {
    if (!ultimaVenta) return;
    const marco = $("marcoImpresion");
    marco.onload = function () {
      try {
        marco.contentWindow.focus();
        marco.contentWindow.print();
      } catch (e) {
        // Si el navegador no deja imprimir desde el iframe, se abre en otra pestaña
        window.open(marco.src, "_blank");
      }
    };
    marco.src =
      urls.ticket(ultimaVenta.id) +
      "?ancho=" +
      anchoPapel() +
      "&t=" +
      Date.now();
  }

  $("btnImprimir").addEventListener("click", imprimir);
  $("modalExito").addEventListener("hidden.bs.modal", enfocar);
  $("modalError").addEventListener("hidden.bs.modal", () => {
    if (cobrando) $("cobroRecibido").focus();
    else enfocar();
  });

  // ------------------------------------------------------------ Utilidades

  function posicionar(flotante, ancla) {
    if (!ancla) return;
    if (window.innerWidth < 992) {
      flotante.classList.add("flotante-movil");
      return;
    }
    flotante.classList.remove("flotante-movil");
    const r = ancla.getBoundingClientRect();
    const base = raiz.getBoundingClientRect();
    const izquierda =
      $("tarjetaTicket").getBoundingClientRect().right - base.left + 12;
    let arriba = r.top - base.top - 8;
    flotante.style.left = izquierda + "px";
    flotante.style.top = Math.max(arriba, 0) + "px";
    // que no se salga por abajo
    requestAnimationFrame(() => {
      const alto = flotante.offsetHeight;
      const max = window.innerHeight - base.top - alto - 16;
      if (arriba > max) flotante.style.top = Math.max(max, 0) + "px";
    });
  }

  function enfocar() {
    if (cobrando || lineaSeleccionada) return;
    campoCodigo.focus();
  }

  function mostrarAviso(texto, tipo) {
    const el = $("aviso");
    el.classList.toggle("text-bg-danger", tipo === "error");
    el.classList.toggle("text-bg-dark", tipo !== "error");
    $("avisoTexto").textContent = texto;
    aviso.show();
  }

  //clic fuera del editor lo cierra
  document.addEventListener("click", (e) => {
    if (
      lineaSeleccionada &&
      !$("editorLinea").contains(e.target) &&
      !e.target.closest(".linea")
    ) {
      seleccionarLinea(null);
      enfocar();
    }
  });

  // Atajos de teclado (RNF-USA-03)
  document.addEventListener("keydown", (e) => {
    if (e.key === "F2") {
      e.preventDefault();
      iniciarCobro();
    } else if (e.key === "Escape") {
      if (lineaSeleccionada) seleccionarLinea(null);
      else if (cobrando) cancelarCobro();
      enfocar();
    }
  });

  //si el usuario hace clic en un area vacia, el foco regresa al lector
  raiz.addEventListener("click", (e) => {
    if (!e.target.closest("input, button, a, .flotante")) enfocar();
  });

  campoCodigo.value = "";
  dibujar();
  cargarProductos({ categoria: "" });
  enfocar();
})();
