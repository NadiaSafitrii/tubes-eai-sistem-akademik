// CONFIGURATION
const API_URLS = {
    siakad: {
        status: '/siakad/status',
        students: '/siakad/students',
        register: (id) => `/siakad/students/${id}/register`
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
        recap: (id) => `/attendance/recap/${id}`
    }
};

// State variables
let studentsList = [];
let billsList = [];
let selectedStudentId = "";
let healthInterval = null;
let dataInterval = null;

// DOM ELEMS & EVENT LISTENERS
document.addEventListener("DOMContentLoaded", () => {
    initNavigation();
    initForms();
    initRefreshes();
    
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
            if (tabId === 'siakad') loadStudents();
            if (tabId === 'keuangan') loadBills();
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

    // Record Attendance Form (Presensi)
    const formRecordAttendance = document.getElementById("form-record-attendance");
    formRecordAttendance.addEventListener("submit", async (e) => {
        e.preventDefault();
        const payload = {
            student_id: document.getElementById("att-student-id").value.trim(),
            class_id: document.getElementById("att-class-id").value.trim(),
            status: document.getElementById("att-status").value
        };
        
        try {
            const res = await fetch(API_URLS.attendance.record, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            
            const xmlText = await res.text();
            
            // Parse XML response
            const parser = new DOMParser();
            const xmlDoc = parser.parseFromString(xmlText, "text/xml");
            const status = xmlDoc.getElementsByTagName("status")[0]?.textContent;
            const message = xmlDoc.getElementsByTagName("message")[0]?.textContent;
            
            if (status === 'success') {
                showAlert(`Presensi berhasil dicatat!`);
                formRecordAttendance.reset();
                loadAttendance(payload.student_id);
            } else {
                showAlert(`Gagal: ${message || 'Akses ditolak.'}`, 'error');
            }
        } catch (e) {
            showAlert(`Koneksi Gagal: ${e.message}`, 'error');
        }
    });

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
    
    document.getElementById("btn-refresh-attendance").addEventListener("click", () => {
        const nim = document.getElementById("att-search-nim").value.trim();
        if (nim) loadAttendance(nim);
        else showAlert("Silakan isi NIM mahasiswa terlebih dahulu", "error");
    });

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
    tbody.innerHTML = `<tr><td colspan="6" class="text-center">Memuat data mahasiswa...</td></tr>`;
    
    try {
        const res = await fetch(API_URLS.siakad.students);
        if (!res.ok) throw new Error("Gagal mengambil data");
        
        studentsList = await res.json();
        tbody.innerHTML = "";
        
        if (studentsList.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" class="text-center">Belum ada mahasiswa terdaftar.</td></tr>`;
            return;
        }
        
        studentsList.forEach(s => {
            const tr = document.createElement("tr");
            const statusBadgeClass = s.status === 'active' ? 'badge-success' : 'badge-danger';
            
            tr.innerHTML = `
                <td><strong>${s.student_id}</strong></td>
                <td>${s.name}</td>
                <td>${s.email}</td>
                <td>${s.semester}</td>
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
async function loadAttendance(nim) {
    const tbody = document.querySelector("#table-attendance tbody");
    const rawPre = document.getElementById("raw-xml-content");
    
    tbody.innerHTML = `<tr><td colspan="4" class="text-center">Memuat rekap presensi...</td></tr>`;
    rawPre.innerText = "Mengambil data XML...";
    
    try {
        const res = await fetch(API_URLS.attendance.recap(nim));
        if (!res.ok) throw new Error("Gagal mengambil data");
        
        const xmlText = await res.text();
        rawPre.innerText = formatXml(xmlText);
        
        // Parse XML
        const parser = new DOMParser();
        const xmlDoc = parser.parseFromString(xmlText, "text/xml");
        
        const logs = xmlDoc.getElementsByTagName("log");
        tbody.innerHTML = "";
        
        if (logs.length === 0) {
            tbody.innerHTML = `<tr><td colspan="4" class="text-center">Belum ada catatan presensi mahasiswa ini.</td></tr>`;
            return;
        }
        
        for (let i = 0; i < logs.length; i++) {
            const log = logs[i];
            const logId = log.getElementsByTagName("id")[0]?.textContent;
            const classId = log.getElementsByTagName("class_id")[0]?.textContent;
            const status = log.getElementsByTagName("status")[0]?.textContent;
            const recordedAt = log.getElementsByTagName("recorded_at")[0]?.textContent;
            
            const tr = document.createElement("tr");
            const statusBadgeClass = getAttendanceBadgeClass(status);
            
            tr.innerHTML = `
                <td><strong>#${logId}</strong></td>
                <td>${classId}</td>
                <td><span class="badge ${statusBadgeClass}">${status}</span></td>
                <td>${new Date(recordedAt).toLocaleString('id-ID')}</td>
            `;
            tbody.appendChild(tr);
        }
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="4" class="text-center text-danger">Gagal mengambil data presensi (XML).</td></tr>`;
        rawPre.innerText = `Terjadi kesalahan saat memproses data: ${e.message}`;
    }
}

function getAttendanceBadgeClass(status) {
    switch (status) {
        case 'present': return 'badge-success';
        case 'permit': return 'badge-info';
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
