const chat = document.getElementById('chat');
let primerMensajeEnviado = false;
let autoScrollActivo = true;

// Leer el token CSRF desde el meta tag
const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');

function estaAlFinal() {
  return chat.scrollHeight - chat.scrollTop - chat.clientHeight < 100;
}

function scrollSuaveAlFinal() {
  chat.scrollTo({ top: chat.scrollHeight, behavior: 'smooth' });
}

chat.addEventListener('scroll', () => {
  autoScrollActivo = estaAlFinal();
});

function animarTexto(burbuja, texto) {
  let puntos = 0;
  const maxPuntos = 3;
  burbuja.textContent = 'Escribiendo';
  burbuja.classList.add('animada');

  const animacion = setInterval(() => {
    puntos = (puntos + 1) % (maxPuntos + 1);
    burbuja.textContent = 'Escribiendo' + '.'.repeat(puntos);
  }, 500);

  const procesado = texto
    .split('\n')
    .map(linea => {
      const trimmed = linea.trim();
      if (trimmed.match(/^([A-ZÁÉÍÓÚÜÑ][\w\s]+:)/)) {
        const parts = trimmed.split(':');
        return `<u><strong>${parts[0]}</strong></u>:${parts.slice(1).join(':')}`;
      }
      return trimmed;
    })
    .join('<br>');

  setTimeout(() => {
    clearInterval(animacion);
    burbuja.innerHTML = procesado;
    burbuja.classList.remove('animada');
    if (estaAlFinal()) chat.scrollTop = chat.scrollHeight;
  }, 2000);
}

function agregarMensaje(texto, clase, imagenSrc = null) {
  const mensaje = document.createElement('div');
  mensaje.className = `mensaje ${clase}`;

  const burbuja = document.createElement('div');
  burbuja.className = 'burbuja';

  if (imagenSrc && clase === 'usuario') {
    const img = document.createElement('img');
    img.src = imagenSrc;
    img.className = 'imagen-mensaje';
    mensaje.appendChild(img);
  }

  if (clase === 'asistente') {
    texto = texto.replace(/\*\*/g, '');
    animarTexto(burbuja, texto);
  } else {
    burbuja.textContent = texto;
  }

  mensaje.appendChild(burbuja);
  chat.appendChild(mensaje);
  if (estaAlFinal()) chat.scrollTop = chat.scrollHeight;
}

window.addEventListener('DOMContentLoaded', () => {
  if (typeof NOMBRE_USUARIO !== 'undefined' && NOMBRE_USUARIO) {
    const mensajeBienvenida = `👋 Bienvenido, ${NOMBRE_USUARIO}`;
    agregarMensaje(mensajeBienvenida, 'asistente');
  }
});

document.getElementById('imagen').addEventListener('change', function (event) {
  const imagen = event.target.files[0];
  if (imagen) {
    const reader = new FileReader();
    reader.onload = function (e) {
      const imgPreview = document.getElementById('imagenPrevio');
      imgPreview.src = e.target.result;
      document.getElementById('imagenPrevioContainer').style.display = 'block';
    };
    reader.readAsDataURL(imagen);
  }
});

document.getElementById('formulario1').addEventListener('submit', async function (e) {
  e.preventDefault();

  const consultaInput = document.getElementById('consulta');
  const consulta = consultaInput.value.trim();
  const imagenInput = document.getElementById('imagen');
  const imagen = imagenInput.files[0];

  if (!consulta) {
    alert("❗ Por favor escribe una consulta.");
    return;
  }

  if (!primerMensajeEnviado) {
    const mensajes = document.querySelectorAll('#chat .mensaje.asistente');
    mensajes.forEach(m => {
      if (m.innerText.includes('Bienvenido')) m.remove();
    });
    primerMensajeEnviado = true;
  }

  consultaInput.value = '';
  imagenInput.value = '';
  document.getElementById('imagenPrevioContainer').style.display = 'none';

  if (imagen) {
    const reader = new FileReader();
    reader.onload = async function (e) {
      const imagenSrc = e.target.result;
      agregarMensaje(consulta, 'usuario', imagenSrc);
      await enviarConsulta(consulta, imagen);
    };
    reader.readAsDataURL(imagen);
  } else {
    agregarMensaje(consulta, 'usuario');
    await enviarConsulta(consulta, null);
  }
});

async function enviarConsulta(consulta, imagen) {
  const formData = new FormData();
  formData.append('consulta', consulta);
  if (imagen) formData.append('imagen', imagen);

  try {
    const response = await fetch('/consultar', {
      method: 'POST',
      body: formData,
      headers: {
        'X-CSRFToken': csrfToken  // ✅ Aquí se agrega el token
      }
    });

    if (!response.ok) {
      const texto = await response.text();
      console.error(`❌ Error HTTP ${response.status}:`, texto);
      agregarMensaje(`❌ Error ${response.status}: ${texto}`, 'asistente');
      return;
    }

    const data = await response.json();
    if (data.error) {
      console.error('❌ Gemini error:', data.error);
      agregarMensaje(data.mensaje || '❌ Error en la respuesta del asistente.', 'asistente');
      return;
    }
    agregarMensaje(data.mensaje || 'Sin respuesta.', 'asistente');
  } catch (error) {
    console.error('❌ Error al enviar la consulta:', error);
    agregarMensaje('❌ Error al procesar la consulta.', 'asistente');
  }
}
