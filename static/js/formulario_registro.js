/* ══════════════════════════════════════
   formulario_registro.js — ORYON
══════════════════════════════════════ */

/* ── Mostrar/ocultar campos según tipo ── */
function actualizarCampos() {
    const tipo            = document.getElementById('tipo').value;
    const campoPersona    = document.getElementById('persona-container');
    const campoCategoria  = document.getElementById('categoria-container');
    const personaInput    = document.getElementById('persona');
    const categoriaSelect = document.getElementById('categoria');
    const labelPersona    = campoPersona ? campoPersona.querySelector('label') : null;

    /* Persona: solo para deuda/préstamo */
    if (tipo === 'deuda') {
        campoPersona.classList.add('visible');
        if (labelPersona) labelPersona.textContent = '¿A quién le debes?';
    } else if (tipo === 'prestamo') {
        campoPersona.classList.add('visible');
        if (labelPersona) labelPersona.textContent = '¿A quién le prestaste?';
    } else {
        campoPersona.classList.remove('visible');
        if (personaInput) personaInput.value = '';
    }

    /* Categoría: solo para ingreso/gasto */
    if (tipo === 'ingreso' || tipo === 'gasto') {
        campoCategoria.style.display = 'block';
    } else {
        campoCategoria.style.display = 'none';
        if (categoriaSelect) categoriaSelect.selectedIndex = 0;
    }
}

window.addEventListener('load', actualizarCampos);

const tipoSelect = document.getElementById('tipo');
if (tipoSelect) tipoSelect.addEventListener('change', actualizarCampos);

/* ── Modal Crear Categoría ── */
function abrirModalCategoria() {
    const modal = document.getElementById('modalCategoria');
    if (modal) modal.classList.add('show');
}

function cerrarModalCategoria() {
    const modal = document.getElementById('modalCategoria');
    if (modal) modal.classList.remove('show');
}

/* Cerrar al click fuera */
window.addEventListener('click', function (e) {
    const modal = document.getElementById('modalCategoria');
    if (modal && e.target === modal) cerrarModalCategoria();
});

/* ── Submit AJAX del form de categoría ── */
const formCategoria = document.getElementById('formCrearCategoria');
if (formCategoria) {
    formCategoria.addEventListener('submit', function (e) {
        e.preventDefault();

        const form     = e.target;
        const formData = new FormData(form);

        fetch(form.action, {
            method: 'POST',
            body: formData
        })
        .then(res => res.json())
        .then(data => {
            if (data.id) {
                /* Agregar nueva opción al select */
                const select = document.getElementById('categoria');
                if (select) {
                    const option = document.createElement('option');
                    option.value    = data.id;
                    option.textContent = data.nombre;
                    option.selected = true;
                    select.appendChild(option);
                }

                cerrarModalCategoria();
                form.reset();
            } else {
                alert('Error al agregar categoría.');
            }
        })
        .catch(err => {
            console.error(err);
            alert('Ocurrió un error al guardar la categoría.');
        });
    });
}