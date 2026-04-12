// ══ Sidebar toggle ══
function toggleSidebar() {
    const MOBILE = window.innerWidth <= 768;
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('overlay');

    if (MOBILE) {
        const isOpen = sidebar.classList.toggle('activo');
        overlay.classList.toggle('activo', isOpen);
    } else {
        const collapsed = document.body.classList.toggle('sidebar-collapsed');
        localStorage.setItem('oryon_sidebar_collapsed', collapsed ? '1' : '0');
    }
}

function closeMobileSidebar() {
    document.getElementById('sidebar').classList.remove('activo');
    document.getElementById('overlay').classList.remove('activo');
}

// Restaurar estado al cargar
(function () {
    if (window.innerWidth > 768 && localStorage.getItem('oryon_sidebar_collapsed') === '1') {
        document.body.classList.add('sidebar-collapsed');
    }
})();

// ══ Notificaciones ══
function toggleNotificaciones() {
    const lista = document.getElementById('lista-notificaciones');
    if (lista) lista.classList.toggle('lista-notificaciones-oculta');
}

document.addEventListener('click', function (e) {
    const contenedor = document.querySelector('.notificaciones-contenedor');
    const lista = document.getElementById('lista-notificaciones');
    if (contenedor && lista && !contenedor.contains(e.target)) {
        lista.classList.add('lista-notificaciones-oculta');
    }
});