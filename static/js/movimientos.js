

/*-------------------------------------->
<!----------Modal categorias-------------->
<!--------------------------------------
        const iconos = [
            { nombre: 'comida', icono: 'fa-utensils', alias: ['alimentación', 'alimentos', 'restaurante'] },
            { nombre: 'salario', icono: 'fa-money-bill-wave', alias: ['sueldo', 'ingreso', 'pago'] },
            { nombre: 'transporte', icono: 'fa-bus', alias: ['bus', 'movilidad', 'viaje urbano'] },
            { nombre: 'educacion', icono: 'fa-book', alias: ['estudios', 'escuela', 'universidad'] },
            { nombre: 'hogar', icono: 'fa-home', alias: ['casa', 'vivienda', 'departamento'] },
            { nombre: 'salud', icono: 'fa-heartbeat', alias: ['medico', 'hospital', 'doctor', 'medicina'] },
            { nombre: 'ropa', icono: 'fa-tshirt', alias: ['vestimenta', 'camisa', 'ropa nueva'] },
            { nombre: 'regalo', icono: 'fa-gift', alias: ['cumpleaños', 'presentes', 'obsequio'] },
            { nombre: 'viaje', icono: 'fa-plane', alias: ['vacaciones', 'turismo', 'vuelo'] },
            { nombre: 'entretenimiento', icono: 'fa-film', alias: ['cine', 'películas', 'series'] },
            { nombre: 'mascota', icono: 'fa-dog', alias: ['perro', 'gato', 'animal', 'veterinario'] },
            { nombre: 'internet', icono: 'fa-wifi', alias: ['wifi', 'red', 'datos'] },
            { nombre: 'telefono', icono: 'fa-phone', alias: ['llamada', 'movil', 'celular'] },
            { nombre: 'electricidad', icono: 'fa-bolt', alias: ['luz', 'corriente', 'factura'] },
            { nombre: 'agua', icono: 'fa-tint', alias: ['servicio de agua', 'factura agua'] },
            { nombre: 'ahorro', icono: 'fa-piggy-bank', alias: ['guardar', 'fondo', 'reserva'] },
            { nombre: 'deporte', icono: 'fa-futbol', alias: ['ejercicio', 'actividad física', 'gimnasio'] },
            { nombre: 'banco', icono: 'fa-university', alias: ['cuenta', 'finanzas', 'entidad financiera'] },
            { nombre: 'tarjeta', icono: 'fa-credit-card', alias: ['crédito', 'pago', 'visa', 'mastercard'] },
            { nombre: 'impuesto', icono: 'fa-file-invoice-dollar', alias: ['renta', 'declaración'] },
            { nombre: 'trabajo', icono: 'fa-briefcase', alias: ['empleo', 'oficina', 'ocupación'] },
            { nombre: 'dinero', icono: 'fa-coins', alias: ['efectivo', 'plata', 'pago'] },
            { nombre: 'carro', icono: 'fa-car', alias: ['vehículo', 'automóvil', 'mantenimiento'] },
            { nombre: 'bicicleta', icono: 'fa-bicycle', alias: ['ciclismo', 'bici', 'movilidad'] },
            { nombre: 'alcohol', icono: 'fa-wine-glass-alt', alias: ['vino', 'cerveza', 'bebida'] },
            { nombre: 'musica', icono: 'fa-music', alias: ['canciones', 'audio', 'spotify'] },
            { nombre: 'libros', icono: 'fa-book-reader', alias: ['leer', 'novela', 'literatura'] },
            { nombre: 'bebida', icono: 'fa-coffee', alias: ['café', 'té', 'refresco'] },
            { nombre: 'belleza', icono: 'fa-spa', alias: ['maquillaje', 'estética', 'cosmética'] },
            { nombre: 'donacion', icono: 'fa-hands-helping', alias: ['caridad', 'iglesia', 'apoyo'] },
            { nombre: 'fiesta', icono: 'fa-glass-cheers', alias: ['celebración', 'cumpleaños', 'evento'] },
            { nombre: 'servicios', icono: 'fa-tools', alias: ['arreglo', 'reparación', 'mantenimiento'] },
            { nombre: 'tecnologia', icono: 'fa-laptop', alias: ['computadora', 'tablet', 'celular'] },
            { nombre: 'juegos', icono: 'fa-gamepad', alias: ['videojuegos', 'ps4', 'xbox', 'steam'] },
            { nombre: 'prestamo', icono: 'fa-hand-holding-usd', alias: ['deuda', 'crédito', 'préstamo'] },
            { nombre: 'inversion', icono: 'fa-chart-line', alias: ['acciones', 'criptos', 'ganancia'] },
            { nombre: 'trabajo freelance', icono: 'fa-user-tie', alias: ['proyecto', 'cliente', 'contrato'] },
            { nombre: 'niños', icono: 'fa-baby', alias: ['hijos', 'niño', 'bebé', 'cuidado infantil'] },
            { nombre: 'limpieza', icono: 'fa-soap', alias: ['aseo', 'productos de limpieza', 'hogar'] },
            { nombre: 'clases', icono: 'fa-chalkboard-teacher', alias: ['curso', 'tutoría', 'educación'] },
            { nombre: 'medios', icono: 'fa-tv', alias: ['netflix', 'televisión', 'streaming'] },
            { nombre: 'seguro', icono: 'fa-umbrella', alias: ['aseguradora', 'cobertura', 'póliza'] }
        ];


        // 🔍 Filtra iconos según nombre o alias
        function sugerirIconos() {
        const texto = document.getElementById("nombreCategoria").value.toLowerCase();
        const sugeridos = iconos.filter(item =>
            item.nombre.includes(texto) ||
            (item.alias && item.alias.some(alias => alias.includes(texto)))
        );
        renderIconos(sugeridos.slice(0, 6)); // solo los primeros 6
        }

        // 🎨 Muestra lista de iconos limitada
        function renderIconos(lista = iconos.slice(0, 6)) {
        const contenedor = document.getElementById("iconoSelector");
        contenedor.innerHTML = '';

        lista.forEach(item => {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "icono-btn";
            btn.title = item.nombre;
            btn.innerHTML = `<i class="fas ${item.icono}"></i>`;
            btn.onclick = () => {
            document.getElementById("iconoInput").value = item.icono;
            document.querySelectorAll('.icono-btn').forEach(b => b.classList.remove('selected'));
            btn.classList.add('selected');
            };
            contenedor.appendChild(btn);
        });
        }

        function abrirModalCategoria() {
            const modal = document.getElementById("modalCategoria");
            if (modal) {
            modal.style.display = "flex";
            modal.classList.add("show");
            modal.classList.remove("hide");
            }
        }

        function cerrarModalCategoria() {
            const modal = document.getElementById("modalCategoria");
            if (modal) {
            modal.classList.add("hide");
            modal.classList.remove("show");
            modal.addEventListener('animationend', function handler() {
                modal.style.display = "none";
                modal.classList.remove("hide");
                modal.removeEventListener('animationend', handler);
            });
            }
        }

        window.addEventListener("click", function (e) {
            const modal = document.getElementById("modalCategoria");
            if (modal && e.target === modal) cerrarModalCategoria();
        });

        // Inicial
        renderIconos();


        //Funcion no recargar la pagina 
        document.getElementById('formCrearCategoria').addEventListener('submit', function(event) {
  event.preventDefault(); // Evita que recargue

  const form = event.target;
  const formData = new FormData(form);

  fetch(form.action, {
    method: 'POST',
    body: formData,
  })
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      const grid = document.querySelector('.categorias-grid');
      const nuevaCategoria = data.categoria;

      // Crear input radio
      const input = document.createElement('input');
      input.type = 'radio';
      input.name = 'categoria_id';
      input.value = nuevaCategoria.id;
      input.id = 'cat' + nuevaCategoria.id;
      input.hidden = true;
      input.required = true;
      input.checked = true;

      // Crear label
      const label = document.createElement('label');
      label.setAttribute('for', input.id);
      label.className = 'categoria-tarjeta';
      label.innerHTML = `<i class="fa-solid ${nuevaCategoria.icono}"></i><br>${nuevaCategoria.nombre}`;

      // Insertar antes del botón "Agregar categoría"
      const btnAgregar = document.querySelector('.categoria-tarjeta.agregar-categoria');
      grid.insertBefore(input, btnAgregar);
      grid.insertBefore(label, btnAgregar);

      // Cerrar el modal
      cerrarModalCategoria();

      // Limpiar formulario e icono seleccionado
      form.reset();
      document.getElementById("iconoInput").value = '';
      renderIconos();
    } else {
      alert('Error: ' + data.message);
    }
  })
  .catch(error => {
    alert('Error al guardar categoría: ' + error);
  });
});
*/




/*--------------------------------------------------
-----------SCRIPT para mostrar formularios----------
--------------------------------------------------

function mostrarFormulario(tipo) {
  console.log("Mostrando formulario: ", tipo);  // para debug

  // Ocultar todos los formularios y el dashboard
  document.querySelectorAll("#dashboard-principal, #form-movimiento, #form-prestamo, #form-deuda")
    .forEach(el => el.classList.remove("mostrar"));

  // Mostrar el formulario adecuado
  switch (tipo) {
    case "ingreso":
    case "gasto":
      document.getElementById("form-movimiento").classList.add("mostrar");
      document.getElementById("tipo").value = tipo;
      break;
    case "prestamo":
      document.getElementById("form-prestamo").classList.add("mostrar");
      break;
    case "deuda":
      document.getElementById("form-deuda").classList.add("mostrar");
      break;
    default:
      console.warn("Tipo de formulario no reconocido:", tipo);
      break;
  }
}

function volverAlInicio() {
  // Ocultar todos los formularios
  document.querySelectorAll("#form-movimiento, #form-prestamo, #form-deuda")
    .forEach(el => el.classList.remove("mostrar"));

  // Mostrar el dashboard principal
  document.getElementById("dashboard-principal").classList.add("mostrar");
}

// Mostrar solo el dashboard al cargar
document.addEventListener("DOMContentLoaded", function () {
  volverAlInicio();
});*/


/*-------------------------------------->
<!----------Asistente de voz------------>
<!--------------------------------------

  // Conversión de texto a número más robusta
  function textoANumero(texto) {
    texto = texto.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, ""); // quitar tildes
    texto = texto.replace(/pesos?/g, "").trim();

    const palabras = {
        'cero': 0, 'uno': 1, 'una': 1, 'dos': 2, 'tres': 3, 'cuatro': 4, 'cinco': 5,
        'seis': 6, 'siete': 7, 'ocho': 8, 'nueve': 9, 'diez': 10,
        'once': 11, 'doce': 12, 'trece': 13, 'catorce': 14, 'quince': 15,
        'veinte': 20, 'treinta': 30, 'cuarenta': 40, 'cincuenta': 50,
        'sesenta': 60, 'setenta': 70, 'ochenta': 80, 'noventa': 90,
        'cien': 100, 'ciento': 100, 'doscientos': 200, 'trescientos': 300,
        'cuatrocientos': 400, 'quinientos': 500, 'seiscientos': 600,
        'setecientos': 700, 'ochocientos': 800, 'novecientos': 900,
        'mil': 1000, 'millon': 1000000, 'millones': 1000000
    };

    const tokens = texto.split(/[\s-]+/);

    let total = 0;
    let parcial = 0;

    for (let token of tokens) {
        if (palabras[token] !== undefined) {
        let valor = palabras[token];

        if (valor === 100) {
            // Si parcial es 0, asumimos "cien" solo = 100
            parcial = (parcial === 0 ? 1 : parcial) * valor;
        } else if (valor === 1000 || valor === 1000000) {
            parcial = (parcial === 0 ? 1 : parcial) * valor;
            total += parcial;
            parcial = 0;
        } else {
            parcial += valor;
        }
        } else if (!isNaN(token)) {
        // Si token es número directo, parseamos y sumamos directo a total
        total += parseInt(token);
        }
    }

    return total + parcial;
    }

    // Función para extraer número en dígitos (considera puntos o espacios como separadores)
    function extraerNumero(texto) {
    // Eliminar puntos y comas como separadores de miles
    const limpio = texto.replace(/[.,]/g, '');
    const match = limpio.match(/\d+/);
    return match ? match[0] : null;
    }



  // Reconocimiento de voz
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const reconocimiento = SpeechRecognition ? new SpeechRecognition() : null;

  if (reconocimiento) {
    reconocimiento.lang = 'es-ES';
    reconocimiento.continuous = false;

    function iniciarReconocimientoVoz() {
      reconocimiento.start();
    }

    reconocimiento.onresult = function(event) {
      const texto = event.results[0][0].transcript;
      document.getElementById('textoReconocido').value = texto;
      procesarEntradaUsuario(texto);
    };
  } else {
    console.warn("Tu navegador no soporta reconocimiento de voz.");
  }

  function procesarEntradaUsuario(texto) {
    const hoy = new Date();
    const ayer = new Date(hoy);
    ayer.setDate(hoy.getDate() - 1);

    texto = texto.toLowerCase();
    let tipo = "";
    let fecha = "";
    let descripcion = "";
    let valor = "";
    let persona = "";

    // --- Fecha ---
    if (texto.includes("ayer")) {
        fecha = ayer.toISOString().split("T")[0];
    } else if (texto.includes("hoy")) {
        fecha = hoy.toISOString().split("T")[0];
    } else if (texto.match(/el (\d+|primero) de este mes/)) {
        const diaMatch = texto.match(/el (\d+|primero) de este mes/)[1];
        const dia = (diaMatch === "primero") ? 1 : parseInt(diaMatch);
        const mes = hoy.getMonth() + 1;
        const year = hoy.getFullYear();
        fecha = `${year}-${String(mes).padStart(2, '0')}-${String(dia).padStart(2, '0')}`;
    } else {
        fecha = hoy.toISOString().split("T")[0]; // por defecto
    }

    // --- Tipo y descripción ---
    if (/(me pagaron|me llegó|recibí|me depositaron)/.test(texto)) {
        tipo = "ingreso";
        descripcion = "Ingreso recibido";
    } else if (/(compré|gasté|pagué|invertí|adquirí)/.test(texto)) {
        tipo = "gasto";
        const partes = texto.split(/compré|gasté|pagué|invertí|adquirí/);
        descripcion = partes[1]?.trim() || "Gasto";
    } else if (/(presté|le presté|me pidió prestado|le di prestado|me prestó)/.test(texto)) {
        tipo = "prestamo";

        // Buscar nombre antes de "me prestó" o con "a" o "para"
        let matchPersona = texto.match(/([a-záéíóúñ]+)\s+me prest[oó]/i);
        if (!matchPersona) {
        matchPersona = texto.match(/(?:a|para)\s+([a-záéíóúñ\s]+)/i);
        }
        persona = matchPersona ? matchPersona[1].trim() : "Sin nombre";

        descripcion = "Préstamo";
    } else if (/(tarjeta de crédito|debo|me endeudé|saqué fiado)/.test(texto)) {
        tipo = "deuda";
        descripcion = "Deuda generada";
        const matchPersona = texto.match(/con\s+([a-záéíóúñ\s]+)/i);
        persona = matchPersona ? matchPersona[1].trim() : "Tarjeta";
    }

    // --- Valor ---
    // Limpiar signos $ y puntuación para detectar números correctamente
    const textoLimpio = texto.replace(/[$.,]/g, '');
    const matchNumero = textoLimpio.match(/\d{3,}/);

    if (matchNumero) {
        valor = Number(matchNumero[0]);
    } else {
        valor = textoANumero(texto);
    }

    // --- Mostrar formulario según tipo ---
    if (tipo) mostrarFormulario(tipo);

    // --- Llenar campos en formulario ---
    setTimeout(() => {
        if (tipo === "ingreso" || tipo === "gasto") {
        document.getElementById('tipo').value = tipo;
        document.getElementById('fecha-mov').value = fecha;
        document.getElementById('descripcion-mov').value = descripcion;
        document.getElementById('valor-mov').value = valor;
        } else if (tipo === "prestamo") {
        document.getElementById('fecha-prestamo').value = fecha;
        document.getElementById('persona-prestamo').value = persona || "Sin nombre";
        document.getElementById('descripcion-prestamo').value = descripcion;
        document.getElementById('valor-prestamo').value = valor;
        } else if (tipo === "deuda") {
        document.getElementById('fecha-deuda').value = fecha;
        document.getElementById('persona-deuda').value = persona || "Tarjeta";
        document.getElementById('descripcion-deuda').value = descripcion;
        document.getElementById('valor-deuda').value = valor;
        }
    }, 500);
    }


  function mostrarFormulario(tipo) {
    document.getElementById("form-movimiento").style.display = "none";
    document.getElementById("form-prestamo").style.display = "none";
    document.getElementById("form-deuda").style.display = "none";

    if (tipo === "ingreso" || tipo === "gasto") {
      document.getElementById("form-movimiento").style.display = "block";
    } else if (tipo === "prestamo") {
      document.getElementById("form-prestamo").style.display = "block";
    } else if (tipo === "deuda") {
      document.getElementById("form-deuda").style.display = "block";
    }
  }



/*-------------------------------------->
<!----------btn de voz------------>
<!--------------------------------------


        const btnVoz = document.getElementById('btn-voz');
        const burbujaInput = document.getElementById('burbuja-input');
        const textoReconocido = document.getElementById('textoReconocido');

        let reconociendo = false;

        function toggleReconocimientoVoz() {
        if (!reconociendo) {
            iniciarReconocimientoVoz();
        } else {
            detenerReconocimientoVoz();
        }
        }

        function iniciarReconocimientoVoz() {
        if (!reconocimiento) {
            alert('Reconocimiento de voz no soportado en este navegador.');
            return;
        }

        reconocimiento.lang = 'es-ES';
        reconocimiento.continuous = true; // Para reconocer mientras hablas
        reconocimiento.interimResults = true; // Para obtener resultados parciales en tiempo real

        reconocimiento.start();
        reconociendo = true;
        btnVoz.classList.add('hablando');
        burbujaInput.classList.remove('oculto');
        textoReconocido.value = "";
        }

        function detenerReconocimientoVoz() {
        if (reconocimiento) {
            reconocimiento.stop();
        }
        reconociendo = false;
        btnVoz.classList.remove('hablando');
        setTimeout(() => {
            burbujaInput.classList.add('oculto');
        }, 500);
        }

        if (reconocimiento) {
        reconocimiento.onresult = (event) => {
            let interimTranscript = '';
            let finalTranscript = '';

            for (let i = event.resultIndex; i < event.results.length; ++i) {
            if (event.results[i].isFinal) {
                finalTranscript += event.results[i][0].transcript;
            } else {
                interimTranscript += event.results[i][0].transcript;
            }
            }

            textoReconocido.value = finalTranscript + interimTranscript;
            procesarEntradaUsuario(textoReconocido.value);
        };

        reconocimiento.onend = () => {
            if (reconociendo) {
            // Si se terminó pero seguimos reconociendo, reiniciar para no cortar la escucha
            reconocimiento.start();
            } else {
            detenerReconocimientoVoz();
            }
        };
        }*/


