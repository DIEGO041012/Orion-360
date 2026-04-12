/* ══════════════════════════════════════
   registros.js — ORYON
══════════════════════════════════════ */

document.addEventListener("DOMContentLoaded", () => {

    /* ── Tabs de sección ── */
    const secciones = {
        ingresos:  document.getElementById("seccionIngresos"),
        deudas:    document.getElementById("seccionDeudas"),
        prestamos: document.getElementById("seccionPrestamos"),
    };

    const botones = {
        ingresos:  document.getElementById("btnIngresos"),
        deudas:    document.getElementById("btnDeudas"),
        prestamos: document.getElementById("btnPrestamos"),
    };

    window.cambiarSeccion = function (nombre) {
        Object.values(secciones).forEach(s => s && s.classList.remove("activa"));
        Object.values(botones).forEach(b => b && b.classList.remove("activo"));

        if (secciones[nombre]) secciones[nombre].classList.add("activa");
        if (botones[nombre])   botones[nombre].classList.add("activo");

        const inputSeccion = document.querySelector('input[name="seccion"]');
        if (inputSeccion) inputSeccion.value = nombre;

        const params = new URLSearchParams(window.location.search);
        params.set("seccion", nombre);
        window.history.replaceState({}, '', `${window.location.pathname}?${params}`);
    };

    /* ── Modal Abono Préstamo ── */
    window.abrirModalAbono = function (id, saldo) {
        document.getElementById('abonoPrestamoId').value = id;
        document.getElementById('saldoPendienteModal').textContent = parseFloat(saldo).toFixed(2);
        document.getElementById('modalAbono').classList.add('open');
    };

    window.cerrarModalAbono = function () {
        document.getElementById('modalAbono').classList.remove('open');
    };

    /* ── Modal Abono Deuda ── */
    window.abrirModalAbonoDeuda = function (id, saldo) {
        document.getElementById('abonoDeudaId').value = id;
        document.getElementById('saldoPendienteDeudaModal').textContent = parseFloat(saldo).toFixed(2);
        document.getElementById('modalAbonoDeuda').classList.add('open');
    };

    window.cerrarModalAbonoDeuda = function () {
        document.getElementById('modalAbonoDeuda').classList.remove('open');
    };

    /* Cerrar modales abono al click fuera */
    ['modalAbono', 'modalAbonoDeuda'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('click', function (e) {
                if (e.target === this) this.classList.remove('open');
            });
        }
    });

    /* ── Modal Detalles ── */
    window.cerrarModalDetalles = function () {
        const modal   = document.getElementById('modal-detalles');
        const overlay = document.getElementById('overlay-detalles');
        if (modal)   modal.style.display = 'none';
        if (overlay) overlay.classList.remove('show');
    };

    document.querySelectorAll('.fila-modal-detalles').forEach(fila => {
        fila.addEventListener('click', () => {
            const modal      = document.getElementById('modal-detalles');
            const overlay    = document.getElementById('overlay-detalles');
            const contenedor = document.getElementById('modal-detalles-contenido-info');
            const divBotones = document.getElementById('modal-detalles-certificado');

            if (!modal || !contenedor) return;

            contenedor.innerHTML = '';
            divBotones.innerHTML = '';

            /* Mostrar atributos data-* como filas */
            for (const attr of fila.attributes) {
                if (attr.name.startsWith('data-') && attr.value.trim() !== '') {
                    let label = attr.name.replace('data-', '').replace(/_/g, ' ');
                    label = label.charAt(0).toUpperCase() + label.slice(1);
                    const p = document.createElement('p');
                    p.style.cssText = 'font-size:13px;color:var(--text-secondary);margin:4px 0';
                    p.innerHTML = `<strong style="color:var(--text-primary)">${label}:</strong> ${attr.value}`;
                    contenedor.appendChild(p);
                }
            }

            /* Botón certificado para préstamos */
            const tipo         = fila.getAttribute('data-tipo');
            const saldo        = parseFloat(fila.getAttribute('data-saldo') || 0);
            const idMovimiento = fila.getAttribute('data-id');

            if ((tipo === 'prestamo') && idMovimiento) {
                const btn = document.createElement('button');
                btn.textContent = saldo <= 0 ? 'Generar Paz y Salvo' : 'Generar Certificado';
                btn.style.cssText = 'padding:8px 16px;background:var(--accent);color:var(--accent-text);border:none;border-radius:var(--radius-md);font-size:13px;font-weight:500;cursor:pointer;margin-top:8px';
                btn.onclick = () => window.open(`/certificado_prestamo/${idMovimiento}`, '_blank');
                divBotones.appendChild(btn);
            }

            modal.style.display = 'block';
            if (overlay) overlay.classList.add('show');
        });
    });

    /* Cerrar detalles al click en overlay */
    const overlayDetalles = document.getElementById('overlay-detalles');
    if (overlayDetalles) {
        overlayDetalles.addEventListener('click', e => {
            if (e.target === overlayDetalles) cerrarModalDetalles();
        });
    }

    /* ── Modal Impresión ── */
    window.abrirModalImpresion = function (seccion) {
        document.getElementById('seccionFiltro').value = seccion;

        const tipoDiv   = document.getElementById('label-tipo');
        const estadoDiv = document.getElementById('label-estado');

        if (seccion === 'ingresos') {
            tipoDiv.style.display   = 'block';
            estadoDiv.style.display = 'none';
        } else {
            tipoDiv.style.display   = 'none';
            estadoDiv.style.display = 'block';
        }

        document.getElementById('modalImpresion').style.display = 'flex';
    };

    window.cerrarModalImpresion = function () {
        document.getElementById('modalImpresion').style.display = 'none';
    };

    /* Enviar filtros al PDF */
    const formImpresion = document.getElementById('formularioFiltroImpresion');
    if (formImpresion) {
        formImpresion.addEventListener('submit', function (e) {
            e.preventDefault();
            const params = new URLSearchParams(new FormData(e.target)).toString();
            document.getElementById('iframeImpresion').src = `/exportar_pdf?${params}`;
        });
    }
});

/* Imprimir desde iframe cuando cargue el PDF */
function imprimirDesdeIframe() {
    const iframe = document.getElementById('iframeImpresion');
    if (iframe && iframe.contentWindow) {
        try {
            iframe.contentWindow.focus();
            iframe.contentWindow.print();
        } catch (e) {
            /* El PDF se descarga directamente, no necesita print() */
        }
    }
}