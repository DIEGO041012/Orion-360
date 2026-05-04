(function () {
    'use strict';

    function parseChartData() {
        const el = document.getElementById('panelUsuarioData');
        if (!el) return null;
        try {
            return JSON.parse(el.textContent.trim() || '{}');
        } catch (error) {
            console.error('Panel Usuario: error parsing chart data', error);
            return null;
        }
    }

    function initCharts(chartData) {
        if (!chartData) return;

        const incomeExpenseCtx = document.getElementById('incomeExpenseChart');
        if (incomeExpenseCtx) {
            new Chart(incomeExpenseCtx, {
                type: 'bar',
                data: {
                    labels: chartData.incomeExpense.labels,
                    datasets: [
                        { label: 'Ingresos', data: chartData.incomeExpense.ingresos, borderWidth: 1 },
                        { label: 'Gastos',   data: chartData.incomeExpense.gastos,   borderWidth: 1 }
                    ]
                },
                options: { responsive: true, maintainAspectRatio: false }
            });
        }

        const categoryBarCtx = document.getElementById('categoryBarChart');
        if (categoryBarCtx) {
            new Chart(categoryBarCtx, {
                type: 'bar',
                data: {
                    labels: chartData.categoryExpense.labels,
                    datasets: [{ label: 'Gastos', data: chartData.categoryExpense.values, borderWidth: 1 }]
                },
                options: {
                    indexAxis: 'y',
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { ticks: { color: '#aaa' } },
                        y: { ticks: { color: '#aaa' } }
                    }
                }
            });
        }

        const balanceTrendCtx = document.getElementById('balanceTrendChart');
        if (balanceTrendCtx) {
            new Chart(balanceTrendCtx, {
                type: 'line',
                data: {
                    labels: chartData.balanceTrend.labels,
                    datasets: [{ label: 'Saldo', data: chartData.balanceTrend.values, tension: 0.35, fill: false, borderWidth: 2 }]
                },
                options: { responsive: true, maintainAspectRatio: false }
            });
        }

        const taskStatusCtx = document.getElementById('taskStatusChart');
        if (taskStatusCtx) {
            new Chart(taskStatusCtx, {
                type: 'doughnut',
                data: {
                    labels: chartData.taskStatus.labels,
                    datasets: [{ data: chartData.taskStatus.values, borderWidth: 1 }]
                },
                options: { responsive: true, maintainAspectRatio: false }
            });
        }

        const debtLoanCtx = document.getElementById('debtLoanChart');
        if (debtLoanCtx) {
            new Chart(debtLoanCtx, {
                type: 'bar',
                data: {
                    labels: chartData.debtLoan.labels,
                    datasets: [{ label: 'Monto', data: chartData.debtLoan.values, borderWidth: 1 }]
                },
                options: { responsive: true, maintainAspectRatio: false }
            });
        }
    }

    function initVoiceAssistant() {
        const csrf  = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
        const btn   = document.getElementById('orionVoiceBtn');
        const icon  = document.getElementById('orionBtnIcon');
        const label = document.getElementById('orionStatusLabel');
        const bars  = document.getElementById('orionBars');
        if (!btn || !icon || !label || !bars) return;

        let rec = null;
        const EST = {
            reposo:     { ico: 'fa-robot',               txt: 'Habla con ORION',                     bars: false, color: ''           },
            escuchando: { ico: 'fa-microphone',           txt: '🎙 Escuchando — presiona para enviar', bars: true,  color: 'escuchando' },
            pensando:   { ico: 'fa-circle-notch fa-spin', txt: 'Pensando...',                         bars: false, color: ''           },
            hablando:   { ico: 'fa-volume-high',          txt: 'ORION está hablando',                 bars: true,  color: 'hablando'   }
        };

        function setEstado(e) {
            const c = EST[e] || EST.reposo;
            btn.className     = `orion-voice-btn ${e}`;
            icon.className    = `fa-solid ${c.ico}`;
            label.textContent = c.txt;
            bars.className    = c.bars ? `orion-bars visible ${c.color}` : 'orion-bars';
        }

        function elegirVoz() {
            const voces = window.speechSynthesis.getVoices();
            if (!voces.length) return null;
            const orden = [
                v => /google.*español|google.*es[-_]/i.test(v.name),
                v => /microsoft.*es[-_]/i.test(v.name),
                v => v.lang === 'es-CO',
                v => v.lang === 'es-ES',
                v => v.lang === 'es-US',
                v => v.lang.startsWith('es'),
            ];
            for (const fn of orden) {
                const voz = voces.find(fn);
                if (voz) return voz;
            }
            return voces[0];
        }

        function hablar(texto) {
            if (!window.speechSynthesis) { setEstado('reposo'); return; }
            const limpio = texto
                .replace(/\*\*/g, '').replace(/\*/g, '')
                .replace(/#+ /g, '').replace(/\n/g, '. ').trim();
            if (!limpio) { setEstado('reposo'); return; }

            window.speechSynthesis.cancel();
            setTimeout(() => {
                const utt = new SpeechSynthesisUtterance(limpio);
                utt.rate   = 1.0;
                utt.pitch  = 1.0;
                utt.volume = 1.0;

                const voz = elegirVoz();
                if (voz) { utt.voice = voz; utt.lang = voz.lang; }
                else     { utt.lang  = 'es-ES'; }

                setEstado('hablando');
                const kv = setInterval(() => {
                    if (!window.speechSynthesis.speaking) { clearInterval(kv); return; }
                    window.speechSynthesis.pause();
                    window.speechSynthesis.resume();
                }, 10000);

                utt.onend   = () => { clearInterval(kv); setEstado('reposo'); };
                utt.onerror = (e) => { console.warn('TTS:', e); clearInterval(kv); setEstado('reposo'); };
                window.speechSynthesis.speak(utt);
            }, 150);
        }

        function crearRec() {
            const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
            if (!SR) return null;

            const r = new SR();
            r.lang            = 'es-CO';
            r.continuous      = true;
            r.interimResults  = true;
            r.maxAlternatives = 1;

            let final = '';
            r.onstart = () => { final = ''; setEstado('escuchando'); };
            r.onresult = (e) => {
                for (let i = e.resultIndex; i < e.results.length; i++) {
                    if (e.results[i].isFinal) final += e.results[i][0].transcript + ' ';
                }
                const v = final.trim();
                label.textContent = v.length > 48
                    ? '…' + v.slice(-48)
                    : (v || '🎙 Escuchando — presiona para enviar');
            };
            r.onerror = (e) => { if (e.error !== 'no-speech') setEstado('reposo'); };
            r.onend = () => { if (btn.classList.contains('escuchando')) setEstado('reposo'); };
            r._get = () => final.trim();
            return r;
        }

        btn.addEventListener('click', async () => {
            if (btn.classList.contains('hablando')) {
                window.speechSynthesis?.cancel();
                setEstado('reposo');
                return;
            }
            if (btn.classList.contains('pensando')) return;
            if (btn.classList.contains('escuchando')) {
                const texto = rec?._get() || '';
                try { rec?.stop(); } catch (_) {}
                rec = null;
                if (!texto) {
                    label.textContent = 'No capturé nada, intenta de nuevo';
                    setTimeout(() => setEstado('reposo'), 1800);
                    return;
                }
                setEstado('pensando');
                try {
                    const fd = new FormData();
                    fd.append('consulta', texto);
                    const resp = await fetch('/consultar', {
                        method: 'POST',
                        body: fd,
                        headers: { 'X-CSRFToken': csrf },
                        credentials: 'same-origin'
                    });
                    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                    const data = await resp.json();
                    hablar(data.mensaje || 'No obtuve respuesta.');
                } catch (err) {
                    console.error('ORION:', err);
                    hablar('Hubo un error al conectar con ORION. Intenta de nuevo.');
                }
                return;
            }
            rec = crearRec();
            if (!rec) {
                label.textContent = 'Voz no disponible en este navegador';
                btn.style.opacity = '0.4';
                btn.style.cursor = 'not-allowed';
                return;
            }
            try { rec.start(); } catch (e) { console.error('Rec start:', e); setEstado('reposo'); }
        });

        if (window.speechSynthesis) {
            window.speechSynthesis.getVoices();
            window.speechSynthesis.onvoiceschanged = () => window.speechSynthesis.getVoices();
        }
        if (!window.SpeechRecognition && !window.webkitSpeechRecognition) {
            label.textContent = 'Voz no disponible';
            btn.style.opacity = '0.4';
            btn.style.cursor  = 'not-allowed';
        }
    }

    function initPanelUsuario() {
        const chartData = parseChartData();
        initCharts(chartData);
        initVoiceAssistant();
    }

    document.addEventListener('DOMContentLoaded', initPanelUsuario);
})();
