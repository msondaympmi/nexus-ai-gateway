import streamlit as st
import httpx
import pandas as pd

# 1. Page Configuration and Sleek Modern Aesthetics
st.set_page_config(
    page_title="Nexus AI Gateway — Admin Panel",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom premium styling (Vibrant gradients, elegant cards, Google Fonts)
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Outfit', sans-serif;
    }
    
    .main-title {
        background: linear-gradient(135deg, #FF6B6B, #4D96FF);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 700;
        font-size: 2.8rem;
        margin-bottom: 0.5rem;
    }
    
    .subtitle {
        color: #8A99AD;
        font-size: 1.1rem;
        margin-bottom: 2rem;
    }
    
    .metric-card {
        background-color: #1E293B;
        border-radius: 12px;
        padding: 1.5rem;
        border-left: 5px solid #4D96FF;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        margin-bottom: 1rem;
    }
    
    .metric-value {
        font-size: 2.2rem;
        font-weight: 700;
        color: #FFFFFF;
    }
    
    .metric-label {
        font-size: 0.9rem;
        color: #94A3B8;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
</style>
""", unsafe_allow_html=True)

# 2. Sidebar Administration Configuration
st.sidebar.markdown("### 🔒 Kredensial Admin")
admin_key = st.sidebar.text_input(
    "X-Admin-Key",
    value="nexus_super_admin_key_2026",
    type="password"
)
api_base_url = st.sidebar.text_input(
    "FastAPI Base URL",
    value="http://127.0.0.1:8100"
)

st.sidebar.markdown("---")
st.sidebar.markdown("### ➕ Daftarkan Aplikasi Baru")

with st.sidebar.form("register_app_form"):
    new_app_name = st.text_input("Nama Aplikasi (misal: eLogbook, CARE)")
    submit_btn = st.form_submit_key = st.form_submit_button("Generate Kunci API")

    if submit_btn:
        if not new_app_name:
            st.sidebar.error("Nama aplikasi wajib diisi!")
        else:
            try:
                headers = {"X-Admin-Key": admin_key}
                response = httpx.post(
                    f"{api_base_url}/v1/admin/apps?app_name={new_app_name}",
                    headers=headers,
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    st.sidebar.success(f"Aplikasi '{new_app_name}' Berhasil Terdaftar!")
                    st.sidebar.code(data["plaintext_api_key"], language="plaintext")
                    st.sidebar.warning("⚠️ SALIN SEKARANG! Kunci ini tidak akan dapat dilihat lagi.")
                else:
                    st.sidebar.error(f"Gagal mendaftarkan aplikasi: {response.text}")
            except Exception as err:
                st.sidebar.error(f"Koneksi ke FastAPI gagal: {err}")

# 3. Main Dashboard Headers
st.markdown('<h1 class="main-title">📊 Nexus AI Services Platform</h1>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">Pusat Pemantauan Biaya AI & Manajemen Aplikasi MPM Insurance</p>', unsafe_allow_html=True)

# 4. Fetch real-time usage data from MySQL via FastAPI Admin Endpoints
headers = {"X-Admin-Key": admin_key}

try:
    # Fetch usage reports
    usage_res = httpx.get(f"{api_base_url}/v1/admin/usage", headers=headers, timeout=5.0)
    # Fetch apps list
    apps_res = httpx.get(f"{api_base_url}/v1/admin/apps", headers=headers, timeout=5.0)

    if usage_res.status_code == 200 and apps_res.status_code == 200:
        usage_data = usage_res.json()
        apps_data = apps_res.json()

        # Create Pandas DataFrames
        df_usage = pd.DataFrame(usage_data)
        df_apps = pd.DataFrame(apps_data)

        # Calculate high-level summary metrics
        total_cost = df_usage["total_cost_usd"].sum() if not df_usage.empty else 0.0
        total_tokens = df_usage["total_tokens"].sum() if not df_usage.empty else 0
        total_requests = df_usage["total_requests"].sum() if not df_usage.empty else 0

        # Display Premium Metrics Row
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown(f"""
            <div class="metric-card" style="border-left-color: #10B981;">
                <div class="metric-value">${total_cost:,.4f}</div>
                <div class="metric-label">Total Biaya Riil (USD)</div>
            </div>
            """, unsafe_allow_html=True)

        with col2:
            st.markdown(f"""
            <div class="metric-card" style="border-left-color: #3B82F6;">
                <div class="metric-value">{total_tokens:,}</div>
                <div class="metric-label">Total Token Dikonsumsi</div>
            </div>
            """, unsafe_allow_html=True)

        with col3:
            st.markdown(f"""
            <div class="metric-card" style="border-left-color: #F59E0B;">
                <div class="metric-value">{total_requests:,}</div>
                <div class="metric-label">Total Request Diproses</div>
            </div>
            """, unsafe_allow_html=True)

        with col4:
            st.markdown(f"""
            <div class="metric-card" style="border-left-color: #8B5CF6;">
                <div class="metric-value">{len(apps_data)}</div>
                <div class="metric-label">Aplikasi Klien Aktif</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # Tabs for detailed views
        tab1, tab2 = st.tabs(["📝 Centralized Cost Tracking", "⚙️ Aplikasi Terdaftar"])

        with tab1:
            st.markdown("### Laporan Pengeluaran AI Terpusat")
            if not df_usage.empty:
                # Rename columns for friendly display
                df_display = df_usage.rename(columns={
                    "app_name": "Nama Aplikasi",
                    "total_requests": "Jumlah Request",
                    "total_tokens": "Total Token",
                    "total_cost_usd": "Akumulasi Biaya (USD)"
                })
                # Add USD symbol to cost column
                df_display["Akumulasi Biaya (USD)"] = df_display["Akumulasi Biaya (USD)"].map(lambda x: f"${x:,.6f}")
                df_display["Total Token"] = df_display["Total Token"].map(lambda x: f"{x:,}")
                df_display["Jumlah Request"] = df_display["Jumlah Request"].map(lambda x: f"{x:,}")
                
                st.dataframe(df_display[["Nama Aplikasi", "Jumlah Request", "Total Token", "Akumulasi Biaya (USD)"]], use_container_width=True)
            else:
                st.info("Belum ada data penggunaan tercatat di database.")

        with tab2:
            st.markdown("### Manajemen Aplikasi Internal")
            if not df_apps.empty:
                df_apps_display = df_apps.rename(columns={
                    "app_name": "Nama Aplikasi",
                    "api_key_prefix": "Prefix Kunci API",
                    "is_active": "Status Aktif",
                    "created_at": "Tanggal Terdaftar"
                })
                st.dataframe(df_apps_display[["Nama Aplikasi", "Prefix Kunci API", "Status Aktif", "Tanggal Terdaftar"]], use_container_width=True)
            else:
                st.info("Belum ada aplikasi klien terdaftar.")

    else:
        st.error(f"Gagal mengambil data dari API Admin. Status: {usage_res.status_code}")
except Exception as e:
    st.info("💡 **Tips untuk Memulai:** Jalankan server FastAPI terlebih dahulu di port 8100 (`uvicorn main:app --port 8100`) agar dashboard dapat menarik data transaksi dan meregistrasi aplikasi baru secara realtime.")
    st.warning(f"Koneksi ke FastAPI Server tidak dapat dibuat: {e}")
