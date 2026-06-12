// CONFIGURATION
const API_URLS = {
    siakad: {
        status: '/siakad/status',
        students: '/siakad/students',
        register: (id) => `/siakad/students/${id}/register`,
        classes: '/siakad/classes',
        enroll: (id) => `/siakad/students/${id}/enroll`
    },
    keuangan: {
        status: '/finance/status',
        bills: '/finance/bills-json',
        createBill: '/finance/bills',
        payBill: (id) => `/finance/bills/${id}/pay`
    },
    library: {
        status: '/library/', // Root health check
        checkStatus: (id) => `/library/status/${id}`,
        borrow: '/library/borrow',
        loans: (id) => `/library/loans/${id}`
    },
    attendance: {
        status: '/attendance/', // Root health check
        record: '/attendance/record',
        recap: (id) => `/attendance/recap/${id}`,
        classes: '/attendance/classes',
        classStudents: (classId) => `/attendance/classes/${classId}/students`
    }
};

// State variables
let studentsList = [];
let billsList = [];
let selectedStudentId = "";
let healthInterval = null;
let dataInterval = null;
let classAttendanceHistory = [];

// DOM ELEMS & EVENT LISTENERS
document.addEventListener("DOMContentLoaded", () => {
    initNavigation();
    initForms();
    initRefreshes();
    initHealthToggler();
    
    // Start periodic health check and stats loading
    runHealthCheck();
    loadDashboardData();
    
    healthInterval = setInterval(runHealthCheck, 5000);
    dataInterval = setInterval(loadDashboardData, 8000);
});

// NAVIGATION LOGIC
function initNavigation() {
    const navItems = document.querySelectorAll(".nav-item");
    const tabPanes = document.querySelectorAll(".tab-pane");

    navItems.forEach(item => {
        item.addEventListener("click", (e) => {
            e.preventDefault();
            const tabId = item.getAttribute("data-tab");

            // Update active sidebar item
            navItems.forEach(nav => nav.classList.remove("active"));
            item.classList.add("active");

            // Update visible tab pane
            tabPanes.forEach(pane => pane.classList.remove("active"));
            document.getElementById(`tab-${tabId}`).classList.add("active");
            
            // Trigger specific load for tabs
            if (tabId === 'siakad') {
                loadStudents();
                loadEnrollmentPanel();
            }
            if (tabId === 'keuangan') loadBills();
            if (tabId === 'attendance') {
                loadAttendanceClasses();
                const dateInput = document.getElementById("att-date-input");
                if (dateInput && !dateInput.value) {
                    dateInput.value = new Date().toISOString().split('T')[0];
                }
            }
        });
    });
    
    // Sub tabs inside Attendance Tab
    const subTabBtns = document.querySelectorAll(".tab-sub-btn");
    const subTabPanels = document.querySelectorAll(".sub-tab-panel");
    
    subTabBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            const subTabId = btn.getAttribute("data-sub");
            subTabBtns.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            
            subTabPanels.forEach(p => p.classList.remove("active"));
            document.getElementById(`${subTabId}-view`).classList.add("active");
        });
    });
}

// HEALTH TOGGLER LOGIC
function initHealthToggler() {
    const toggleBtn = document.getElementById("toggle-health-btn");
    const healthSummary = document.querySelector(".health-summary");
    
    if (toggleBtn && healthSummary) {
        toggleBtn.addEventListener("click", (e) => {
            e.preventDefault();
            const isVisible = healthSummary.classList.toggle("visible");
            toggleBtn.classList.toggle("active", isVisible);
            
            if (isVisible) {
                toggleBtn.setAttribute("title", "Sembunyikan Status Layanan");
            } else {
                toggleBtn.setAttribute("title", "Tampilkan Status Layanan");
            }
        });
    }
}

// ALERT DISPLAY SYSTEM
function showAlert(message, type = 'success') {
    const container = document.getElementById("alert-container");
    const alertDiv = document.createElement("div");
    alertDiv.className = `alert alert-${type}`;
    
    alertDiv.innerHTML = `
        <span>${message}</span>
        <button class="alert-close">&times;</button>
    `;
    
    // Close event
    alertDiv.querySelector(".alert-close").addEventListener("click", () => {
        alertDiv.remove();
    });
    
    container.appendChild(alertDiv);
    
    // Auto remove after 5 seconds
    setTimeout(() => {
        if (alertDiv.parentNode) {
            alertDiv.remove();
        }
    }, 5000);
}

// SYSTEM HEALTH MONITORS
async function runHealthCheck() {
    // 1. SIAKAD Status
    try {
        const res = await fetch(API_URLS.siakad.status);
        const data = await res.json();
        updateHealthIndicator('siakad', data.status === 'online', 'Online');
    } catch (e) {
        updateHealthIndicator('siakad', false, 'Offline');
    }

    // 2. Keuangan Status
    try {
        const res = await fetch(API_URLS.keuangan.status);
        const data = await res.json();
        updateHealthIndicator('keuangan', data.status === 'online', 'Online');
    } catch (e) {
        updateHealthIndicator('keuangan', false, 'Offline');
    }

    // 3. Perpustakaan Status
    try {
        const res = await fetch(API_URLS.library.checkStatus('health'));
        const data = await res.json();
        const isOnline = data && data.hasOwnProperty('is_active');
        updateHealthIndicator('library', isOnline, isOnline ? 'Online' : 'Error');
    } catch (e) {
        updateHealthIndicator('library', false, 'Offline');
    }

    // 4. Presensi Status
    try {
        const res = await fetch(API_URLS.attendance.recap('health'));
        const xmlText = await res.text();
        const parser = new DOMParser();
        const xmlDoc = parser.parseFromString(xmlText, "text/xml");
        const studentIdText = xmlDoc.getElementsByTagName("student_id")[0]?.textContent;
        const isOnline = studentIdText === 'health';
        updateHealthIndicator('attendance', isOnline, isOnline ? 'Online' : 'Error');
    } catch (e) {
        updateHealthIndicator('attendance', false, 'Offline');
    }
}

function updateHealthIndicator(service, isOnline, text) {
    const card = document.getElementById(`health-${service}`);
    const dot = card.querySelector(".indicator");
    const statusText = card.querySelector(".service-status");
    
    if (isOnline) {
        dot.className = "indicator dot-online";
        statusText.innerText = text;
        statusText.style.color = "var(--success)";
    } else {
        dot.className = "indicator dot-offline";
        statusText.innerText = text;
        statusText.style.color = "var(--danger)";
    }
}

// FORMS SUBMISSION HANDLERS
function initForms() {
    // Add Student Form (SIAKAD)
    const formAddStudent = document.getElementById("form-add-student");
    formAddStudent.addEventListener("submit", async (e) => {
        e.preventDefault();
        const payload = {
            student_id: document.getElementById("student-id").value.trim(),
            name: document.getElementById("student-name").value.trim(),
            email: document.getElementById("student-email").value.trim(),
            semester: parseInt(document.getElementById("student-semester").value)
        };
        
        try {
            const res = await fetch('/siakad/students', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            
            if (res.status === 201) {
                showAlert(`Mahasiswa "${payload.name}" berhasil didaftarkan di SIAKAD!`);
                formAddStudent.reset();
                loadStudents();
                loadDashboardData();
            } else {
                const err = await res.json();
                showAlert(`Gagal: ${err.detail || 'Terjadi kesalahan'}`, 'error');
            }
        } catch (e) {
            showAlert(`Koneksi Gagal: ${e.message}`, 'error');
        }
    });

    // Create Bill Form (Keuangan)
    const formCreateBill = document.getElementById("form-create-bill");
    formCreateBill.addEventListener("submit", async (e) => {
        e.preventDefault();
        const payload = {
            bill_id: document.getElementById("bill-id").value.trim(),
            student_id: document.getElementById("bill-student-id").value.trim(),
            amount: parseFloat(document.getElementById("bill-amount").value),
            semester: parseInt(document.getElementById("bill-semester").value)
        };
        
        try {
            const res = await fetch('/finance/bills', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            
            if (res.status === 201) {
                showAlert(`Tagihan "${payload.bill_id}" diterbitkan untuk NIM ${payload.student_id}!`);
                formCreateBill.reset();
                loadBills();
                loadDashboardData();
            } else {
                const err = await res.json();
                showAlert(`Gagal: ${err.detail || 'Terjadi kesalahan'}`, 'error');
            }
        } catch (e) {
            showAlert(`Koneksi Gagal: ${e.message}`, 'error');
        }
    });

    // Borrow Book Form (Library)
    const formBorrowBook = document.getElementById("form-borrow-book");
    formBorrowBook.addEventListener("submit", async (e) => {
        e.preventDefault();
        const payload = {
            student_id: document.getElementById("borrow-nim").value.trim(),
            book_id: document.getElementById("borrow-book-id").value.trim(),
            book_title: document.getElementById("borrow-book-title").value.trim()
        };
        
        try {
            const res = await fetch(API_URLS.library.borrow, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            
            if (res.status === 200) {
                showAlert(`Buku "${payload.book_title}" berhasil dipinjam!`);
                formBorrowBook.reset();
                loadLoans(payload.student_id);
            } else {
                const err = await res.json();
                showAlert(`Ditolak: ${err.detail?.message || err.detail || 'Akses ditolak.'}`, 'error');
            }
        } catch (e) {
            showAlert(`Koneksi Gagal: ${e.message}`, 'error');
        }
    });

    // Class Enrollment Form (SIAKAD)
    const formEnrollStudent = document.getElementById("form-enroll-student");
    if (formEnrollStudent) {
        formEnrollStudent.addEventListener("submit", async (e) => {
            e.preventDefault();
            const studentId = document.getElementById("enroll-student-select").value;
            const checkedCbs = document.querySelectorAll(".enroll-class-cb:checked");
            const classIds = Array.from(checkedCbs).map(cb => cb.value);
            
            if (!studentId) {
                showAlert("Silakan pilih mahasiswa terlebih dahulu", "error");
                return;
            }
            
            try {
                const res = await fetch(API_URLS.siakad.enroll(studentId), {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ class_ids: classIds })
                });
                
                if (res.ok) {
                    showAlert("Kelas mahasiswa berhasil didaftarkan di SIAKAD!");
                    formEnrollStudent.reset();
                    loadStudents();
                    loadEnrollmentPanel();
                } else {
                    const err = await res.json();
                    showAlert(`Gagal: ${err.detail || 'Terjadi kesalahan'}`, 'error');
                }
            } catch (e) {
                showAlert(`Koneksi Gagal: ${e.message}`, 'error');
            }
        });
    }

    // Classroom Attendance Listeners
    const classSelect = document.getElementById("att-class-select");
    if (classSelect) {
        classSelect.addEventListener("change", loadClassroomStudents);
    }

    const saveAttendanceBtn = document.getElementById("btn-save-classroom-attendance");
    if (saveAttendanceBtn) {
        saveAttendanceBtn.addEventListener("click", saveClassroomAttendance);
    }

    const historySearch = document.getElementById("att-history-search");
    if (historySearch) {
        historySearch.addEventListener("input", filterClassAttendanceHistory);
    }

    // Access Check Form (Library check status)
    document.getElementById("btn-check-lib").addEventListener("click", checkLibraryAccess);
}

// REFRESH BUTTON LISTENERS
function initRefreshes() {
    document.getElementById("btn-refresh-students").addEventListener("click", loadStudents);
    document.getElementById("btn-refresh-bills").addEventListener("click", loadBills);
    
    document.getElementById("btn-refresh-loans").addEventListener("click", () => {
        const nim = document.getElementById("lib-search-nim").value.trim();
        if (nim) loadLoans(nim);
        else showAlert("Silakan isi NIM mahasiswa terlebih dahulu", "error");
    });
    
    const btnRefreshAttendance = document.getElementById("btn-refresh-attendance");
    if (btnRefreshAttendance) {
        btnRefreshAttendance.addEventListener("click", () => {
            const nim = document.getElementById("att-search-nim").value.trim();
            if (nim) loadAttendance(nim);
            else showAlert("Silakan isi NIM mahasiswa terlebih dahulu", "error");
        });
    }

    // Tracker select student dropdown
    document.getElementById("active-student-select").addEventListener("change", (e) => {
        selectedStudentId = e.target.value;
        updateStepperVisualization();
    });
}

// DATA LOADING FUNCTIONS
async function loadDashboardData() {
    try {
        // Load students
        const resSt = await fetch(API_URLS.siakad.students);
        if (resSt.ok) {
            studentsList = await resSt.json();
            document.getElementById("stats-total-students").innerText = studentsList.length;
            document.getElementById("stats-active-students").innerText = studentsList.filter(s => s.status === 'active').length;
            
            // Sync tracker select dropdown
            syncStudentSelector();
        }
        
        // Load bills
        const resBl = await fetch(API_URLS.keuangan.bills);
        if (resBl.ok) {
            billsList = await resBl.json();
            document.getElementById("stats-total-bills").innerText = billsList.length;
            document.getElementById("stats-paid-bills").innerText = billsList.filter(b => b.status === 'paid').length;
        }
    } catch (e) {
        console.error("Dashboard sync error:", e);
    }
}

function syncStudentSelector() {
    const select = document.getElementById("active-student-select");
    const currentVal = select.value;
    
    // Clear and build options
    select.innerHTML = '<option value="">-- Hubungkan dengan Mahasiswa --</option>';
    studentsList.forEach(s => {
        const option = document.createElement("option");
        option.value = s.student_id;
        option.text = `${s.student_id} - ${s.name} (${s.status.toUpperCase()})`;
        select.appendChild(option);
    });
    
    // Restore value
    if (currentVal && studentsList.some(s => s.student_id === currentVal)) {
        select.value = currentVal;
    }
}

// 1. SIAKAD Load
async function loadStudents() {
    const tbody = document.querySelector("#table-students tbody");
    tbody.innerHTML = `<tr><td colspan="7" class="text-center">Memuat data mahasiswa...</td></tr>`;
    
    try {
        const res = await fetch(API_URLS.siakad.students);
        if (!res.ok) throw new Error("Gagal mengambil data");
        
        studentsList = await res.json();
        tbody.innerHTML = "";
        
        if (studentsList.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center">Belum ada mahasiswa terdaftar.</td></tr>`;
            return;
        }
        
        studentsList.forEach(s => {
            const tr = document.createElement("tr");
            const statusBadgeClass = s.status === 'active' ? 'badge-success' : 'badge-danger';
            const enrolledClasses = s.classes && s.classes.length > 0 ? s.classes.map(c => c.id).join(', ') : '-';
            
            tr.innerHTML = `
                <td><strong>${s.student_id}</strong></td>
                <td>${s.name}</td>
                <td>${s.email}</td>
                <td>${s.semester}</td>
                <td><span style="font-size: 11px; font-weight: 600;">${enrolledClasses}</span></td>
                <td><span class="badge ${statusBadgeClass}">${s.status}</span></td>
                <td>
                    ${s.status === 'inactive' ? 
                        `<button class="btn btn-xs btn-primary" onclick="reRegisterStudent('${s.student_id}')">Re-Daftar</button>` : 
                        `<span class="text-muted">Sudah Aktif</span>`}
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="6" class="text-center text-danger">Gagal mengambil data dari SIAKAD.</td></tr>`;
    }
}

async function reRegisterStudent(nim) {
    try {
        const res = await fetch(API_URLS.siakad.register(nim), { method: 'POST' });
        if (res.ok) {
            showAlert(`Registrasi Ulang sukses untuk NIM ${nim}! Event student.registered dikirim ke RabbitMQ.`);
            loadStudents();
            loadDashboardData();
            
            // Auto update stepper if checking this student
            if (selectedStudentId === nim) {
                updateStepperVisualization();
            }
        } else {
            const err = await res.json();
            showAlert(`Registrasi Gagal: ${err.detail || 'Error'}`, 'error');
        }
    } catch (e) {
        showAlert(`Error: ${e.message}`, 'error');
    }
}

// Expose to window for onclick callback in table
window.reRegisterStudent = reRegisterStudent;

// 2. KEUANGAN Load
async function loadBills() {
    const tbody = document.querySelector("#table-bills tbody");
    tbody.innerHTML = `<tr><td colspan="6" class="text-center">Memuat data tagihan...</td></tr>`;
    
    try {
        const res = await fetch(API_URLS.keuangan.bills);
        if (!res.ok) throw new Error("Gagal mengambil data");
        
        billsList = await res.json();
        tbody.innerHTML = "";
        
        if (billsList.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" class="text-center">Belum ada tagihan terbit.</td></tr>`;
            return;
        }
        
        billsList.forEach(b => {
            const tr = document.createElement("tr");
            const statusBadgeClass = b.status === 'paid' ? 'badge-success' : 'badge-warning';
            
            tr.innerHTML = `
                <td><strong>${b.bill_id}</strong></td>
                <td>${b.student_id}</td>
                <td>Rp ${b.amount.toLocaleString('id-ID')}</td>
                <td>${b.semester}</td>
                <td><span class="badge ${statusBadgeClass}">${b.status}</span></td>
                <td>
                    ${b.status === 'unpaid' ? 
                        `<button class="btn btn-xs btn-success" onclick="payBill('${b.bill_id}')">Bayar</button>` : 
                        `<span class="text-muted">Lunas</span>`}
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="6" class="text-center text-danger">Gagal mengambil data tagihan Keuangan.</td></tr>`;
    }
}

async function payBill(billId) {
    try {
        const res = await fetch(API_URLS.keuangan.payBill(billId), { method: 'POST' });
        if (res.ok) {
            showAlert(`Pembayaran tagihan ${billId} berhasil! Event spp.paid dikirim ke RabbitMQ.`);
            loadBills();
            loadDashboardData();
            
            // Re-sync visualizer state if active
            updateStepperVisualization();
        } else {
            const err = await res.json();
            showAlert(`Gagal bayar: ${err.detail || 'Error'}`, 'error');
        }
    } catch (e) {
        showAlert(`Error: ${e.message}`, 'error');
    }
}

window.payBill = payBill;

// 3. LIBRARY Access & Loans Load
async function checkLibraryAccess() {
    const nim = document.getElementById("lib-check-nim").value.trim();
    if (!nim) {
        showAlert("Silakan masukkan NIM", "error");
        return;
    }
    
    const resultDiv = document.getElementById("lib-status-result");
    resultDiv.innerHTML = "Memeriksa status akses...";
    resultDiv.className = "status-result";
    
    try {
        const res = await fetch(API_URLS.library.checkStatus(nim));
        if (res.ok) {
            const data = await res.json();
            if (data.is_active) {
                resultDiv.innerHTML = `
                    <strong>Akses Diterima!</strong><br>
                    Status: Aktif<br>
                    Keterangan: ${data.reason}<br>
                    Sinkronisasi: ${new Date(data.updated_at).toLocaleString('id-ID')}
                `;
                resultDiv.className = "status-result status-result-active";
            } else {
                resultDiv.innerHTML = `
                    <strong>Akses Ditolak!</strong><br>
                    Status: Ditangguhkan<br>
                    Keterangan: ${data.reason}
                `;
                resultDiv.className = "status-result status-result-inactive";
            }
        } else {
            resultDiv.innerHTML = "Gagal memproses data NIM.";
            resultDiv.className = "status-result status-result-inactive";
        }
    } catch (e) {
        resultDiv.innerHTML = `Terjadi kesalahan koneksi: ${e.message}`;
        resultDiv.className = "status-result status-result-inactive";
    }
}

async function loadLoans(nim) {
    const tbody = document.querySelector("#table-loans tbody");
    tbody.innerHTML = `<tr><td colspan="3" class="text-center">Memuat riwayat peminjaman...</td></tr>`;
    
    try {
        const res = await fetch(API_URLS.library.loans(nim));
        if (!res.ok) throw new Error("Gagal mengambil data");
        
        const data = await res.json();
        tbody.innerHTML = "";
        
        if (data.loans.length === 0) {
            tbody.innerHTML = `<tr><td colspan="3" class="text-center">Mahasiswa ini tidak memiliki pinjaman aktif.</td></tr>`;
            return;
        }
        
        data.loans.forEach(l => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td><strong>${l.book_id}</strong></td>
                <td>${l.book_title}</td>
                <td>${new Date(l.borrowed_at).toLocaleString('id-ID')}</td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="3" class="text-center text-danger">Gagal mengambil data peminjaman perpustakaan.</td></tr>`;
    }
}

// 4. ATTENDANCE Record & Recap Load
async function loadAttendanceLogs(url, emptyMessage) {
    const tbody = document.querySelector("#table-attendance tbody");
    const rawPre = document.getElementById("raw-xml-content");
    
    tbody.innerHTML = `<tr><td colspan="5" class="text-center">Memuat rekap presensi...</td></tr>`;
    rawPre.innerText = "Mengambil data XML...";
    
    try {
        const res = await fetch(url);
        if (!res.ok) throw new Error("Gagal mengambil data");
        
        const xmlText = await res.text();
        rawPre.innerText = formatXml(xmlText);
        
        // Parse XML
        const parser = new DOMParser();
        const xmlDoc = parser.parseFromString(xmlText, "text/xml");
        
        const logs = xmlDoc.getElementsByTagName("log");
        tbody.innerHTML = "";
        
        if (logs.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5" class="text-center">${emptyMessage}</td></tr>`;
            return;
        }
        
        for (let i = 0; i < logs.length; i++) {
            const log = logs[i];
            const logId = log.getElementsByTagName("id")[0]?.textContent;
            const studentId = log.getElementsByTagName("student_id")[0]?.textContent || "";
            const studentName = log.getElementsByTagName("student_name")[0]?.textContent || "";
            const classId = log.getElementsByTagName("class_id")[0]?.textContent;
            const status = log.getElementsByTagName("status")[0]?.textContent || "";
            const recordedAt = log.getElementsByTagName("recorded_at")[0]?.textContent;
            
            const tr = document.createElement("tr");
            const statusBadgeClass = getAttendanceBadgeClass(status);
            const statusLabel = getIndonesianStatusLabel(status);
            
            const studentDisplay = studentName ? `<strong>${studentName}</strong> <span class="text-muted" style="font-size: 11px;">(${studentId})</span>` : `<strong>${studentId}</strong>`;
            
            tr.innerHTML = `
                <td><strong>#${logId}</strong></td>
                <td>${studentDisplay}</td>
                <td>${classId}</td>
                <td><span class="badge ${statusBadgeClass}">${statusLabel}</span></td>
                <td>${new Date(recordedAt).toLocaleString('id-ID')}</td>
            `;
            tbody.appendChild(tr);
        }
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="5" class="text-center text-danger">Gagal mengambil data presensi (XML).</td></tr>`;
        rawPre.innerText = `Terjadi kesalahan saat memproses data: ${e.message}`;
    }
}

async function loadAttendance(nim) {
    await loadAttendanceLogs(API_URLS.attendance.recap(nim), "Belum ada catatan presensi mahasiswa ini.");
}

async function loadClassAttendance(classId) {
    await loadAttendanceLogs(`/attendance/recap/class/${classId}`, "Belum ada catatan presensi untuk kelas ini.");
}

function getAttendanceBadgeClass(status) {
    if (!status) return 'badge-primary';
    switch (status.toLowerCase()) {
        case 'present': return 'badge-success';
        case 'permit':
        case 'excused': return 'badge-info';
        case 'sick': return 'badge-warning';
        case 'absent': return 'badge-danger';
        default: return 'badge-primary';
    }
}

// Formatter to make XML pretty print in browser pre tag
function formatXml(xml) {
    let formatted = '';
    const reg = /(>)(<)(\/*)/g;
    xml = xml.replace(reg, '$1\r\n$2$3');
    let pad = 0;
    xml.split('\r\n').forEach(node => {
        let indent = 0;
        if (node.match( /.+<\/\w[^>]*>$/ )) {
            indent = 0;
        } else if (node.match( /^<\/\w/ )) {
            if (pad !== 0) pad -= 1;
        } else if (node.match( /^<\w[^>]*[^\/]>.*$/ )) {
            indent = 1;
        } else {
            indent = 0;
        }
        let padding = '';
        for (let i = 0; i < pad; i++) {
            padding += '  ';
        }
        formatted += padding + node + '\r\n';
        pad += indent;
    });
    return formatted.trim();
}

// 5. PIPELINE VISUALIZATION & STEPPER
async function updateStepperVisualization() {
    const detailsPanel = document.getElementById("stepper-details-panel");
    const steps = [
        document.getElementById("step-1"),
        document.getElementById("step-2"),
        document.getElementById("step-3"),
        document.getElementById("step-4"),
        document.getElementById("step-5")
    ];
    const stepLines = document.querySelectorAll(".step-line");
    
    // Reset steps
    steps.forEach(s => s.className = "step");
    stepLines.forEach(l => l.className = "step-line");
    
    if (!selectedStudentId) {
        detailsPanel.innerHTML = "Pilih mahasiswa di atas untuk memantau perjalanan data integrasinya secara real-time.";
        return;
    }
    
    detailsPanel.innerHTML = "<em>Menganalisa kondisi integrasi mahasiswa across microservices...</em>";
    
    try {
        // 1. Fetch info dari SIAKAD
        const student = studentsList.find(s => s.student_id === selectedStudentId);
        if (!student) {
            detailsPanel.innerHTML = `<strong>Error:</strong> Mahasiswa ${selectedStudentId} tidak ditemukan.`;
            return;
        }
        
        // 2. Fetch info dari Keuangan (Bills)
        const bill = billsList.find(b => b.student_id === selectedStudentId);
        
        // 3. Fetch status Perpustakaan
        let libraryActive = false;
        try {
            const resLib = await fetch(API_URLS.library.checkStatus(selectedStudentId));
            if (resLib.ok) {
                const dataLib = await resLib.json();
                libraryActive = dataLib.is_active;
            }
        } catch (e) {
            console.error("Stepper checks: library error", e);
        }
        
        // 4. Fetch status Presensi
        let attendanceActive = false;
        try {
            const resAtt = await fetch(API_URLS.attendance.recap(selectedStudentId));
            if (resAtt.ok) {
                const xmlText = await resAtt.text();
                const parser = new DOMParser();
                const xmlDoc = parser.parseFromString(xmlText, "text/xml");
                const activeText = xmlDoc.getElementsByTagName("is_active")[0]?.textContent;
                attendanceActive = activeText === 'true';
            }
        } catch (e) {
            console.error("Stepper checks: attendance error", e);
        }
        
        // Determine States
        // Step 1: Terdaftar
        steps[0].classList.add("completed");
        
        // Step 2: Registrasi Ulang (SIAKAD Status Active)
        let step2Completed = student.status === 'active';
        if (step2Completed) {
            steps[1].classList.add("completed");
            stepLines[0].classList.add("completed");
        } else {
            steps[1].classList.add("active");
            stepLines[0].classList.add("active");
        }
        
        // Step 3: Tagihan Terbuat
        let step3Completed = !!bill;
        if (step3Completed) {
            steps[2].classList.add("completed");
            stepLines[1].classList.add("completed");
        } else if (step2Completed) {
            steps[2].classList.add("active");
            stepLines[1].classList.add("active");
        }
        
        // Step 4: SPP Lunas
        let step4Completed = bill && bill.status === 'paid';
        if (step4Completed) {
            steps[3].classList.add("completed");
            stepLines[2].classList.add("completed");
        } else if (step3Completed) {
            steps[3].classList.add("active");
            stepLines[2].classList.add("active");
        }
        
        // Step 5: Hak Akses Perpustakaan & Presensi Aktif
        let step5Completed = libraryActive && attendanceActive;
        if (step5Completed) {
            steps[4].classList.add("completed");
            stepLines[3].classList.add("completed");
        } else if (step4Completed) {
            steps[4].classList.add("active");
            stepLines[3].classList.add("active");
        }
        
        // Build Narrative Description
        let narrative = `<h3>Laporan Integrasi: <strong>${student.name} (${student.student_id})</strong></h3>`;
        narrative += `<p>• <strong>Status Akademik (SIAKAD):</strong> Mahasiswa terdaftar dalam status <span class="badge ${student.status === 'active' ? 'badge-success' : 'badge-danger'}">${student.status}</span> di semester ${student.semester}.</p>`;
        
        if (bill) {
            narrative += `<p>• <strong>Status Keuangan (SPP):</strong> Tagihan sebesar <strong>Rp ${bill.amount.toLocaleString('id-ID')}</strong> telah diterbitkan dengan status <span class="badge ${bill.status === 'paid' ? 'badge-success' : 'badge-warning'}">${bill.status}</span>.</p>`;
        } else {
            narrative += `<p>• <strong>Status Keuangan (SPP):</strong> <span class="badge badge-danger">Tagihan Belum Dibuat</span>. Lakukan registrasi ulang di SIAKAD agar event diteruskan ke Broker untuk membuat tagihan otomatis.</p>`;
        }
        
        narrative += `<p>• <strong>Akses Perpustakaan:</strong> Status akses saat ini <span class="badge ${libraryActive ? 'badge-success' : 'badge-danger'}">${libraryActive ? 'AKTIF (Diijinkan Pinjam)' : 'DITANGGUHKAN'}</span>.</p>`;
        narrative += `<p>• <strong>Akses Presensi Kuliah:</strong> Status akses di sistem Presensi saat ini <span class="badge ${attendanceActive ? 'badge-success' : 'badge-danger'}">${attendanceActive ? 'AKTIF (Bisa Absen)' : 'MATI (Belum Aktif)'}</span>.</p>`;
        
        // Add Advice
        narrative += `<div class="divider"></div><p><strong>Rekomendasi Tindakan Berikutnya:</strong><br>`;
        if (!step2Completed) {
            narrative += `Silakan pergi ke tab <strong>SIAKAD (Akademik)</strong> dan klik tombol <strong>Re-Daftar</strong> untuk melakukan daftar ulang semester baru.`;
        } else if (!step3Completed) {
            narrative += `Daftar ulang berhasil. Menunggu event sinkronisasi database untuk membuat tagihan otomatis. Anda juga dapat menerbitkan tagihan manual di tab <strong>Keuangan (SPP)</strong>.`;
        } else if (!step4Completed) {
            narrative += `Tagihan SPP telah terbit! Silakan pergi ke tab <strong>Keuangan (SPP)</strong> lalu klik tombol <strong>Bayar</strong> untuk melunasi tagihan kuliah mahasiswa.`;
        } else if (!step5Completed) {
            narrative += `Pembayaran SPP telah lunas. Adapter/broker sedang meneruskan data aktif mahasiswa ke Perpustakaan dan Presensi. Silakan tunggu beberapa saat atau refresh panel.`;
        } else {
            narrative += `<span style="color: var(--success); font-weight: bold;">Seluruh sistem telah terintegrasi dengan sukses!</span> Mahasiswa sekarang dapat meminjam buku di Perpustakaan dan melakukan absensi perkuliahan di sistem Presensi.`;
        }
        narrative += `</p>`;
        
        detailsPanel.innerHTML = narrative;
        
    } catch (e) {
        detailsPanel.innerHTML = `<strong>Gagal mengambil detail visualisasi:</strong> ${e.message}`;
    }
}

// NEW HELPERS FOR CLASS-BASED SYSTEM

async function loadEnrollmentPanel() {
    const studentSelect = document.getElementById("enroll-student-select");
    const checkboxesDiv = document.getElementById("enroll-classes-checkboxes");
    if (!studentSelect || !checkboxesDiv) return;
    
    // Populate student selector
    studentSelect.innerHTML = '<option value="">-- Pilih Mahasiswa --</option>';
    studentsList.forEach(s => {
        const option = document.createElement("option");
        option.value = s.student_id;
        option.text = `${s.student_id} - ${s.name}`;
        studentSelect.appendChild(option);
    });
    
    // Fetch classes
    try {
        const res = await fetch(API_URLS.siakad.classes);
        if (res.ok) {
            const classes = await res.json();
            checkboxesDiv.innerHTML = "";
            classes.forEach(c => {
                const label = document.createElement("label");
                label.style.display = "flex";
                label.style.alignItems = "center";
                label.style.gap = "8px";
                label.style.fontSize = "13px";
                label.style.cursor = "pointer";
                
                const cb = document.createElement("input");
                cb.type = "checkbox";
                cb.value = c.class_id;
                cb.className = "enroll-class-cb";
                
                label.appendChild(cb);
                label.appendChild(document.createTextNode(`${c.class_id} - ${c.name}`));
                checkboxesDiv.appendChild(label);
            });
        }
    } catch (e) {
        console.error("Error loading classes for enrollment panel:", e);
    }
}

async function loadAttendanceClasses() {
    const classSelect = document.getElementById("att-class-select");
    if (!classSelect) return;
    try {
        const res = await fetch(API_URLS.attendance.classes);
        if (res.ok) {
            const classes = await res.json();
            classSelect.innerHTML = '<option value="">-- Pilih Kelas --</option>';
            classes.forEach(c => {
                const option = document.createElement("option");
                option.value = c.class_id;
                option.text = `${c.class_id} - ${c.name}`;
                classSelect.appendChild(option);
            });
        }
    } catch (e) {
        console.error("Error loading attendance classes:", e);
    }
}

const statusTranslations = {
    present: 'Hadir',
    excused: 'Izin',
    absent: 'Alpa'
};

function getIndonesianStatusLabel(status) {
    return statusTranslations[status.toLowerCase()] || status;
}

async function loadClassroomStudents() {
    const classId = document.getElementById("att-class-select").value;
    const wrapper = document.getElementById("classroom-attendance-wrapper");
    const emptyMsg = document.getElementById("classroom-empty-message");
    const tbody = document.querySelector("#table-classroom-students tbody");
    if (!tbody) return;
    
    if (!classId) {
        if (wrapper) wrapper.style.display = "none";
        if (emptyMsg) {
            emptyMsg.style.display = "block";
            emptyMsg.innerText = "Pilih kelas di atas untuk memuat daftar mahasiswa.";
        }
        // Clear history table
        const histTbody = document.querySelector("#table-attendance-history tbody");
        if (histTbody) histTbody.innerHTML = `<tr><td colspan="5" class="text-center">Pilih kelas di sebelah kiri untuk melihat riwayat.</td></tr>`;
        const detailsBtn = document.getElementById("tab-session-details-btn");
        if (detailsBtn) detailsBtn.style.display = "none";
        return;
    }
    
    tbody.innerHTML = '<tr><td colspan="2" class="text-center">Memuat daftar mahasiswa...</td></tr>';
    if (wrapper) wrapper.style.display = "flex";
    if (emptyMsg) emptyMsg.style.display = "none";
    
    try {
        const res = await fetch(API_URLS.attendance.classStudents(classId));
        if (res.ok) {
            const students = await res.json();
            tbody.innerHTML = "";
            
            if (students.length === 0) {
                tbody.innerHTML = '<tr><td colspan="2" class="text-center text-muted">Tidak ada mahasiswa aktif terdaftar di kelas ini.</td></tr>';
                loadClassSessionsHistory(classId);
                return;
            }
            
            students.forEach(s => {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td><strong>${s.name}</strong> <span class="text-muted" style="font-size: 11px;">(${s.student_id})</span></td>
                    <td>
                        <select class="form-control student-status-select" data-student-id="${s.student_id}">
                            <option value="present">Hadir</option>
                            <option value="excused">Izin</option>
                            <option value="absent">Alpa</option>
                        </select>
                    </td>
                `;
                tbody.appendChild(tr);
            });
            
            // Auto load attendance logs history for this class
            loadClassSessionsHistory(classId);
        } else {
            tbody.innerHTML = '<tr><td colspan="2" class="text-center text-danger">Gagal memuat mahasiswa.</td></tr>';
        }
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="2" class="text-center text-danger">Koneksi gagal: ${e.message}</td></tr>`;
    }
}

async function saveClassroomAttendance() {
    const classId = document.getElementById("att-class-select").value;
    const meetingNum = parseInt(document.getElementById("att-meeting-input").value);
    const dateInput = document.getElementById("att-date-input").value;
    const selects = document.querySelectorAll(".student-status-select");
    
    if (!classId) {
        showAlert("Silakan pilih kelas terlebih dahulu", "error");
        return;
    }
    if (!meetingNum) {
        showAlert("Silakan pilih pertemuan terlebih dahulu", "error");
        return;
    }
    if (!dateInput) {
        showAlert("Silakan pilih tanggal absensi", "error");
        return;
    }
    
    const records = [];
    selects.forEach(select => {
        records.push({
            student_id: select.getAttribute("data-student-id"),
            status: select.value
        });
    });
    
    if (records.length === 0) {
        showAlert("Tidak ada mahasiswa untuk diabsen", "error");
        return;
    }
    
    const payload = {
        class_id: classId,
        meeting_number: meetingNum,
        attendance_date: dateInput,
        records: records
    };
    
    try {
        const res = await fetch('/attendance/session', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        if (res.ok) {
            showAlert("Absensi kelas berhasil dicatat!");
            
            // Increment meeting selection automatically
            const mtgSelect = document.getElementById("att-meeting-input");
            if (mtgSelect && mtgSelect.selectedIndex < mtgSelect.options.length - 1) {
                mtgSelect.selectedIndex += 1;
            }
            
            loadClassroomStudents();
        } else {
            const err = await res.json();
            showAlert(`Gagal: ${err.detail || 'Terjadi kesalahan'}`, 'error');
        }
    } catch (e) {
        showAlert(`Koneksi Gagal: ${e.message}`, 'error');
    }
}

async function loadClassSessionsHistory(classId) {
    const tbody = document.querySelector("#table-attendance-history tbody");
    const rawPre = document.getElementById("raw-xml-content");
    const historyTitle = document.getElementById("attendance-history-title");
    const detailsBtn = document.getElementById("tab-session-details-btn");
    
    if (historyTitle) historyTitle.innerText = `Riwayat Presensi - ${classId}`;
    if (detailsBtn) detailsBtn.style.display = "none";
    
    // Reset search input value
    const searchInput = document.getElementById("att-history-search");
    if (searchInput) searchInput.value = "";
    
    // Switch active sub-tab back to "Riwayat"
    const subTabBtns = document.querySelectorAll(".tab-sub-btn");
    const subTabPanels = document.querySelectorAll(".sub-tab-panel");
    subTabBtns.forEach(btn => {
        btn.classList.toggle("active", btn.getAttribute("data-sub") === "history-rendered");
    });
    subTabPanels.forEach(p => {
        p.classList.toggle("active", p.id === "history-rendered-view");
    });
    
    tbody.innerHTML = `<tr><td colspan="5" class="text-center">Memuat riwayat...</td></tr>`;
    rawPre.innerText = "Mengambil data XML...";
    
    try {
        const res = await fetch(`/attendance/classes/${classId}/history`);
        if (!res.ok) throw new Error("Gagal mengambil data riwayat");
        
        const xmlText = await res.text();
        rawPre.innerText = formatXml(xmlText);
        
        const parser = new DOMParser();
        const xmlDoc = parser.parseFromString(xmlText, "text/xml");
        
        const records = xmlDoc.getElementsByTagName("record");
        classAttendanceHistory = [];
        
        for (let i = 0; i < records.length; i++) {
            const rec = records[i];
            const attDate = rec.getElementsByTagName("attendance_date")[0]?.textContent;
            const mtgNum = rec.getElementsByTagName("meeting_number")[0]?.textContent;
            const studentId = rec.getElementsByTagName("student_id")[0]?.textContent;
            const studentName = rec.getElementsByTagName("student_name")[0]?.textContent;
            const status = rec.getElementsByTagName("status")[0]?.textContent;
            const sessionId = rec.getElementsByTagName("session_id")[0]?.textContent;
            
            classAttendanceHistory.push({
                attendanceDate: attDate,
                meetingNumber: mtgNum,
                studentId: studentId,
                studentName: studentName,
                status: status,
                sessionId: sessionId
            });
        }
        
        renderAttendanceHistory(classAttendanceHistory);
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="5" class="text-center text-danger">Gagal memuat riwayat: ${e.message}</td></tr>`;
        rawPre.innerText = `Error: ${e.message}`;
    }
}

function renderAttendanceHistory(records) {
    const tbody = document.querySelector("#table-attendance-history tbody");
    if (!tbody) return;
    
    tbody.innerHTML = "";
    if (records.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="text-center">Belum ada riwayat presensi yang cocok.</td></tr>`;
        return;
    }
    
    records.forEach(rec => {
        const tr = document.createElement("tr");
        tr.style.cursor = "pointer";
        const statusBadgeClass = getAttendanceBadgeClass(rec.status);
        const statusLabel = getIndonesianStatusLabel(rec.status);
        
        tr.innerHTML = `
            <td>${rec.attendanceDate}</td>
            <td><strong>Pertemuan ${rec.meetingNumber}</strong></td>
            <td><code>${rec.studentId}</code></td>
            <td>${rec.studentName}</td>
            <td><span class="badge ${statusBadgeClass}">${statusLabel}</span></td>
        `;
        
        tr.addEventListener("click", () => {
            loadSessionDetails(rec.sessionId);
        });
        
        tbody.appendChild(tr);
    });
}

function filterClassAttendanceHistory() {
    const query = (document.getElementById("att-history-search")?.value || "").toLowerCase().trim();
    if (!query) {
        renderAttendanceHistory(classAttendanceHistory);
        return;
    }
    
    const filtered = classAttendanceHistory.filter(rec => 
        rec.studentId.toLowerCase().includes(query) || 
        rec.studentName.toLowerCase().includes(query)
    );
    
    renderAttendanceHistory(filtered);
}

async function loadSessionDetails(sessionId) {
    const headerDiv = document.getElementById("session-details-header");
    const tbody = document.querySelector("#table-session-details tbody");
    const rawPre = document.getElementById("raw-xml-content");
    const detailsBtn = document.getElementById("tab-session-details-btn");
    
    tbody.innerHTML = `<tr><td colspan="2" class="text-center">Memuat detail pertemuan...</td></tr>`;
    if (detailsBtn) detailsBtn.style.display = "inline-block";
    
    // Switch active sub-tab to "Detail Pertemuan"
    const subTabBtns = document.querySelectorAll(".tab-sub-btn");
    const subTabPanels = document.querySelectorAll(".sub-tab-panel");
    subTabBtns.forEach(btn => {
        btn.classList.toggle("active", btn.getAttribute("data-sub") === "session-details-rendered");
    });
    subTabPanels.forEach(p => {
        p.classList.toggle("active", p.id === "session-details-rendered-view");
    });
    
    try {
        const res = await fetch(`/attendance/sessions/${sessionId}`);
        if (!res.ok) throw new Error("Gagal mengambil detail pertemuan");
        
        const xmlText = await res.text();
        rawPre.innerText = formatXml(xmlText);
        
        const parser = new DOMParser();
        const xmlDoc = parser.parseFromString(xmlText, "text/xml");
        
        const classId = xmlDoc.getElementsByTagName("class_id")[0]?.textContent;
        const mtgNum = xmlDoc.getElementsByTagName("meeting_number")[0]?.textContent;
        const attDate = xmlDoc.getElementsByTagName("attendance_date")[0]?.textContent;
        
        headerDiv.innerHTML = `
            <strong>Kelas:</strong> ${classId}<br>
            <strong>Pertemuan Ke:</strong> ${mtgNum}<br>
            <strong>Tanggal:</strong> ${attDate}
        `;
        
        const records = xmlDoc.getElementsByTagName("record");
        tbody.innerHTML = "";
        
        for (let i = 0; i < records.length; i++) {
            const rec = records[i];
            const stdId = rec.getElementsByTagName("student_id")[0]?.textContent;
            const stdName = rec.getElementsByTagName("student_name")[0]?.textContent;
            const status = rec.getElementsByTagName("status")[0]?.textContent || "";
            
            const tr = document.createElement("tr");
            const statusBadgeClass = getAttendanceBadgeClass(status);
            const statusLabel = getIndonesianStatusLabel(status);
            
            tr.innerHTML = `
                <td><strong>${stdName}</strong> <span class="text-muted" style="font-size: 11px;">(${stdId})</span></td>
                <td><span class="badge ${statusBadgeClass}">${statusLabel}</span></td>
            `;
            tbody.appendChild(tr);
        }
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="2" class="text-center text-danger">Gagal memuat detail: ${e.message}</td></tr>`;
        rawPre.innerText = `Error: ${e.message}`;
    }
}
